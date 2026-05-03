from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agents.learning_skills import (
    CITIZEN_PLAYBOOK_NAME,
    LEARNED_PATTERNS_SECTION,
    LEARNED_PATTERNS_MAX_LINES,
    MAYOR_PLAYBOOK_NAME,
    apply_citizen_learning_patterns,
    ensure_citizen_playbook_skill,
    ensure_mayor_playbook_skill,
    load_citizen_learning_context,
    normalize_citizen_profile_artifacts,
    refresh_hermes_skill_modules,
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
                "## Learned Patterns",
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
            mayor_text = mayor_path.read_text(encoding="utf-8")
            self.assertIn("Use `SURVEIL` as a first-contact pressure tool on clean targets", mayor_text)
            self.assertIn("High `SHIVA` lowers citizen catch risk", mayor_text)

    def test_apply_learning_patterns_updates_bounded_skill_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp)
            ensure_citizen_playbook_skill(profile)

            with patch.dict("os.environ", {"HERMES_HOME": str(profile)}, clear=False):
                first = apply_citizen_learning_patterns(profile, [
                    "Prefer `COVER_TRACKS` when `SURVEILLED` and trace is already elevated.",
                    "Use `SYNC` recovery before another expensive action when SHIVA is low and exposure is rising.",
                ])
                second = apply_citizen_learning_patterns(profile, [
                    f"Pattern {idx}: keep the rule compact and durable."
                    for idx in range(1, LEARNED_PATTERNS_MAX_LINES + 4)
                ])

            skill_text = (profile / "skills" / CITIZEN_PLAYBOOK_NAME / "SKILL.md").read_text(encoding="utf-8")
            context = load_citizen_learning_context(profile)
            section = context.split(f"## {LEARNED_PATTERNS_SECTION}\n", 1)[1]
            lines = [line.strip() for line in section.splitlines() if line.strip().startswith("- ")]

            self.assertTrue(first["changed"])
            self.assertTrue(second["changed"])
            self.assertLessEqual(len(lines), LEARNED_PATTERNS_MAX_LINES)
            self.assertIn("Pattern 1", skill_text)
            self.assertNotIn("Pattern 9", skill_text)
            self.assertNotIn("- None yet.", section)

    def test_apply_learning_patterns_rejects_game_specific_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp)
            ensure_citizen_playbook_skill(profile)

            with patch.dict("os.environ", {"HERMES_HOME": str(profile)}, clear=False):
                with self.assertRaisesRegex(ValueError, "must stay generic"):
                    apply_citizen_learning_patterns(profile, ["Always hunt citizen-001 after game-123."])

    def test_refresh_exposes_profile_local_skill_to_hermes_tools_and_allows_patch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp)
            citizen_path = ensure_citizen_playbook_skill(profile)

            with patch.dict("os.environ", {"HERMES_HOME": str(profile)}, clear=False):
                skills_tool, skill_manager_tool = refresh_hermes_skill_modules()

                viewed = json.loads(skills_tool.skill_view(CITIZEN_PLAYBOOK_NAME))
                self.assertTrue(viewed["success"])
                self.assertIn("OptimiCity Citizen Playbook", viewed["content"])

                patched = json.loads(skill_manager_tool.skill_manage(
                    action="patch",
                    name=CITIZEN_PLAYBOOK_NAME,
                    old_string="## Known Pitfalls",
                    new_string="## Known Pitfalls\n- Prefer patch-based updates when a durable tactic changes.",
                ))
                self.assertTrue(patched["success"], patched)

            updated = citizen_path.read_text(encoding="utf-8")
            self.assertIn("Prefer patch-based updates", updated)

    def test_refresh_switches_skill_resolution_with_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile_a = root / "a"
            profile_b = root / "b"
            path_a = ensure_citizen_playbook_skill(profile_a)
            path_b = ensure_citizen_playbook_skill(profile_b)
            path_a.write_text(path_a.read_text(encoding="utf-8") + "\n## Marker\nA only.\n", encoding="utf-8")
            path_b.write_text(path_b.read_text(encoding="utf-8") + "\n## Marker\nB only.\n", encoding="utf-8")

            with patch.dict("os.environ", {"HERMES_HOME": str(profile_a)}, clear=False):
                skills_tool, _ = refresh_hermes_skill_modules()
                viewed_a = json.loads(skills_tool.skill_view(CITIZEN_PLAYBOOK_NAME))

            with patch.dict("os.environ", {"HERMES_HOME": str(profile_b)}, clear=False):
                skills_tool, _ = refresh_hermes_skill_modules()
                viewed_b = json.loads(skills_tool.skill_view(CITIZEN_PLAYBOOK_NAME))

            self.assertIn("A only.", viewed_a["content"])
            self.assertNotIn("B only.", viewed_a["content"])
            self.assertIn("B only.", viewed_b["content"])
            self.assertNotIn("A only.", viewed_b["content"])

    def test_mayor_playbook_normalization_adds_current_pressure_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp)
            skill_path = ensure_mayor_playbook_skill(profile)
            text = skill_path.read_text(encoding="utf-8")
            self.assertIn("Use `SURVEIL` as a first-contact pressure tool on clean targets", text)
            self.assertIn("Use `STK_DRAIN` on high-STK citizens", text)
            self.assertIn("High `SHIVA` lowers citizen catch risk", text)

    def test_normalization_rewrites_false_citizen_playbook_mechanics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp)
            skill_path = ensure_citizen_playbook_skill(profile)
            mutated = skill_path.read_text(encoding="utf-8")
            mutated = mutated.replace(
                "- `GHOSTED`: follows successful `SNIFF` and provides stealth benefit; do not treat it as a danger signal by itself.\n",
                "- `GHOSTED`: highly dangerous and overrides action-specific risk.\n",
            )
            mutated = mutated.replace(
                "- `CURFEW`: city pressure only in the current build. It is not a citizen status and does not directly change your catch probability.\n",
                "- `CURFEW`: directly elevates personal catch probability and blocks action quality.\n",
            )
            mutated = mutated.replace(
                "- `PROTECTED`: follows successful `DECOY_SIGNAL` and helps the next non-`DECOY_SIGNAL` action resist surveillance targeting.\n",
                "- `PROTECTED`: helps the next action generally and cancels all targeting pressure.\n",
            )
            mutated = mutated.replace(
                "## Learned Patterns\n- None yet.\n",
                "## Learned Patterns\n- Jailed citizens get a status-free reset but cannot act during jail period; treat JAILED as a full action block and assume trace, SHIVA, and statuses may be reset.\n",
            )
            skill_path.write_text(
                mutated,
                encoding="utf-8",
            )

            normalize_citizen_profile_artifacts(profile)
            normalized = skill_path.read_text(encoding="utf-8")

            self.assertIn("GHOSTED`: follows successful `SNIFF` and provides stealth benefit", normalized)
            self.assertIn("`CURFEW`: city pressure only in the current build", normalized)
            self.assertIn("`PROTECTED`: follows successful `DECOY_SIGNAL`, clears `SURVEILLED`, and blocks fresh `SURVEIL` application", normalized)
            self.assertIn("`JAILED` is a full action and mode-change block until release", normalized)
            self.assertNotIn("highly dangerous and overrides action-specific risk", normalized)
            self.assertNotIn("directly elevates personal catch probability", normalized)
            self.assertNotIn("helps the next action generally", normalized)
            self.assertNotIn("status-free reset", normalized)

    def test_normalization_rewrites_false_citizen_memory_mechanics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp)
            ensure_citizen_playbook_skill(profile)
            memories_dir = profile / "memories"
            memories_dir.mkdir(parents=True, exist_ok=True)
            memory_path = memories_dir / "MEMORY.md"
            memory_path.write_text(
                "GHOSTED is highly dangerous and increases risk on its own.\n"
                "§\n"
                "CURFEW is basically a catch-probability status like SURVEILLED.\n"
                "§\n"
                "PROTECTED helps the next action as a general catch-probability bonus.\n"
                "§\n"
                "JAILED is basically a general reset of trace and SHIVA.\n"
                "§\n"
                "Keep DECOY_SIGNAL available when SHIVA is low.\n",
                encoding="utf-8",
            )

            normalize_citizen_profile_artifacts(profile)
            normalized = memory_path.read_text(encoding="utf-8")

            self.assertIn("GHOSTED follows successful SNIFF and is a stealth-oriented status", normalized)
            self.assertIn("CURFEW often coincides with late high-Heat mayor pressure", normalized)
            self.assertIn("PROTECTED from a successful DECOY_SIGNAL is a short anti-SURVEIL window", normalized)
            self.assertIn("JAILED is a full action and mode-change block until release.", normalized)
            self.assertIn("Keep DECOY_SIGNAL available when SHIVA is low.", normalized)
            self.assertNotIn("GHOSTED is highly dangerous", normalized)
            self.assertNotIn("CURFEW is basically a catch-probability status", normalized)
            self.assertNotIn("PROTECTED helps the next action as a general catch-probability bonus.", normalized)
            self.assertNotIn("general reset of trace and SHIVA", normalized)

    def test_apply_learning_patterns_rejects_false_jailed_reset_lesson(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp)
            ensure_citizen_playbook_skill(profile)

            with patch.dict("os.environ", {"HERMES_HOME": str(profile)}, clear=False):
                with self.assertRaisesRegex(ValueError, "contradicts JAILED mechanics"):
                    apply_citizen_learning_patterns(
                        profile,
                        ["JAILED is a general reset of trace and SHIVA before you restart play."],
                    )


if __name__ == "__main__":
    unittest.main()
