from __future__ import annotations

import asyncio
import traceback
import time
from typing import TYPE_CHECKING

from src.server.config import Settings
from src.server.game_finalizer import GameFinalizer
from src.server.game_engine import advance_tick, apply_citizen_decision, apply_mayor_decree, build_citizen_observation, due_citizens
from src.server.models import Citizen, CitizenDecision, DecisionKind, JobKind, StatusEffect, to_plain

if TYPE_CHECKING:
    from src.agents.hermes_runner import HermesAgentRunner
    from src.server.postgres_store import PostgresJobQueue, PostgresStore


async def run_game_loop(
    store: PostgresStore,
    game_id: str,
    queue: PostgresJobQueue,
    settings: Settings,
    tick_counter: list[int],
    game_lock: asyncio.Lock,
    finalizer: GameFinalizer,
) -> None:
    while True:
        started = time.monotonic()
        try:
            to_enqueue = []
            already_queued = await queue.queued_citizen_ids()
            sleep_finished = False

            async with game_lock:
                state = await store.load_state(game_id)
                if state.is_finished:
                    await finalizer.finalize_if_needed(store, game_id, state)
                    sleep_finished = True
                else:
                    tick_counter[0] += 1
                    result = advance_tick(state, seconds=settings.server_tick_seconds, tick=tick_counter[0])

                    server_held: list[tuple] = []
                    if state.is_finished:
                        sleep_finished = True
                    else:
                        for citizen in due_citizens(state, min_decision_interval=settings.min_decision_interval):
                            if citizen.citizen_id in already_queued:
                                continue
                            citizen.last_decision_at = state.now
                            if citizen.has_status(StatusEffect.JAILED, state.now) or citizen.has_status(StatusEffect.JAMMED, state.now):
                                # server-side auto-HOLD: don't burn an LLM call on a blocked citizen
                                server_held.append((citizen.citizen_id, "jailed" if citizen.has_status(StatusEffect.JAILED, state.now) else "jammed"))
                                continue
                            to_enqueue.append((
                                citizen.citizen_id,
                                citizen.behavior,
                                build_citizen_observation(state, citizen.citizen_id),
                            ))

                    await store.save_state(state)
                    all_events = list(result.events)
                    for cid, reason in server_held:
                        hold_result = apply_citizen_decision(
                            state,
                            CitizenDecision(citizen_id=cid, kind=DecisionKind.HOLD, rationale=f"server: {reason}"),
                            tick=tick_counter[0],
                        )
                        all_events.extend(hold_result.events)
                    if all_events:
                        await store.append_events(all_events, game_id)
                    if state.is_finished:
                        await finalizer.finalize_if_needed(store, game_id, state)
                        sleep_finished = True

            if sleep_finished:
                await asyncio.sleep(5.0)
                continue

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
    finalizer: GameFinalizer,
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

            async with game_lock:
                state = await store.load_state(game_id)
                if citizen_id not in state.citizens:
                    print(f"[citizen_worker:{worker_id}] {citizen_id} not in game {game_id}, skipping stale job")
                    await queue.complete(job.job_id)
                    job = None
                    continue
                if state.is_finished:
                    await finalizer.finalize_if_needed(store, game_id, state)
                    print(f"[citizen_worker:{worker_id}] {citizen_id} stale job after game finish, skipping")
                    await queue.complete(job.job_id)
                    job = None
                    continue

            print(f"[citizen_worker:{worker_id}] calling LLM for {citizen_id} ({behavior})", flush=True)
            async with semaphore:
                decision = await loop.run_in_executor(
                    None,
                    lambda cid=citizen_id, obs=observation, beh=behavior, gid=game_id: runner.decide_citizen(cid, obs, beh, gid),
                )

            async with game_lock:
                state = await store.load_state(game_id)
                if citizen_id not in state.citizens:
                    print(f"[citizen_worker:{worker_id}] {citizen_id} not in game {game_id}, skipping stale job")
                    await queue.complete(job.job_id)
                    job = None
                    continue
                if state.is_finished:
                    await finalizer.finalize_if_needed(store, game_id, state)
                    print(f"[citizen_worker:{worker_id}] {citizen_id} stale job after game finish, skipping")
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
                if state.is_finished:
                    await finalizer.finalize_if_needed(store, game_id, state)

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
    finalizer: GameFinalizer,
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
                    await finalizer.finalize_if_needed(store, game_id, state)
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
            context_snapshot = {
                "kind": "mayor_context",
                "heat": dossier_dict["heat"],
                "game_hour": dossier_dict["game_hour"],
                "recent_actions": dossier_dict["recent_actions"],
                "recent_evidence": _recent_evidence_summary(dossiers),
                "active_citizens": dossier_dict["active_citizens"],
                "citizen_snapshots": [_citizen_snapshot(citizen, state.now) for citizen in state.citizens.values()],
            }

            async with semaphore:
                decree = await loop.run_in_executor(
                    None,
                    lambda dd=dossier_dict, at=allowed_targets, gid=game_id, ctx=context_snapshot: runner.decide_mayor(
                        dd, at, "optimizer", gid, ctx
                    ),
                )

            async with game_lock:
                state = await store.load_state(game_id)
                if state.is_finished:
                    await finalizer.finalize_if_needed(store, game_id, state)
                    print("[mayor_worker] stale decree after game finish, skipping", flush=True)
                    continue
                events = apply_mayor_decree(state, decree, tick=0)
                await store.save_state(state)
                await store.save_mayor_decree(decree, game_id)
                if events:
                    await store.append_events(events, game_id)
                if state.is_finished:
                    await finalizer.finalize_if_needed(store, game_id, state)

            print(f"[mayor_worker] decree → {decree.action} targets={decree.targets}", flush=True)

        except Exception:
            print(f"[mayor_worker] error:\n{traceback.format_exc()}")


def _citizen_snapshot(citizen: Citizen, now: float) -> dict[str, object]:
    return {
        "citizen_id": citizen.citizen_id,
        "behavior": citizen.behavior,
        "mode": citizen.mode.value,
        "queued_mode": citizen.queued_mode.value if citizen.queued_mode else None,
        "statuses": [status.effect.value for status in citizen.active_statuses(now)],
        "stk": int(citizen.stk),
        "shiva": round(citizen.shiva, 2),
        "trace": round(citizen.trace, 2),
        "action_cooldown_remaining": round(max(0.0, citizen.action_cooldown_until - now), 2),
    }


def _recent_evidence_summary(dossiers: list) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for dossier in dossiers:
        for target in dossier.targets:
            rows.append({
                "citizen_id": target.citizen_id,
                "action": target.action.value,
                "p_catch": round(target.p_catch, 3),
                "trace": round(target.trace, 2),
                "shiva": round(target.shiva, 2),
            })
    return rows
