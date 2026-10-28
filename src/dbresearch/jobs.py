"""PostgreSQL-backed job queue (no Redis): enqueue, claim with SKIP LOCKED, finish, retry."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from dbresearch.models import Job, JobState

MAX_ATTEMPTS = 3
# A job "running" longer than this was left behind by a crashed worker: hand it out again.
STALE_AFTER = timedelta(minutes=30)


def enqueue(db: Session, kind: str, **payload: Any) -> Job:
    job = Job(kind=kind, payload={k: str(v) for k, v in payload.items()})
    db.add(job)
    return job


def claim(db: Session) -> Job | None:
    """Take the next due job; other workers skip it while this transaction holds the lock."""
    now = datetime.now(UTC)
    due = or_(
        (Job.state == JobState.QUEUED) & (Job.run_after <= now),
        (Job.state == JobState.RUNNING) & (Job.updated_at < now - STALE_AFTER),
    )
    job = db.scalar(
        select(Job)
        .where(due)
        .order_by(Job.run_after, Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return None
    job.state = JobState.RUNNING
    job.attempts += 1
    job.updated_at = now
    db.commit()
    return job


def finish(db: Session, job: Job) -> None:
    db.execute(
        update(Job)
        .where(Job.id == job.id)
        .values(state=JobState.DONE, updated_at=datetime.now(UTC))
    )
    db.commit()


def fail(db: Session, job: Job, error: str) -> bool:
    """Record a failure; returns True if the job will be retried (with backoff)."""
    retry = job.attempts < MAX_ATTEMPTS
    now = datetime.now(UTC)
    db.execute(
        update(Job)
        .where(Job.id == job.id)
        .values(
            state=JobState.QUEUED if retry else JobState.FAILED,
            run_after=now + timedelta(minutes=2**job.attempts) if retry else now,
            last_error=error[:2000],
            updated_at=now,
        )
    )
    db.commit()
    return retry
