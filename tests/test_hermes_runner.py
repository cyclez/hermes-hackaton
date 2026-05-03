from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agents import hermes_runner
from src.agents.hermes_runner import HermesAgentRunner
from src.agents.profiles import ensure_citizen_profile
from src.server.config import Settings
from src.server.models import CitizenAction, DecisionKind


def _settings() -> Settings:
    return Settings(
        llm_provider="openrouter",
        ollama_base_url="http://localhost:11434",
        openrouter_base_url="https://openrouter.ai/api/v1",
        openrouter_api_key="test-key",
        openrouter_reasoning_effort="none",
        llm_temperature=0.2,
        llm_max_tokens=2048,
        learning_max_tokens=1024,
        learning_max_iterations=6,
        enable_postgame_training=True,
        citizens_model="moonshotai/kimi-k2-0905",
        mayor_model="moonshotai/kimi-k2.6",
        citizen_count=5,
        citizen_worker_count=5,
        max_concurrent_llm_calls=5,
        run_target="local",
        worker_ssh_target="root@127.0.0.1",
        season_seconds=600,
        mayor_tick_seconds=10,
        server_tick_seconds=1.0,
        min_decision_interval=10.0,
        database_url="postgresql://test",
        database_url_unpooled="postgresql://test",
    )


class HermesRunnerUsageTests(unittest.TestCase):
    def test_usage_delta_keeps_last_prompt_tokens_raw(self) -> None:
        runner = HermesAgentRunner(_settings())

        first = runner._usage_delta("citizen-001", {
            "input_tokens": 100,
            "output_tokens": 20,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "reasoning_tokens": 0,
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "total_tokens": 120,
            "estimated_cost_usd": 0.001,
            "last_prompt_tokens": 100,
        })
        second = runner._usage_delta("citizen-001", {
            "input_tokens": 250,
            "output_tokens": 35,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "reasoning_tokens": 0,
            "prompt_tokens": 250,
            "completion_tokens": 35,
            "total_tokens": 285,
            "estimated_cost_usd": 0.0025,
            "last_prompt_tokens": 90,
        })

        self.assertEqual(first["last_prompt_tokens"], 100.0)
        self.assertEqual(second["input_tokens"], 150.0)
        self.assertEqual(second["total_tokens"], 165.0)
        self.assertEqual(second["last_prompt_tokens"], 90.0)

    def test_gameplay_agent_reads_memory_without_exposing_memory_or_skills_tools(self) -> None:
        calls = []
        normalized_memory = ""

        class FakeAIAgent:
            def __init__(self, **kwargs):
                calls.append(kwargs)

        with tempfile.TemporaryDirectory() as tmp, patch.object(hermes_runner, "AIAgent", FakeAIAgent):
            runner = HermesAgentRunner(_settings(), profiles_root=Path(tmp))
            profile_dir = ensure_citizen_profile("citizen-001", "aggressive", root=Path(tmp))
            playbook = profile_dir / "skills" / "optimicity-citizen-playbook" / "SKILL.md"
            playbook.write_text(
                playbook.read_text(encoding="utf-8") + "\n## Learned Addition\nPrefer DECOY_SIGNAL before SNIFF when SURVEILLED.\n",
                encoding="utf-8",
            )
            memory_path = profile_dir / "memories" / "MEMORY.md"
            memory_path.write_text(
                "GHOSTED is highly dangerous and increases risk on its own.\n",
                encoding="utf-8",
            )
            runner._get_citizen_agent("citizen-001", "aggressive")
            normalized_memory = memory_path.read_text(encoding="utf-8")

        self.assertEqual(len(calls), 1)
        kwargs = calls[0]
        self.assertFalse(kwargs["skip_memory"])
        self.assertEqual(kwargs["enabled_toolsets"], ["_game_output_only_"])
        self.assertIn("memory", kwargs["disabled_toolsets"])
        self.assertIn("skills", kwargs["disabled_toolsets"])
        self.assertIn("## Learned Playbook", kwargs["ephemeral_system_prompt"])
        self.assertIn("## Learned Addition", kwargs["ephemeral_system_prompt"])
        self.assertNotIn("name: optimicity-citizen-playbook", kwargs["ephemeral_system_prompt"])
        self.assertIn("GHOSTED follows successful SNIFF and is a stealth-oriented status", normalized_memory)

    def test_learning_turn_keeps_profile_home_active_during_conversation(self) -> None:
        seen = {}

        class FakeAIAgent:
            def __init__(self, **kwargs):
                seen["init_home"] = os.environ.get("HERMES_HOME")
                seen["kwargs"] = kwargs

            def run_conversation(self, user_message: str, conversation_history=None):
                seen["run_home"] = os.environ.get("HERMES_HOME")
                seen["prompt"] = user_message
                profile_dir = Path(seen["run_home"])
                skill_path = profile_dir / "skills" / "optimicity-citizen-playbook" / "SKILL.md"
                skill_path.write_text(
                    skill_path.read_text(encoding="utf-8").replace(
                        "## Learned Patterns\n- None yet.\n",
                        "## Learned Patterns\n- Prefer `COVER_TRACKS` when `SURVEILLED` and trace is already elevated.\n",
                    ),
                    encoding="utf-8",
                )
                memory_path = profile_dir / "memories" / "MEMORY.md"
                memory_path.parent.mkdir(parents=True, exist_ok=True)
                memory_path.write_text(
                    "Prefer `COVER_TRACKS` when `SURVEILLED` and trace is already elevated.\n",
                    encoding="utf-8",
                )
                return {
                    "final_response": (
                        '{"decision":"applied","selected_patterns":['
                        '"Prefer `COVER_TRACKS` when `SURVEILLED` and trace is already elevated."'
                        '],"memory_note":"Prefer `COVER_TRACKS` when `SURVEILLED` and trace is already elevated.","notes":"durable recovery pattern"}'
                    ),
                    "completed": True,
                    "partial": False,
                    "messages": [{"role": "assistant", "content": "learned"}],
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cache_read_tokens": 0,
                    "cache_write_tokens": 0,
                    "reasoning_tokens": 0,
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                    "estimated_cost_usd": 0,
                    "last_prompt_tokens": 10,
                    "api_calls": 1,
                }

            def shutdown_memory_provider(self, messages=None):
                seen["shutdown_home"] = os.environ.get("HERMES_HOME")

        with tempfile.TemporaryDirectory() as tmp, patch.object(hermes_runner, "AIAgent", FakeAIAgent), patch.object(hermes_runner, "refresh_hermes_skill_modules", lambda: (None, None)):
            old_home = os.environ.get("HERMES_HOME")
            os.environ["HERMES_HOME"] = "outside-home"
            try:
                runner = HermesAgentRunner(_settings(), profiles_root=Path(tmp))
                result = runner.learn_citizen_from_game(
                    "citizen-001",
                    "stealth_first",
                    {
                        "kind": "citizen_learning_evidence",
                        "agent_id": "citizen-001",
                        "candidate_lessons": [
                            {
                                "pattern": "Prefer `COVER_TRACKS` when `SURVEILLED` and trace is already elevated.",
                                "support": "2 uncaught `COVER_TRACKS` actions in this game.",
                            }
                        ],
                    },
                    "game-1",
                )
            finally:
                if old_home is not None:
                    os.environ["HERMES_HOME"] = old_home
                else:
                    os.environ.pop("HERMES_HOME", None)

        expected_home = str((Path(tmp) / "citizen-001").resolve())
        self.assertEqual(seen["init_home"], expected_home)
        self.assertEqual(seen["run_home"], expected_home)
        self.assertEqual(seen["shutdown_home"], expected_home)
        self.assertEqual(os.environ.get("HERMES_HOME"), old_home)
        self.assertTrue(result["ok"])
        self.assertTrue(result["completed"])
        self.assertFalse(result["partial"])
        self.assertEqual(seen["kwargs"]["enabled_toolsets"], ["memory", "skills"])
        self.assertEqual(seen["kwargs"]["max_iterations"], 6)
        self.assertFalse(seen["kwargs"]["skip_memory"])
        self.assertEqual(result["decision"], "applied")
        self.assertTrue(result["skill_update"]["changed"])
        self.assertTrue(result["memory_update"]["changed"])
        self.assertIn("Current learned patterns block", seen["prompt"])
        self.assertIn("Candidate lessons:", seen["prompt"])
        self.assertIn("skill_manage(action=\"patch\"", seen["prompt"])
        self.assertIn("memory(action=\"add\", target=\"memory\"", seen["prompt"])
        self.assertIn(
            "CURFEW is city pressure, not a citizen status effect. Do not learn or write that CURFEW alone directly changes personal catch probability or blocks actions.",
            seen["prompt"],
        )

    def test_mayor_learning_turn_mentions_updated_pressure_semantics(self) -> None:
        seen = {}

        class FakeAIAgent:
            def __init__(self, **kwargs):
                seen["init_home"] = os.environ.get("HERMES_HOME")
                seen["kwargs"] = kwargs

            def run_conversation(self, user_message: str, conversation_history=None):
                seen["run_home"] = os.environ.get("HERMES_HOME")
                seen["prompt"] = user_message
                profile_dir = Path(seen["run_home"])
                skill_path = profile_dir / "skills" / "optimicity-mayor-playbook" / "SKILL.md"
                skill_path.write_text(
                    skill_path.read_text(encoding="utf-8").replace(
                        "## Learned Patterns\n- None yet.\n",
                        "## Learned Patterns\n- Pivot from repeated `SURVEIL` to `MOST_WANTED` or `JAIL` when the same visible target keeps acting through pressure.\n",
                    ),
                    encoding="utf-8",
                )
                return {
                    "final_response": (
                        '{"decision":"applied","selected_patterns":['
                        '"Pivot from repeated `SURVEIL` to `MOST_WANTED` or `JAIL` when the same visible target keeps acting through pressure."'
                        '],"memory_note":null,"notes":"durable escalation rule"}'
                    ),
                    "completed": True,
                    "partial": False,
                    "messages": [{"role": "assistant", "content": "learned"}],
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cache_read_tokens": 0,
                    "cache_write_tokens": 0,
                    "reasoning_tokens": 0,
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                    "estimated_cost_usd": 0,
                    "last_prompt_tokens": 10,
                    "api_calls": 1,
                }

            def shutdown_memory_provider(self, messages=None):
                seen["shutdown_home"] = os.environ.get("HERMES_HOME")

        with tempfile.TemporaryDirectory() as tmp, patch.object(hermes_runner, "AIAgent", FakeAIAgent), patch.object(hermes_runner, "refresh_hermes_skill_modules", lambda: (None, None)):
            old_home = os.environ.get("HERMES_HOME")
            os.environ["HERMES_HOME"] = "outside-home"
            try:
                runner = HermesAgentRunner(_settings(), profiles_root=Path(tmp))
                result = runner.learn_mayor_from_game(
                    "optimizer",
                    {
                        "kind": "mayor_learning_evidence",
                        "agent_id": "mayor",
                        "candidate_lessons": [
                            {
                                "pattern": "Pivot from repeated `SURVEIL` to `MOST_WANTED` or `JAIL` when the same visible target keeps acting through pressure.",
                                "support": "`MOST_WANTED` applied 3 times in this game.",
                            }
                        ],
                    },
                    "game-2",
                )
            finally:
                if old_home is not None:
                    os.environ["HERMES_HOME"] = old_home
                else:
                    os.environ.pop("HERMES_HOME", None)

        expected_home = str((Path(tmp) / "mayor").resolve())
        self.assertEqual(seen["init_home"], expected_home)
        self.assertEqual(seen["run_home"], expected_home)
        self.assertEqual(seen["shutdown_home"], expected_home)
        self.assertEqual(os.environ.get("HERMES_HOME"), old_home)
        self.assertTrue(result["ok"])
        self.assertTrue(result["completed"])
        self.assertFalse(result["partial"])
        self.assertEqual(seen["kwargs"]["enabled_toolsets"], ["memory", "skills"])
        self.assertFalse(seen["kwargs"]["skip_memory"])
        self.assertEqual(result["decision"], "applied")
        self.assertTrue(result["skill_update"]["changed"])
        self.assertIn("MOST_WANTED applies a distinct stronger targeting state: MOST_WANTED and removes SURVEILLED.", seen["prompt"])
        self.assertIn("MOST_WANTED also adds passive trace pressure over time, so SYNC alone will not safely bleed trace while it is active.", seen["prompt"])
        self.assertIn("STK_DRAIN removes 500 STK from targets immediately and adds trace at once.", seen["prompt"])

    def test_learning_turn_marks_max_iteration_summary_incomplete(self) -> None:
        seen = {}

        class FakeAIAgent:
            def __init__(self, **kwargs):
                seen["kwargs"] = kwargs

            def run_conversation(self, user_message: str, conversation_history=None):
                return {
                    "final_response": "summary after budget exhaustion",
                    "completed": False,
                    "partial": False,
                    "messages": [{"role": "assistant", "content": "summary after budget exhaustion"}],
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cache_read_tokens": 0,
                    "cache_write_tokens": 0,
                    "reasoning_tokens": 0,
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                    "estimated_cost_usd": 0,
                    "last_prompt_tokens": 10,
                    "api_calls": 4,
                }

            def shutdown_memory_provider(self, messages=None):
                pass

        with tempfile.TemporaryDirectory() as tmp, patch.object(hermes_runner, "AIAgent", FakeAIAgent):
            runner = HermesAgentRunner(_settings(), profiles_root=Path(tmp))
            game_id = f"game-incomplete-{Path(tmp).name}"
            result = runner.learn_citizen_from_game(
                "citizen-001",
                "aggressive",
                {"kind": "citizen_learning_evidence", "agent_id": "citizen-001"},
                game_id,
            )

            entries = runner.log_store.read_entries(game_id, limit=0)

        self.assertFalse(result["ok"])
        self.assertFalse(result["completed"])
        self.assertTrue(result["partial"])
        self.assertEqual(len(entries), 1)
        self.assertFalse(entries[0]["final"]["ok"])
        self.assertFalse(entries[0]["final"]["payload"]["completed"])
        self.assertTrue(entries[0]["final"]["payload"]["partial"])

    def test_learning_turn_tolerates_unparseable_final_summary(self) -> None:
        class FakeAIAgent:
            def __init__(self, **kwargs):
                pass

            def run_conversation(self, user_message: str, conversation_history=None):
                profile_dir = Path(os.environ["HERMES_HOME"])
                skill_path = profile_dir / "skills" / "optimicity-citizen-playbook" / "SKILL.md"
                skill_path.write_text(
                    skill_path.read_text(encoding="utf-8").replace(
                        "## Learned Patterns\n- None yet.\n",
                        "## Learned Patterns\n- When trace is already high, recover before forcing a second exposed action.\n",
                    ),
                    encoding="utf-8",
                )
                return {
                    "final_response": "done",
                    "completed": True,
                    "partial": False,
                    "messages": [{"role": "assistant", "content": "bad plan"}],
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cache_read_tokens": 0,
                    "cache_write_tokens": 0,
                    "reasoning_tokens": 0,
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                    "estimated_cost_usd": 0,
                    "last_prompt_tokens": 10,
                    "api_calls": 1,
                }

            def shutdown_memory_provider(self, messages=None):
                pass

        with tempfile.TemporaryDirectory() as tmp, patch.object(hermes_runner, "AIAgent", FakeAIAgent), patch.object(hermes_runner, "refresh_hermes_skill_modules", lambda: (None, None)):
            runner = HermesAgentRunner(_settings(), profiles_root=Path(tmp))
            result = runner.learn_citizen_from_game(
                "citizen-001",
                "aggressive",
                {
                    "kind": "citizen_learning_evidence",
                    "agent_id": "citizen-001",
                    "candidate_lessons": [
                        {
                            "pattern": "When trace is already high, recover before forcing a second exposed action.",
                            "support": "2 uncaught `COVER_TRACKS` actions in this game.",
                        }
                    ],
                },
                "game-invalid-plan",
            )

        self.assertTrue(result["ok"])
        self.assertTrue(result["completed"])
        self.assertFalse(result["partial"])
        self.assertEqual(result["decision"], "applied")
        self.assertIsNone(result["learning_summary"])

    def test_learning_turn_strips_tool_writes_outside_curated_candidates(self) -> None:
        class FakeAIAgent:
            def __init__(self, **kwargs):
                pass

            def run_conversation(self, user_message: str, conversation_history=None):
                profile_dir = Path(os.environ["HERMES_HOME"])
                skill_path = profile_dir / "skills" / "optimicity-citizen-playbook" / "SKILL.md"
                skill_path.write_text(
                    skill_path.read_text(encoding="utf-8").replace(
                        "## Learned Patterns\n- None yet.\n",
                        "## Learned Patterns\n- Always hunt citizen-001 after every game.\n",
                    ),
                    encoding="utf-8",
                )
                memory_path = profile_dir / "memories" / "MEMORY.md"
                memory_path.parent.mkdir(parents=True, exist_ok=True)
                memory_path.write_text("Always hunt citizen-001 after every game.\n", encoding="utf-8")
                return {
                    "final_response": '{"decision":"applied","selected_patterns":["Always hunt citizen-001 after every game."],"memory_note":"Always hunt citizen-001 after every game.","notes":"bad write"}',
                    "completed": True,
                    "partial": False,
                    "messages": [{"role": "assistant", "content": "bad write"}],
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cache_read_tokens": 0,
                    "cache_write_tokens": 0,
                    "reasoning_tokens": 0,
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                    "estimated_cost_usd": 0,
                    "last_prompt_tokens": 10,
                    "api_calls": 1,
                }

            def shutdown_memory_provider(self, messages=None):
                pass

        with tempfile.TemporaryDirectory() as tmp, patch.object(hermes_runner, "AIAgent", FakeAIAgent), patch.object(hermes_runner, "refresh_hermes_skill_modules", lambda: (None, None)):
            runner = HermesAgentRunner(_settings(), profiles_root=Path(tmp))
            result = runner.learn_citizen_from_game(
                "citizen-001",
                "aggressive",
                {
                    "kind": "citizen_learning_evidence",
                    "agent_id": "citizen-001",
                    "candidate_lessons": [
                        {
                            "pattern": "When trace is already high, recover before forcing a second exposed action.",
                            "support": "2 uncaught `COVER_TRACKS` actions in this game.",
                        }
                    ],
                },
                "game-strip-bad-write",
            )

            profile_dir = Path(tmp) / "citizen-001"
            skill_text = (profile_dir / "skills" / "optimicity-citizen-playbook" / "SKILL.md").read_text(encoding="utf-8")
            memory_text = (profile_dir / "memories" / "MEMORY.md").read_text(encoding="utf-8")

        self.assertTrue(result["ok"])
        self.assertEqual(result["decision"], "no_change")
        self.assertFalse(result["skill_update"]["changed"])
        self.assertFalse(result["memory_update"]["changed"])
        self.assertNotIn("Always hunt citizen-001 after every game.", skill_text)
        self.assertNotIn("Always hunt citizen-001 after every game.", memory_text)

    def test_decide_citizen_repairs_unaffordable_action_before_engine_apply(self) -> None:
        prompts: list[str] = []

        class FakeAIAgent:
            def __init__(self, **kwargs):
                pass

            def run_conversation(self, user_message: str, conversation_history=None):
                prompts.append(user_message)
                if len(prompts) == 1:
                    response = (
                        '{"kind":"ACTION","action":"SNIFF","mode":null,'
                        '"rationale":"take the stronger action"}'
                    )
                else:
                    response = (
                        '{"kind":"ACTION","action":"COVER_TRACKS","mode":null,'
                        '"rationale":"only affordable action"}'
                    )
                return {
                    "final_response": response,
                    "messages": [{"role": "assistant", "content": response}],
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cache_read_tokens": 0,
                    "cache_write_tokens": 0,
                    "reasoning_tokens": 0,
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                    "estimated_cost_usd": 0,
                    "last_prompt_tokens": 10,
                    "api_calls": 1,
                }

        observation = {
            "citizen_id": "citizen-001",
            "game_hour": 10.0,
            "global": {"heat": 50.0, "season_seconds_remaining": 500.0},
            "private": {
                "mode": "SYNC",
                "queued_mode": None,
                "statuses": [],
                "stk": 150,
                "shiva": 50.0,
                "trace": 20.0,
                "action_cooldown_remaining": 0.0,
            },
            "allowed_actions": ["SNIFF", "JAM_SCAN", "DECOY_SIGNAL", "COVER_TRACKS"],
            "affordable_actions": ["COVER_TRACKS"],
            "allowed_modes": ["MINE", "SYNC", "SLEEP"],
            "action_tradeoffs": [],
            "selection_hint": "Factual observation only.",
        }

        with tempfile.TemporaryDirectory() as tmp, patch.object(hermes_runner, "AIAgent", FakeAIAgent):
            runner = HermesAgentRunner(_settings(), profiles_root=Path(tmp))
            decision = runner.decide_citizen("citizen-001", observation, "aggressive", "game-1")

        self.assertEqual(decision.kind, DecisionKind.ACTION)
        self.assertEqual(decision.action, CitizenAction.COVER_TRACKS)
        self.assertEqual(len(prompts), 2)
        self.assertIn("not in affordable_actions ['COVER_TRACKS']", prompts[1])

    def test_decide_mayor_uses_context_snapshot_in_live_prompt(self) -> None:
        prompts: list[str] = []

        class FakeAIAgent:
            def __init__(self, **kwargs):
                pass

            def run_conversation(self, user_message: str, conversation_history=None):
                prompts.append(user_message)
                response = (
                    '{"action":"SURVEIL","targets":["citizen-001"],'
                    '"duration_seconds":30,"rationale":"watch target"}'
                )
                return {
                    "final_response": response,
                    "messages": [{"role": "assistant", "content": response}],
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cache_read_tokens": 0,
                    "cache_write_tokens": 0,
                    "reasoning_tokens": 0,
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                    "estimated_cost_usd": 0,
                    "last_prompt_tokens": 10,
                    "api_calls": 1,
                }

        dossier = {
            "heat": 50.0,
            "game_hour": 10.0,
            "recent_actions": [],
            "recent_evidence": [],
            "active_citizens": ["citizen-001"],
        }
        context_snapshot = {
            "kind": "mayor_context",
            "heat": 50.0,
            "game_hour": 10.0,
            "recent_actions": [],
            "recent_evidence": [],
            "active_citizens": ["citizen-001"],
            "citizen_snapshots": [{
                "citizen_id": "citizen-001",
                "behavior": "aggressive",
                "mode": "SYNC",
                "queued_mode": None,
                "statuses": ["PROTECTED"],
                "stk": 900,
                "shiva": 80.0,
                "trace": 12.0,
                "action_cooldown_remaining": 0.0,
            }],
        }

        with tempfile.TemporaryDirectory() as tmp, patch.object(hermes_runner, "AIAgent", FakeAIAgent):
            runner = HermesAgentRunner(_settings(), profiles_root=Path(tmp))
            decree = runner.decide_mayor(
                dossier,
                {"citizen-001"},
                "optimizer",
                "game-1",
                context_snapshot,
            )

        self.assertEqual(decree.targets, ["citizen-001"])
        self.assertEqual(len(prompts), 1)
        self.assertIn('"citizen_snapshots"', prompts[0])
        self.assertIn('"statuses": ["PROTECTED"]', prompts[0])


if __name__ == "__main__":
    unittest.main()
