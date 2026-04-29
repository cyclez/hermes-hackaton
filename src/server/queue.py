from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from src.server.models import JobKind, JobStatus


@dataclass
class Job:
    job_id: str
    kind: JobKind
    payload: dict[str, Any]
    status: JobStatus = JobStatus.PENDING
    attempts: int = 0


class InMemoryJobQueue:
    """Test-only queue with the same semantics as the Postgres job contract."""

    def __init__(self) -> None:
        self._jobs: list[Job] = []

    def enqueue(self, kind: JobKind, payload: dict[str, Any]) -> Job:
        job = Job(job_id=str(uuid.uuid4()), kind=kind, payload=payload)
        self._jobs.append(job)
        return job

    def claim(self, kind: JobKind, limit: int = 1) -> list[Job]:
        claimed: list[Job] = []
        for job in self._jobs:
            if len(claimed) >= limit:
                break
            if job.kind == kind and job.status == JobStatus.PENDING:
                job.status = JobStatus.RUNNING
                job.attempts += 1
                claimed.append(job)
        return claimed

    def complete(self, job_id: str) -> None:
        self._set_status(job_id, JobStatus.DONE)

    def fail(self, job_id: str) -> None:
        self._set_status(job_id, JobStatus.FAILED)

    def pending_count(self, kind: JobKind | None = None) -> int:
        return sum(
            1
            for job in self._jobs
            if job.status == JobStatus.PENDING and (kind is None or job.kind == kind)
        )

    def _set_status(self, job_id: str, status: JobStatus) -> None:
        for job in self._jobs:
            if job.job_id == job_id:
                job.status = status
                return
        raise KeyError(job_id)
