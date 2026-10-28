from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables (and `.env` if present)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://dbresearch@localhost:5432/dbresearch"
    # Encrypted file versions live here (see BlobStore in Phase 2). Ciphertext only.
    blob_dir: Path = Path("/data/blobs")
    # The DB must use ICU th-TH, or pg_trgm ignores Thai text (DESIGN §5).
    expected_db_locale: str = "th-TH"


@lru_cache
def get_settings() -> Settings:
    return Settings()
