"""Background OCR worker: connects to MySQL queue and executes document processing.

Production Backend: MySQL Queue Adapter (CALL ocr_claim_job, ocr_heartbeat, etc.)
Logs never contain document text or passwords, only ids and counts.
"""

import logging
import signal
import time

from dbresearch.config import get_settings
from dbresearch.settings_parser import get_mysql_config

log = logging.getLogger("dbresearch.worker")
_running = True


def _stop(signum, _frame) -> None:
    global _running
    log.info("signal %s: finishing the current job, then stopping", signum)
    _running = False


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
    log.info("OCR worker process started")

    mysql_cfg = get_mysql_config()
    if not (mysql_cfg.get("host") and mysql_cfg.get("username") and mysql_cfg.get("password")):
        log.error("MySQL configuration missing in setting.txt. Please check host, username, and password.")
        while _running:
            time.sleep(5)
        return

    run_mysql_worker()


if __name__ == "__main__":
    main()
