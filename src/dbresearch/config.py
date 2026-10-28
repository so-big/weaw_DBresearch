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

    # Sessions (local login; college SSO replaces the provider later).
    session_cookie: str = "dbr_session"
    session_ttl_hours: int = 12
    cookie_secure: bool = False  # True behind HTTPS; the SSH-tunnel demo is plain HTTP
    # Signs short-lived guest grants after a share-link password is entered.
    secret_key: str = "dev-only-change-me"

    max_upload_mb: int = 100


@lru_cache
def get_settings() -> Settings:
    return Settings()
