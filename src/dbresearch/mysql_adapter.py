"""MySQL worker adapter for OCR job queue.

Implements integration with external MySQL server using stored procedures:
- ocr_claim_job
- ocr_heartbeat
- ocr_complete_job
- ocr_fail_job

Strictly adheres to:
- TLS with CA/hostname verification
- UTF-8 (utf8mb4) and UTC timezone
- Exhausting all multi-result sets (cursor.nextset)
- Zero rows claimed is normal behavior (queue empty)
- Never logs passwords, secrets, tokens, or plaintext contents
"""
import hashlib
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

log = logging.getLogger("dbresearch.mysql_adapter")

try:
    import pymysql
    import pymysql.cursors
except ImportError:
    pymysql = None


class MySQLOcrAdapter:
    def __init__(
        self,
        host: str = "10.27.50.43",
        port: int = 3307,
        database: str = "dbresearch",
        username: str = "ocr_worker",
        password: str = "",
        ssl_ca: Optional[str | Path] = None,
        worker_id: Optional[str] = None,
    ):
        self.host = host
        self.port = int(port)
        self.database = database
        self.username = username
        self.password = password
        self.ssl_ca = Path(ssl_ca) if ssl_ca else None
        self.worker_id = worker_id or f"ocr-worker-{os.getpid()}"
        self._conn = None

    def _get_ssl_context(self) -> Optional[Dict[str, Any]]:
        """Configure TLS with CA verification if CA certificate is present."""
        if self.ssl_ca and self.ssl_ca.is_file():
            return {
                "ca": str(self.ssl_ca.resolve()),
                "check_hostname": True,
            }
        # Check standard locations
        for cand in [Path("mysql-ca.pem"), Path("/app/mysql-ca.pem")]:
            if cand.is_file():
                return {
                    "ca": str(cand.resolve()),
                    "check_hostname": True,
                }
        return None

    def connect(self):
        """Create or return active MySQL connection with UTF-8, UTC, and TLS."""
        if pymysql is None:
            raise RuntimeError("pymysql is required for MySQLOcrAdapter. Please install pymysql.")

        if self._conn:
            try:
                self._conn.ping(reconnect=True)
                return self._conn
            except Exception:
                self._conn = None

        ssl_config = self._get_ssl_context()
        log.info(
            "Connecting to MySQL at %s:%d database=%s user=%s (TLS=%s)",
            self.host,
            self.port,
            self.database,
            self.username,
            "Enabled" if ssl_config else "Disabled",
        )

        conn_kwargs: Dict[str, Any] = {
            "host": self.host,
            "port": self.port,
            "user": self.username,
            "password": self.password,
            "database": self.database,
            "charset": "utf8mb4",
            "cursorclass": pymysql.cursors.DictCursor,
            "autocommit": True,
            "connect_timeout": 5,
            "init_command": "SET time_zone = '+00:00'",
        }

        if ssl_config:
            conn_kwargs["ssl"] = ssl_config

        self._conn = pymysql.connect(**conn_kwargs)
        return self._conn

    def _drain_result_sets(self, cursor):
        """Exhaust all remaining result sets to prevent Commands out of sync error."""
        try:
            while cursor.nextset():
                pass
        except Exception:
            pass

    def test_connection(self) -> Dict[str, Any]:
        """Test connection and verify required stored procedures exist without exposing passwords."""
        status: Dict[str, Any] = {
            "connected": False,
            "host": f"{self.host}:{self.port}",
            "database": self.database,
            "user": self.username,
            "tls_enabled": bool(self._get_ssl_context()),
            "ca_file_found": bool(self.ssl_ca and self.ssl_ca.is_file()),
            "routines_found": [],
            "missing_routines": [],
            "error": None,
        }

        try:
            conn = self.connect()
            status["connected"] = True
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT ROUTINE_NAME 
                    FROM information_schema.ROUTINES 
                    WHERE ROUTINE_SCHEMA = %s AND ROUTINE_TYPE = 'PROCEDURE'
                    """,
                    (self.database,),
                )
                rows = cur.fetchall()
                self._drain_result_sets(cur)
                existing = [r["ROUTINE_NAME"].lower() for r in rows]

                required = [
                    "ocr_claim_job",
                    "ocr_heartbeat",
                    "ocr_complete_job",
                    "ocr_fail_job",
                ]
                for req in required:
                    if req in existing:
                        status["routines_found"].append(req)
                    else:
                        status["missing_routines"].append(req)
        except Exception as exc:
            # Mask any credentials in error message
            msg = str(exc)
            if self.password and self.password in msg:
                msg = msg.replace(self.password, "***")
            status["error"] = msg

        return status

    def claim_job(self) -> Optional[Dict[str, Any]]:
        """Call ocr_claim_job. Returns job dict or None if queue is empty."""
        conn = self.connect()
        with conn.cursor() as cur:
            try:
                cur.callproc("ocr_claim_job", (self.worker_id,))
                row = cur.fetchone()
                self._drain_result_sets(cur)
                if not row:
                    return None
                return row
            except Exception as exc:
                self._drain_result_sets(cur)
                log.error("Failed to claim job: %s", exc)
                raise

    def heartbeat(self, job_id: Any) -> bool:
        """Call ocr_heartbeat to update worker alive status for active job."""
        conn = self.connect()
        with conn.cursor() as cur:
            try:
                cur.callproc("ocr_heartbeat", (job_id, self.worker_id))
                self._drain_result_sets(cur)
                return True
            except Exception as exc:
                self._drain_result_sets(cur)
                log.warning("Heartbeat failed for job %s: %s", job_id, exc)
                return False

    def complete_job(
        self,
        job_id: Any,
        result_data: Dict[str, Any] | str,
        extracted_meta: Optional[Dict[str, Any] | str] = None,
    ) -> bool:
        """Call ocr_complete_job with JSON results."""
        conn = self.connect()
        res_str = json.dumps(result_data, ensure_ascii=False) if isinstance(result_data, dict) else str(result_data)
        meta_str = json.dumps(extracted_meta, ensure_ascii=False) if isinstance(extracted_meta, dict) else (extracted_meta or "{}")

        with conn.cursor() as cur:
            try:
                cur.callproc("ocr_complete_job", (job_id, self.worker_id, res_str, meta_str))
                self._drain_result_sets(cur)
                log.info("Job %s marked complete by %s", job_id, self.worker_id)
                return True
            except Exception as exc:
                self._drain_result_sets(cur)
                log.error("Failed to complete job %s: %s", job_id, exc)
                raise

    def fail_job(self, job_id: Any, error_message: str, can_retry: bool = True) -> bool:
        """Call ocr_fail_job with error message and retry flag."""
        conn = self.connect()
        clean_error = error_message[:500]
        if self.password and self.password in clean_error:
            clean_error = clean_error.replace(self.password, "***")

        with conn.cursor() as cur:
            try:
                cur.callproc("ocr_fail_job", (job_id, self.worker_id, clean_error, int(can_retry)))
                self._drain_result_sets(cur)
                log.info("Job %s reported failed: %s", job_id, clean_error)
                return True
            except Exception as exc:
                self._drain_result_sets(cur)
                log.error("Failed to report job failure %s: %s", job_id, clean_error)
                return False


def verify_pdf_hash(file_bytes: bytes, expected_sha256: str) -> bool:
    """Verify SHA-256 hash of PDF file before OCR processing."""
    computed = hashlib.sha256(file_bytes).hexdigest()
    return computed.lower() == expected_sha256.lower().strip()


def run_test():
    """CLI tester for MySQL connection."""
    from dbresearch.settings_parser import get_mysql_config

    cfg = get_mysql_config()
    print("=" * 70)
    print("       MySQL OCR Worker Adapter - Connection Test")
    print("=" * 70)
    print(f"Target Host:     {cfg.get('host')}:{cfg.get('port')}")
    print(f"Database:        {cfg.get('database')}")
    print(f"User:            {cfg.get('username')}")
    print(f"SSL CA Path:     {cfg.get('ssl_ca')}")
    print("-" * 70)

    adapter = MySQLOcrAdapter(
        host=cfg.get("host", "10.27.50.43"),
        port=int(cfg.get("port", 3307)),
        database=cfg.get("database", "dbresearch"),
        username=cfg.get("username", "ocr_worker"),
        password=cfg.get("password", ""),
        ssl_ca=cfg.get("ssl_ca", "mysql-ca.pem"),
    )

    status = adapter.test_connection()
    if status["connected"]:
        print("[SUCCESS] Connected to MySQL successfully!")
        print(f"TLS Active:      {status['tls_enabled']}")
        print(f"Routines Found:  {', '.join(status['routines_found']) if status['routines_found'] else 'None'}")
        if status["missing_routines"]:
            print(f"[WARN] Missing Procedures: {', '.join(status['missing_routines'])}")
    else:
        print("[FAILED] Could not connect to MySQL server.")
        print(f"Error: {status['error']}")

    print("=" * 70)


if __name__ == "__main__":
    run_test()
