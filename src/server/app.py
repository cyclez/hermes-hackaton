from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import threading
import time
from contextlib import asynccontextmanager
from typing import Any

try:
    from fastapi import FastAPI, Query
    from fastapi.middleware.cors import CORSMiddleware
except ModuleNotFoundError as exc:  # pragma: no cover
    raise RuntimeError("FastAPI is not installed. Run: uv pip install -e .") from exc

from src.agents.hermes_runner import HermesAgentRunner
from src.agents.profiles import ensure_profiles
from src.server.config import Settings
from src.server.game_finalizer import GameFinalizer
from src.server.game_engine import create_initial_state
from src.server.game_loop import run_citizen_worker_loop, run_game_loop, run_mayor_worker_loop
from src.server.models import to_plain
from src.server.postgres_store import PostgresJobQueue, PostgresStore

_CITIZEN_BEHAVIORS = [
    "aggressive",
    "cautious",
    "opportunistic",
    "stealth_first",
    "resource_maximizer",
]


def _process_command(pid: int) -> str:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
        )
    except Exception:
        return ""
    return result.stdout.strip()


def _stop_target_pid() -> tuple[int, str]:
    current_pid = os.getpid()
    parent_pid = os.getppid()
    parent_command = _process_command(parent_pid)
    if "uvicorn" in parent_command and "--reload" in parent_command:
        return parent_pid, "uvicorn_reload_parent"
    return current_pid, "current_process"


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _stop_server_processes() -> None:
    time.sleep(0.2)
    current_pid = os.getpid()
    target_pid, reason = _stop_target_pid()
    print(f"[app] Stop target pid={target_pid} reason={reason}", flush=True)

    if target_pid != current_pid:
        try:
            os.kill(target_pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        time.sleep(0.7)
        if _pid_is_alive(target_pid):
            try:
                os.kill(target_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    try:
        os.kill(current_pid, signal.SIGTERM)
    except ProcessLookupError:
        pass

    # If graceful shutdown is blocked by in-flight executor/LLM threads, exit.
    time.sleep(1.5)
    os._exit(0)


def _launch_game_tasks(
    store: PostgresStore,
    queue: PostgresJobQueue,
    runner: HermesAgentRunner,
    settings: Settings,
    game_id: str,
    finalizer: GameFinalizer,
) -> tuple[list[asyncio.Task], asyncio.Lock, list[int]]:
    """Create and start all background tasks for a game session."""
    game_lock = asyncio.Lock()
    tick_counter = [0]

    tasks: list[asyncio.Task] = [
        asyncio.create_task(
            run_game_loop(store, game_id, queue, settings, tick_counter, game_lock, finalizer),
            name="game_loop",
        ),
        asyncio.create_task(
            run_mayor_worker_loop(store, runner, settings,
                                  asyncio.Semaphore(settings.max_concurrent_llm_calls),
                                  game_id, game_lock, finalizer),
            name="mayor_worker",
        ),
    ]
    for i in range(settings.citizen_worker_count):
        tasks.append(asyncio.create_task(
            run_citizen_worker_loop(
                store, queue, runner, settings,
                asyncio.Semaphore(settings.max_concurrent_llm_calls),
                f"worker-{i}", game_lock, finalizer,
            ),
            name=f"citizen_worker_{i}",
        ))
    return tasks, game_lock, tick_counter


async def _init_game(store: PostgresStore, queue: PostgresJobQueue, settings: Settings) -> str:
    """Create a fresh game state in Postgres; return the new game_id."""
    await queue.clear_all_jobs()

    state = create_initial_state(
        citizen_count=settings.citizen_count,
        season_seconds=settings.season_seconds,
    )
    now = time.time()
    state.started_at = now
    state.now = now
    for idx, citizen in enumerate(state.citizens.values()):
        citizen.behavior = _CITIZEN_BEHAVIORS[idx % len(_CITIZEN_BEHAVIORS)]
    await store.save_state(state)

    provider = "ollama" if settings.llm_provider.lower() == "ollama" else "openrouter"
    api_key = "ollama" if provider == "ollama" else (settings.openrouter_api_key or "")
    base_url = (settings.ollama_base_url.rstrip("/") + "/v1") if provider == "ollama" else ""
    ensure_profiles(
        citizen_count=settings.citizen_count,
        behaviors=_CITIZEN_BEHAVIORS,
        mayor_behavior="optimizer",
        citizens_model=settings.citizens_model,
        mayor_model=settings.mayor_model,
        provider=provider,
        api_key=api_key,
        base_url=base_url,
    )
    return state.game_id


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.load()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Inject credentials into os.environ so Hermes AIAgent finds them via
        # its native provider resolver (reads OPENROUTER_API_KEY from os.getenv).
        if settings.llm_provider.lower() != "ollama" and settings.openrouter_api_key:
            os.environ.setdefault("OPENROUTER_API_KEY", settings.openrouter_api_key)

        store = PostgresStore(settings.database_url)
        await store.connect()
        await store.init_schema()

        queue = PostgresJobQueue(store._pool)
        cleared = await queue.clear_all_jobs()
        if cleared:
            print(f"[app] Cleared {cleared} stale jobs from previous session.", flush=True)

        game_id = await _init_game(store, queue, settings)
        runner = HermesAgentRunner(settings)
        finalizer = GameFinalizer(log_store=runner.log_store, runner=runner)
        tasks, _, _ = _launch_game_tasks(store, queue, runner, settings, game_id, finalizer)

        app.state.store = store
        app.state.queue = queue
        app.state.runner = runner
        app.state.finalizer = finalizer
        app.state.settings = settings
        app.state.game_id = game_id
        app.state.tasks = tasks

        print(f"[app] Game {game_id} started — {settings.citizen_count} citizens, "
              f"{settings.season_seconds}s season, provider={settings.llm_provider}", flush=True)

        yield

        for task in app.state.tasks:
            task.cancel()
        await asyncio.gather(*app.state.tasks, return_exceptions=True)
        await store.close()
        print("[app] Shutdown complete.", flush=True)

    app = FastAPI(title="OptimiCity Simulator", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {
            "ok": True,
            "llm_provider": settings.llm_provider,
            "citizen_count": settings.citizen_count,
            "database_configured": bool(settings.database_url),
        }

    @app.get("/api/state")
    async def get_state() -> dict[str, Any]:
        state = await app.state.store.load_state(app.state.game_id)
        d = to_plain(state)
        d["game_hour"] = state.game_hour
        d["is_finished"] = state.is_finished
        d["winner"] = (
            "mayor" if state.heat >= 100.0
            else "citizens" if state.is_finished
            else None
        )
        d["training"] = app.state.finalizer.learning_status(app.state.game_id, state_finished=state.is_finished)
        return d

    @app.get("/api/training-status")
    async def training_status(game_id: str | None = Query(default=None)) -> dict[str, Any]:
        target_game_id = game_id or app.state.game_id
        state_finished: bool | None = None
        if target_game_id == app.state.game_id:
            state = await app.state.store.load_state(app.state.game_id)
            state_finished = state.is_finished
        return app.state.finalizer.learning_status(target_game_id, state_finished=state_finished)

    @app.get("/api/events")
    async def get_events(
        limit: int = Query(default=50, le=500),
        kinds: str = Query(default=""),
    ) -> list[dict[str, Any]]:
        kind_filter = [k.strip() for k in kinds.split(",") if k.strip()] if kinds else None
        events = await app.state.store.get_events(app.state.game_id, limit=limit, kinds=kind_filter)
        return [to_plain(e) for e in events]

    @app.get("/api/public-events")
    async def public_events(limit: int = Query(default=50, le=200)) -> list[dict[str, Any]]:
        events = await app.state.store.public_events(app.state.game_id, limit=limit)
        return [to_plain(e) for e in events]

    @app.get("/api/mayor/latest")
    async def latest_mayor_decree() -> dict[str, Any]:
        decree = await app.state.store.latest_mayor_decree(app.state.game_id)
        return decree or {}

    @app.get("/api/agents/logs")
    async def agent_logs() -> dict:
        return app.state.runner._agent_logs

    @app.get("/api/decision-log-runs")
    async def decision_log_runs() -> dict[str, Any]:
        return {
            "current_game_id": app.state.game_id,
            "runs": app.state.runner.log_store.list_runs(app.state.game_id),
        }

    @app.get("/api/decision-logs")
    async def decision_logs(
        game_id: str | None = Query(default=None),
        limit: int = Query(default=200, ge=1, le=2000),
        role: str = Query(default=""),
        agent_id: str = Query(default=""),
    ) -> list[dict[str, Any]]:
        return app.state.runner.log_store.read_entries(
            game_id or app.state.game_id,
            limit=limit,
            role=role or None,
            agent_id=agent_id or None,
        )

    @app.post("/api/server/stop")
    async def server_stop() -> dict[str, str]:
        """Gracefully stop the server process."""
        threading.Thread(target=_stop_server_processes, name="server-stop", daemon=True).start()
        print("[app] Stop requested via API.", flush=True)
        return {"status": "stopping"}

    @app.post("/api/server/restart")
    async def server_restart() -> dict[str, Any]:
        """Cancel all background tasks, reset game state, relaunch tasks."""
        print("[app] Restart requested via API — cancelling tasks...", flush=True)

        for task in app.state.tasks:
            task.cancel()
        await asyncio.gather(*app.state.tasks, return_exceptions=True)

        game_id = await _init_game(app.state.store, app.state.queue, app.state.settings)
        app.state.game_id = game_id

        # Full runner reset so the new game gets fresh agents with no stale state
        app.state.runner.reset()

        tasks, _, _ = _launch_game_tasks(
            app.state.store, app.state.queue, app.state.runner,
            app.state.settings, game_id, app.state.finalizer,
        )
        app.state.tasks = tasks

        print(f"[app] Restarted — new game {game_id}", flush=True)
        return {"status": "restarted", "game_id": game_id}

    return app


app = create_app()
