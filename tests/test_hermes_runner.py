from __future__ import annotations

import unittest

from src.agents.hermes_runner import HermesAgentRunner
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


if __name__ == "__main__":
    unittest.main()
