"""Background worker: takes jobs from the PostgreSQL `jobs` table and runs them.

Job kinds:
- ocr   {version_id}: auto-fill a stored version (dbresearch.autofill.pipeline)

Logs never contain document text, only ids and counts (CLAUDE.md).
"""

import logging
import signal
import time
import uuid

from dbresearch import jobs
from dbresearch.config import get_settings
from dbresearch.db import new_session
from dbresearch.models import DocStatus, Document, DocumentVersion, Job, OcrStatus

log = logging.getLogger("dbresearch.worker")
_running = True


def _stop(signum, _frame) -> None:
    global _running
    log.info("signal %s: finishing the current job, then stopping", signum)
    _running = False


def run_job(job: Job) -> None:
    if job.kind == "ocr":
        from dbresearch.autofill.pipeline import process_version  # heavy imports: lazy

        with new_session() as db:
            process_version(db, uuid.UUID(job.payload["version_id"]))
    else:
        raise ValueError(f"unknown job kind {job.kind!r}")


def give_up(job: Job, error: str) -> None:
    """OCR failed for good: let the user fill the metadata by hand instead of blocking."""
    if job.kind != "ocr":
        return
    with new_session() as db:
        version = db.get(DocumentVersion, uuid.UUID(job.payload["version_id"]))
        if version is None:
            return
        version.ocr_status = OcrStatus.FAILED
        version.extracted_fields = {"warnings": [{"code": "ocr_failed", "error": error[:200]}]}
        document = db.get(Document, version.document_id)
        if document.current_version_id == version.id and document.status == DocStatus.PROCESSING:
            document.status = DocStatus.NEEDS_REVIEW
        db.commit()


def run_once() -> bool:
    """Process one job if any is due. Returns True if a job was taken."""
    with new_session() as db:
        job = jobs.claim(db)
        if job is None:
            return False
        log.info("job %s (%s) attempt %d", job.id, job.kind, job.attempts)
        try:
            run_job(job)
        except Exception as exc:
            db.rollback()
            error = f"{type(exc).__name__}: {exc}"
            log.exception("job %s failed", job.id)
            if not jobs.fail(db, job, error):
                give_up(job, error)
            return True
        jobs.finish(db, job)
        return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    idle = get_settings().worker_idle_seconds
    log.info("worker started")
    while _running:
        if not run_once():
            time.sleep(idle)


if __name__ == "__main__":
    main()
