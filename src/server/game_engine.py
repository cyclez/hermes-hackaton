from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field

from src.server.models import (
    Citizen,
    CitizenAction,
    CitizenDecision,
    CitizenMode,
    CityState,
    DecisionKind,
    Dossier,
    DossierTarget,
    GameEvent,
    MayorAction,
    MayorDecree,
    StatusEffect,
    TimedStatus,
)


ACTION_RULES: dict[CitizenAction, dict[str, float]] = {
    CitizenAction.SNIFF: {
        "base_catch": 0.34,
        "success_heat_delta": -0.9,
        "caught_heat_delta": 1.4,
        "trace_success": 6.0,
        "trace_caught": 14.0,
        "stk_cost": 500,
        "cooldown": 5.0,
    },
    CitizenAction.JAM_SCAN: {
        "base_catch": 0.42,
        "success_heat_delta": -1.2,
        "caught_heat_delta": 1.8,
        "trace_success": 8.0,
        "trace_caught": 18.0,
        "stk_cost": 800,
        "cooldown": 7.0,
    },
    CitizenAction.DECOY_SIGNAL: {
        "base_catch": 0.24,
        "success_heat_delta": -0.5,
        "caught_heat_delta": 0.9,
        "trace_success": 4.0,
        "trace_caught": 10.0,
        "stk_cost": 200,
        "cooldown": 35.0,
    },
    CitizenAction.COVER_TRACKS: {
        "base_catch": 0.16,
        "success_heat_delta": -0.3,
        "caught_heat_delta": 0.6,
        "trace_success": -12.0,
        "trace_caught": 5.0,
        "stk_cost": 100,
        "cooldown": 4.0,
    },
}

SHIVA_CATCH_REDUCTION_PER_POINT = 0.0035


MAYOR_ACTION_HEAT: dict[MayorAction, float] = {
    MayorAction.SURVEIL:        1.0,  # watching — low tension
    MayorAction.JAM:            2.0,  # signal disruption — medium
    MayorAction.CURFEW:         2.0,  # city-wide order — medium
    MayorAction.STK_DRAIN:      2.0,  # economic attack — medium
    MayorAction.JAIL:           3.0,  # full arrest — high tension
    MayorAction.MOST_WANTED:    3.0,  # public bounty — high tension
}


ACTION_TRADEOFFS: dict[CitizenAction, dict[str, object]] = {
    CitizenAction.SNIFF: {
        "role": "recon",
        "on_success": "grants GHOSTED",
    },
    CitizenAction.JAM_SCAN: {
        "role": "disrupt",
        "on_success": "reduces server scan pressure for everyone",
    },
    CitizenAction.DECOY_SIGNAL: {
        "role": "setup",
        "on_success": "clears SURVEILLED and grants a short PROTECTED anti-SURVEIL window",
    },
    CitizenAction.COVER_TRACKS: {
        "role": "recover",
        "on_success": "reduces your trace directly",
    },
}


@dataclass
class EngineResult:
    events: list[GameEvent] = field(default_factory=list)
    dossiers: list[Dossier] = field(default_factory=list)


def create_initial_state(citizen_count: int = 5, season_seconds: int = 600) -> CityState:
    citizens = {
        f"citizen-{idx:03d}": Citizen(citizen_id=f"citizen-{idx:03d}")
        for idx in range(1, citizen_count + 1)
    }
    return CityState(
        game_id=str(uuid.uuid4()),
        season_seconds=season_seconds,
        citizens=citizens,
    )


def advance_tick(state: CityState, seconds: float = 1.0, tick: int = 0) -> EngineResult:
    state.now += seconds
    result = EngineResult()
    _expire_statuses_and_resolve_modes(state)
    _apply_passive_mode_effects(state, seconds)
    _apply_mayor_heat_pressure(state, seconds)
    state.heat = _clamp(state.heat, 0.0, 100.0)
    result.events.append(
        GameEvent(
            event_id=str(uuid.uuid4()),
            tick=tick,
            game_hour=state.game_hour,
            kind="server_tick",
            message="Server advanced simulation tick.",
            payload={"heat": round(state.heat, 3)},
            public=False,
        )
    )
    return result


