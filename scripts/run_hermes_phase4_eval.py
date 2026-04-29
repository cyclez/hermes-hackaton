#!/usr/bin/env python3
"""Phase 4 validation: one citizen + one Mayor decision through Hermes AIAgent.

Run from project root:
    .venv/bin/python scripts/run_hermes_phase4_eval.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.hermes_runner import HermesAgentRunner
from src.server.config import Settings
from src.server.game_engine import build_citizen_observation, create_initial_state
from src.server.models import CitizenAction, Dossier, DossierTarget, to_plain

settings = Settings.load()
print(f"Provider: {settings.llm_provider}")
print(f"Citizens model: {settings.citizens_model}")
print(f"Mayor model:    {settings.mayor_model}")
print()

runner = HermesAgentRunner(settings)
state = create_initial_state(1, 600)
citizen_id = list(state.citizens.keys())[0]

# --- Citizen decision ---
observation = build_citizen_observation(state, citizen_id)
print(f"Testing citizen {citizen_id} decision via Hermes AIAgent ...")
t0 = time.monotonic()
try:
    decision = runner.decide_citizen(citizen_id, observation, "aggressive")
    elapsed = time.monotonic() - t0
    print(f"  kind={decision.kind}  action={decision.action}  elapsed={elapsed:.1f}s")
    print(f"  rationale: {decision.rationale[:120]}")
except Exception as exc:
    print(f"  FAILED: {exc}")
    sys.exit(1)

print()

# --- Mayor decision ---
dossier = Dossier(
    dossier_id="eval-1",
    created_at=0.0,
    heat=58.0,
    targets=[
        DossierTarget(
            citizen_id=citizen_id,
            action=CitizenAction.SNIFF,
            p_catch=0.45,
            trace=18.0,
            shiva=30.0,
            evidence=f"{citizen_id} was caught executing SNIFF.",
        )
    ],
)
dossier_dict = {
    "heat": dossier.heat,
    "game_hour": 6.0,
    "recent_evidence": [to_plain(dossier)],
    "active_citizens": [citizen_id],
}

print("Testing Mayor decision via Hermes AIAgent ...")
t0 = time.monotonic()
try:
    decree = runner.decide_mayor(dossier_dict, {citizen_id}, "optimizer")
    elapsed = time.monotonic() - t0
    print(f"  action={decree.action}  targets={decree.targets}  elapsed={elapsed:.1f}s")
    print(f"  rationale: {decree.rationale[:120]}")
except Exception as exc:
    print(f"  FAILED: {exc}")
    sys.exit(1)

print()
print("Phase 4 PASS — Hermes AIAgent integration verified.")
