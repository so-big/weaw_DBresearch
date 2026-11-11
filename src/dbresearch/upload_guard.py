"""Refuse file uploads from visitors without a live session before the body is read.

FastAPI parses a multipart form (spooling files to /tmp) before any dependency runs, so the
`current_user` check alone would let anyone fill the disk with 100 MB bodies before the 401.
This is a pure ASGI middleware: it answers without ever calling `receive`. Every multipart
route under /api is staff-only; guests (share links) only send small JSON bodies.
"""

from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers
from starlette.requests import cookie_parser
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from dbresearch.auth import resolve_session
from dbresearch.config import get_settings
from dbresearch.db import new_session

GUARDED_METHODS = {"POST", "PUT", "PATCH"}
# FastAPI parses a form body for any route with Form()/File() fields, whatever the type.
FORM_TYPES = ("multipart/", "application/x-www-form-urlencoded")


def _has_live_session(token: str) -> bool:
    """Same check as `current_user` (idle and absolute timeouts, active user)."""
    with new_session() as db:
        return resolve_session(db, token) is not None


class UploadAuthGuard:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] in GUARDED_METHODS
            and scope["path"].startswith("/api/")
        ):
            headers = Headers(scope=scope)
            if headers.get("content-type", "").lower().startswith(FORM_TYPES):
                # Same parser as `Request.cookies`, which `current_user` reads.
                cookies = cookie_parser(headers.get("cookie", ""))
                token = cookies.get(get_settings().session_cookie)
                if not token or not await run_in_threadpool(_has_live_session, token):
                    response = JSONResponse({"detail": "Not logged in"}, status_code=401)
                    await response(scope, receive, send)
                    return
        await self.app(scope, receive, send)