def due_citizens(state: CityState, min_decision_interval: float = 10.0) -> list[Citizen]:
    return [
        citizen
        for citizen in state.citizens.values()
        if state.now - citizen.last_decision_at >= min_decision_interval
    ]


def build_citizen_observation(state: CityState, citizen_id: str) -> dict[str, object]:
    citizen = state.citizens[citizen_id]
    active_statuses = [status.effect.value for status in citizen.active_statuses(state.now)]
    action_tradeoffs = [
        f"{action.value}: role={ACTION_TRADEOFFS[action]['role']}, "
        f"stk_cost={ACTION_RULES[action]['stk_cost']:.0f}, "
        f"cooldown={ACTION_RULES[action]['cooldown']:.0f}, "
        f"base_catch={ACTION_RULES[action]['base_catch']:.2f}, "
        f"success_heat_delta={ACTION_RULES[action]['success_heat_delta']:.1f}, "
        f"caught_heat_delta={ACTION_RULES[action]['caught_heat_delta']:.1f}, "
        f"trace_success={ACTION_RULES[action]['trace_success']:.1f}, "
        f"trace_caught={ACTION_RULES[action]['trace_caught']:.1f}, "
        f"on_success={ACTION_TRADEOFFS[action]['on_success']}"
        for action in CitizenAction
    ]
    jailed = citizen.has_status(StatusEffect.JAILED, state.now)
    jammed = citizen.has_status(StatusEffect.JAMMED, state.now)
    sleeping = citizen.mode == CitizenMode.SLEEP
    cooldown_remaining = max(0.0, citizen.action_cooldown_until - state.now)
    on_cooldown = cooldown_remaining > 0
    actions_blocked = jailed or jammed or sleeping or on_cooldown

    if jailed:
        hint = "JAILED: all actions and mode changes are blocked. You must HOLD until released. Pre-jail mode restores automatically."
    elif jammed:
        hint = "JAMMED: all active control is blocked right now. You must HOLD until the jam expires."
    elif sleeping:
        hint = "SLEEPING: active actions are blocked while in SLEEP mode. Switch to MINE or SYNC to act, or HOLD to keep recovering trace."
    elif on_cooldown:
        hint = (
            f"COOLDOWN: action blocked for {cooldown_remaining:.0f}s. Change mode or HOLD — do NOT attempt an action right now."
        )
    else:
        hint = (
            "Factual observation only: choose from allowed_actions, affordable_actions, and allowed_modes. "
            "STK is the action currency. MINE is the exposed posture. SYNC builds SHIVA and lowers trace. "
            "Trace raises catch risk continuously. SHIVA lowers catch risk continuously. "
            "SURVEILLED raises catch risk. MOST_WANTED is stronger targeting pressure than SURVEILLED. "
            "MOST_WANTED also adds passive trace pressure over time. "
            "GHOSTED is a stealth benefit after successful SNIFF. "
            "PROTECTED from successful DECOY_SIGNAL clears SURVEILLED and blocks fresh SURVEIL for a short window. "
            "CURFEW is city pressure, not a personal action block or direct catch modifier."
        )

    return {
        "citizen_id": citizen.citizen_id,
        "game_hour": round(state.game_hour, 2),
        "global": {
            "heat": round(state.heat, 2),
            "season_seconds_remaining": max(0, round(state.season_seconds - state.elapsed, 2)),
        },
        "private": {
            "mode": citizen.mode.value,
            "queued_mode": citizen.queued_mode.value if citizen.queued_mode else None,
            "statuses": active_statuses,
            "stk": int(citizen.stk),
            "shiva": round(citizen.shiva, 2),
            "trace": round(citizen.trace, 2),
            "action_cooldown_remaining": round(cooldown_remaining, 2),
        },
        "allowed_actions": [] if actions_blocked else [action.value for action in CitizenAction],
        "affordable_actions": [] if actions_blocked else [action.value for action in CitizenAction if citizen.stk >= ACTION_RULES[action]["stk_cost"]],
        "action_tradeoffs": action_tradeoffs,
        "selection_hint": hint,
        "allowed_modes": [] if (jailed or jammed) else [mode.value for mode in CitizenMode],
    }


