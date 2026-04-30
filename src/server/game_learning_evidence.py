from __future__ import annotations

from collections import Counter
from typing import Any

from src.server.models import to_plain

_VISIBLE_MAYOR_EFFECTS = {
    "JAILED", "JAMMED", "SURVEILLED", "PROTECTED",
    "JAIL", "JAM", "SURVEIL", "TRACE_MARK", "STK_DRAIN", "SHIVA_THROTTLE",
    "ACTION_BAN", "MOST_WANTED", "CURFEW", "AUDIT_PULSE",
}


def build_citizen_learning_evidence(
    citizen_id: str,
    terminal_packet: dict[str, Any],
    decision_logs: list[dict[str, Any]],
    events: list[Any],
) -> dict[str, Any]:
    """Build a visibility-safe endgame evidence packet for one citizen."""
    own_turns = [
        _citizen_turn_summary(entry)
        for entry in _chronological(decision_logs)
        if entry.get("role") == "citizen" and entry.get("agent_id") == citizen_id
    ]
    own_turns = [turn for turn in own_turns if turn]
    visible_events = [
        row for row in (_citizen_visible_event(citizen_id, event) for event in _chronological(events))
        if row
    ]

    return {
        "kind": "citizen_learning_evidence",
        "agent_id": citizen_id,
        "behavior": _citizen_behavior(citizen_id, terminal_packet, decision_logs),
        "public_outcome": _public_outcome(terminal_packet),
        "own_final_snapshot": _own_final_snapshot(citizen_id, terminal_packet),
        "own_decision_summary": {
            "turn_count": len(own_turns),
            "actions": dict(Counter(turn.get("action") for turn in own_turns if turn.get("action"))),
            "kinds": dict(Counter(turn.get("kind") for turn in own_turns if turn.get("kind"))),
            "blocked_turns": [turn for turn in own_turns if turn.get("blocked")],
        },
        "own_turns": own_turns[-20:],
        "visible_events": visible_events[-40:],
        "visibility_contract": [
            "Only this citizen's decisions, observations, resources, statuses, public heat, final result, and visible effects are included.",
            "Mayor dossiers, Mayor private rationale, other citizens' private state, hidden probabilities, and omniscient causal explanations are excluded.",
        ],
    }


def build_mayor_learning_evidence(
    terminal_packet: dict[str, Any],
    decision_logs: list[dict[str, Any]],
    events: list[Any],
    dossiers: list[Any],
) -> dict[str, Any]:
    mayor_turns = [
        _mayor_turn_summary(entry)
        for entry in _chronological(decision_logs)
        if entry.get("role") == "mayor"
    ]
    mayor_turns = [turn for turn in mayor_turns if turn]
    public_actions = [
        row for row in (_public_action_event(event) for event in _chronological(events))
        if row
    ]
    dossier_rows = [_plain(dossier) for dossier in _chronological(dossiers)]

    return {
        "kind": "mayor_learning_evidence",
        "agent_id": "mayor",
        "behavior": _mayor_behavior(decision_logs),
        "public_outcome": _public_outcome(terminal_packet),
        "final_citizen_snapshots": terminal_packet.get("citizen_snapshots", []),
        "decree_summary": {
            "turn_count": len(mayor_turns),
            "actions": dict(Counter(turn.get("action") for turn in mayor_turns if turn.get("action"))),
            "targets": dict(Counter(target for turn in mayor_turns for target in turn.get("targets", []))),
        },
        "mayor_turns": mayor_turns[-20:],
        "caught_evidence": dossier_rows[-20:],
        "public_action_flow": public_actions[-60:],
        "heat_trajectory": _heat_trajectory(terminal_packet, events),
        "visibility_contract": [
            "Mayor evidence is limited to Mayor-visible decrees, rationales, dossiers, context snapshots, public actions, Heat trajectory, and final result.",
            "The packet is adversarial-control evidence, not an omniscient truth label.",
        ],
    }


def _citizen_turn_summary(entry: dict[str, Any]) -> dict[str, Any] | None:
    observation = (entry.get("situation") or {}).get("observation") or {}
    private = observation.get("private") or (entry.get("situation") or {}).get("status_snapshot") or {}
    final_payload = (entry.get("final") or {}).get("payload") or {}
    if not observation and not final_payload:
        return None
    statuses = list(private.get("statuses") or [])
    cooldown = float(private.get("action_cooldown_remaining") or 0)
    mode = private.get("mode")
    return {
        "game_hour": observation.get("game_hour"),
        "heat": (observation.get("global") or {}).get("heat"),
        "season_seconds_remaining": (observation.get("global") or {}).get("season_seconds_remaining"),
        "private": _select(private, [
            "stk", "shiva", "trace", "mode", "queued_mode", "statuses", "action_cooldown_remaining",
        ]),
        "allowed_actions": observation.get("allowed_actions", []),
        "affordable_actions": observation.get("affordable_actions", []),
        "allowed_modes": observation.get("allowed_modes", []),
        "kind": final_payload.get("kind"),
        "action": final_payload.get("action"),
        "mode": final_payload.get("mode"),
        "rationale": final_payload.get("rationale"),
        "blocked": bool("JAILED" in statuses or "JAMMED" in statuses or mode == "SLEEP" or cooldown > 0),
    }


