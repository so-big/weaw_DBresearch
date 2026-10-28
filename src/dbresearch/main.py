import os

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text

from dbresearch.api import auth as auth_api
from dbresearch.config import get_settings
from dbresearch.db import get_engine

app = FastAPI(title="DBresearch")

# Browsers can't add custom headers to cross-site requests without a CORS preflight, which
# this API never allows. Requiring one on every state-changing request blocks CSRF even if
# a cookie were sent.
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "dbresearch"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@app.middleware("http")
async def csrf_guard(request: Request, call_next) -> Response:
    if request.method not in SAFE_METHODS and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        return JSONResponse(
            {"detail": f"Missing header {CSRF_HEADER}: {CSRF_VALUE}"}, status_code=403
        )
    return await call_next(request)


app.include_router(auth_api.router)


def _check_database() -> dict[str, str]:
    settings = get_settings()
    try:
        with get_engine().connect() as conn:
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