def build_mayor_context(state: CityState, dossiers: list[Dossier], recent_events: list[GameEvent]) -> dict[str, object]:
    return {
        "kind": "mayor_context",
        "heat": round(state.heat, 2),
        "game_hour": round(state.game_hour, 2),
        "recent_actions": [
            {
                "citizen_id": event.payload.get("citizen_id"),
                "public_label": event.payload.get("public_label"),
                "action": event.payload.get("action"),
                "caught": event.payload.get("caught"),
                "heat_after": event.payload.get("heat"),
            }
            for event in recent_events
            if event.kind == "citizen_action"
        ],
        "recent_evidence": [
            {
                "citizen_id": target.citizen_id,
                "action": target.action.value,
                "p_catch": round(target.p_catch, 3),
                "trace": round(target.trace, 2),
                "shiva": round(target.shiva, 2),
            }
            for dossier in dossiers
            for target in dossier.targets
        ],
        "active_citizens": list(state.citizens.keys()),
        "citizen_snapshots": [
            {
                "citizen_id": citizen.citizen_id,
                "behavior": citizen.behavior,
                "mode": citizen.mode.value,
                "queued_mode": citizen.queued_mode.value if citizen.queued_mode else None,
                "statuses": [status.effect.value for status in citizen.active_statuses(state.now)],
                "stk": int(citizen.stk),
                "shiva": round(citizen.shiva, 2),
                "trace": round(citizen.trace, 2),
                "action_cooldown_remaining": round(max(0.0, citizen.action_cooldown_until - state.now), 2),
            }
            for citizen in state.citizens.values()
        ],
    }


def apply_citizen_decision(
    state: CityState,
    decision: CitizenDecision,
    *,
    tick: int = 0,
    rng: random.Random | None = None,
) -> EngineResult:
    rng = rng or random.Random()
    citizen = state.citizens[decision.citizen_id]
    citizen.last_decision_at = state.now
    if decision.kind == DecisionKind.MODE_CHANGE:
        return _apply_mode_change(state, citizen, decision, tick)
    if decision.kind == DecisionKind.HOLD:
        return _hold_decision(state, citizen, decision, tick)
    if decision.kind == DecisionKind.ACTION and decision.action:
        return _apply_action(state, citizen, decision.action, tick, rng)
    return _invalid_decision(state, citizen, "Decision did not include a valid action or mode.", tick)


def apply_mayor_decree(state: CityState, decree: MayorDecree, *, tick: int = 0) -> list[GameEvent]:
    events: list[GameEvent] = []
    duration = max(1, decree.duration_seconds)
    heat_delta = MAYOR_ACTION_HEAT.get(decree.action, 1.0)

    if decree.action == MayorAction.CURFEW:
        state.heat = _clamp(state.heat + heat_delta, 0.0, 100.0)
        events.append(
            GameEvent(
                event_id=str(uuid.uuid4()),
                tick=tick,
                game_hour=state.game_hour,
                kind="mayor_decree",
                message="Mayor applied CURFEW citywide.",
                payload={
                    "action": decree.action.value,
                    "rationale": decree.rationale,
                    "heat_delta": heat_delta,
                    "scope": "citywide",
                    "applied": True,
                    "blocked_reason": None,
                },
                public=True,
            )
        )
        return events

    outcomes: list[tuple[str, bool, str | None]] = []
    for target_id in decree.targets:
        citizen = state.citizens.get(target_id)
        if citizen is None:
            continue
        applied, blocked_reason = _apply_mayor_effect(state, citizen, decree.action, duration)
        outcomes.append((target_id, applied, blocked_reason))
    affected_any = any(applied for _, applied, _ in outcomes)
    if affected_any:
        state.heat = _clamp(state.heat + heat_delta, 0.0, 100.0)
    applied_heat_delta = heat_delta if affected_any else 0.0
    for target_id, applied, blocked_reason in outcomes:
        events.append(
            GameEvent(
                event_id=str(uuid.uuid4()),
                tick=tick,
                game_hour=state.game_hour,
                kind="mayor_decree",
                message=(
                    f"Mayor applied {decree.action.value} to {target_id}."
                    if applied
                    else f"Mayor attempted {decree.action.value} on {target_id}, but it was blocked."
                ),
                payload={
                    "target": target_id,
                    "action": decree.action.value,
                    "rationale": decree.rationale,
                    "heat_delta": applied_heat_delta,
                    "applied": applied,
                    "blocked_reason": blocked_reason,
                },
                public=True,
            )
        )
    return events


