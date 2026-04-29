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
        "stk_cost": 1000,
        "cooldown": 7.0,
    },
    CitizenAction.DECOY_SIGNAL: {
        "base_catch": 0.24,
        "success_heat_delta": -0.5,
        "caught_heat_delta": 0.9,
        "trace_success": 4.0,
        "trace_caught": 10.0,
        "stk_cost": 200,
        "cooldown": 4.0,
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


MAYOR_ACTION_HEAT: dict[MayorAction, float] = {
    MayorAction.SURVEIL:        1.0,  # watching — low tension
    MayorAction.TRACE_MARK:     1.0,  # marking for trace — low tension
    MayorAction.JAM:            2.0,  # signal disruption — medium
    MayorAction.CURFEW:         2.0,  # city-wide order — medium
    MayorAction.AUDIT_PULSE:    2.0,  # system scan — medium
    MayorAction.SHIVA_THROTTLE: 2.0,  # collective punishment — medium
    MayorAction.STK_DRAIN:      2.0,  # economic attack — medium
    MayorAction.ACTION_BAN:     2.0,  # restriction decree — medium
    MayorAction.JAIL:           3.0,  # full arrest — high tension
    MayorAction.MOST_WANTED:    3.0,  # public bounty — high tension
}


ACTION_TRADEOFFS: dict[CitizenAction, dict[str, object]] = {
    CitizenAction.SNIFF: {
        "role": "recon",
        "impact": 2,
        "risk": 3,
        "trace_pressure": 3,
        "best_when": "trace is manageable and reconnaissance pressure is useful",
    },
    CitizenAction.JAM_SCAN: {
        "role": "disrupt",
        "impact": 3,
        "risk": 4,
        "trace_pressure": 4,
        "best_when": "server catch pressure is high enough to justify a risky disruption",
    },
    CitizenAction.DECOY_SIGNAL: {
        "role": "setup",
        "impact": 1,
        "risk": 2,
        "trace_pressure": 2,
        "best_when": "preparing a safer future action or avoiding predictable patterns",
    },
    CitizenAction.COVER_TRACKS: {
        "role": "recover",
        "impact": 0,
        "risk": 1,
        "trace_pressure": -3,
        "best_when": "trace is high, especially above 45, and continued action would invite punishment",
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
        f"impact={ACTION_TRADEOFFS[action]['impact']}, "
        f"risk={ACTION_TRADEOFFS[action]['risk']}, "
        f"trace={ACTION_TRADEOFFS[action]['trace_pressure']}, "
        f"use={ACTION_TRADEOFFS[action]['best_when']}"
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
        hint = "JAMMED: active actions are blocked. You may change mode (e.g. switch to MINE to earn STK) or HOLD."
    elif sleeping:
        hint = "SLEEPING: active actions are blocked while in SLEEP mode. Switch to MINE or SYNC to act, or HOLD to keep recovering trace."
    elif on_cooldown:
        hint = (
            f"COOLDOWN: action blocked for {cooldown_remaining:.0f}s. Change mode or HOLD — do NOT attempt an action right now."
        )
    else:
        hint = (
            "STK is your action currency (costs: COVER_TRACKS=100, DECOY_SIGNAL=200, SNIFF=500, JAM_SCAN=1000). "
            "MINE refills STK fast (+12/s). Only pick from affordable_actions. "
            "At low trace, prefer impact actions. At high trace, reduce exposure. "
            "COVER_TRACKS is recovery, not the default aggressive move. "
            "Switch to MINE if STK is low; switch to SYNC to build SHIVA and reduce trace."
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
        "allowed_modes": [] if jailed else [mode.value for mode in CitizenMode],
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
    for target_id in decree.targets:
        citizen = state.citizens.get(target_id)
        if citizen is None:
            continue
        duration = max(1, decree.duration_seconds)
        if decree.action == MayorAction.JAIL:
            citizen.queued_mode = citizen.mode  # save pre-jail mode for restoration
            _add_status(citizen, StatusEffect.JAILED, state.now + duration)
        elif decree.action == MayorAction.JAM:
            _add_status(citizen, StatusEffect.JAMMED, state.now + duration)
        elif decree.action in {MayorAction.SURVEIL, MayorAction.TRACE_MARK, MayorAction.MOST_WANTED}:
            _add_status(citizen, StatusEffect.SURVEILLED, state.now + duration)
        elif decree.action == MayorAction.STK_DRAIN:
            citizen.stk = max(0.0, citizen.stk - 500.0)
        heat_delta = MAYOR_ACTION_HEAT.get(decree.action, 1.0)
        state.heat = _clamp(state.heat + heat_delta, 0.0, 100.0)
        events.append(
            GameEvent(
                event_id=str(uuid.uuid4()),
                tick=tick,
                game_hour=state.game_hour,
                kind="mayor_decree",
                message=f"Mayor applied {decree.action.value} to {target_id}.",
                payload={"target": target_id, "action": decree.action.value, "rationale": decree.rationale, "heat_delta": heat_delta},
                public=True,
            )
        )
    if decree.action == MayorAction.SHIVA_THROTTLE:
        for citizen in state.citizens.values():
            citizen.shiva = max(0.0, citizen.shiva - 5.0)
    return events


def _apply_mode_change(state: CityState, citizen: Citizen, decision: CitizenDecision, tick: int) -> EngineResult:
    result = EngineResult()
    if decision.mode is None:
        return _invalid_decision(state, citizen, "Mode change did not include target mode.", tick)
    if citizen.has_status(StatusEffect.JAILED, state.now):
        return _invalid_decision(state, citizen, "Jailed: no mode changes. Pre-jail mode restores on release.", tick)
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
    if citizen.has_status(StatusEffect.GHOSTED, state.now):
        p_catch -= 0.16
    if state.server_scan_jammed_until > state.now:
        p_catch -= 0.15
    p_catch += citizen.trace * 0.003
    p_catch -= citizen.shiva * 0.004
    return _clamp(p_catch, 0.05, 0.95)


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


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))
