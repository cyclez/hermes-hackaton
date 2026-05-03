from __future__ import annotations

import random
import unittest

from src.server.game_engine import (
    advance_tick,
    apply_citizen_decision,
    apply_mayor_decree,
    build_mayor_context,
    build_citizen_observation,
    catch_probability,
    create_initial_state,
)
from src.server.models import (
    CitizenAction,
    CitizenDecision,
    CitizenMode,
    DecisionKind,
    Dossier,
    DossierTarget,
    GameEvent,
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

    def test_most_wanted_adds_passive_trace_pressure_during_tick(self) -> None:
        state = create_initial_state(citizen_count=1)
        citizen = state.citizens["citizen-001"]
        citizen.mode = CitizenMode.SYNC
        citizen.trace = 10.0

        apply_mayor_decree(
            state,
            MayorDecree(
                action=MayorAction.MOST_WANTED,
                targets=["citizen-001"],
                rationale="Escalate targeting.",
                duration_seconds=30,
            ),
        )

        advance_tick(state, seconds=1)

        self.assertTrue(citizen.has_status(StatusEffect.MOST_WANTED, state.now))
        self.assertAlmostEqual(citizen.trace, 10.105, places=3)

    def test_stk_drain_reduces_stk_and_increases_trace(self) -> None:
        state = create_initial_state(citizen_count=1)
        citizen = state.citizens["citizen-001"]
        citizen.stk = 1200.0
        citizen.trace = 12.5

        apply_mayor_decree(
            state,
            MayorDecree(
                action=MayorAction.STK_DRAIN,
                targets=["citizen-001"],
                rationale="Economic pressure.",
                duration_seconds=30,
            ),
        )

        self.assertAlmostEqual(citizen.stk, 700.0)
        self.assertAlmostEqual(citizen.trace, 20.5)

    def test_observation_exposes_action_tradeoffs(self) -> None:
        state = create_initial_state(citizen_count=1)

        observation = build_citizen_observation(state, "citizen-001")
        tradeoffs = observation["action_tradeoffs"]

        self.assertEqual(len(tradeoffs), 4)
        self.assertTrue(any("JAM_SCAN" in row and "base_catch=0.42" in row for row in tradeoffs))
        self.assertTrue(any("COVER_TRACKS" in row and "trace_success=-12.0" in row for row in tradeoffs))
        self.assertTrue(any("DECOY_SIGNAL" in row and "clears SURVEILLED" in row for row in tradeoffs))
        self.assertIn("selection_hint", observation)
        self.assertIn("Factual observation only", observation["selection_hint"])
        self.assertIn("MOST_WANTED is stronger targeting pressure than SURVEILLED", observation["selection_hint"])
        self.assertIn("GHOSTED is a stealth benefit", observation["selection_hint"])
        self.assertIn("PROTECTED from successful DECOY_SIGNAL clears SURVEILLED and blocks fresh SURVEIL", observation["selection_hint"])
        self.assertIn("CURFEW is city pressure", observation["selection_hint"])
        self.assertNotIn("prefer DECOY_SIGNAL or SYNC", observation["selection_hint"])

    def test_jammed_observation_blocks_modes_and_forces_hold_hint(self) -> None:
        state = create_initial_state(citizen_count=1)
        apply_mayor_decree(
            state,
            MayorDecree(
                action=MayorAction.JAM,
                targets=["citizen-001"],
                rationale="Block target.",
                duration_seconds=30,
            ),
        )

        observation = build_citizen_observation(state, "citizen-001")

        self.assertEqual(observation["allowed_actions"], [])
        self.assertEqual(observation["allowed_modes"], [])
        self.assertIn("must HOLD until the jam expires", observation["selection_hint"])

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

    def test_successful_decoy_signal_grants_protected_and_clears_surveilled(self) -> None:
        state = create_initial_state(citizen_count=1)
        citizen = state.citizens["citizen-001"]
        apply_mayor_decree(
            state,
            MayorDecree(
                action=MayorAction.SURVEIL,
                targets=["citizen-001"],
                rationale="Watch target.",
                duration_seconds=30,
            ),
        )
        self.assertTrue(citizen.has_status(StatusEffect.SURVEILLED, state.now))

        apply_citizen_decision(
            state,
            CitizenDecision(
                citizen_id="citizen-001",
                kind=DecisionKind.ACTION,
                action=CitizenAction.DECOY_SIGNAL,
            ),
            rng=random.Random(999),
        )

        self.assertTrue(citizen.has_status(StatusEffect.PROTECTED, state.now))
        self.assertFalse(citizen.has_status(StatusEffect.SURVEILLED, state.now))

    def test_successful_decoy_signal_uses_long_cooldown(self) -> None:
        state = create_initial_state(citizen_count=1)
        citizen = state.citizens["citizen-001"]

        apply_citizen_decision(
            state,
            CitizenDecision(
                citizen_id="citizen-001",
                kind=DecisionKind.ACTION,
                action=CitizenAction.DECOY_SIGNAL,
            ),
            rng=random.Random(999),
        )

        self.assertAlmostEqual(citizen.action_cooldown_until - state.now, 35.0)

    def test_jam_scan_uses_reduced_stk_cost(self) -> None:
        state = create_initial_state(citizen_count=1)
        citizen = state.citizens["citizen-001"]
        start_stk = citizen.stk

        apply_citizen_decision(
            state,
            CitizenDecision(
                citizen_id="citizen-001",
                kind=DecisionKind.ACTION,
                action=CitizenAction.JAM_SCAN,
            ),
            rng=random.Random(999),
        )

        self.assertAlmostEqual(citizen.stk, start_stk - 800.0)

    def test_shiva_reduction_is_weaker_than_previous_curve(self) -> None:
        state = create_initial_state(citizen_count=1)
        citizen = state.citizens["citizen-001"]
        citizen.mode = CitizenMode.MINE
        citizen.trace = 0
        citizen.shiva = 100

        p_catch = catch_probability(state, citizen, CitizenAction.SNIFF)

        self.assertAlmostEqual(p_catch, 0.11, places=3)

    def test_protected_blocks_fresh_surveil_while_active(self) -> None:
        state = create_initial_state(citizen_count=1)
        citizen = state.citizens["citizen-001"]

        apply_citizen_decision(
            state,
            CitizenDecision(
                citizen_id="citizen-001",
                kind=DecisionKind.ACTION,
                action=CitizenAction.DECOY_SIGNAL,
            ),
            rng=random.Random(999),
        )
        self.assertTrue(citizen.has_status(StatusEffect.PROTECTED, state.now))

        apply_mayor_decree(
            state,
            MayorDecree(
                action=MayorAction.SURVEIL,
                targets=["citizen-001"],
                rationale="Try to watch target.",
                duration_seconds=30,
            ),
        )

        self.assertFalse(citizen.has_status(StatusEffect.SURVEILLED, state.now))
        self.assertTrue(citizen.has_status(StatusEffect.PROTECTED, state.now))

        citizen.action_cooldown_until = state.now
        apply_citizen_decision(
            state,
            CitizenDecision(
                citizen_id="citizen-001",
                kind=DecisionKind.ACTION,
                action=CitizenAction.SNIFF,
            ),
            rng=random.Random(999),
        )

        self.assertTrue(citizen.has_status(StatusEffect.PROTECTED, state.now))

    def test_protected_does_not_cancel_most_wanted_or_later_dossier_creation(self) -> None:
        state = create_initial_state(citizen_count=1)
        citizen = state.citizens["citizen-001"]

        apply_citizen_decision(
            state,
            CitizenDecision(
                citizen_id="citizen-001",
                kind=DecisionKind.ACTION,
                action=CitizenAction.DECOY_SIGNAL,
            ),
            rng=random.Random(999),
        )
        apply_mayor_decree(
            state,
            MayorDecree(
                action=MayorAction.MOST_WANTED,
                targets=["citizen-001"],
                rationale="Escalate targeting.",
                duration_seconds=30,
            ),
        )
        self.assertTrue(citizen.has_status(StatusEffect.MOST_WANTED, state.now))
        self.assertTrue(citizen.has_status(StatusEffect.PROTECTED, state.now))
        citizen.trace = 100
        citizen.shiva = 0

        citizen.action_cooldown_until = state.now
        result = apply_citizen_decision(
            state,
            CitizenDecision(
                citizen_id="citizen-001",
                kind=DecisionKind.ACTION,
                action=CitizenAction.SNIFF,
            ),
            rng=random.Random(1),
        )

        self.assertTrue(result.events[0].payload["caught"])
        self.assertEqual(len(result.dossiers), 1)
        self.assertTrue(citizen.has_status(StatusEffect.PROTECTED, state.now))
        self.assertTrue(citizen.has_status(StatusEffect.MOST_WANTED, state.now))

    def test_decoy_signal_cooldown_outlasts_protected_window(self) -> None:
        state = create_initial_state(citizen_count=1)
        citizen = state.citizens["citizen-001"]

        apply_citizen_decision(
            state,
            CitizenDecision(
                citizen_id="citizen-001",
                kind=DecisionKind.ACTION,
                action=CitizenAction.DECOY_SIGNAL,
            ),
            rng=random.Random(999),
        )

        self.assertTrue(citizen.has_status(StatusEffect.PROTECTED, state.now))
        self.assertGreater(citizen.action_cooldown_until - state.now, 30.0)

        advance_tick(state, seconds=31)

        self.assertFalse(citizen.has_status(StatusEffect.PROTECTED, state.now))
        self.assertGreater(citizen.action_cooldown_until, state.now)

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

    def test_jammed_citizen_rejects_mode_change(self) -> None:
        state = create_initial_state(citizen_count=1)
        citizen = state.citizens["citizen-001"]
        start_heat = state.heat
        start_trace = citizen.trace

        apply_mayor_decree(
            state,
            MayorDecree(
                action=MayorAction.JAM,
                targets=["citizen-001"],
                rationale="Interrupt target.",
                duration_seconds=30,
            ),
        )

        result = apply_citizen_decision(
            state,
            CitizenDecision(
                citizen_id="citizen-001",
                kind=DecisionKind.MODE_CHANGE,
                mode=CitizenMode.SYNC,
            ),
        )

        self.assertEqual(result.events[0].kind, "invalid_decision")
        self.assertAlmostEqual(state.heat, start_heat + 2.2)
        self.assertEqual(citizen.trace, start_trace + 1.0)

    def test_jail_clears_surveillance_targeting_states(self) -> None:
        state = create_initial_state(citizen_count=1)
        citizen = state.citizens["citizen-001"]

        apply_mayor_decree(
            state,
            MayorDecree(
                action=MayorAction.SURVEIL,
                targets=["citizen-001"],
                rationale="Watch target.",
                duration_seconds=30,
            ),
        )
        apply_mayor_decree(
            state,
            MayorDecree(
                action=MayorAction.MOST_WANTED,
                targets=["citizen-001"],
                rationale="Escalate targeting.",
                duration_seconds=30,
            ),
        )
        self.assertTrue(citizen.has_status(StatusEffect.MOST_WANTED, state.now))

        apply_mayor_decree(
            state,
            MayorDecree(
                action=MayorAction.JAIL,
                targets=["citizen-001"],
                rationale="Detain target.",
                duration_seconds=30,
            ),
        )

        self.assertTrue(citizen.has_status(StatusEffect.JAILED, state.now))
        self.assertFalse(citizen.has_status(StatusEffect.SURVEILLED, state.now))
        self.assertFalse(citizen.has_status(StatusEffect.MOST_WANTED, state.now))

    def test_jail_also_clears_ghosted_and_protected(self) -> None:
        state = create_initial_state(citizen_count=1)
        citizen = state.citizens["citizen-001"]

        apply_citizen_decision(
            state,
            CitizenDecision(
                citizen_id="citizen-001",
                kind=DecisionKind.ACTION,
                action=CitizenAction.SNIFF,
            ),
            rng=random.Random(999),
        )
        advance_tick(state, seconds=5)
        apply_citizen_decision(
            state,
            CitizenDecision(
                citizen_id="citizen-001",
                kind=DecisionKind.ACTION,
                action=CitizenAction.DECOY_SIGNAL,
            ),
            rng=random.Random(999),
        )

        self.assertTrue(citizen.has_status(StatusEffect.GHOSTED, state.now))
        self.assertTrue(citizen.has_status(StatusEffect.PROTECTED, state.now))

        apply_mayor_decree(
            state,
            MayorDecree(
                action=MayorAction.JAIL,
                targets=["citizen-001"],
                rationale="Detain target.",
                duration_seconds=30,
            ),
        )

        self.assertTrue(citizen.has_status(StatusEffect.JAILED, state.now))
        self.assertFalse(citizen.has_status(StatusEffect.GHOSTED, state.now))
        self.assertFalse(citizen.has_status(StatusEffect.PROTECTED, state.now))

    def test_jail_also_clears_jammed(self) -> None:
        state = create_initial_state(citizen_count=1)
        citizen = state.citizens["citizen-001"]

        apply_mayor_decree(
            state,
            MayorDecree(
                action=MayorAction.JAM,
                targets=["citizen-001"],
                rationale="Block actions.",
                duration_seconds=30,
            ),
        )
        self.assertTrue(citizen.has_status(StatusEffect.JAMMED, state.now))

        apply_mayor_decree(
            state,
            MayorDecree(
                action=MayorAction.JAIL,
                targets=["citizen-001"],
                rationale="Detain target.",
                duration_seconds=30,
            ),
        )

        self.assertTrue(citizen.has_status(StatusEffect.JAILED, state.now))
        self.assertFalse(citizen.has_status(StatusEffect.JAMMED, state.now))

    def test_jam_clears_surveilled_but_preserves_most_wanted(self) -> None:
        state = create_initial_state(citizen_count=1)
        citizen = state.citizens["citizen-001"]

        apply_mayor_decree(
            state,
            MayorDecree(
                action=MayorAction.SURVEIL,
                targets=["citizen-001"],
                rationale="Watch target.",
                duration_seconds=30,
            ),
        )
        apply_mayor_decree(
            state,
            MayorDecree(
                action=MayorAction.MOST_WANTED,
                targets=["citizen-001"],
                rationale="Escalate targeting.",
                duration_seconds=30,
            ),
        )

        self.assertFalse(citizen.has_status(StatusEffect.SURVEILLED, state.now))
        self.assertTrue(citizen.has_status(StatusEffect.MOST_WANTED, state.now))

        apply_mayor_decree(
            state,
            MayorDecree(
                action=MayorAction.JAM,
                targets=["citizen-001"],
                rationale="Block actions.",
                duration_seconds=30,
            ),
        )

        self.assertTrue(citizen.has_status(StatusEffect.JAMMED, state.now))
        self.assertFalse(citizen.has_status(StatusEffect.SURVEILLED, state.now))
        self.assertTrue(citizen.has_status(StatusEffect.MOST_WANTED, state.now))

    def test_surveil_does_not_apply_while_jammed(self) -> None:
        state = create_initial_state(citizen_count=1)
        citizen = state.citizens["citizen-001"]

        apply_mayor_decree(
            state,
            MayorDecree(
                action=MayorAction.JAM,
                targets=["citizen-001"],
                rationale="Block actions.",
                duration_seconds=30,
            ),
        )
        apply_mayor_decree(
            state,
            MayorDecree(
                action=MayorAction.SURVEIL,
                targets=["citizen-001"],
                rationale="Try to watch target.",
                duration_seconds=30,
            ),
        )

        self.assertTrue(citizen.has_status(StatusEffect.JAMMED, state.now))
        self.assertFalse(citizen.has_status(StatusEffect.SURVEILLED, state.now))

    def test_blocked_surveil_reports_blocked_reason_and_does_not_add_heat(self) -> None:
        state = create_initial_state(citizen_count=1)
        citizen = state.citizens["citizen-001"]
        apply_citizen_decision(
            state,
            CitizenDecision(
                citizen_id="citizen-001",
                kind=DecisionKind.ACTION,
                action=CitizenAction.DECOY_SIGNAL,
            ),
            rng=random.Random(999),
        )
        start_heat = state.heat

        events = apply_mayor_decree(
            state,
            MayorDecree(
                action=MayorAction.SURVEIL,
                targets=["citizen-001"],
                rationale="Attempt surveillance.",
                duration_seconds=30,
            ),
        )

        self.assertEqual(len(events), 1)
        self.assertFalse(events[0].payload["applied"])
        self.assertEqual(events[0].payload["blocked_reason"], "target_protected")
        self.assertAlmostEqual(events[0].payload["heat_delta"], 0.0)
        self.assertAlmostEqual(state.heat, start_heat)
        self.assertFalse(citizen.has_status(StatusEffect.SURVEILLED, state.now))

    def test_multi_target_decree_only_charges_heat_if_any_target_applies(self) -> None:
        state = create_initial_state(citizen_count=2)
        apply_citizen_decision(
            state,
            CitizenDecision(
                citizen_id="citizen-001",
                kind=DecisionKind.ACTION,
                action=CitizenAction.DECOY_SIGNAL,
            ),
            rng=random.Random(999),
        )
        start_heat = state.heat

        events = apply_mayor_decree(
            state,
            MayorDecree(
                action=MayorAction.SURVEIL,
                targets=["citizen-001", "citizen-002"],
                rationale="Watch both.",
                duration_seconds=30,
            ),
        )

        self.assertEqual(len(events), 2)
        blocked = next(event for event in events if event.payload["target"] == "citizen-001")
        applied = next(event for event in events if event.payload["target"] == "citizen-002")
        self.assertFalse(blocked.payload["applied"])
        self.assertEqual(blocked.payload["blocked_reason"], "target_protected")
        self.assertTrue(applied.payload["applied"])
        self.assertAlmostEqual(state.heat, start_heat + 1.0)
        self.assertTrue(state.citizens["citizen-002"].has_status(StatusEffect.SURVEILLED, state.now))

    def test_most_wanted_is_distinct_status_and_stronger_than_surveillance(self) -> None:
        state = create_initial_state(citizen_count=1)
        citizen = state.citizens["citizen-001"]

        surveilled_only = catch_probability(state, citizen, CitizenAction.SNIFF)
        apply_mayor_decree(
            state,
            MayorDecree(
                action=MayorAction.SURVEIL,
                targets=["citizen-001"],
                rationale="Watch target.",
                duration_seconds=30,
            ),
        )
        surveilled_only = catch_probability(state, citizen, CitizenAction.SNIFF)

        citizen.statuses.clear()
        apply_mayor_decree(
            state,
            MayorDecree(
                action=MayorAction.MOST_WANTED,
                targets=["citizen-001"],
                rationale="Escalate targeting.",
                duration_seconds=30,
            ),
        )
        most_wanted = catch_probability(state, citizen, CitizenAction.SNIFF)

        self.assertTrue(citizen.has_status(StatusEffect.MOST_WANTED, state.now))
        self.assertFalse(citizen.has_status(StatusEffect.SURVEILLED, state.now))
        self.assertGreater(most_wanted, surveilled_only)

    def test_most_wanted_replaces_surveilled(self) -> None:
        state = create_initial_state(citizen_count=1)
        citizen = state.citizens["citizen-001"]

        apply_mayor_decree(
            state,
            MayorDecree(
                action=MayorAction.SURVEIL,
                targets=["citizen-001"],
                rationale="Watch target.",
                duration_seconds=30,
            ),
        )
        self.assertTrue(citizen.has_status(StatusEffect.SURVEILLED, state.now))

        apply_mayor_decree(
            state,
            MayorDecree(
                action=MayorAction.MOST_WANTED,
                targets=["citizen-001"],
                rationale="Escalate targeting.",
                duration_seconds=30,
            ),
        )

        self.assertTrue(citizen.has_status(StatusEffect.MOST_WANTED, state.now))
        self.assertFalse(citizen.has_status(StatusEffect.SURVEILLED, state.now))

    def test_curfew_applies_heat_once_citywide(self) -> None:
        state = create_initial_state(citizen_count=5)
        start_heat = state.heat

        events = apply_mayor_decree(
            state,
            MayorDecree(
                action=MayorAction.CURFEW,
                targets=[f"citizen-{idx:03d}" for idx in range(1, 6)],
                rationale="Citywide pressure.",
                duration_seconds=45,
            ),
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].message, "Mayor applied CURFEW citywide.")
        self.assertAlmostEqual(state.heat, start_heat + 2.0)
        self.assertTrue(all(not citizen.statuses for citizen in state.citizens.values()))

    def test_multi_target_targeted_decree_applies_heat_once(self) -> None:
        state = create_initial_state(citizen_count=2)
        start_heat = state.heat

        events = apply_mayor_decree(
            state,
            MayorDecree(
                action=MayorAction.SURVEIL,
                targets=["citizen-001", "citizen-002"],
                rationale="Watch both targets.",
                duration_seconds=30,
            ),
        )

        self.assertEqual(len(events), 2)
        self.assertAlmostEqual(state.heat, start_heat + 1.0)
        self.assertTrue(state.citizens["citizen-001"].has_status(StatusEffect.SURVEILLED, state.now))
        self.assertTrue(state.citizens["citizen-002"].has_status(StatusEffect.SURVEILLED, state.now))

    def test_build_mayor_context_exposes_filtered_server_snapshot(self) -> None:
        state = create_initial_state(citizen_count=1)
        state.citizens["citizen-001"].behavior = "aggressive"
        dossiers = [
            Dossier(
                dossier_id="d1",
                created_at=1.0,
                heat=48.0,
                targets=[
                    DossierTarget(
                        citizen_id="citizen-001",
                        action=CitizenAction.SNIFF,
                        p_catch=0.42,
                        trace=22.0,
                        shiva=41.0,
                        evidence="caught",
                    )
                ],
            )
        ]
        recent_events = [
            GameEvent(
                event_id="e1",
                tick=1,
                game_hour=1.0,
                kind="citizen_action",
                message="event",
                payload={
                    "citizen_id": "citizen-001",
                    "public_label": "unidentified citizen",
                    "action": "SNIFF",
                    "caught": True,
                    "heat": 46.2,
                    "extra_noise": "ignored",
                },
                public=True,
            )
        ]

        context = build_mayor_context(state, dossiers, recent_events)

        self.assertEqual(context["kind"], "mayor_context")
        self.assertIn("citizen_snapshots", context)
        self.assertEqual(context["recent_actions"][0]["public_label"], "unidentified citizen")
        self.assertNotIn("extra_noise", context["recent_actions"][0])
        self.assertEqual(
            set(context["citizen_snapshots"][0].keys()),
            {"citizen_id", "behavior", "mode", "queued_mode", "statuses", "stk", "shiva", "trace", "action_cooldown_remaining"},
        )


if __name__ == "__main__":
    unittest.main()
