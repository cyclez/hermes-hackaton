from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents.profiles import ensure_profiles
from src.agents.runner import LiveAgentRunner
from src.server.config import Settings
from src.server.game_engine import (
    apply_citizen_decision,
    apply_mayor_decree,
    build_citizen_observation,
    create_initial_state,
)
from src.server.models import CitizenAction, CitizenDecision, Dossier, DossierTarget, to_plain


def synthetic_dossier(state, decision: CitizenDecision) -> Dossier:
    citizen = state.citizens["citizen-001"]
    action = decision.action or CitizenAction.DECOY_SIGNAL
    return Dossier(
        dossier_id="phase4-eval-dossier",
        created_at=state.now,
        heat=state.heat,
        targets=[
            DossierTarget(
                citizen_id=citizen.citizen_id,
                action=action,
                p_catch=0.55,
                trace=max(45.0, citizen.trace),
                shiva=citizen.shiva,
                evidence=f"{citizen.citizen_id} produced a medium-confidence {action.value} leak.",
            )
        ],
    )


def main() -> None:
    settings = Settings.load()
    if settings.llm_provider.lower() == "ollama":
        from src.agents.llm_client import LLMClient

        models = LLMClient(settings).list_ollama_models()
        required = {settings.citizens_model, settings.mayor_model}
        missing = sorted(model for model in required if model not in models)
        if missing:
            raise SystemExit(f"Missing Ollama models: {', '.join(missing)}")

    ensure_profiles(settings.citizen_count)
    state = create_initial_state(settings.citizen_count, settings.season_seconds)
    runner = LiveAgentRunner(settings)

    observation = build_citizen_observation(state, "citizen-001")
    citizen_decision = runner.decide_citizen("citizen-001", observation)
    citizen_result = apply_citizen_decision(state, citizen_decision, tick=1, rng=random.Random(4))

    dossier = citizen_result.dossiers[0] if citizen_result.dossiers else synthetic_dossier(state, citizen_decision)
    mayor_decree = runner.decide_mayor(
        to_plain(dossier),
        allowed_targets=set(state.citizens),
        behavior="optimizer",
    )
    mayor_events = apply_mayor_decree(state, mayor_decree, tick=2)

    print("phase4_live_eval=ok")
    print(f"provider={settings.llm_provider}")
    print(f"citizens_model={settings.citizens_model}")
    print(f"mayor_model={settings.mayor_model}")
    print(f"llm_temperature={settings.llm_temperature}")
    print(f"llm_max_tokens={settings.llm_max_tokens}")
    print(f"openrouter_reasoning_effort={settings.openrouter_reasoning_effort}")
    print(f"citizen_attempts={runner.last_citizen_attempts}")
    print(f"citizen_seconds={runner.last_citizen_elapsed_seconds:.2f}")
    print(f"citizen_usage={runner.last_citizen_usage}")
    print(f"citizen_decision={to_plain(citizen_decision)}")
    print(f"citizen_events={len(citizen_result.events)}")
    print(f"dossiers={len(citizen_result.dossiers)}")
    print(f"dossier_action={dossier.targets[0].action.value}")
    print(f"mayor_attempts={runner.last_mayor_attempts}")
    print(f"mayor_seconds={runner.last_mayor_elapsed_seconds:.2f}")
    print(f"mayor_usage={runner.last_mayor_usage}")
    print(f"mayor_decree={to_plain(mayor_decree)}")
    print(f"mayor_events={len(mayor_events)}")
    print(f"heat={state.heat:.2f}")


if __name__ == "__main__":
    main()
