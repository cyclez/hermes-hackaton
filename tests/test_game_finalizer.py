from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from src.server.decision_log_store import DecisionLogStore
from src.server.config import Settings
from src.server.game_engine import create_initial_state
from src.server.game_finalizer import GameFinalizer
from src.server.game_loop import run_citizen_worker_loop, run_game_loop
from src.server.models import CitizenAction, CitizenDecision, DecisionKind, Dossier, DossierTarget, GameEvent, JobKind
from src.server.queue import Job


class _StubStore:
    def __init__(self, events: list[GameEvent] | None = None, dossiers: list[Dossier] | None = None) -> None:
        self.events = list(events or [])
        self.dossiers = list(dossiers or [])

    async def get_events(self, game_id: str, limit: int = 50, kinds: list[str] | None = None) -> list[GameEvent]:
        return self.events[:limit]

    async def get_recent_dossiers(self, game_id: str, limit: int = 10) -> list[Dossier]:
        return self.dossiers[:limit]


class _LoopStore(_StubStore):
    def __init__(self, state, events: list[GameEvent] | None = None, dossiers: list[Dossier] | None = None) -> None:
        super().__init__(events=events, dossiers=dossiers)
        self.state = state
        self.save_count = 0

    async def load_state(self, game_id: str):
        if game_id != self.state.game_id:
            raise RuntimeError(f"unexpected game_id={game_id}")
        return self.state

    async def save_state(self, state) -> None:
        self.state = state
        self.save_count += 1

    async def append_events(self, events: list[GameEvent], game_id: str) -> None:
        self.events.extend(events)

    async def append_dossier(self, dossier: Dossier, game_id: str) -> None:
        self.dossiers.append(dossier)


class _AsyncQueue:
    def __init__(self, jobs: list[Job] | None = None) -> None:
        self.jobs = list(jobs or [])
        self.enqueued: list[tuple[JobKind, dict]] = []
        self.completed: list[str] = []
        self.failed: list[str] = []
        self.completed_event = asyncio.Event()

    async def queued_citizen_ids(self) -> set[str]:
        return set()

    async def enqueue(self, kind: JobKind, payload: dict) -> Job:
        self.enqueued.append((kind, payload))
        job = Job(job_id=f"enqueued-{len(self.enqueued)}", kind=kind, payload=payload)
        self.jobs.append(job)
        return job

    async def claim(self, kind: JobKind, worker_id: str, limit: int = 1) -> list[Job]:
        claimed: list[Job] = []
        remaining: list[Job] = []
        for job in self.jobs:
            if len(claimed) < limit and job.kind == kind:
                claimed.append(job)
            else:
                remaining.append(job)
        self.jobs = remaining
        return claimed

    async def complete(self, job_id: str) -> None:
        self.completed.append(job_id)
        self.completed_event.set()

    async def fail(self, job_id: str) -> None:
        self.failed.append(job_id)


class _FakeRunner:
    def __init__(self) -> None:
        self.calls = 0

    def decide_citizen(self, citizen_id: str, observation: dict, behavior: str, game_id: str) -> CitizenDecision:
        self.calls += 1
        return CitizenDecision(
            citizen_id=citizen_id,
            kind=DecisionKind.ACTION,
            action=CitizenAction.COVER_TRACKS,
            rationale="stale worker result",
        )


def _settings() -> Settings:
    return Settings(
        llm_provider="openrouter",
        ollama_base_url="http://localhost:11434",
        openrouter_base_url="https://openrouter.ai/api/v1",
        openrouter_api_key="test-key",
        openrouter_reasoning_effort="none",
        llm_temperature=0.2,
        llm_max_tokens=2048,
        citizens_model="moonshotai/kimi-k2-0905",
        mayor_model="moonshotai/kimi-k2.6",
        citizen_count=1,
        citizen_worker_count=1,
        max_concurrent_llm_calls=1,
        run_target="local",
        worker_ssh_target="root@127.0.0.1",
        season_seconds=60,
        mayor_tick_seconds=1,
        server_tick_seconds=1.0,
        min_decision_interval=1.0,
        database_url="postgresql://test",
        database_url_unpooled="postgresql://test",
    )


