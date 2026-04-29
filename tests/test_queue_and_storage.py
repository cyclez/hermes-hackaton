from __future__ import annotations

import unittest

from src.server.game_engine import advance_tick, create_initial_state
from src.server.models import JobKind
from src.server.queue import InMemoryJobQueue
from src.server.storage import InMemoryStore, POSTGRES_CLAIM_JOB_SQL, POSTGRES_SCHEMA
from src.workers.scheduler import enqueue_due_citizen_jobs


class QueueAndStorageTests(unittest.TestCase):
    def test_postgres_schema_contains_required_tables_and_skip_locked_claim(self) -> None:
        for table in [
            "games",
            "citizens",
            "events",
            "dossiers",
            "mayor_decrees",
            "jobs",
            "worker_heartbeats",
        ]:
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", POSTGRES_SCHEMA)
        self.assertIn("FOR UPDATE SKIP LOCKED", POSTGRES_CLAIM_JOB_SQL)

    def test_scheduler_enqueues_configurable_citizen_jobs(self) -> None:
        state = create_initial_state(citizen_count=5)
        queue = InMemoryJobQueue()

        count = enqueue_due_citizen_jobs(state, queue)

        self.assertEqual(count, 5)
        self.assertEqual(queue.pending_count(JobKind.CITIZEN_DECISION), 5)

    def test_queue_claim_and_complete(self) -> None:
        queue = InMemoryJobQueue()
        queue.enqueue(JobKind.CITIZEN_DECISION, {"citizen_id": "citizen-001"})

        claimed = queue.claim(JobKind.CITIZEN_DECISION)
        self.assertEqual(len(claimed), 1)
        self.assertEqual(queue.pending_count(), 0)

        queue.complete(claimed[0].job_id)
        self.assertEqual(queue.pending_count(), 0)

    def test_in_memory_store_round_trips_state_and_public_events(self) -> None:
        state = create_initial_state(citizen_count=1)
        result = advance_tick(state, seconds=1)
        store = InMemoryStore()

        store.save_state(state)
        store.append_events(result.events)

        loaded = store.load_state()
        self.assertEqual(loaded.game_id, state.game_id)
        self.assertEqual(store.public_events(), [])


if __name__ == "__main__":
    unittest.main()
