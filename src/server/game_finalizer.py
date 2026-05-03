from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from src.server.decision_log_store import DecisionLogStore
from src.server.game_learning_evidence import build_citizen_learning_evidence, build_mayor_learning_evidence
from src.server.models import Citizen, CityState, to_plain

if TYPE_CHECKING:
    from src.agents.hermes_runner import HermesAgentRunner


class FinalizerStore(Protocol):
    async def get_events(self, game_id: str, limit: int = 50, kinds: list[str] | None = None) -> list[Any]:
        ...

    async def get_recent_dossiers(self, game_id: str, limit: int = 10) -> list[Any]:
        ...


class GameFinalizer:
    def __init__(
        self,
        *,
        log_store: DecisionLogStore,
        runner: HermesAgentRunner | None = None,
        training_enabled: bool = True,
        root: Path | None = None,
        recent_event_limit: int = 25,
        recent_dossier_limit: int = 10,
        learning_event_limit: int = 2000,
        learning_dossier_limit: int = 2000,
    ) -> None:
        self.log_store = log_store
        self.runner = runner
        self.training_enabled = training_enabled
        self.root = root or (Path(".runtime") / "finalized-games")
        self.root.mkdir(parents=True, exist_ok=True)
        self.recent_event_limit = recent_event_limit
        self.recent_dossier_limit = recent_dossier_limit
        self.learning_event_limit = learning_event_limit
        self.learning_dossier_limit = learning_dossier_limit
        self._learning_progress: dict[str, dict[str, Any]] = {}

    async def finalize_if_needed(self, store: FinalizerStore, game_id: str, state: CityState) -> bool:
        if not state.is_finished:
            return False

        marker_path = self._marker_path(game_id)
        if marker_path.exists():
            return False

        packet = await self._build_packet(store, game_id, state)
        packet_path = self._packet_path(game_id)
        self._write_json_atomic(packet_path, packet)
        self._write_json_atomic(marker_path, {
            "game_id": game_id,
            "finalized_at": packet["finalized_at"],
            "winner": packet["winner"],
            "reason": packet["reason"],
            "packet_path": str(packet_path),
        })
        print(
            f"[finalizer] finalized game {game_id} winner={packet['winner']} reason={packet['reason']}",
            flush=True,
        )
        self._schedule_learning_if_configured(store, game_id, packet)
        return True

    def is_finalized(self, game_id: str) -> bool:
        return self._marker_path(game_id).exists()

    def is_learning_started(self, game_id: str) -> bool:
        return self._learning_started_path(game_id).exists()

    def learning_status(self, game_id: str, *, state_finished: bool | None = None) -> dict[str, Any]:
        current = self._learning_progress.get(game_id)
        if current is not None:
            return dict(current)

        started = self._read_json_if_exists(self._learning_started_path(game_id))
        completed = self._read_json_if_exists(self._learning_completed_path(game_id))
        failed = self._read_json_if_exists(self._learning_failed_path(game_id))

        if completed is not None:
            results = list(completed.get("results") or [])
            started_at = started.get("learning_started_at") if started else None
            return {
                "game_id": game_id,
                "status": "completed",
                "started_at": started_at,
                "completed_at": completed.get("learning_completed_at"),
                "failed_at": None,
                "completed_count": len(results),
                "total_count": len(results),
                "current_role": None,
                "current_agent_id": None,
                "current_behavior": None,
                "error": None,
                "results": results,
            }

        if failed is not None:
            failed_results = list(failed.get("results") or [])
            return {
                "game_id": game_id,
                "status": "failed",
                "started_at": started.get("learning_started_at") if started else None,
                "completed_at": None,
                "failed_at": failed.get("failed_at"),
                "completed_count": int(failed.get("completed_count") or (started or {}).get("completed_count") or 0),
                "total_count": int(failed.get("total_count") or (started or {}).get("total_count") or 0),
                "current_role": None,
                "current_agent_id": None,
                "current_behavior": None,
                "error": str(failed.get("error") or "learning pass failed"),
                "results": failed_results,
            }

        if started is not None:
            return {
                "game_id": game_id,
                "status": "pending",
                "started_at": started.get("learning_started_at"),
                "completed_at": None,
                "failed_at": None,
                "completed_count": int(started.get("completed_count") or 0),
                "total_count": int(started.get("total_count") or 0),
                "current_role": None,
                "current_agent_id": None,
                "current_behavior": None,
                "error": None,
                "results": [],
            }

        if not self.training_enabled and state_finished:
            return {
                "game_id": game_id,
                "status": "disabled",
                "started_at": None,
                "completed_at": None,
                "failed_at": None,
                "completed_count": 0,
                "total_count": 0,
                "current_role": None,
                "current_agent_id": None,
                "current_behavior": None,
                "error": None,
                "results": [],
            }

        return {
            "game_id": game_id,
            "status": "pending" if state_finished else "idle",
            "started_at": None,
            "completed_at": None,
            "failed_at": None,
            "completed_count": 0,
            "total_count": 0,
            "current_role": None,
            "current_agent_id": None,
            "current_behavior": None,
            "error": None,
            "results": [],
        }

    async def _build_packet(self, store: FinalizerStore, game_id: str, state: CityState) -> dict[str, Any]:
        finalized_at = time.time()
        winner, reason = terminal_outcome(state)
        recent_events = await store.get_events(game_id, limit=self.recent_event_limit)
        recent_dossiers = await store.get_recent_dossiers(game_id, limit=self.recent_dossier_limit)
        decision_log = self.log_store.get_run_record(game_id)
        decision_log["path"] = str(self.log_store.log_path(game_id))

        return {
            "game_id": game_id,
            "finalized_at": finalized_at,
            "winner": winner,
            "reason": reason,
            "final_heat": round(state.heat, 3),
            "elapsed": round(state.elapsed, 3),
            "season_seconds": state.season_seconds,
            "game_hour": round(state.game_hour, 3),
            "started_at": state.started_at,
            "now": state.now,
            "citizen_snapshots": [_citizen_snapshot(citizen, state.now) for citizen in state.citizens.values()],
            "recent_events": [to_plain(event) for event in recent_events],
            "recent_dossiers": [to_plain(dossier) for dossier in recent_dossiers],
            "decision_log": decision_log,
        }

    def _game_dir(self, game_id: str) -> Path:
        return self.root / game_id

    def _packet_path(self, game_id: str) -> Path:
        return self._game_dir(game_id) / "terminal-packet.json"

    def _marker_path(self, game_id: str) -> Path:
        return self._game_dir(game_id) / "finalized.json"

    def _learning_started_path(self, game_id: str) -> Path:
        return self._game_dir(game_id) / "learning-started.json"

    def _learning_completed_path(self, game_id: str) -> Path:
        return self._game_dir(game_id) / "learning-completed.json"

    def _learning_failed_path(self, game_id: str) -> Path:
        return self._game_dir(game_id) / "learning-failed.json"

    def _schedule_learning_if_configured(self, store: FinalizerStore, game_id: str, packet: dict[str, Any]) -> None:
        if self.runner is None or not self.training_enabled:
            return
        if packet.get("reason") not in {"heat_maxed", "heat_depleted", "timeout_survived"}:
            return
        started_path = self._learning_started_path(game_id)
        if started_path.exists() or self._learning_completed_path(game_id).exists():
            return
        total_count = len(packet.get("citizen_snapshots") or []) + 1
        started_payload = {
            "game_id": game_id,
            "learning_started_at": time.time(),
            "reason": packet.get("reason"),
            "completed_count": 0,
            "total_count": total_count,
        }
        self._write_json_atomic(started_path, started_payload)
        self._set_learning_progress(
            game_id,
            status="pending",
            started_at=started_payload["learning_started_at"],
            completed_at=None,
            failed_at=None,
            completed_count=0,
            total_count=total_count,
            current_role=None,
            current_agent_id=None,
            current_behavior=None,
            error=None,
            results=[],
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._run_learning_pass(store, game_id, packet), name=f"learning:{game_id}")
        except RuntimeError:
            self._write_json_atomic(self._learning_failed_path(game_id), {
                "game_id": game_id,
                "failed_at": time.time(),
                "error": "no running event loop for learning pass",
            })
            self._set_learning_progress(
                game_id,
                status="failed",
                completed_at=None,
                failed_at=time.time(),
                current_role=None,
                current_agent_id=None,
                current_behavior=None,
                error="no running event loop for learning pass",
                results=[],
            )

    async def _run_learning_pass(self, store: FinalizerStore, game_id: str, packet: dict[str, Any]) -> None:
        assert self.runner is not None
        loop = asyncio.get_running_loop()
        total_count = len(packet.get("citizen_snapshots") or []) + 1
        try:
            events = await store.get_events(game_id, limit=self.learning_event_limit)
            dossiers = await store.get_recent_dossiers(game_id, limit=self.learning_dossier_limit)
            decision_logs = self.log_store.read_entries(game_id, limit=0)
            results: list[dict[str, Any]] = []
            self._set_learning_progress(
                game_id,
                status="running",
                total_count=total_count,
                completed_count=0,
                current_role=None,
                current_agent_id=None,
                current_behavior=None,
                error=None,
                results=[],
            )

            for snapshot in packet.get("citizen_snapshots") or []:
                citizen_id = snapshot.get("citizen_id")
                behavior = snapshot.get("behavior") or "aggressive"
                if not citizen_id:
                    continue
                self._set_learning_progress(
                    game_id,
                    status="running",
                    current_role="citizen_learning",
                    current_agent_id=citizen_id,
                    current_behavior=behavior,
                )
                print(
                    f"[finalizer] learning citizen {citizen_id} behavior={behavior} game={game_id}",
                    flush=True,
                )
                evidence = build_citizen_learning_evidence(citizen_id, packet, decision_logs, events)
                result = await loop.run_in_executor(
                    None,
                    lambda cid=citizen_id, beh=behavior, ev=evidence: self.runner.learn_citizen_from_game(
                        cid, beh, ev, game_id
                    ),
                )
                row = _learning_result_row(citizen_id, "citizen_learning", result)
                print(
                    f"[finalizer] learned citizen {citizen_id} decision={row['decision']} ok={row['ok']} game={game_id}",
                    flush=True,
                )
                results.append(row)
                self._set_learning_progress(
                    game_id,
                    completed_count=len(results),
                    results=list(results),
                )

            mayor_evidence = build_mayor_learning_evidence(packet, decision_logs, events, dossiers)
            mayor_behavior = mayor_evidence.get("behavior") or "optimizer"
            self._set_learning_progress(
                game_id,
                status="running",
                current_role="mayor_learning",
                current_agent_id="mayor",
                current_behavior=mayor_behavior,
            )
            print(
                f"[finalizer] learning mayor behavior={mayor_behavior} game={game_id}",
                flush=True,
            )
            mayor_result = await loop.run_in_executor(
                None,
                lambda ev=mayor_evidence, beh=mayor_behavior: self.runner.learn_mayor_from_game(beh, ev, game_id),
            )
            mayor_row = _learning_result_row("mayor", "mayor_learning", mayor_result)
            print(
                f"[finalizer] learned mayor decision={mayor_row['decision']} ok={mayor_row['ok']} game={game_id}",
                flush=True,
            )
            results.append(mayor_row)
            completed_at = time.time()
            self._write_json_atomic(self._learning_completed_path(game_id), {
                "game_id": game_id,
                "learning_completed_at": completed_at,
                "results": results,
            })
            self._set_learning_progress(
                game_id,
                status="completed",
                completed_at=completed_at,
                failed_at=None,
                completed_count=len(results),
                total_count=total_count,
                current_role=None,
                current_agent_id=None,
                current_behavior=None,
                error=None,
                results=list(results),
            )
            print(f"[finalizer] learning completed for game {game_id}", flush=True)
        except Exception as exc:
            failed_at = time.time()
            self._write_json_atomic(self._learning_failed_path(game_id), {
                "game_id": game_id,
                "failed_at": failed_at,
                "error": str(exc),
                "results": results,
                "completed_count": len(results),
                "total_count": total_count,
            })
            self._set_learning_progress(
                game_id,
                status="failed",
                completed_at=None,
                failed_at=failed_at,
                completed_count=len(results),
                total_count=total_count,
                current_role=None,
                current_agent_id=None,
                current_behavior=None,
                error=str(exc),
                results=list(results),
            )
            print(f"[finalizer] learning failed for game {game_id}: {exc}", flush=True)

    def _write_json_atomic(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f"{path.name}.tmp-{uuid.uuid4()}")
        with temp_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=True, indent=2, sort_keys=True)
            fh.write("\n")
        temp_path.replace(path)

    def _set_learning_progress(self, game_id: str, **updates: Any) -> None:
        current = dict(self._learning_progress.get(game_id) or {"game_id": game_id})
        current.update(updates)
        self._learning_progress[game_id] = current

    @staticmethod
    def _read_json_if_exists(path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))


def terminal_outcome(state: CityState) -> tuple[str, str]:
    if state.heat >= 100.0:
        return "mayor", "heat_maxed"
    if state.heat <= 0.0:
        return "citizens", "heat_depleted"
    if state.elapsed >= state.season_seconds:
        return "citizens", "timeout_survived"
    raise ValueError(f"state for game {state.game_id} is not terminal")


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


def _learning_result_row(agent_id: str, role: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent_id": agent_id,
        "role": role,
        "ok": bool(result.get("ok")),
        "completed": bool(result.get("completed")),
        "partial": bool(result.get("partial")),
        "error": result.get("error"),
        "decision": result.get("decision") or ("failed" if not result.get("ok") else "no_change"),
        "skill_changed": bool((result.get("skill_update") or {}).get("changed")),
        "memory_changed": bool((result.get("memory_update") or {}).get("changed")),
    }
