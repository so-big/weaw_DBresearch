"""Background worker: takes jobs from the PostgreSQL `jobs` table and runs them.

Job kinds:
- ocr   {version_id}: auto-fill a stored version (dbresearch.autofill.pipeline)
- search_text {category_id}: rebuild search_text of the documents tagged with a category

Logs never contain document text, only ids and counts (CLAUDE.md).
"""

import logging
import signal
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert

from dbresearch import jobs, search_text
from dbresearch.config import get_settings
from dbresearch.db import new_session
from dbresearch.models import DocStatus, Document, DocumentVersion, Job, OcrStatus, Setting

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
    elif job.kind == "search_text":
        with new_session() as db:
            search_text.rebuild_for_category(db, uuid.UUID(job.payload["category_id"]))
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
        if document.current_version_id == version.id:
            # Nothing was read: keep the upload findable by its metadata and file name.
            document.search_text = search_text.build(db, document, extra=version.original_filename)
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


HEARTBEAT_KEY = "worker.heartbeat"  # read by GET /admin/health
HEARTBEAT_EVERY = 30.0  # seconds


def heartbeat() -> None:
    """Tell the admin overview this worker is alive (one upserted settings row)."""
    value = {"at": datetime.now(UTC).isoformat()}
    try:
        with new_session() as db:
            db.execute(
                insert(Setting)
                .values(key=HEARTBEAT_KEY, value=value)
                .on_conflict_do_update(index_elements=[Setting.key], set_={"value": value})
            )
            db.commit()
    except Exception:  # never let monitoring stop the job loop
        log.exception("heartbeat failed")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    idle = get_settings().worker_idle_seconds
    log.info("worker started")
    beat = 0.0
    while _running:
        if time.monotonic() - beat >= HEARTBEAT_EVERY:
            heartbeat()
            beat = time.monotonic()
        if not run_once():
            time.sleep(idle)


if __name__ == "__main__":
    main()