def _apply_mode_change(state: CityState, citizen: Citizen, decision: CitizenDecision, tick: int) -> EngineResult:
    result = EngineResult()
    if decision.mode is None:
        return _invalid_decision(state, citizen, "Mode change did not include target mode.", tick)
    if citizen.has_status(StatusEffect.JAILED, state.now):
        return _invalid_decision(state, citizen, "Jailed: no mode changes. Pre-jail mode restores on release.", tick)
    if citizen.has_status(StatusEffect.JAMMED, state.now):
        return _invalid_decision(state, citizen, "Jammed: no mode changes until the jam expires.", tick)
    citizen.mode = decision.mode
    citizen.queued_mode = None
    result.events.append(
        GameEvent(
            event_id=str(uuid.uuid4()),
            tick=tick,
            game_hour=state.game_hour,
            kind="mode_change",
            message=f"{citizen.citizen_id} set mode to {decision.mode.value}.",
            payload={"citizen_id": citizen.citizen_id, "mode": decision.mode.value},
            public=True,
        )
    )
    return result


def _hold_decision(state: CityState, citizen: Citizen, decision: CitizenDecision, tick: int) -> EngineResult:
    return EngineResult(
        events=[
            GameEvent(
                event_id=str(uuid.uuid4()),
                tick=tick,
                game_hour=state.game_hour,
                kind="hold",
                message=f"{citizen.citizen_id} held position.",
                payload={"citizen_id": citizen.citizen_id, "rationale": decision.rationale},
                public=True,
            )
        ]
    )


def _apply_action(
    state: CityState,
    citizen: Citizen,
    action: CitizenAction,
    tick: int,
    rng: random.Random,
) -> EngineResult:
    if citizen.mode == CitizenMode.SLEEP:
        return _invalid_decision(state, citizen, "Sleeping citizens cannot perform active actions.", tick)
    if citizen.has_status(StatusEffect.JAILED, state.now):
        return _invalid_decision(state, citizen, "Jailed citizens cannot perform active actions.", tick)
    if citizen.has_status(StatusEffect.JAMMED, state.now):
        return _invalid_decision(state, citizen, "Jammed citizens cannot perform active actions.", tick)
    if citizen.action_cooldown_until > state.now:
        return _invalid_decision(state, citizen, "Citizen action is still on cooldown.", tick)

    rule = ACTION_RULES[action]
    if citizen.stk < rule["stk_cost"]:
        return _invalid_decision(state, citizen, "Citizen does not have enough STK.", tick)

    citizen.stk -= rule["stk_cost"]
    p_catch = catch_probability(state, citizen, action)
    caught = rng.random() < p_catch
    result = EngineResult()
    if caught:
        state.heat += rule["caught_heat_delta"]
        citizen.trace += rule["trace_caught"]
        target = DossierTarget(
            citizen_id=citizen.citizen_id,
            action=action,
            p_catch=p_catch,
            trace=citizen.trace,
            shiva=citizen.shiva,
            evidence=f"{citizen.citizen_id} was caught executing {action.value}.",
        )
        result.dossiers.append(
            Dossier(
                dossier_id=str(uuid.uuid4()),
                created_at=state.now,
                heat=state.heat,
                targets=[target],
            )
        )
    else:
        state.heat += rule["success_heat_delta"]
        citizen.trace += rule["trace_success"]
        if action == CitizenAction.SNIFF:
            _add_status(citizen, StatusEffect.GHOSTED, state.now + 15.0)
        if action == CitizenAction.DECOY_SIGNAL:
            _remove_status(citizen, StatusEffect.SURVEILLED)
            _add_status(citizen, StatusEffect.PROTECTED, state.now + 30.0)
        if action == CitizenAction.JAM_SCAN:
            state.server_scan_jammed_until = max(state.server_scan_jammed_until, state.now + 10.0)

    citizen.trace = _clamp(citizen.trace, 0.0, 100.0)
    citizen.action_cooldown_until = state.now + rule["cooldown"]
    state.heat = _clamp(state.heat, 0.0, 100.0)
    result.events.append(
        GameEvent(
            event_id=str(uuid.uuid4()),
            tick=tick,
            game_hour=state.game_hour,
            kind="citizen_action",
            message=f"{citizen.citizen_id} executed {action.value}; caught={caught}.",
            payload={
                "citizen_id": citizen.citizen_id,
                "public_label": "unidentified citizen",
                "action": action.value,
                "caught": caught,
                "p_catch": round(p_catch, 3),
                "heat": round(state.heat, 3),
            },
            public=True,
        )
    )
    return result


