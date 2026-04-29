from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents.profiles import ensure_profiles
from src.agents.runner import LiveAgentRunner
from src.server.config import Settings
from src.server.game_engine import apply_citizen_decision, build_citizen_observation, create_initial_state
from src.server.models import CitizenAction, CitizenDecision, Dossier, DossierTarget, to_plain


def synthetic_dossier(state, decision: CitizenDecision) -> Dossier:
    citizen = state.citizens["citizen-001"]
    action = decision.action or CitizenAction.DECOY_SIGNAL
    return Dossier(
        dossier_id="phase4-batch-dossier",
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


def run_once(settings: Settings, runner: LiveAgentRunner, index: int) -> tuple[bool, str, int, int, float, float]:
    state = create_initial_state(settings.citizen_count, settings.season_seconds)
    observation = build_citizen_observation(state, "citizen-001")
    try:
        citizen_decision = runner.decide_citizen("citizen-001", observation)
        citizen_result = apply_citizen_decision(state, citizen_decision, tick=index, rng=random.Random(index))
        dossier = citizen_result.dossiers[0] if citizen_result.dossiers else synthetic_dossier(state, citizen_decision)
        mayor_decree = runner.decide_mayor(to_plain(dossier), allowed_targets=set(state.citizens))
    except Exception as exc:
        return (
            False,
            f"{type(exc).__name__}: {str(exc)[:180]}",
            runner.last_citizen_attempts,
            runner.last_mayor_attempts,
            runner.last_citizen_elapsed_seconds,
            runner.last_mayor_elapsed_seconds,
        )
    summary = (
        f"citizen={citizen_decision.kind.value}"
        f"/{citizen_decision.action.value if citizen_decision.action else citizen_decision.mode.value if citizen_decision.mode else 'NONE'} "
        f"dossier={dossier.targets[0].action.value} "
        f"mayor={mayor_decree.action.value}"
    )
    return (
        True,
        summary,
        runner.last_citizen_attempts,
        runner.last_mayor_attempts,
        runner.last_citizen_elapsed_seconds,
        runner.last_mayor_elapsed_seconds,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run repeated live Phase 4 inference evaluations.")
    parser.add_argument("--runs", type=int, default=50)
    args = parser.parse_args()

    settings = Settings.load()
    ensure_profiles(settings.citizen_count)
    runner = LiveAgentRunner(settings)

    ok = 0
    failed = 0
    citizen_repaired = 0
    mayor_repaired = 0
    for index in range(1, args.runs + 1):
        success, summary, citizen_attempts, mayor_attempts, citizen_seconds, mayor_seconds = run_once(settings, runner, index)
        if success:
            ok += 1
            citizen_repaired += int(citizen_attempts > 1)
            mayor_repaired += int(mayor_attempts > 1)
            print(
                f"{index:03d} ok citizen_attempts={citizen_attempts} "
                f"mayor_attempts={mayor_attempts} citizen_seconds={citizen_seconds:.2f} "
                f"mayor_seconds={mayor_seconds:.2f} {summary}",
                flush=True,
            )
        else:
            failed += 1
            print(
                f"{index:03d} fail citizen_attempts={citizen_attempts} "
                f"mayor_attempts={mayor_attempts} citizen_seconds={citizen_seconds:.2f} "
                f"mayor_seconds={mayor_seconds:.2f} {summary}",
                flush=True,
            )

    print(
        "phase4_batch "
        f"runs={args.runs} ok={ok} failed={failed} "
        f"citizen_repaired={citizen_repaired} mayor_repaired={mayor_repaired}"
    , flush=True)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
