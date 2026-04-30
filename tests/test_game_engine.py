from __future__ import annotations

import random
import unittest

from src.server.game_engine import (
    advance_tick,
    apply_citizen_decision,
    apply_mayor_decree,
    build_citizen_observation,
    catch_probability,
    create_initial_state,
)
from src.server.models import (
    CitizenAction,
    CitizenDecision,
    CitizenMode,
    DecisionKind,
    MayorAction,
    MayorDecree,
    StatusEffect,
)


class GameEngineTests(unittest.TestCase):
    def test_initial_state_uses_configurable_citizen_count(self) -> None:
        state = create_initial_state(citizen_count=5, season_seconds=600)

        self.assertEqual(len(state.citizens), 5)
        self.assertEqual(state.season_seconds, 600)
        self.assertEqual(state.heat, 45.0)

    def test_sync_lowers_catch_probability_against_mine(self) -> None:
        state = create_initial_state(citizen_count=1)
        citizen = state.citizens["citizen-001"]
        citizen.trace = 30
        citizen.shiva = 40
        citizen.mode = CitizenMode.MINE
        mine_p = catch_probability(state, citizen, CitizenAction.SNIFF)

        citizen.mode = CitizenMode.SYNC
        sync_p = catch_probability(state, citizen, CitizenAction.SNIFF)

        self.assertLess(sync_p, mine_p)

    def test_observation_exposes_action_tradeoffs(self) -> None:
        state = create_initial_state(citizen_count=1)

        observation = build_citizen_observation(state, "citizen-001")
        tradeoffs = observation["action_tradeoffs"]

        self.assertEqual(len(tradeoffs), 4)
        self.assertTrue(any("JAM_SCAN" in row and "impact=3" in row for row in tradeoffs))
        self.assertTrue(any("COVER_TRACKS" in row and "trace=-3" in row for row in tradeoffs))
        self.assertIn("selection_hint", observation)

    def test_successful_uncaught_action_lowers_heat(self) -> None:
        state = create_initial_state(citizen_count=1)
        start_heat = state.heat

        result = apply_citizen_decision(
            state,
            CitizenDecision(
                citizen_id="citizen-001",
                kind=DecisionKind.ACTION,
                action=CitizenAction.COVER_TRACKS,
            ),
            rng=random.Random(999),
        )

        self.assertLess(state.heat, start_heat)
        self.assertEqual(result.dossiers, [])
        self.assertEqual(result.events[0].kind, "citizen_action")
        self.assertFalse(result.events[0].payload["caught"])

    def test_caught_action_raises_heat_and_creates_dossier(self) -> None:
        state = create_initial_state(citizen_count=1)
        citizen = state.citizens["citizen-001"]
        citizen.trace = 100
        citizen.shiva = 0
        start_heat = state.heat

        result = apply_citizen_decision(
            state,
            CitizenDecision(
                citizen_id="citizen-001",
                kind=DecisionKind.ACTION,
                action=CitizenAction.JAM_SCAN,
            ),
            rng=random.Random(1),
        )

        self.assertGreater(state.heat, start_heat)
        self.assertEqual(len(result.dossiers), 1)
        self.assertTrue(result.events[0].payload["caught"])

    def test_jailed_citizen_keeps_pre_jail_mode_and_rejects_mode_change(self) -> None:
        state = create_initial_state(citizen_count=1)
        citizen = state.citizens["citizen-001"]
        citizen.mode = CitizenMode.SYNC
        start_heat = state.heat
        start_trace = citizen.trace

        apply_mayor_decree(
            state,
            MayorDecree(
                action=MayorAction.JAIL,
                targets=["citizen-001"],
                rationale="Efficiency correction.",
                duration_seconds=3,
            ),
        )

        result = apply_citizen_decision(
            state,
            CitizenDecision(
                citizen_id="citizen-001",
                kind=DecisionKind.MODE_CHANGE,
                mode=CitizenMode.SLEEP,
            ),
        )

        self.assertTrue(citizen.has_status(StatusEffect.JAILED, state.now))
        self.assertEqual(citizen.mode, CitizenMode.SYNC)
        self.assertEqual(citizen.queued_mode, CitizenMode.SYNC)
        self.assertEqual(result.events[0].kind, "invalid_decision")
        self.assertAlmostEqual(state.heat, start_heat + 3.2)
        self.assertEqual(citizen.trace, start_trace + 1.0)

        advance_tick(state, seconds=4)

        self.assertFalse(citizen.has_status(StatusEffect.JAILED, state.now))
        self.assertEqual(citizen.mode, CitizenMode.SYNC)
        self.assertIsNone(citizen.queued_mode)


if __name__ == "__main__":
    unittest.main()
