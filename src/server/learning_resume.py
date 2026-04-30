from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.agents.hermes_runner import HermesAgentRunner
from src.server.config import Settings
from src.server.decision_log_store import DecisionLogStore
from src.server.game_learning_evidence import build_citizen_learning_evidence, build_mayor_learning_evidence


FINALIZED_ROOT = Path(".runtime") / "finalized-games"
LEARNING_EVENT_LIMIT = 2000
LEARNING_DOSSIER_LIMIT = 2000


@dataclass(frozen=True)
class LearningAgent:
    role: str
    agent_id: str
    behavior: str


def completed_learning_agents(decision_logs: list[dict[str, Any]]) -> set[str]:
    completed: set[str] = set()
    for entry in decision_logs:
        role = entry.get("role")
        if role == "citizen_learning" and entry.get("agent_id"):
            completed.add(str(entry["agent_id"]))
        elif role == "mayor_learning":
            completed.add("mayor")
    return completed


def planned_learning_agents(
    terminal_packet: dict[str, Any],
    decision_logs: list[dict[str, Any]],
    *,
    skip: set[str] | None = None,
    include_existing: bool = False,
) -> list[LearningAgent]:
    manual_skip = skip or set()
    completed = set() if include_existing else completed_learning_agents(decision_logs)
    agents: list[LearningAgent] = []

    for snapshot in terminal_packet.get("citizen_snapshots") or []:
        citizen_id = snapshot.get("citizen_id")
        if not citizen_id:
            continue
        citizen_id = str(citizen_id)
        if citizen_id in manual_skip or citizen_id in completed:
            continue
        agents.append(LearningAgent(
            role="citizen",
            agent_id=citizen_id,
            behavior=str(snapshot.get("behavior") or "aggressive"),
        ))

    if "mayor" not in manual_skip and "mayor" not in completed:
        agents.append(LearningAgent(
            role="mayor",
            agent_id="mayor",
            behavior=_mayor_behavior(decision_logs) or "optimizer",
        ))

    return agents


async def resume_learning_for_game(
    game_id: str,
    *,
    skip: set[str] | None = None,
    include_existing: bool = False,
    settings: Settings | None = None,
    finalized_root: Path = FINALIZED_ROOT,
    decision_log_store: DecisionLogStore | None = None,
    runner: HermesAgentRunner | None = None,
) -> dict[str, Any]:
    settings = settings or Settings.load()
    if settings.llm_provider.lower() != "ollama" and settings.openrouter_api_key:
        os.environ.setdefault("OPENROUTER_API_KEY", settings.openrouter_api_key)

    log_store = decision_log_store or DecisionLogStore()
    runner = runner or HermesAgentRunner(settings)
    packet = _read_terminal_packet(finalized_root, game_id)
    decision_logs = log_store.read_entries(game_id, limit=0)
    agents = planned_learning_agents(
        packet,
        decision_logs,
        skip=skip,
        include_existing=include_existing,
    )

    from src.server.postgres_store import PostgresStore

    store = PostgresStore(settings.database_url)
    try:
        await store.connect()
        events = await store.get_events(game_id, limit=LEARNING_EVENT_LIMIT)
        dossiers = await store.get_recent_dossiers(game_id, limit=LEARNING_DOSSIER_LIMIT)
    finally:
        await store.close()

    results: list[dict[str, Any]] = []
    completed_ok = False
    try:
        for agent in agents:
            if agent.role == "citizen":
                evidence = build_citizen_learning_evidence(agent.agent_id, packet, decision_logs, events)
                result = runner.learn_citizen_from_game(agent.agent_id, agent.behavior, evidence, game_id)
            else:
                evidence = build_mayor_learning_evidence(packet, decision_logs, events, dossiers)
                result = runner.learn_mayor_from_game(agent.behavior, evidence, game_id)
            results.append({
                "agent_id": agent.agent_id,
                "role": f"{agent.role}_learning",
                "ok": bool(result.get("ok")),
            })
            decision_logs = log_store.read_entries(game_id, limit=0)

        payload = {
            "game_id": game_id,
            "learning_completed_at": time.time(),
            "resumed": True,
            "skipped": sorted(skip or set()),
            "include_existing": include_existing,
            "results": results,
        }
        _write_json_atomic(_completed_path(finalized_root, game_id), payload)
        completed_ok = True
        return payload
    except Exception as exc:
        payload = {
            "game_id": game_id,
            "failed_at": time.time(),
            "resumed": True,
            "error": str(exc),
            "results": results,
        }
        _write_json_atomic(_failed_path(finalized_root, game_id), payload)
        raise
    finally:
        if not completed_ok and not results:
            # Keep a marker for failures that occur before the first agent call.
            failed_path = _failed_path(finalized_root, game_id)
            if not failed_path.exists():
                _write_json_atomic(failed_path, {
                    "game_id": game_id,
                    "failed_at": time.time(),
                    "resumed": True,
                    "error": "resume did not complete",
                    "results": results,
                })


def _read_terminal_packet(root: Path, game_id: str) -> dict[str, Any]:
    path = root / game_id / "terminal-packet.json"
    if not path.exists():
        raise FileNotFoundError(f"terminal packet not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _completed_path(root: Path, game_id: str) -> Path:
    return root / game_id / "learning-completed.json"


def _failed_path(root: Path, game_id: str) -> Path:
    return root / game_id / "learning-failed.json"


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp-{uuid.uuid4()}")
    with temp_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=True, indent=2, sort_keys=True)
        fh.write("\n")
    temp_path.replace(path)


def _mayor_behavior(decision_logs: list[dict[str, Any]]) -> str | None:
    for entry in decision_logs:
        if entry.get("role") == "mayor" and entry.get("behavior"):
            return str(entry["behavior"])
    return None
