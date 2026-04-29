from __future__ import annotations

from src.server.game_engine import build_citizen_observation, due_citizens
from src.server.models import CityState, JobKind
from src.server.queue import InMemoryJobQueue


def enqueue_due_citizen_jobs(state: CityState, queue: InMemoryJobQueue, *, min_interval: float = 10.0) -> int:
    count = 0
    for citizen in due_citizens(state, min_interval):
        queue.enqueue(
            JobKind.CITIZEN_DECISION,
            {
                "citizen_id": citizen.citizen_id,
                "observation": build_citizen_observation(state, citizen.citizen_id),
            },
        )
        count += 1
    return count