async def _wait_until(predicate, timeout: float = 1.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("condition was not met")
        await asyncio.sleep(0.01)


class GameFinalizerTests(unittest.IsolatedAsyncioTestCase):
    async def test_finalizer_skips_unfinished_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_store = DecisionLogStore(root / "logs")
            finalizer = GameFinalizer(log_store=log_store, root=root / "finalized")
            state = create_initial_state(citizen_count=1, season_seconds=600)
            state.started_at = 100.0
            state.now = 150.0

            finalized = await finalizer.finalize_if_needed(_StubStore(), state.game_id, state)

            self.assertFalse(finalized)
            self.assertFalse(finalizer.is_finalized(state.game_id))
            self.assertFalse((root / "finalized" / state.game_id / "terminal-packet.json").exists())

    async def test_finalizer_writes_terminal_packet_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_store = DecisionLogStore(root / "logs")
            log_store.append("game-finished", {
                "log_id": "1",
                "game_id": "game-finished",
                "ts": 123.0,
                "role": "citizen",
                "agent_id": "citizen-001",
                "summary": "aggressive -> ACTION:SNIFF",
            })
            finalizer = GameFinalizer(log_store=log_store, root=root / "finalized")
            state = create_initial_state(citizen_count=1, season_seconds=600)
            state.game_id = "game-finished"
            state.started_at = 100.0
            state.now = 700.0
            state.heat = 0.0
            store = _StubStore(
                events=[
                    GameEvent(
                        event_id="event-1",
                        tick=9,
                        game_hour=72.0,
                        kind="citizen_action",
                        message="Citizen pushed heat to zero.",
                        payload={"citizen_id": "citizen-001", "action": "COVER_TRACKS"},
                        public=True,
                    )
                ],
                dossiers=[
                    Dossier(
                        dossier_id="dossier-1",
                        created_at=680.0,
                        heat=1.0,
                        targets=[
                            DossierTarget(
                                citizen_id="citizen-001",
                                action=CitizenAction.SNIFF,
                                p_catch=0.3,
                                trace=24.0,
                                shiva=36.0,
                                evidence="noise",
                            )
                        ],
                    )
                ],
            )

            first = await finalizer.finalize_if_needed(store, state.game_id, state)
            second = await finalizer.finalize_if_needed(store, state.game_id, state)

            self.assertTrue(first)
            self.assertFalse(second)
            packet_path = root / "finalized" / state.game_id / "terminal-packet.json"
            marker_path = root / "finalized" / state.game_id / "finalized.json"
            self.assertTrue(packet_path.exists())
            self.assertTrue(marker_path.exists())

            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            self.assertEqual(packet["game_id"], state.game_id)
            self.assertEqual(packet["winner"], "citizens")
            self.assertEqual(packet["reason"], "heat_depleted")
            self.assertEqual(packet["final_heat"], 0.0)
            self.assertEqual(packet["decision_log"]["entry_count"], 1)
            self.assertTrue(packet["decision_log"]["path"].endswith("decision-turns.jsonl"))
            self.assertEqual(len(packet["citizen_snapshots"]), 1)
            self.assertEqual(len(packet["recent_events"]), 1)
            self.assertEqual(len(packet["recent_dossiers"]), 1)
            self.assertEqual(marker["packet_path"], str(packet_path))
            self.assertEqual(marker["finalized_at"], packet["finalized_at"])

    async def test_restart_before_terminal_does_not_finalize_old_game(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_store = DecisionLogStore(root / "logs")
            finalizer = GameFinalizer(log_store=log_store, root=root / "finalized")
            unfinished = create_initial_state(citizen_count=1, season_seconds=600)
            unfinished.game_id = "game-before-restart"
            unfinished.started_at = 100.0
            unfinished.now = 200.0
            unfinished.heat = 55.0

            finished = create_initial_state(citizen_count=1, season_seconds=600)
            finished.game_id = "game-after-restart"
            finished.started_at = 100.0
            finished.now = 701.0
            finished.heat = 44.0

            first = await finalizer.finalize_if_needed(_StubStore(), unfinished.game_id, unfinished)
            second = await finalizer.finalize_if_needed(_StubStore(), finished.game_id, finished)

            self.assertFalse(first)
            self.assertTrue(second)
            self.assertFalse(finalizer.is_finalized(unfinished.game_id))
            self.assertTrue(finalizer.is_finalized(finished.game_id))
            packet = json.loads((root / "finalized" / finished.game_id / "terminal-packet.json").read_text(encoding="utf-8"))
            self.assertEqual(packet["winner"], "citizens")
            self.assertEqual(packet["reason"], "timeout_survived")

    async def test_terminal_tick_finalizes_without_enqueuing_new_citizen_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_store = DecisionLogStore(root / "logs")
            finalizer = GameFinalizer(log_store=log_store, root=root / "finalized")
            state = create_initial_state(citizen_count=1, season_seconds=60)
            state.game_id = "terminal-on-tick"
            state.started_at = 0.0
            state.now = 59.0
            state.heat = 55.0
            store = _LoopStore(state)
            queue = _AsyncQueue()
            task = asyncio.create_task(
                run_game_loop(
                    store,
                    state.game_id,
                    queue,
                    _settings(),
                    [0],
                    asyncio.Lock(),
                    finalizer,
                )
            )

            try:
                await _wait_until(lambda: finalizer.is_finalized(state.game_id))
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

            self.assertTrue(store.state.is_finished)
            self.assertEqual(queue.enqueued, [])
            self.assertTrue(finalizer.is_finalized(state.game_id))

    async def test_citizen_worker_completes_stale_job_without_mutating_finished_game(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_store = DecisionLogStore(root / "logs")
            finalizer = GameFinalizer(log_store=log_store, root=root / "finalized")
            state = create_initial_state(citizen_count=1, season_seconds=60)
            state.game_id = "finished-before-worker-apply"
            state.started_at = 0.0
            state.now = 60.0
            state.heat = 55.0
            store = _LoopStore(state)
            queue = _AsyncQueue([
                Job(
                    job_id="job-1",
                    kind=JobKind.CITIZEN_DECISION,
                    payload={
                        "citizen_id": "citizen-001",
                        "behavior": "aggressive",
                        "game_id": state.game_id,
                        "observation": {},
                    },
                )
            ])
            runner = _FakeRunner()
            task = asyncio.create_task(
                run_citizen_worker_loop(
                    store,
                    queue,
                    runner,
                    _settings(),
                    asyncio.Semaphore(1),
                    "worker-test",
                    asyncio.Lock(),
                    finalizer,
                )
            )

            try:
                await asyncio.wait_for(queue.completed_event.wait(), timeout=1.0)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

            self.assertEqual(queue.completed, ["job-1"])
            self.assertEqual(queue.failed, [])
            self.assertEqual(runner.calls, 0)
            self.assertEqual(store.save_count, 0)
            self.assertEqual(store.events, [])
            self.assertEqual(store.state.heat, 55.0)
            self.assertTrue(finalizer.is_finalized(state.game_id))
            packet = json.loads((root / "finalized" / state.game_id / "terminal-packet.json").read_text(encoding="utf-8"))
            self.assertEqual(packet["winner"], "citizens")
            self.assertEqual(packet["reason"], "timeout_survived")


if __name__ == "__main__":
    unittest.main()
