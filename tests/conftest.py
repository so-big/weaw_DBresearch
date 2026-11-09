"""Shared fixtures. DB-backed tests run on the server's compose stack (DATABASE_URL set).

A session-wide throwaway database (ICU th-TH, migrated to head) backs the API tests; user
data is truncated after every test, while seeded reference data stays.
"""

import os
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
HAS_DB = "DATABASE_URL" in os.environ
needs_db = pytest.mark.skipif(not HAS_DB, reason="needs the compose stack (DATABASE_URL)")
CSRF = {"X-Requested-With": "dbresearch"}
# The web app owns every other path; tests talk to the API.
API = "http://testserver/api"

# Everything users create. Seeded reference data (categories, settings, templates) is kept:
# `users` is DELETEd, not truncated, because TRUNCATE … CASCADE would follow
# extraction_templates.created_by and wipe the seeded templates too.
# `audit_events` is append-only (a trigger blocks TRUNCATE), so it is emptied separately.
USER_DATA_TABLES = (
    "people, tags, jobs, documents, document_versions, sessions, "
    "auth_identities, share_links, share_access_log, budget_lines, document_pages, "
    "document_sections, document_people, document_categories, document_tags"
)


@contextmanager
def temp_database() -> Iterator[str]:
    base = make_url(os.environ["DATABASE_URL"])
    name = f"dbresearch_test_{uuid.uuid4().hex[:8]}"
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(
            text(
                f'CREATE DATABASE "{name}" TEMPLATE template0 ENCODING UTF8 '
                "LOCALE_PROVIDER icu ICU_LOCALE 'th-TH' LOCALE 'C.UTF-8'"
            )
        )
    try:
        yield base.set(database=name).render_as_string(hide_password=False)
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def alembic_config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


@pytest.fixture(scope="session")
def app_db(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Migrated test DB; also points the app's engine and settings at test locations."""
    if not HAS_DB:
        pytest.skip("needs the compose stack (DATABASE_URL)")
    from dbresearch.config import get_settings
    from dbresearch.crypto import generate_kek_json
    from dbresearch.db import configure_engine

    with temp_database() as url:
        command.upgrade(alembic_config(url), "head")
        os.environ["BLOB_DIR"] = str(tmp_path_factory.mktemp("blobs"))
        kek_path = tmp_path_factory.mktemp("secrets") / "kek.json"
        kek_path.write_text(generate_kek_json())
        os.environ["KEK_PATH"] = str(kek_path)
        # Tests talk plain http://testserver and set no proxy header, whatever the server's
        # .env says for the public demo (HTTPS cookies, Cloudflare IP header).
        os.environ["COOKIE_SECURE"] = "false"
        os.environ.pop("TRUSTED_IP_HEADER", None)
        get_settings.cache_clear()
        configure_engine(url)
        yield url
        configure_engine(os.environ["DATABASE_URL"])


@pytest.fixture
def db_clean(app_db: str) -> Iterator[None]:
    yield
    engine = create_engine(app_db)
    with engine.begin() as conn:
        # Replica mode skips ordinary triggers (superuser only), here the append-only guard.
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        conn.execute(text("TRUNCATE audit_events RESTART IDENTITY"))
        conn.execute(text("SET LOCAL session_replication_role = origin"))
        conn.execute(text(f"TRUNCATE {USER_DATA_TABLES} RESTART IDENTITY CASCADE"))
        conn.execute(text("DELETE FROM users"))
    engine.dispose()


@pytest.fixture
def client(db_clean: None):
    from fastapi.testclient import TestClient

    from dbresearch.main import app

    with TestClient(app, headers=CSRF, base_url=API) as test_client:
        yield test_client


@pytest.fixture
def make_user(db_clean: None) -> Callable[..., tuple[uuid.UUID, str, str]]:
    """Create a user with a local login; returns (user_id, username, password)."""
    from dbresearch.auth import add_local_identity
    from dbresearch.db import new_session
    from dbresearch.models import User, UserRole

    def factory(role: UserRole = UserRole.USER, username: str | None = None):
        username = username or f"user{uuid.uuid4().hex[:6]}"
        password = "correct horse battery"
        with new_session() as db:
            user = User(email=f"{username}@example.test", display_name=username, role=role)
            db.add(user)
            db.flush()
            add_local_identity(db, user, username, password)
            db.commit()
            return user.id, username, password

    return factory


@pytest.fixture
def login(client, make_user) -> Callable[..., uuid.UUID]:
    """Log the test client in as a new user of the given role; returns the user id."""
    from dbresearch.models import UserRole

    def do_login(role: UserRole = UserRole.USER) -> uuid.UUID:
        user_id, username, password = make_user(role)
        response = client.post("/auth/login", json={"username": username, "password": password})
        assert response.status_code == 200, response.text
        return user_id

    return do_login


def make_pdf(pages: int = 1) -> bytes:
    """A small valid PDF; random page width makes every call's bytes unique."""
    import io
    import random

    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument.new()
    for _ in range(pages):
        pdf.new_page(random.randint(500, 600), 842)
    buffer = io.BytesIO()
    pdf.save(buffer)
    return buffer.getvalue()
