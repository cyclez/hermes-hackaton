from __future__ import annotations

import unittest

from src.server.config import Settings


class SettingsTests(unittest.TestCase):
    def test_loads_existing_env_example_values(self) -> None:
        settings = Settings.load(".env.example")

        self.assertEqual(settings.llm_provider, "openrouter")
        self.assertEqual(settings.citizens_model, "deepseek/deepseek-v3.2")
        self.assertEqual(settings.mayor_model, "moonshotai/kimi-k2.6")
        self.assertEqual(settings.llm_max_tokens, 2048)
        self.assertEqual(settings.openrouter_reasoning_effort, "none")
        self.assertEqual(settings.citizen_count, 10)
        self.assertEqual(settings.citizen_worker_count, 10)
        self.assertEqual(settings.season_seconds, 600)


if __name__ == "__main__":
    unittest.main()
