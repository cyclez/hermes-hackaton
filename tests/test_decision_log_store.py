from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.server.decision_log_store import DecisionLogStore


class DecisionLogStoreTests(unittest.TestCase):
    def test_append_read_and_list_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = DecisionLogStore(Path(tmp))

            store.append("game-a", {
                "log_id": "1",
                "game_id": "game-a",
                "ts": 1.0,
                "role": "citizen",
                "agent_id": "citizen-001",
                "summary": "aggressive -> ACTION:JAM_SCAN",
            })
            store.append("game-a", {
                "log_id": "2",
                "game_id": "game-a",
                "ts": 2.0,
                "role": "mayor",
                "agent_id": "mayor",
                "summary": "optimizer -> SURVEIL",
            })

            entries = store.read_entries("game-a", limit=10)
            self.assertEqual([entry["log_id"] for entry in entries], ["2", "1"])

            citizen_only = store.read_entries("game-a", role="citizen", limit=10)
            self.assertEqual(len(citizen_only), 1)
            self.assertEqual(citizen_only[0]["agent_id"], "citizen-001")

            runs = store.list_runs(current_game_id="game-b")
            self.assertEqual(runs[0]["game_id"], "game-b")
            self.assertEqual(runs[0]["entry_count"], 0)
            self.assertTrue(any(run["game_id"] == "game-a" and run["entry_count"] == 2 for run in runs))


if __name__ == "__main__":
    unittest.main()
