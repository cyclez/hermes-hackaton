from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any


class DecisionLogStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (Path(".runtime") / "decision-logs")
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def append(self, game_id: str, entry: dict[str, Any]) -> None:
        log_file = self._log_file(game_id)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(entry, ensure_ascii=False)
        with self._lock:
            with log_file.open("a", encoding="utf-8") as fh:
                fh.write(payload)
                fh.write("\n")

    def read_entries(
        self,
        game_id: str,
        *,
        limit: int = 200,
        role: str | None = None,
        agent_id: str | None = None,
    ) -> list[dict[str, Any]]:
        log_file = self._log_file(game_id)
        if not log_file.exists():
            return []

        entries: list[dict[str, Any]] = []
        with log_file.open("r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    entry = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if role and entry.get("role") != role:
                    continue
                if agent_id and entry.get("agent_id") != agent_id:
                    continue
                entries.append(entry)

        if limit > 0:
            entries = entries[-limit:]
        entries.reverse()
        return entries

    def list_runs(self, current_game_id: str | None = None) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        seen: set[str] = set()

        for game_dir in sorted(self.root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not game_dir.is_dir():
                continue
            game_id = game_dir.name
            runs.append(self.get_run_record(game_id))
            seen.add(game_id)

        if current_game_id and current_game_id not in seen:
            runs.insert(0, self.get_run_record(current_game_id))
        return runs

    def get_run_record(self, game_id: str) -> dict[str, Any]:
        log_file = self.log_path(game_id)
        entry_count = 0
        updated_at = None
        if log_file.exists():
            updated_at = log_file.stat().st_mtime
            with log_file.open("r", encoding="utf-8") as fh:
                entry_count = sum(1 for _ in fh)
        return {
            "game_id": game_id,
            "updated_at": updated_at,
            "entry_count": entry_count,
        }

    def log_path(self, game_id: str) -> Path:
        return self.root / game_id / "decision-turns.jsonl"

    def _log_file(self, game_id: str) -> Path:
        return self.log_path(game_id)