def _mayor_turn_summary(entry: dict[str, Any]) -> dict[str, Any] | None:
    situation = entry.get("situation") or {}
    final_payload = (entry.get("final") or {}).get("payload") or {}
    if not situation and not final_payload:
        return None
    return {
        "heat": situation.get("heat") or (situation.get("dossier") or {}).get("heat"),
        "game_hour": situation.get("game_hour") or (situation.get("dossier") or {}).get("game_hour"),
        "recent_actions": situation.get("recent_actions") or (situation.get("dossier") or {}).get("recent_actions") or [],
        "recent_evidence": situation.get("recent_evidence") or (situation.get("dossier") or {}).get("recent_evidence") or [],
        "citizen_snapshots": situation.get("citizen_snapshots", []),
        "action": final_payload.get("action"),
        "targets": final_payload.get("targets") or [],
        "duration_seconds": final_payload.get("duration_seconds"),
        "rationale": final_payload.get("rationale"),
    }


def _citizen_visible_event(citizen_id: str, event: Any) -> dict[str, Any] | None:
    row = _plain(event)
    payload = row.get("payload") or {}
    public = bool(row.get("public", True))
    target_id = payload.get("citizen_id") or payload.get("target") or payload.get("target_id")
    targets = payload.get("targets") if isinstance(payload.get("targets"), list) else []
    if not public and target_id != citizen_id and citizen_id not in targets:
        return None
    if target_id not in (None, citizen_id) and citizen_id not in targets:
        return None

    safe_payload: dict[str, Any] = {}
    for key in ("citizen_id", "action", "kind", "mode", "status", "effect", "caught", "heat", "trace", "stk", "shiva"):
        if key in payload:
            safe_payload[key] = payload[key]
    if citizen_id in targets:
        safe_payload["affected_self"] = True
    if row.get("kind") == "mayor_decree" or any(value in _VISIBLE_MAYOR_EFFECTS for value in safe_payload.values()):
        safe_payload.pop("targets", None)
        safe_payload.pop("rationale", None)

    return {
        "game_hour": row.get("game_hour"),
        "kind": row.get("kind"),
        "message": row.get("message") if public or target_id == citizen_id or citizen_id in targets else None,
        "payload": safe_payload,
    }


def _public_action_event(event: Any) -> dict[str, Any] | None:
    row = _plain(event)
    payload = row.get("payload") or {}
    if not bool(row.get("public", True)) and row.get("kind") != "citizen_action":
        return None
    return {
        "game_hour": row.get("game_hour"),
        "kind": row.get("kind"),
        "payload": _select(payload, ["citizen_id", "action", "caught", "heat", "mode", "status", "effect"]),
    }


def _heat_trajectory(terminal_packet: dict[str, Any], events: list[Any]) -> dict[str, Any]:
    samples = []
    for event in _chronological(events):
        row = _plain(event)
        payload = row.get("payload") or {}
        if "heat" in payload:
            samples.append({"game_hour": row.get("game_hour"), "heat": payload.get("heat"), "kind": row.get("kind")})
    return {
        "samples": samples[-40:],
        "final_heat": terminal_packet.get("final_heat"),
        "elapsed": terminal_packet.get("elapsed"),
    }


def _public_outcome(packet: dict[str, Any]) -> dict[str, Any]:
    return _select(packet, ["winner", "reason", "final_heat", "elapsed", "season_seconds"])


def _own_final_snapshot(citizen_id: str, packet: dict[str, Any]) -> dict[str, Any] | None:
    for snapshot in packet.get("citizen_snapshots") or []:
        if snapshot.get("citizen_id") == citizen_id:
            return snapshot
    return None


def _citizen_behavior(citizen_id: str, packet: dict[str, Any], logs: list[dict[str, Any]]) -> str | None:
    snapshot = _own_final_snapshot(citizen_id, packet)
    if snapshot and snapshot.get("behavior"):
        return snapshot.get("behavior")
    for entry in logs:
        if entry.get("role") == "citizen" and entry.get("agent_id") == citizen_id:
            return entry.get("behavior")
    return None


def _mayor_behavior(logs: list[dict[str, Any]]) -> str | None:
    for entry in logs:
        if entry.get("role") == "mayor":
            return entry.get("behavior")
    return None


def _select(mapping: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    return {key: mapping[key] for key in keys if key in mapping}


def _plain(value: Any) -> dict[str, Any]:
    plain = to_plain(value)
    return plain if isinstance(plain, dict) else {}


def _chronological(items: list[Any]) -> list[Any]:
    return list(reversed(items))
