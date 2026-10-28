"""Envelope encryption with Tink (DESIGN §2).

- KEK: a Tink AEAD keyset (AES-256-GCM) in a JSON file outside git, the DB and data backups.
  Rotation = add a key to that keyset and make it primary; old keys stay so old DEKs unwrap.
- DEK: one Tink Streaming AEAD keyset (AES256_GCM_HKDF_1MB) per file version, stored in
  `document_versions.wrapped_dek`, encrypted with the KEK.
- Associated data for both layers is the version id, so a ciphertext or wrapped DEK copied
  onto another row fails to decrypt.
"""

import io
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import BinaryIO

import tink
from tink import aead, secret_key_access, streaming_aead

aead.register()
streaming_aead.register()

CHUNK = 1 << 20


class KeyringError(RuntimeError):
    pass


class Keyring:
    def __init__(self, kek_json: str) -> None:
        handle = tink.json_proto_keyset_format.parse(kek_json, secret_key_access.TOKEN)
        self._kek = handle.primitive(aead.Aead)
        self.kek_id = str(handle.keyset_info().primary_key_id)

    def new_dek(self, associated_data: bytes) -> tuple[streaming_aead.StreamingAead, bytes]:
        """Return (streaming cipher, wrapped DEK for the database)."""
        dek = tink.new_keyset_handle(
            streaming_aead.streaming_aead_key_templates.AES256_GCM_HKDF_1MB
        )
        wrapped = tink.proto_keyset_format.serialize_encrypted(dek, self._kek, associated_data)
        return dek.primitive(streaming_aead.StreamingAead), wrapped

    def open_dek(self, wrapped: bytes, associated_data: bytes) -> streaming_aead.StreamingAead:
        dek = tink.proto_keyset_format.parse_encrypted(wrapped, self._kek, associated_data)
        return dek.primitive(streaming_aead.StreamingAead)


def generate_kek_json() -> str:
    handle = tink.new_keyset_handle(aead.aead_key_templates.AES256_GCM)
    return tink.json_proto_keyset_format.serialize(handle, secret_key_access.TOKEN)


@lru_cache
def load_keyring(path: Path) -> Keyring:
    try:
        return Keyring(path.read_text())
    except FileNotFoundError as exc:
        raise KeyringError(f"KEK file missing: {path} (run `dbresearch.cli kek-init`)") from exc


class _KeepOpen(io.RawIOBase):
    """Tink closes the destination when its stream closes; keep the real file open for fsync."""

    def __init__(self, target: BinaryIO) -> None:
        self._target = target

    def writable(self) -> bool:
        return True

    def write(self, data) -> int:
        return self._target.write(data)

    def close(self) -> None:
        self._target.flush()
        super().close()


def encrypt_stream(
    cipher: streaming_aead.StreamingAead,
    chunks: Iterator[bytes],
    destination: BinaryIO,
    associated_data: bytes,
) -> None:
    with cipher.new_encrypting_stream(_KeepOpen(destination), associated_data) as encrypted:
        for chunk in chunks:
            encrypted.write(chunk)


def decrypt_chunks(
    cipher: streaming_aead.StreamingAead, source: BinaryIO, associated_data: bytes
) -> Iterator[bytes]:
    with cipher.new_decrypting_stream(source, associated_data) as plain:
        while chunk := plain.read(CHUNK):
            yield chunk
