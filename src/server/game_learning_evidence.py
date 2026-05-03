from __future__ import annotations

from collections import Counter
from typing import Any

from src.server.models import to_plain

_VISIBLE_MAYOR_EFFECTS = {
    "JAILED", "JAMMED", "SURVEILLED", "PROTECTED",
    "JAIL", "JAM", "SURVEIL", "STK_DRAIN", "MOST_WANTED", "CURFEW",
}

_CITIZEN_ACTION_LESSONS = {
    "SNIFF": "Successful `SNIFF` can create a `GHOSTED` window before a higher-commitment action.",
    "JAM_SCAN": "When STK is available, successful `JAM_SCAN` can buy shared breathing room by lowering catch pressure.",
    "DECOY_SIGNAL": "Use `DECOY_SIGNAL` against live `SURVEILLED` pressure or to open a short anti-`SURVEIL` window, not as a generic safety button.",
    "COVER_TRACKS": "When trace is already elevated, `COVER_TRACKS` can preserve survival better than forcing another exposed action.",
}

_MAYOR_ACTION_LESSONS = {
    "SURVEIL": "Use `SURVEIL` as first-contact pressure on clean targets, not as a repeat decree into protected or already-targeted citizens.",
    "JAIL": "Use `JAIL` to convert strong evidence or terminal urgency into reliable tempo denial.",
    "JAM": "Use `JAM` when a citizen is cycling safe actions and a short full lock is worth more than soft pressure.",
    "STK_DRAIN": "Use `STK_DRAIN` on high-STK repeat operators; it cuts tempo and adds trace immediately.",
    "MOST_WANTED": "Escalate to `MOST_WANTED` when ordinary surveillance is no longer enough; it adds ongoing trace pressure.",
    "CURFEW": "Use `CURFEW` as Heat tempo support when targeted decrees are thin, not as a replacement for enforcement.",
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
        "candidate_lessons": _citizen_candidate_lessons(citizen_id, terminal_packet, events),
        "own_decision_summary": {
            "turn_count": len(own_turns),
            "actions": dict(Counter(turn.get("action") for turn in own_turns if turn.get("action"))),
            "kinds": dict(Counter(turn.get("kind") for turn in own_turns if turn.get("kind"))),
            "blocked_turn_count": sum(1 for turn in own_turns if turn.get("blocked")),
        },
        "own_turns": own_turns[-12:],
        "visible_events": visible_events[-24:],
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
        "candidate_lessons": _mayor_candidate_lessons(events),
        "decree_summary": {
            "turn_count": len(mayor_turns),
            "actions": dict(Counter(turn.get("action") for turn in mayor_turns if turn.get("action"))),
            "targets": dict(Counter(target for turn in mayor_turns for target in turn.get("targets", []))),
        },
        "mayor_turns": mayor_turns[-12:],
        "caught_evidence": dossier_rows[-12:],
        "public_action_flow": public_actions[-30:],
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
        "rationale": _clip_text(final_payload.get("rationale"), 140),
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
        "recent_actions": (situation.get("recent_actions") or (situation.get("dossier") or {}).get("recent_actions") or [])[-6:],
        "recent_evidence": (situation.get("recent_evidence") or (situation.get("dossier") or {}).get("recent_evidence") or [])[-6:],
        "citizen_snapshots": (situation.get("citizen_snapshots") or [])[-10:],
        "action": final_payload.get("action"),
        "targets": final_payload.get("targets") or [],
        "duration_seconds": final_payload.get("duration_seconds"),
        "rationale": _clip_text(final_payload.get("rationale"), 140),
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
        "message": _clip_text(row.get("message"), 140) if public or target_id == citizen_id or citizen_id in targets else None,
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
        "samples": samples[-30:],
        "final_heat": terminal_packet.get("final_heat"),
        "elapsed": terminal_packet.get("elapsed"),
    }


def _public_outcome(packet: dict[str, Any]) -> dict[str, Any]:
    return _select(packet, ["winner", "reason", "final_heat", "elapsed", "season_seconds"])


def _citizen_candidate_lessons(
    citizen_id: str,
    packet: dict[str, Any],
    events: list[Any],
) -> list[dict[str, str]]:
    counts: Counter[tuple[str, bool]] = Counter()
    for event in _chronological(events):
        row = _plain(event)
        if row.get("kind") != "citizen_action":
            continue
        payload = row.get("payload") or {}
        if payload.get("citizen_id") != citizen_id:
            continue
        action = str(payload.get("action") or "").strip()
        if not action:
            continue
        counts[(action, bool(payload.get("caught")))] += 1

    ranked_actions: list[tuple[str, int, int]] = []
    for action, lesson in _CITIZEN_ACTION_LESSONS.items():
        successes = counts.get((action, False), 0)
        failures = counts.get((action, True), 0)
        if successes <= 0:
            continue
        ranked_actions.append((action, successes, failures))
    ranked_actions.sort(key=lambda item: (-item[1], item[2], item[0]))

    candidates: list[dict[str, str]] = []
    for action, successes, failures in ranked_actions[:2]:
        candidates.append({
            "pattern": _CITIZEN_ACTION_LESSONS[action],
            "support": f"{successes} uncaught and {failures} caught `{action}` actions in this game.",
            "source": "successful_action_pattern",
        })

    snapshot = _own_final_snapshot(citizen_id, packet) or {}
    statuses = set(snapshot.get("statuses") or [])
    mode = snapshot.get("mode")
    shiva = float(snapshot.get("shiva") or 0.0)
    trace = float(snapshot.get("trace") or 0.0)
    if len(candidates) < 3 and mode == "SYNC" and shiva >= 60.0 and trace <= 20.0 and "JAILED" not in statuses:
        candidates.append({
            "pattern": "Late in a hostile board, `SYNC` plus high `SHIVA` can hold a survivable posture without feeding extra catches.",
            "support": f"Final snapshot ended in `SYNC` with SHIVA {shiva:.2f} and trace {trace:.2f}.",
            "source": "stable_endgame_posture",
        })

    return candidates[:3]


def _mayor_candidate_lessons(events: list[Any]) -> list[dict[str, str]]:
    applied_counts: Counter[str] = Counter()
    blocked_counts: Counter[str] = Counter()
    for event in _chronological(events):
        row = _plain(event)
        if row.get("kind") != "mayor_decree":
            continue
        payload = row.get("payload") or {}
        action = str(payload.get("action") or "").strip()
        if not action:
            continue
        if payload.get("applied") is True:
            applied_counts[action] += 1
        else:
            blocked_counts[action] += 1

    ranked = [
        (action, count, blocked_counts.get(action, 0))
        for action, count in applied_counts.items()
        if action in _MAYOR_ACTION_LESSONS
    ]
    ranked.sort(key=lambda item: (-item[1], item[2], item[0]))

    candidates: list[dict[str, str]] = []
    for action, applied, blocked in ranked[:3]:
        candidates.append({
            "pattern": _MAYOR_ACTION_LESSONS[action],
            "support": f"`{action}` applied {applied} times and was blocked {blocked} times in this game.",
            "source": "applied_decree_pattern",
        })
    return candidates


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


def _clip_text(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _select(mapping: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    return {key: mapping[key] for key in keys if key in mapping}


def _plain(value: Any) -> dict[str, Any]:
    plain = to_plain(value)
    return plain if isinstance(plain, dict) else {}


def _chronological(items: list[Any]) -> list[Any]:
    return list(reversed(items))