def catch_probability(state: CityState, citizen: Citizen, action: CitizenAction) -> float:
    rule = ACTION_RULES[action]
    p_catch = rule["base_catch"]
    if citizen.mode == CitizenMode.MINE:
        p_catch += 0.12
    elif citizen.mode == CitizenMode.SYNC:
        p_catch -= 0.12
    elif citizen.mode == CitizenMode.SLEEP:
        p_catch -= 0.25
    if citizen.has_status(StatusEffect.SURVEILLED, state.now):
        p_catch += 0.22
    if citizen.has_status(StatusEffect.MOST_WANTED, state.now):
        p_catch += 0.32
    if citizen.has_status(StatusEffect.GHOSTED, state.now):
        p_catch -= 0.16
    if state.server_scan_jammed_until > state.now:
        p_catch -= 0.15
    p_catch += citizen.trace * 0.003
    p_catch -= citizen.shiva * SHIVA_CATCH_REDUCTION_PER_POINT
    return _clamp(p_catch, 0.05, 0.95)


def _apply_mayor_effect(
    state: CityState,
    citizen: Citizen,
    action: MayorAction,
    duration: int,
) -> tuple[bool, str | None]:
    if action == MayorAction.JAIL:
        if citizen.has_status(StatusEffect.JAILED, state.now):
            return False, "already_jailed"
        citizen.queued_mode = citizen.mode
        _remove_status(citizen, StatusEffect.JAMMED)
        _remove_status(citizen, StatusEffect.SURVEILLED)
        _remove_status(citizen, StatusEffect.MOST_WANTED)
        _remove_status(citizen, StatusEffect.GHOSTED)
        _remove_status(citizen, StatusEffect.PROTECTED)
        _add_status(citizen, StatusEffect.JAILED, state.now + duration)
        return True, None

    if action == MayorAction.JAM:
        if citizen.has_status(StatusEffect.JAILED, state.now):
            return False, "target_jailed"
        if citizen.has_status(StatusEffect.JAMMED, state.now):
            return False, "already_jammed"
        _remove_status(citizen, StatusEffect.SURVEILLED)
        _add_status(citizen, StatusEffect.JAMMED, state.now + duration)
        return True, None

    if action == MayorAction.SURVEIL:
        if citizen.has_status(StatusEffect.JAILED, state.now):
            return False, "target_jailed"
        if citizen.has_status(StatusEffect.JAMMED, state.now):
            return False, "target_jammed"
        if citizen.has_status(StatusEffect.PROTECTED, state.now):
            return False, "target_protected"
        if citizen.has_status(StatusEffect.SURVEILLED, state.now):
            return False, "already_surveilled"
        if citizen.has_status(StatusEffect.MOST_WANTED, state.now):
            return False, "already_most_wanted"
        _add_status(citizen, StatusEffect.SURVEILLED, state.now + duration)
        return True, None

    if action == MayorAction.MOST_WANTED:
        if citizen.has_status(StatusEffect.JAILED, state.now):
            return False, "target_jailed"
        if citizen.has_status(StatusEffect.MOST_WANTED, state.now):
            return False, "already_most_wanted"
        _remove_status(citizen, StatusEffect.SURVEILLED)
        _add_status(citizen, StatusEffect.MOST_WANTED, state.now + duration)
        return True, None

    if action == MayorAction.STK_DRAIN:
        if citizen.stk <= 0.0:
            return False, "no_stk_to_drain"
        citizen.stk = max(0.0, citizen.stk - 500.0)
        citizen.trace = _clamp(citizen.trace + 8.0, 0.0, 100.0)
        return True, None

    return False, "unsupported_action"


