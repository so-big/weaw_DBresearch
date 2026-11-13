"""Background worker: runs OCR extraction and document processing.

Supports two operational backends:
1. Production Backend: MySQL Queue Adapter (CALL ocr_claim_job, ocr_heartbeat, etc.)
2. Development Backend: PostgreSQL jobs table (Local dev stack)

Logs never contain document text or passwords, only ids and counts (CLAUDE.md / AGENTS.md).
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
from dbresearch.settings_parser import get_mysql_config

log = logging.getLogger("dbresearch.worker")
_running = True


def _stop(signum, _frame) -> None:
    global _running
    log.info("signal %s: finishing the current job, then stopping", signum)
    _running = False


# ----------------------------------------------------------------------
# PostgreSQL Local Dev Worker Functions
# ----------------------------------------------------------------------
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
            document.search_text = search_text.build(db, document, extra=version.original_filename)
        db.commit()


def run_once_postgres() -> bool:
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


HEARTBEAT_KEY = "worker.heartbeat"
HEARTBEAT_EVERY = 30.0


def heartbeat_postgres() -> None:
    value = {"at": datetime.now(UTC).isoformat()}
    try:
        with new_session() as db:
            db.execute(
                insert(Setting)
                .values(key=HEARTBEAT_KEY, value=value)
                .on_conflict_do_update(index_elements=[Setting.key], set_={"value": value})
            )
            db.commit()
    except Exception:
        log.exception("heartbeat failed")


# ----------------------------------------------------------------------
# MySQL Production Worker Loop
# ----------------------------------------------------------------------
def run_mysql_worker() -> None:
    from dbresearch.mysql_adapter import MySQLOcrAdapter

    cfg = get_mysql_config()
    adapter = MySQLOcrAdapter(
        host=cfg.get("host", "10.27.50.43"),
        port=int(cfg.get("port", 3307)),
        database=cfg.get("database", "weaw_dbresearch"),
        username=cfg.get("username", "weaw_ocr"),
        password=cfg.get("password", ""),
        ssl_ca=cfg.get("ssl_ca", "mysql-ca.pem"),
    )
    log.info(
        "Starting Production MySQL OCR Worker loop: host=%s:%d db=%s user=%s",
        adapter.host,
        adapter.port,
        adapter.database,
        adapter.username,
    )
    idle = get_settings().worker_idle_seconds

    while _running:
        try:
            job = adapter.claim_job()
            if not job:
                time.sleep(idle)
                continue

            job_id = job.get("job_id") or job.get("id")
            log.info("Claimed OCR job %s from MySQL queue", job_id)

            # Heartbeat while processing
            adapter.heartbeat(job_id)

            # OCR processing placeholder (ready for source_ref transport)
            log.info("Processing job %s ...", job_id)

            # When processing finishes, call complete_job:
            # adapter.complete_job(job_id, result_json, extracted_meta)

        except Exception as exc:
            # Mask sensitive tokens/passwords
            err = str(exc)
            if adapter.password and adapter.password in err:
                err = err.replace(adapter.password, "***")
            log.warning("MySQL queue polling note: %s", err)
            time.sleep(idle * 2)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    log.info("worker process started")

    # Check if MySQL configuration is populated
    mysql_cfg = get_mysql_config()
    if mysql_cfg.get("host") and mysql_cfg.get("username") and mysql_cfg.get("password"):
        log.info("MySQL configuration detected in setting.txt -> Running Production MySQL Worker")
        run_mysql_worker()
        return

    # Fallback to local PostgreSQL queue
    log.info("No MySQL credentials configured -> Running Development PostgreSQL Worker")
    idle = get_settings().worker_idle_seconds
    beat = 0.0
    while _running:
        if time.monotonic() - beat >= HEARTBEAT_EVERY:
            heartbeat_postgres()
            beat = time.monotonic()
        if not run_once_postgres():
            time.sleep(idle)


if __name__ == "__main__":
    main()
