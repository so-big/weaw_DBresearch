import os
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from dbresearch.api import admin as admin_api
from dbresearch.api import auth as auth_api
from dbresearch.api import catalog as catalog_api
from dbresearch.api import documents as documents_api
from dbresearch.api import shares as shares_api
from dbresearch.config import get_settings
from dbresearch.crypto import load_keyring
from dbresearch.db import get_engine

app = FastAPI(
    title="DBresearch",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)

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


@app.middleware("http")
async def security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    # Share tokens live in URLs: never leak them to other sites via Referer.
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    return response


@app.middleware("http")
async def upload_size_limit(request: Request, call_next) -> Response:
    """Reject oversized uploads before they are spooled (exact limit enforced while reading)."""
    length = request.headers.get("content-length")
    limit = (get_settings().max_upload_mb + 1) << 20
    if length and length.isdigit() and int(length) > limit:
        return JSONResponse({"detail": "Upload too large"}, status_code=413)
    return await call_next(request)


# Everything the web app calls lives under /api; other paths belong to the web app's pages.
api = APIRouter(prefix="/api")
for router in (
    auth_api.router,
    documents_api.router,
    catalog_api.router,
    shares_api.router,
    shares_api.guest,
    admin_api.router,
):
    api.include_router(router)


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


def _check_kek() -> dict[str, str]:
    try:
        load_keyring(get_settings().kek_path)
    except Exception as exc:  # missing or unreadable master key
        return {"kek": f"error: {type(exc).__name__}"}
    return {"kek": "ok"}


@app.get("/health")
@api.get("/health")
def health(response: Response) -> dict:
    checks = _check_database() | _check_blob_store() | _check_kek()
    healthy = all(value == "ok" for value in checks.values())
    if not healthy:
        response.status_code = 503
    return {"status": "ok" if healthy else "degraded", "checks": checks}


app.include_router(api)

# ───────────── Web app (built by Vite into web/dist) ─────────────
# The page's own scripts and styles only; Svelte transitions add inline styles at runtime.
WEB_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; frame-src 'self'; "
    "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'self'"
)


def mount_web(target: FastAPI, web_dir: Path) -> None:
    """Serve the built web app: hashed assets cached forever, every other path gets index.html."""
    index = web_dir / "index.html"
    if not index.is_file():
        return  # API-only (tests, or the web app not built yet)
    root = web_dir.resolve()
    target.mount("/assets", StaticFiles(directory=web_dir / "assets"), name="assets")

    @target.get("/{path:path}", include_in_schema=False)
    def web_page(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "Not found")
        file = (web_dir / path).resolve()
        if path and file.is_file() and file.is_relative_to(root):
            return FileResponse(file)
        return FileResponse(
            index, headers={"Cache-Control": "no-cache", "Content-Security-Policy": WEB_CSP}
        )


mount_web(app, get_settings().web_dir)
