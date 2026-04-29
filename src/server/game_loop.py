from __future__ import annotations

import asyncio
import traceback
import time

from src.agents.hermes_runner import HermesAgentRunner
from src.server.config import Settings
from src.server.game_engine import advance_tick, apply_citizen_decision, apply_mayor_decree, build_citizen_observation, due_citizens
from src.server.models import JobKind, to_plain
from src.server.postgres_store import PostgresJobQueue, PostgresStore


async def run_game_loop(
    store: PostgresStore,
    game_id: str,
    queue: PostgresJobQueue,
    settings: Settings,
    tick_counter: list[int],
    game_lock: asyncio.Lock,
) -> None:
    while True:
        started = time.monotonic()
        try:
            to_enqueue = []
            already_queued = await queue.queued_citizen_ids()

            async with game_lock:
                state = await store.load_state(game_id)
                if state.is_finished:
                    await asyncio.sleep(5.0)
                    continue
                tick_counter[0] += 1
                result = advance_tick(state, seconds=settings.server_tick_seconds, tick=tick_counter[0])

                for citizen in due_citizens(state, min_decision_interval=settings.min_decision_interval):
                    if citizen.citizen_id in already_queued:
                        continue  # already has a pending/running job — skip
                    citizen.last_decision_at = state.now
                    to_enqueue.append((
                        citizen.citizen_id,
                        citizen.behavior,
                        build_citizen_observation(state, citizen.citizen_id),
                    ))

                await store.save_state(state)
                if result.events:
                    await store.append_events(result.events, game_id)

            for cid, behavior, obs in to_enqueue:
                await queue.enqueue(JobKind.CITIZEN_DECISION, {
                    "citizen_id": cid,
                    "behavior": behavior,
                    "game_id": game_id,
                    "observation": obs,
                })

        except Exception:
            print(f"[game_loop] tick error:\n{traceback.format_exc()}")

        elapsed = time.monotonic() - started
        await asyncio.sleep(max(0.0, settings.server_tick_seconds - elapsed))


async def run_citizen_worker_loop(
    store: PostgresStore,
    queue: PostgresJobQueue,
    runner: HermesAgentRunner,
    settings: Settings,
    semaphore: asyncio.Semaphore,
    worker_id: str,
    game_lock: asyncio.Lock,
) -> None:
    loop = asyncio.get_event_loop()
    job = None
    while True:
        try:
            jobs = await queue.claim(JobKind.CITIZEN_DECISION, worker_id=worker_id, limit=1)
            if not jobs:
                await asyncio.sleep(0.5)
                continue

            job = jobs[0]
            payload = job.payload
            citizen_id: str = payload["citizen_id"]
            behavior: str = payload.get("behavior", "aggressive")
            observation: dict = payload["observation"]
            game_id: str = payload["game_id"]

            print(f"[citizen_worker:{worker_id}] calling LLM for {citizen_id} ({behavior})", flush=True)
            async with semaphore:
                decision = await loop.run_in_executor(
                    None,
                    lambda cid=citizen_id, obs=observation, beh=behavior: runner.decide_citizen(cid, obs, beh),
                )

            async with game_lock:
                state = await store.load_state(game_id)
                if citizen_id not in state.citizens:
                    print(f"[citizen_worker:{worker_id}] {citizen_id} not in game {game_id}, skipping stale job")
                    await queue.complete(job.job_id)
                    job = None
                    continue
                result = apply_citizen_decision(state, decision, tick=0)
                await store.save_state(state)
                if result.events:
                    await store.append_events(result.events, game_id)
                if result.dossiers:
                    for dossier in result.dossiers:
                        await store.append_dossier(dossier, game_id)

            print(f"[citizen_worker:{worker_id}] {citizen_id} → {decision.kind.value} {decision.action}", flush=True)
            await queue.complete(job.job_id)
            job = None

        except Exception:
            print(f"[citizen_worker:{worker_id}] error:\n{traceback.format_exc()}")
            if job is not None:
                try:
                    await queue.fail(job.job_id)
                except Exception:
                    pass
                job = None
            await asyncio.sleep(1.0)


async def run_mayor_worker_loop(
    store: PostgresStore,
    runner: HermesAgentRunner,
    settings: Settings,
    semaphore: asyncio.Semaphore,
    game_id: str,
    game_lock: asyncio.Lock,
) -> None:
    loop = asyncio.get_event_loop()
    while True:
        await asyncio.sleep(settings.mayor_tick_seconds)
        try:
            dossiers, recent_events = await asyncio.gather(
                store.get_recent_dossiers(game_id, limit=10),
                store.get_events(game_id, limit=20, kinds=["citizen_action", "mode_change"]),
            )

            async with game_lock:
                state = await store.load_state(game_id)
                if state.is_finished:
                    continue

            dossier_dict = {
                "heat": round(state.heat, 2),
                "game_hour": round(state.game_hour, 2),
                "recent_actions": [
                    {"citizen_id": e.payload.get("citizen_id"), "action": e.payload.get("action"),
                     "caught": e.payload.get("caught"), "heat_after": e.payload.get("heat")}
                    for e in recent_events if e.kind == "citizen_action"
                ],
                "recent_evidence": [to_plain(d) for d in dossiers],
                "active_citizens": list(state.citizens.keys()),
            }
            allowed_targets = set(state.citizens.keys())

            async with semaphore:
                decree = await loop.run_in_executor(
                    None,
                    lambda dd=dossier_dict, at=allowed_targets: runner.decide_mayor(dd, at, "optimizer"),
                )

            async with game_lock:
                state = await store.load_state(game_id)
                events = apply_mayor_decree(state, decree, tick=0)
                await store.save_state(state)
                await store.save_mayor_decree(decree, game_id)
                if events:
                    await store.append_events(events, game_id)

            print(f"[mayor_worker] decree → {decree.action} targets={decree.targets}", flush=True)

        except Exception:
            print(f"[mayor_worker] error:\n{traceback.format_exc()}")
