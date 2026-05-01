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


def _settings() -> Settings:
    return Settings(
        llm_provider="openrouter",
        ollama_base_url="http://localhost:11434",
        openrouter_base_url="https://openrouter.ai/api/v1",
        openrouter_api_key="test-key",
        openrouter_reasoning_effort="none",
        llm_temperature=0.2,
        llm_max_tokens=2048,
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
                return {
                    "final_response": "learned",
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

        def fake_refresh() -> tuple[object, object]:
            seen["refresh_home"] = os.environ.get("HERMES_HOME")
            return object(), object()

        with tempfile.TemporaryDirectory() as tmp, patch.object(hermes_runner, "AIAgent", FakeAIAgent), patch.object(hermes_runner, "refresh_hermes_skill_modules", fake_refresh):
            old_home = os.environ.get("HERMES_HOME")
            os.environ["HERMES_HOME"] = "outside-home"
            try:
                runner = HermesAgentRunner(_settings(), profiles_root=Path(tmp))
                result = runner.learn_citizen_from_game(
                    "citizen-001",
                    "stealth_first",
                    {"kind": "citizen_learning_evidence", "agent_id": "citizen-001"},
                    "game-1",
                )
            finally:
                if old_home is not None:
                    os.environ["HERMES_HOME"] = old_home
                else:
                    os.environ.pop("HERMES_HOME", None)

        expected_home = str((Path(tmp) / "citizen-001").resolve())
        self.assertEqual(seen["init_home"], expected_home)
        self.assertEqual(seen["refresh_home"], expected_home)
        self.assertEqual(seen["run_home"], expected_home)
        self.assertEqual(seen["shutdown_home"], expected_home)
        self.assertEqual(os.environ.get("HERMES_HOME"), old_home)
        self.assertTrue(result["ok"])
        self.assertEqual(seen["kwargs"]["enabled_toolsets"], ["memory", "skills"])
        self.assertEqual(seen["kwargs"]["max_iterations"], 4)
        self.assertFalse(seen["kwargs"]["skip_memory"])
        self.assertIn('skill_view(name="optimicity-citizen-playbook")', seen["prompt"])
        self.assertIn('skill_manage(action="patch"', seen["prompt"])
        self.assertIn("Only call skills_list() if the named playbook fails to load.", seen["prompt"])
        self.assertIn("GHOSTED is a stealth benefit granted after a successful SNIFF.", seen["prompt"])
        self.assertIn(
            "CURFEW is city pressure, not a citizen status effect. Do not learn or write that CURFEW alone directly changes personal catch probability",
            seen["prompt"],
        )


if __name__ == "__main__":
    unittest.main()