def _invalid_decision(state: CityState, citizen: Citizen, reason: str, tick: int) -> EngineResult:
    citizen.trace = _clamp(citizen.trace + 1.0, 0.0, 100.0)
    state.heat = _clamp(state.heat + 0.2, 0.0, 100.0)
    return EngineResult(
        events=[
            GameEvent(
                event_id=str(uuid.uuid4()),
                tick=tick,
                game_hour=state.game_hour,
                kind="invalid_decision",
                message=f"{citizen.citizen_id} submitted invalid decision: {reason}",
                payload={"citizen_id": citizen.citizen_id, "reason": reason},
                public=False,
            )
        ]
    )


def _apply_passive_mode_effects(state: CityState, seconds: float) -> None:
    for citizen in state.citizens.values():
        if citizen.has_status(StatusEffect.JAILED, state.now):
            continue  # jailed: full freeze, nothing accumulates

        if citizen.mode == CitizenMode.MINE:
            citizen.stk += 12 * seconds
            citizen.trace += 0.025 * seconds
        elif citizen.mode == CitizenMode.SYNC:
            citizen.stk += 5 * seconds
            citizen.shiva += 0.12 * seconds
            citizen.trace -= 0.015 * seconds
        elif citizen.mode == CitizenMode.SLEEP:
            citizen.stk += 1.5 * seconds
            citizen.trace -= 0.09 * seconds
            citizen.shiva -= 0.025 * seconds

        if citizen.has_status(StatusEffect.MOST_WANTED, state.now):
            citizen.trace += 0.12 * seconds

        citizen.stk = _clamp(citizen.stk, 0.0, 9999.0)
        citizen.shiva = _clamp(citizen.shiva, 0.0, 100.0)
        citizen.trace = _clamp(citizen.trace, 0.0, 100.0)


def _apply_mayor_heat_pressure(state: CityState, seconds: float) -> None:
    progress = _clamp(state.elapsed / state.season_seconds, 0.0, 1.0)
    pressure_per_second = 0.015 + (0.08 * (progress**1.8))
    state.heat += pressure_per_second * seconds


def _expire_statuses_and_resolve_modes(state: CityState) -> None:
    for citizen in state.citizens.values():
        had_jail = any(status.effect == StatusEffect.JAILED for status in citizen.statuses)
        citizen.statuses = citizen.active_statuses(state.now)
        has_jail = citizen.has_status(StatusEffect.JAILED, state.now)
        if had_jail and not has_jail and citizen.queued_mode is not None:
            citizen.mode = citizen.queued_mode
            citizen.queued_mode = None


def _add_status(citizen: Citizen, effect: StatusEffect, expires_at: float) -> None:
    citizen.statuses = [status for status in citizen.statuses if status.effect != effect]
    citizen.statuses.append(TimedStatus(effect=effect, expires_at=expires_at))


def _remove_status(citizen: Citizen, effect: StatusEffect) -> None:
    citizen.statuses = [status for status in citizen.statuses if status.effect != effect]


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))
