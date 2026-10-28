import os

from fastapi import FastAPI, Response
from sqlalchemy import text

from dbresearch.config import get_settings
from dbresearch.db import engine

app = FastAPI(title="DBresearch")


def _check_database() -> dict[str, str]:
    settings = get_settings()
    try:
        with engine.connect() as conn:
            provider, locale = conn.execute(
                text(
                    "SELECT datlocprovider, datlocale FROM pg_database "
                    "WHERE datname = current_database()"
                )
            ).one()
    except Exception as exc:  # health must report, not crash
        return {"database": f"error: {type(exc).__name__}"}
    ok = provider == "i" and locale == settings.expected_db_locale
    locale_status = "ok" if ok else f"error: provider={provider} locale={locale}"
    return {"database": "ok", "db_locale": locale_status}


def _check_blob_store() -> dict[str, str]:
    blob_dir = get_settings().blob_dir
    ok = blob_dir.is_dir() and os.access(blob_dir, os.W_OK)
    return {"blob_store": "ok" if ok else "error: missing or not writable"}


@app.get("/health")
def health(response: Response) -> dict:
    checks = _check_database() | _check_blob_store()
    healthy = all(value == "ok" for value in checks.values())
    if not healthy:
        response.status_code = 503
    return {"status": "ok" if healthy else "degraded", "checks": checks}
