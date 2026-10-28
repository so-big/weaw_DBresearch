"""Document storage: upload (encrypt + store + queue OCR), new versions, decrypting reads."""

import hashlib
import uuid
from collections.abc import Iterator
from pathlib import PurePath
from typing import BinaryIO

import pypdfium2 as pdfium
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dbresearch import audit, jobs
from dbresearch.blobstore import get_blobstore
from dbresearch.config import get_settings
from dbresearch.crypto import CHUNK, decrypt_chunks, encrypt_stream, load_keyring
from dbresearch.models import (
    DocKind,
    DocStatus,
    Document,
    DocumentVersion,
    FundingType,
    OcrStatus,
    User,
    UserRole,
)

PDF_MAGIC = b"%PDF-"


class UploadError(ValueError):
    """The upload was rejected; the message is safe to show to the user."""


class DuplicateUpload(UploadError):
    def __init__(self, document_id: uuid.UUID) -> None:
        super().__init__("This exact file is already stored")
        self.document_id = document_id


def can_edit(user: User, document: Document) -> bool:
    return user.role == UserRole.ADMIN or document.uploaded_by == user.id


def _inspect_pdf(file: BinaryIO) -> int:
    """Check the upload is a readable PDF; return its page count."""
    file.seek(0)
    if file.read(len(PDF_MAGIC)) != PDF_MAGIC:
        raise UploadError("Only PDF files can be uploaded")
    file.seek(0)
    try:
        pdf = pdfium.PdfDocument(file)
        pages = len(pdf)
        pdf.close()
    except pdfium.PdfiumError as exc:
        raise UploadError("The PDF is damaged or password-protected") from exc
    if pages == 0:
        raise UploadError("The PDF has no pages")
    file.seek(0)
    return pages


class _Measured:
    """Reads the upload in chunks while hashing, counting and enforcing the size limit."""

    def __init__(self, file: BinaryIO, limit: int) -> None:
        self.file, self.limit = file, limit
        self.size = 0
        self.digest = hashlib.sha256()

    def __iter__(self) -> Iterator[bytes]:
        while chunk := self.file.read(CHUNK):
            self.size += len(chunk)
            if self.size > self.limit:
                raise UploadError(f"File is larger than {self.limit >> 20} MB")
            self.digest.update(chunk)
            yield chunk


def store_version(
    db: Session,
    user: User,
    file: BinaryIO,
    filename: str,
    *,
    document: Document | None = None,
    kind: DocKind | None = None,
    funding_type: FundingType | None = None,
    ip: str | None = None,
) -> DocumentVersion:
    """Encrypt and store an upload as a new document (or a new version of `document`).

    The caller commits. Plaintext is only read from `file` (memory/tmpfs) and never written.
    """
    settings = get_settings()
    page_count = _inspect_pdf(file)
    keyring = load_keyring(settings.kek_path)
    store = get_blobstore()

    version_id = uuid.uuid4()
    associated_data = version_id.bytes
    cipher, wrapped_dek = keyring.new_dek(associated_data)
    key = store.new_key()
    measured = _Measured(file, settings.max_upload_mb << 20)
    with store.writer(key) as out:
        encrypt_stream(cipher, iter(measured), out, associated_data)
    size, sha = measured.size, measured.digest.digest()

    try:
        duplicate = db.scalar(
            select(Document.id)
            .join(DocumentVersion, DocumentVersion.document_id == Document.id)
            .where(DocumentVersion.sha256_plain == sha, Document.deleted_at.is_(None))
            .limit(1)
        )
        if duplicate is not None:
            raise DuplicateUpload(duplicate)

        safe_name = PurePath(filename or "document.pdf").name[:200] or "document.pdf"
        if document is None:
            document = Document(
                kind=kind,
                funding_type=funding_type,
                title=PurePath(safe_name).stem,  # placeholder until review
                uploaded_by=user.id,
                status=DocStatus.PROCESSING,
            )
            db.add(document)
            db.flush()
            version_no = 1
            action = "document.upload"
        else:
            version_no = 1 + (
                db.scalar(
                    select(func.max(DocumentVersion.version_no)).where(
                        DocumentVersion.document_id == document.id
                    )
                )
                or 0
            )
            document.status = DocStatus.PROCESSING
            action = "document.new_version"

        version = DocumentVersion(
            id=version_id,
            document_id=document.id,
            version_no=version_no,
            storage_key=key,
            original_filename=safe_name,
            mime_type="application/pdf",
            size_bytes=size,
            sha256_plain=sha,
            page_count=page_count,
            wrapped_dek=wrapped_dek,
            kek_id=keyring.kek_id,
            ocr_status=OcrStatus.PENDING,
            uploaded_by=user.id,
        )
        db.add(version)
        document.current_version_id = version_id
        jobs.enqueue(db, "ocr", version_id=version_id)
        audit.record(
            db,
            action,
            "document",
            document.id,
            actor_id=user.id,
            ip=ip,
            version=version_no,
            pages=page_count,
            size=size,
        )
        db.flush()
    except BaseException:
        store.delete(key)  # never leave an orphan blob behind a failed insert
        raise
    return version


def read_version(version: DocumentVersion) -> Iterator[bytes]:
    """Decrypt a stored version chunk by chunk (for streaming responses and the worker)."""
    keyring = load_keyring(get_settings().kek_path)
    associated_data = version.id.bytes
    cipher = keyring.open_dek(version.wrapped_dek, associated_data)
    with get_blobstore().open(version.storage_key) as source:
        yield from decrypt_chunks(cipher, source, associated_data)
