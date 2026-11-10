from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables (and `.env` if present)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://dbresearch@localhost:5432/dbresearch"
    # Encrypted file versions live here (BlobStore). Ciphertext only.
    blob_dir: Path = Path("/data/blobs")
    # Tink AEAD keyset (JSON) holding the KEK. Never in git, the DB, or data backups.
    kek_path: Path = Path("/run/secrets/kek.json")
    # The DB must use ICU th-TH, or pg_trgm ignores Thai text (DESIGN §5).
    expected_db_locale: str = "th-TH"

    # Login providers, tried in this order: "local" (dev/demo + bootstrap admins) and
    # "university" (the university login API, dbresearch.university).
    auth_providers: str = "local"
    # University login API (placeholder until the API spec arrives). HTTPS only.
    university_api_url: str | None = None
    university_api_key: str | None = None
    university_api_timeout_seconds: float = 5.0
    # Account types allowed in, as the API names them (comma list). Only staff/employees
    # (research office) log in; teachers get share links instead, students never get in.
    # "staff" is a placeholder until the API spec gives the exact type names.
    university_allowed_types: str = "staff"
    # A first login nobody added yet becomes a *pending* request that ADMIN approves on the
    # Users page. Departments listed here (comma list, as the API names them) skip the queue;
    # it only works once the API returns the department.
    university_auto_approve_departments: str = ""
    # Which university client to use: "api" (the real API, spec pending) or "php_ldap_test"
    # (TEST ONLY: IT's RealLogin.php LDAP script, which only says right/wrong password, so
    # our users table decides who gets in; plain http allowed). DESIGN §9.
    university_client: str = "api"
    # Staff email domain; the test client builds `<username>@<domain>` to match users ADMIN added.
    university_email_domain: str = "nu.ac.th"

    # Sessions: hard limit, idle timeout, and how many devices one user may stay logged in on.
    session_cookie: str = "dbr_session"
    session_ttl_hours: int = 12
    session_idle_minutes: int = 60
    session_max_per_user: int = 5
    cookie_secure: bool = False  # True behind HTTPS; the SSH-tunnel demo is plain HTTP
    # Behind Cloudflare Tunnel: take the visitor's IP from this header (e.g. CF-Connecting-IP).
    # Safe only because the API port is bound to 127.0.0.1, so only the local tunnel reaches it.
    trusted_ip_header: str | None = None
    # Local-login brute-force guard: failed attempts per username (x4 per IP) in a window.
    login_max_failures: int = 5
    login_window_minutes: int = 15
    # Signs short-lived guest grants after a share-link password is entered.
    secret_key: str = "dev-only-change-me"

    max_upload_mb: int = 100
    # Built web app (Vite output). Missing folder = API only.
    web_dir: Path = Path("/app/web/dist")
    # Worker scratch space for decrypted files: must be a tmpfs (CLAUDE.md).
    work_dir: Path = Path("/tmp/work")
    worker_idle_seconds: float = 2.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
