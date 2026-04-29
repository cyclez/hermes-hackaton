from __future__ import annotations

from copy import deepcopy

from src.server.models import CityState, GameEvent


POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
  game_id UUID PRIMARY KEY,
  season_seconds INTEGER NOT NULL,
  started_at DOUBLE PRECISION NOT NULL,
  now DOUBLE PRECISION NOT NULL,
  heat DOUBLE PRECISION NOT NULL,
  server_scan_jammed_until DOUBLE PRECISION NOT NULL DEFAULT 0,
  mayor_next_tick_at DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS citizens (
  citizen_id TEXT PRIMARY KEY,
  game_id UUID NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
  behavior TEXT NOT NULL,
  mode TEXT NOT NULL,
  queued_mode TEXT,
  stk DOUBLE PRECISION NOT NULL,
  shiva DOUBLE PRECISION NOT NULL,
  trace DOUBLE PRECISION NOT NULL,
  last_decision_at DOUBLE PRECISION NOT NULL,
  action_cooldown_until DOUBLE PRECISION NOT NULL,
  statuses JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS events (
  event_id UUID PRIMARY KEY,
  game_id UUID NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
  tick INTEGER NOT NULL,
  game_hour DOUBLE PRECISION NOT NULL,
  kind TEXT NOT NULL,
  message TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  public BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dossiers (
  dossier_id UUID PRIMARY KEY,
  game_id UUID NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
  heat DOUBLE PRECISION NOT NULL,
  targets JSONB NOT NULL,
  created_at DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS mayor_decrees (
  decree_id UUID PRIMARY KEY,
  game_id UUID NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
  action TEXT NOT NULL,
  targets JSONB NOT NULL,
  rationale TEXT NOT NULL,
  duration_seconds INTEGER NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS jobs (
  job_id UUID PRIMARY KEY,
  kind TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'PENDING',
  payload JSONB NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  locked_by TEXT,
  locked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_jobs_claim
  ON jobs (kind, status, created_at);

CREATE TABLE IF NOT EXISTS worker_heartbeats (
  worker_id TEXT PRIMARY KEY,
  worker_kind TEXT NOT NULL,
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  meta JSONB NOT NULL DEFAULT '{}'::jsonb
);
"""


POSTGRES_CLAIM_JOB_SQL = """
WITH next_jobs AS (
  SELECT job_id
  FROM jobs
  WHERE kind = %(kind)s AND status = 'PENDING'
  ORDER BY created_at
  FOR UPDATE SKIP LOCKED
  LIMIT %(limit)s
)
UPDATE jobs
SET status = 'RUNNING',
    attempts = attempts + 1,
    locked_by = %(worker_id)s,
    locked_at = now(),
    updated_at = now()
WHERE job_id IN (SELECT job_id FROM next_jobs)
RETURNING *;
"""


class InMemoryStore:
    """Test-only store; Postgres schema above is the production contract."""

    def __init__(self) -> None:
        self.state: CityState | None = None
        self.events: list[GameEvent] = []

    def save_state(self, state: CityState) -> None:
        self.state = deepcopy(state)

    def load_state(self) -> CityState:
        if self.state is None:
            raise RuntimeError("No game state has been saved.")
        return deepcopy(self.state)

    def append_events(self, events: list[GameEvent]) -> None:
        self.events.extend(deepcopy(events))

    def public_events(self) -> list[GameEvent]:
        return [event for event in self.events if event.public]
