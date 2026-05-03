from __future__ import annotations

import unittest

from src.server.learning_resume import completed_learning_agents, planned_learning_agents


class LearningResumeTests(unittest.TestCase):
    def test_completed_learning_agents_reads_durable_learning_rows(self) -> None:
        logs = [
            {"role": "citizen", "agent_id": "citizen-001"},
            {
                "role": "citizen_learning",
                "agent_id": "citizen-002",
                "final": {"ok": True, "payload": {"completed": True, "partial": False, "error": None}},
            },
            {
                "role": "mayor_learning",
                "agent_id": "mayor",
                "final": {"ok": True, "payload": {"completed": True, "partial": False, "error": None}},
            },
        ]

        self.assertEqual(completed_learning_agents(logs), {"citizen-002", "mayor"})

    def test_completed_learning_agents_ignores_partial_rows(self) -> None:
        logs = [
            {
                "role": "citizen_learning",
                "agent_id": "citizen-001",
                "final": {"ok": False, "payload": {"completed": False, "partial": True, "error": None}},
            },
            {
                "role": "mayor_learning",
                "agent_id": "mayor",
                "final": {"ok": True, "payload": {"completed": True, "partial": False, "error": None}},
            },
        ]

        self.assertEqual(completed_learning_agents(logs), {"mayor"})

    def test_completed_learning_agents_ignores_legacy_rows_that_hit_budget(self) -> None:
        logs = [
            {
                "role": "citizen_learning",
                "agent_id": "citizen-001",
                "final": {"ok": True, "payload": {"response": "summary only"}},
                "attempts": [{"api_calls": 4}],
            },
            {
                "role": "citizen_learning",
                "agent_id": "citizen-002",
                "final": {"ok": True, "payload": {"response": "clean"}},
                "attempts": [{"api_calls": 2}],
            },
        ]

        self.assertEqual(completed_learning_agents(logs), {"citizen-002"})

    def test_planned_agents_skip_completed_and_manual_skip(self) -> None:
        packet = _packet()
        logs = [
            {
                "role": "citizen_learning",
                "agent_id": "citizen-001",
                "final": {"ok": True, "payload": {"completed": True, "partial": False, "error": None}},
            },
            {"role": "mayor", "agent_id": "mayor", "behavior": "optimizer"},
        ]

        planned = planned_learning_agents(packet, logs, skip={"citizen-003"})

        self.assertEqual(
            [(agent.role, agent.agent_id, agent.behavior) for agent in planned],
            [("citizen", "citizen-002", "cautious"), ("mayor", "mayor", "optimizer")],
        )

    def test_include_existing_reruns_completed_but_not_manual_skip(self) -> None:
        packet = _packet()
        logs = [
            {
                "role": "citizen_learning",
                "agent_id": "citizen-001",
                "final": {"ok": True, "payload": {"completed": True, "partial": False, "error": None}},
            },
            {
                "role": "mayor_learning",
                "agent_id": "mayor",
                "final": {"ok": True, "payload": {"completed": True, "partial": False, "error": None}},
            },
            {"role": "mayor", "agent_id": "mayor", "behavior": "optimizer"},
        ]

        planned = planned_learning_agents(
            packet,
            logs,
            skip={"citizen-002"},
            include_existing=True,
        )

        self.assertEqual(
            [(agent.role, agent.agent_id, agent.behavior) for agent in planned],
            [
                ("citizen", "citizen-001", "aggressive"),
                ("citizen", "citizen-003", "opportunistic"),
                ("mayor", "mayor", "optimizer"),
            ],
        )


def _packet() -> dict:
    return {
        "citizen_snapshots": [
            {"citizen_id": "citizen-001", "behavior": "aggressive"},
            {"citizen_id": "citizen-002", "behavior": "cautious"},
            {"citizen_id": "citizen-003", "behavior": "opportunistic"},
        ]
    }


if __name__ == "__main__":
    unittest.main()
