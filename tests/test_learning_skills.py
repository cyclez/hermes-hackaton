from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.agents.learning_skills import (
    CITIZEN_PLAYBOOK_NAME,
    MAYOR_PLAYBOOK_NAME,
    ensure_citizen_playbook_skill,
    ensure_mayor_playbook_skill,
)


class LearningSkillTests(unittest.TestCase):
    def test_bootstrap_creates_role_specific_valid_skill_without_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp)

            citizen_path = ensure_citizen_playbook_skill(profile)
            mayor_path = ensure_mayor_playbook_skill(profile)

            self.assertEqual(citizen_path, profile / "skills" / CITIZEN_PLAYBOOK_NAME / "SKILL.md")
            self.assertEqual(mayor_path, profile / "skills" / MAYOR_PLAYBOOK_NAME / "SKILL.md")
            citizen_text = citizen_path.read_text(encoding="utf-8")
            self.assertTrue(citizen_text.startswith("---\nname: optimicity-citizen-playbook"))
            for section in (
                "## Role",
                "## Current Strategy",
                "## Action Rules",
                "## Resource Rules",
                "## Status Rules",
                "## Known Pitfalls",
                "## Evidence Standard",
            ):
                self.assertIn(section, citizen_text)

            citizen_path.write_text(citizen_text + "\n## Learned Addition\nKeep this.\n", encoding="utf-8")
            ensure_citizen_playbook_skill(profile)
            self.assertIn("## Learned Addition", citizen_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
