from __future__ import annotations

import json
import uuid
from typing import Any

from psycopg_pool import AsyncConnectionPool

from src.server.models import (
    Citizen,
    CitizenAction,
    CitizenMode,
    CityState,
    Dossier,
    DossierTarget,
    GameEvent,
    JobKind,
    JobStatus,
    MayorDecree,
    MayorAction,
    StatusEffect,
    TimedStatus,
)
from src.server.queue import Job
from src.server.storage import POSTGRES_CLAIM_JOB_SQL, POSTGRES_SCHEMA


class PostgresStore:
    def __init__(self, database_url: str) -> None:
        self._url = database_url
        self._pool: AsyncConnectionPool | None = None

    async def connect(self) -> None:
        self._pool = AsyncConnectionPool(conninfo=self._url, open=False, min_size=1, max_size=10)
        await self._pool.open()

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    async def init_schema(self) -> None:
        assert self._pool
        async with self._pool.connection() as conn:
            await conn.set_autocommit(True)
            for stmt in POSTGRES_SCHEMA.split(";"):
                stmt = stmt.strip()
                if stmt:
                    await conn.execute(stmt)

    # ------------------------------------------------------------------ state

    async def save_state(self, state: CityState) -> None:
        assert self._pool
        async with self._pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO games (game_id, season_seconds, started_at, now, heat,
                                   server_scan_jammed_until, mayor_next_tick_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (game_id) DO UPDATE
                  SET now = EXCLUDED.now,
                      heat = EXCLUDED.heat,
                      server_scan_jammed_until = EXCLUDED.server_scan_jammed_until,
                      mayor_next_tick_at = EXCLUDED.mayor_next_tick_at
                """,
                (
                    state.game_id,
                    state.season_seconds,
                    state.started_at,
                    state.now,
                    state.heat,
                    state.server_scan_jammed_until,
                    state.mayor_next_tick_at,
                ),
            )
            for citizen in state.citizens.values():
                statuses_json = json.dumps(
                    [{"effect": s.effect.value, "expires_at": s.expires_at} for s in citizen.statuses]
                )
                await conn.execute(
                    """
                    INSERT INTO citizens (citizen_id, game_id, behavior, mode, queued_mode,
                                         stk, shiva, trace, last_decision_at,
                                         action_cooldown_until, statuses)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (citizen_id) DO UPDATE
                      SET game_id = EXCLUDED.game_id,
                          behavior = EXCLUDED.behavior,
                          mode = EXCLUDED.mode,
                          queued_mode = EXCLUDED.queued_mode,
                          stk = EXCLUDED.stk,
                          shiva = EXCLUDED.shiva,
                          trace = EXCLUDED.trace,
                          last_decision_at = EXCLUDED.last_decision_at,
                          action_cooldown_until = EXCLUDED.action_cooldown_until,
                          statuses = EXCLUDED.statuses
                    """,
                    (
                        citizen.citizen_id,
                        state.game_id,
                        citizen.behavior,
                        citizen.mode.value,
                        citizen.queued_mode.value if citizen.queued_mode else None,
                        citizen.stk,
                        citizen.shiva,
                        citizen.trace,
                        citizen.last_decision_at,
                        citizen.action_cooldown_until,
                        statuses_json,
                    ),
                )

    async def load_state(self, game_id: str) -> CityState:
        assert self._pool
        async with self._pool.connection() as conn:
            row = await (await conn.execute(
                "SELECT season_seconds, started_at, now, heat, server_scan_jammed_until, mayor_next_tick_at "
                "FROM games WHERE game_id = %s",
                (game_id,),
            )).fetchone()
            if row is None:
                raise RuntimeError(f"No game found for game_id={game_id}")
            season_seconds, started_at, now, heat, jammed_until, mayor_next = row

            citizen_rows = await (await conn.execute(
                "SELECT citizen_id, behavior, mode, queued_mode, stk, shiva, trace, "
                "last_decision_at, action_cooldown_until, statuses "
                "FROM citizens WHERE game_id = %s",
                (game_id,),
            )).fetchall()

        citizens: dict[str, Citizen] = {}
        for crow in citizen_rows:
            cid, behavior, mode, qmode, stk, shiva, trace, last_dec, cooldown, statuses_raw = crow
            raw_statuses = statuses_raw if isinstance(statuses_raw, list) else json.loads(statuses_raw or "[]")
            statuses = [
                TimedStatus(effect=StatusEffect(s["effect"]), expires_at=s["expires_at"])
                for s in raw_statuses
            ]
            citizens[cid] = Citizen(
                citizen_id=cid,
                behavior=behavior,
                mode=CitizenMode(mode),
                queued_mode=CitizenMode(qmode) if qmode else None,
                stk=stk,
                shiva=shiva,
                trace=trace,
                last_decision_at=last_dec,
                action_cooldown_until=cooldown,
                statuses=statuses,
            )

        return CityState(
            game_id=game_id,
            season_seconds=int(season_seconds),
            started_at=started_at,
            now=now,
            heat=heat,
            server_scan_jammed_until=jammed_until,
            mayor_next_tick_at=mayor_next,
            citizens=citizens,
        )

    # ----------------------------------------------------------------- events

    async def append_events(self, events: list[GameEvent], game_id: str) -> None:
        if not events:
            return
        assert self._pool
        async with self._pool.connection() as conn:
            for event in events:
                await conn.execute(
                    """
                    INSERT INTO events (event_id, game_id, tick, game_hour, kind, message, payload, public)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                    ON CONFLICT (event_id) DO NOTHING
                    """,
                    (
                        event.event_id,
                        game_id,
                        event.tick,
                        event.game_hour,
                        event.kind,
                        event.message,
                        json.dumps(event.payload),
                        event.public,
                    ),
                )

    async def get_events(
        self, game_id: str, limit: int = 50, kinds: list[str] | None = None
    ) -> list[GameEvent]:
        assert self._pool
        async with self._pool.connection() as conn:
            if kinds:
                rows = await (await conn.execute(
                    "SELECT event_id, tick, game_hour, kind, message, payload, public "
                    "FROM events WHERE game_id = %s AND kind = ANY(%s) ORDER BY created_at DESC LIMIT %s",
                    (game_id, kinds, limit),
                )).fetchall()
            else:
                rows = await (await conn.execute(
                    "SELECT event_id, tick, game_hour, kind, message, payload, public "
                    "FROM events WHERE game_id = %s ORDER BY created_at DESC LIMIT %s",
                    (game_id, limit),
                )).fetchall()
        return [
            GameEvent(
                event_id=str(r[0]),
                tick=r[1],
                game_hour=r[2],
                kind=r[3],
                message=r[4],
                payload=r[5] if isinstance(r[5], dict) else json.loads(r[5] or "{}"),
                public=r[6],
            )
            for r in rows
        ]

    async def public_events(self, game_id: str, limit: int = 50) -> list[GameEvent]:
        assert self._pool
        async with self._pool.connection() as conn:
            rows = await (await conn.execute(
                "SELECT event_id, tick, game_hour, kind, message, payload, public "
                "FROM events WHERE game_id = %s AND public = true ORDER BY created_at DESC LIMIT %s",
                (game_id, limit),
            )).fetchall()
        return [
            GameEvent(
                event_id=str(r[0]),
                tick=r[1],
                game_hour=r[2],
                kind=r[3],
                message=r[4],
                payload=r[5] if isinstance(r[5], dict) else json.loads(r[5] or "{}"),
                public=r[6],
            )
            for r in rows
        ]

    # --------------------------------------------------------------- dossiers

    async def append_dossier(self, dossier: Dossier, game_id: str) -> None:
        assert self._pool
        targets_json = json.dumps(
            [
                {
                    "citizen_id": t.citizen_id,
                    "action": t.action.value,
                    "p_catch": t.p_catch,
                    "trace": t.trace,
                    "shiva": t.shiva,
                    "evidence": t.evidence,
                }
                for t in dossier.targets
            ]
        )
        async with self._pool.connection() as conn:
            await conn.execute(
                "INSERT INTO dossiers (dossier_id, game_id, heat, targets, created_at) "
                "VALUES (%s, %s, %s, %s::jsonb, %s) ON CONFLICT (dossier_id) DO NOTHING",
                (dossier.dossier_id, game_id, dossier.heat, targets_json, dossier.created_at),
            )

    async def get_recent_dossiers(self, game_id: str, limit: int = 10) -> list[Dossier]:
        assert self._pool
        async with self._pool.connection() as conn:
            rows = await (await conn.execute(
                "SELECT dossier_id, heat, targets, created_at FROM dossiers "
                "WHERE game_id = %s ORDER BY created_at DESC LIMIT %s",
                (game_id, limit),
            )).fetchall()
        result = []
        for r in rows:
            raw_targets = r[2] if isinstance(r[2], list) else json.loads(r[2] or "[]")
            targets = [
                DossierTarget(
                    citizen_id=t["citizen_id"],
                    action=CitizenAction(t["action"]),
                    p_catch=t["p_catch"],
                    trace=t["trace"],
                    shiva=t["shiva"],
                    evidence=t["evidence"],
                )
                for t in raw_targets
            ]
            result.append(Dossier(dossier_id=str(r[0]), created_at=r[3], heat=r[1], targets=targets))
        return result

    # ----------------------------------------------------------- mayor decrees

    async def save_mayor_decree(self, decree: MayorDecree, game_id: str) -> None:
        assert self._pool
        async with self._pool.connection() as conn:
            await conn.execute(
                "INSERT INTO mayor_decrees (decree_id, game_id, action, targets, rationale, duration_seconds) "
                "VALUES (%s, %s, %s, %s::jsonb, %s, %s)",
                (
                    str(uuid.uuid4()),
                    game_id,
                    decree.action.value,
                    json.dumps(decree.targets),
                    decree.rationale,
                    decree.duration_seconds,
                ),
            )

    async def latest_mayor_decree(self, game_id: str) -> dict[str, Any] | None:
        assert self._pool
        async with self._pool.connection() as conn:
            row = await (await conn.execute(
                "SELECT action, targets, rationale, duration_seconds, created_at "
                "FROM mayor_decrees WHERE game_id = %s ORDER BY created_at DESC LIMIT 1",
                (game_id,),
            )).fetchone()
        if row is None:
            return None
        targets = row[1] if isinstance(row[1], list) else json.loads(row[1] or "[]")
        return {
            "action": row[0],
            "targets": targets,
            "rationale": row[2],
            "duration_seconds": row[3],
            "created_at": row[4].isoformat() if row[4] else None,
        }


# ====================================================================== queue


class PostgresJobQueue:
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def enqueue(self, kind: JobKind, payload: dict[str, Any]) -> Job:
        job_id = str(uuid.uuid4())
        async with self._pool.connection() as conn:
            await conn.execute(
                "INSERT INTO jobs (job_id, kind, status, payload) VALUES (%s, %s, %s, %s::jsonb)",
                (job_id, kind.value, JobStatus.PENDING.value, json.dumps(payload)),
            )
        return Job(job_id=job_id, kind=kind, payload=payload)

    async def claim(self, kind: JobKind, worker_id: str, limit: int = 1) -> list[Job]:
        async with self._pool.connection() as conn:
            rows = await (await conn.execute(
                POSTGRES_CLAIM_JOB_SQL,
                {"kind": kind.value, "limit": limit, "worker_id": worker_id},
            )).fetchall()
        jobs = []
        for row in rows:
            col_names = ["job_id", "kind", "status", "payload", "attempts", "locked_by", "locked_at", "created_at", "updated_at"]
            data = dict(zip(col_names, row))
            payload = data["payload"] if isinstance(data["payload"], dict) else json.loads(data["payload"] or "{}")
            jobs.append(Job(
                job_id=str(data["job_id"]),
                kind=JobKind(data["kind"]),
                payload=payload,
                status=JobStatus(data["status"]),
                attempts=data["attempts"],
            ))
        return jobs

    async def complete(self, job_id: str) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                "UPDATE jobs SET status = %s, updated_at = now() WHERE job_id = %s",
                (JobStatus.DONE.value, job_id),
            )

    async def fail(self, job_id: str) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                "UPDATE jobs SET status = %s, updated_at = now() WHERE job_id = %s",
                (JobStatus.FAILED.value, job_id),
            )

    async def queued_citizen_ids(self) -> set[str]:
        """Return citizen_ids that already have a PENDING or RUNNING CITIZEN_DECISION job."""
        async with self._pool.connection() as conn:
            rows = await (await conn.execute(
                "SELECT DISTINCT payload->>'citizen_id' FROM jobs "
                "WHERE kind = 'CITIZEN_DECISION' AND status IN ('PENDING', 'RUNNING')"
            )).fetchall()
        return {r[0] for r in rows if r[0]}

    async def clear_all_jobs(self) -> int:
        async with self._pool.connection() as conn:
            row = await (await conn.execute(
                "DELETE FROM jobs WHERE status IN ('PENDING', 'RUNNING', 'FAILED') RETURNING job_id"
            )).fetchall()
        return len(row)

    async def pending_count(self, kind: JobKind | None = None) -> int:
        assert self._pool
        async with self._pool.connection() as conn:
            if kind is None:
                row = await (await conn.execute(
                    "SELECT COUNT(*) FROM jobs WHERE status = %s",
                    (JobStatus.PENDING.value,),
                )).fetchone()
            else:
                row = await (await conn.execute(
                    "SELECT COUNT(*) FROM jobs WHERE status = %s AND kind = %s",
                    (JobStatus.PENDING.value, kind.value),
                )).fetchone()
        return int(row[0]) if row else 0
