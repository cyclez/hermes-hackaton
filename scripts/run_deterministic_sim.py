from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.server.config import Settings
from src.server.game_engine import advance_tick, apply_citizen_decision, create_initial_state
from src.server.models import CitizenAction, CitizenDecision, CitizenMode, DecisionKind


def choose_deterministic_decision(citizen_id: str, index: int) -> CitizenDecision:
    actions = [
        CitizenAction.SNIFF,
        CitizenAction.JAM_SCAN,
        CitizenAction.DECOY_SIGNAL,
        CitizenAction.COVER_TRACKS,
    ]
    if index % 11 == 0:
        return CitizenDecision(citizen_id=citizen_id, kind=DecisionKind.MODE_CHANGE, mode=CitizenMode.SYNC)
    if index % 17 == 0:
        return CitizenDecision(citizen_id=citizen_id, kind=DecisionKind.MODE_CHANGE, mode=CitizenMode.MINE)
    return CitizenDecision(citizen_id=citizen_id, kind=DecisionKind.ACTION, action=actions[index % len(actions)])


def main() -> None:
    settings = Settings.load()
    state = create_initial_state(settings.citizen_count, settings.season_seconds)
    rng = random.Random(7)
    events = []
    dossiers = []
    decision_index = 0
    total_ticks = int(settings.season_seconds)
    for tick in range(1, total_ticks + 1):
        events.extend(advance_tick(state, settings.server_tick_seconds, tick).events)
        if tick % 10 == 0:
            for citizen_id in sorted(state.citizens):
                decision_index += 1
                result = apply_citizen_decision(
                    state,
                    choose_deterministic_decision(citizen_id, decision_index),
                    tick=tick,
                    rng=rng,
                )
                events.extend(result.events)
                dossiers.extend(result.dossiers)
        if state.is_finished:
            break
    public_actions = [event for event in events if event.kind == "citizen_action"]
    print(
        "deterministic_sim "
        f"ticks={tick} citizens={len(state.citizens)} heat={state.heat:.2f} "
        f"actions={len(public_actions)} dossiers={len(dossiers)} finished={state.is_finished}"
    )


if __name__ == "__main__":
    main()
