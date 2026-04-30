from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Protocol

from src.server.decision_log_store import DecisionLogStore
from src.server.models import Citizen, CityState, to_plain


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
        root: Path | None = None,
        recent_event_limit: int = 25,
        recent_dossier_limit: int = 10,
    ) -> None:
        self.log_store = log_store
        self.root = root or (Path(".runtime") / "finalized-games")
        self.root.mkdir(parents=True, exist_ok=True)
        self.recent_event_limit = recent_event_limit
        self.recent_dossier_limit = recent_dossier_limit

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
        return True

    def is_finalized(self, game_id: str) -> bool:
        return self._marker_path(game_id).exists()

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

    def _write_json_atomic(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f"{path.name}.tmp-{uuid.uuid4()}")
        with temp_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=True, indent=2, sort_keys=True)
            fh.write("\n")
        temp_path.replace(path)


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
