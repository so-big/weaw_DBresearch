"""Password hashing and opaque tokens. Tokens are only ever stored as SHA-256 hashes."""

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()  # argon2id with library defaults

# No 0/O/1/l/I: share-link passwords are read aloud and typed by guests.
_PASSWORD_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def new_token() -> tuple[str, bytes]:
    """Return (token for the client, hash for the database)."""
    token = secrets.token_urlsafe(32)
    return token, token_hash(token)


def generate_share_password(length: int = 10) -> str:
    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))
