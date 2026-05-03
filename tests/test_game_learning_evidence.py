from __future__ import annotations

import unittest

from src.server.game_learning_evidence import build_citizen_learning_evidence, build_mayor_learning_evidence
from src.server.models import CitizenAction, Dossier, DossierTarget, GameEvent


class GameLearningEvidenceTests(unittest.TestCase):
    def test_citizen_evidence_excludes_hidden_and_other_private_fields(self) -> None:
        packet = {
            "winner": "citizens",
            "reason": "timeout_survived",
            "final_heat": 72.0,
            "elapsed": 600.0,
            "season_seconds": 600,
            "citizen_snapshots": [
                {"citizen_id": "citizen-001", "behavior": "stealth_first", "trace": 31.0, "stk": 500},
                {"citizen_id": "citizen-002", "behavior": "aggressive", "trace": 90.0, "stk": 9999},
            ],
        }
        logs = [
            {
                "role": "mayor",
                "agent_id": "mayor",
                "behavior": "optimizer",
                "situation": {"dossier": {"recent_evidence": [{"secret": "do-not-show"}]}},
                "final": {"payload": {"action": "JAIL", "targets": ["citizen-002"], "rationale": "secret mayor reason"}},
            },
            {
                "role": "citizen",
                "agent_id": "citizen-002",
                "behavior": "aggressive",
                "situation": {"observation": {"private": {"trace": 90.0}}},
                "final": {"payload": {"kind": "ACTION", "action": "SNIFF", "rationale": "other private"}},
            },
            {
                "role": "citizen",
                "agent_id": "citizen-001",
                "behavior": "stealth_first",
                "situation": {
                    "observation": {
                        "game_hour": 12.0,
                        "global": {"heat": 60.0},
                        "private": {"stk": 300, "shiva": 35.0, "trace": 31.0, "mode": "SYNC", "statuses": ["SURVEILLED"]},
                        "allowed_actions": ["SNIFF", "COVER_TRACKS"],
                        "affordable_actions": ["COVER_TRACKS"],
                    }
                },
                "final": {"payload": {"kind": "ACTION", "action": "COVER_TRACKS", "rationale": "visible self reason"}},
            },
        ]
        events = [
            GameEvent("e1", 1, 10.0, "citizen_action", "other citizen acted", {
                "citizen_id": "citizen-002", "action": "SNIFF", "p_catch": 0.99, "heat": 65.0,
            }),
            GameEvent("e2", 2, 10.5, "citizen_action", "you recovered cleanly", {
                "citizen_id": "citizen-001", "action": "COVER_TRACKS", "caught": False, "heat": 58.0,
            }),
            GameEvent("e3", 3, 11.0, "mayor_decree", "Mayor pressure affected you", {
                "targets": ["citizen-001", "citizen-002"], "action": "SURVEIL", "rationale": "private mayor rationale",
            }),
        ]

        evidence = build_citizen_learning_evidence("citizen-001", packet, logs, events)

        text = repr(evidence)
        self.assertEqual(evidence["agent_id"], "citizen-001")
        self.assertEqual(evidence["behavior"], "stealth_first")
        self.assertEqual(len(evidence["own_turns"]), 1)
        self.assertEqual(len(evidence["candidate_lessons"]), 1)
        self.assertIn("COVER_TRACKS", evidence["candidate_lessons"][0]["pattern"])
        self.assertIn("COVER_TRACKS", evidence["own_decision_summary"]["actions"])
        self.assertNotIn("citizen-002', 'behavior", text)
        self.assertNotIn("secret mayor reason", text)
        self.assertNotIn("do-not-show", text)
        self.assertNotIn("p_catch", text)
        self.assertNotIn("private mayor rationale", text)

    def test_mayor_evidence_keeps_mayor_visible_context(self) -> None:
        packet = {"winner": "mayor", "reason": "heat_maxed", "final_heat": 100.0, "citizen_snapshots": []}
        logs = [{
            "role": "mayor",
            "agent_id": "mayor",
            "behavior": "optimizer",
            "situation": {"heat": 88.0, "recent_evidence": [{"citizen_id": "citizen-001"}]},
            "final": {"payload": {"action": "JAIL", "targets": ["citizen-001"], "duration_seconds": 60, "rationale": "repeated caught action"}},
        }]
        dossiers = [
            Dossier("d1", 100.0, 80.0, [
                DossierTarget("citizen-001", CitizenAction.SNIFF, 0.7, 45.0, 30.0, "caught sniff")
            ])
        ]
        events = [
            GameEvent("e1", 1, 10.0, "citizen_action", "caught", {"citizen_id": "citizen-001", "action": "SNIFF", "caught": True, "heat": 82.0}),
            GameEvent("e2", 2, 11.0, "mayor_decree", "Mayor applied SURVEIL to citizen-001.", {"target": "citizen-001", "action": "SURVEIL", "applied": True, "blocked_reason": None}),
        ]

        evidence = build_mayor_learning_evidence(packet, logs, events, dossiers)

        text = repr(evidence)
        self.assertEqual(evidence["agent_id"], "mayor")
        self.assertEqual(len(evidence["candidate_lessons"]), 1)
        self.assertIn("SURVEIL", evidence["candidate_lessons"][0]["pattern"])
        self.assertIn("JAIL", evidence["decree_summary"]["actions"])
        self.assertIn("citizen-001", evidence["decree_summary"]["targets"])
        self.assertIn("repeated caught action", text)
        self.assertIn("caught sniff", text)


if __name__ == "__main__":
    unittest.main()
