"""Document storage: upload (encrypt + store + queue OCR), new versions, decrypting reads."""

import hashlib
import uuid
import zipfile
from collections.abc import Iterable, Iterator
from datetime import UTC, date, datetime
from pathlib import PurePath
from typing import BinaryIO
from zoneinfo import ZoneInfo

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
    ShareLink,
    User,
    UserRole,
    VersionPurpose,
)

PDF_MAGIC = b"%PDF-"


class UploadError(ValueError):
    """The upload was rejected; the message is safe to show to the user."""


class DuplicateUpload(UploadError):
    def __init__(
        self, document_id: uuid.UUID, *, trashed: bool = False, can_restore: bool = False
    ) -> None:
        super().__init__(
            "This exact file is in the trash" if trashed else "This exact file is already stored"
        )
        self.document_id = document_id
        self.trashed = trashed
        self.can_restore = can_restore


def can_edit(user: User, document: Document) -> bool:
    return user.role == UserRole.ADMIN or document.uploaded_by == user.id


def can_restore(user: User, document: Document) -> bool:
    """Uploaders undo their own deletes; something an admin removed stays with the admin."""
    return user.role == UserRole.ADMIN or (
        document.uploaded_by == user.id and document.deleted_by == user.id
    )


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
    purpose: VersionPurpose = VersionPurpose.MAIN,
    ip: str | None = None,
) -> DocumentVersion:
    """Encrypt and store an upload as a new document (or a new version of `document`).

    `purpose=CLOSURE` attaches a closing paper to `document`: it is OCR'd for search but
    leaves the current version and the review status alone.

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
        # Two uploads of the same file at once: the second waits here until the first commits,
        # then sees it below. Released automatically at commit/rollback.
        db.execute(select(func.pg_advisory_xact_lock(int.from_bytes(sha[:8], "big", signed=True))))
        # A live copy wins over a trashed one (purged documents have no rows left).
        duplicate = db.scalar(
            select(Document)
            .join(DocumentVersion, DocumentVersion.document_id == Document.id)
            .where(DocumentVersion.sha256_plain == sha)
            .order_by(Document.deleted_at.is_not(None))
            .limit(1)
        )
        if duplicate is not None:
            trashed = duplicate.deleted_at is not None
            raise DuplicateUpload(
                duplicate.id, trashed=trashed, can_restore=trashed and can_restore(user, duplicate)
            )

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
                        DocumentVersion.document_id == document.id,
                        DocumentVersion.purpose == purpose,
                    )
                )
                or 0
            )
            if purpose == VersionPurpose.MAIN:
                document.status = DocStatus.PROCESSING
                action = "document.new_version"
            else:
                action = "document.closure_file"

        version = DocumentVersion(
            id=version_id,
            document_id=document.id,
            purpose=purpose,
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
        if purpose == VersionPurpose.MAIN:
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


# ───────────── Several files as one zip ─────────────
MAX_BUNDLE = 100


def bundle_names(items: Iterable[tuple[str | None, str]]) -> list[str]:
    """File names inside the zip: contract no. first (scanner names say little), no clashes.

    `items` are (reference_no, original_filename) pairs, in order.
    """
    names, used = [], set()
    for reference_no, filename in items:
        name = PurePath(filename.replace("\\", "/")).name or "document.pdf"
        if reference_no and reference_no.lower() not in name.lower():
            name = f"{reference_no}_{name}"
        stem, dot, ext = name.rpartition(".")
        if not dot:
            stem, ext = name, ""
        candidate, n = name, 1
        while candidate.lower() in used:
            n += 1
            candidate = f"{stem} ({n}).{ext}" if ext else f"{name} ({n})"
        used.add(candidate.lower())
        names.append(candidate)
    return names


class _Sink:
    """Write-only buffer for ZipFile. Not seekable, so the zip is written in streaming form."""

    def __init__(self) -> None:
        self.parts: list[bytes] = []

    def write(self, data) -> int:
        self.parts.append(bytes(data))
        return len(data)

    def flush(self) -> None:
        pass

    def take(self) -> bytes:
        data = b"".join(self.parts)
        self.parts.clear()
        return data


def zip_versions(entries: list[tuple[str, DocumentVersion]]) -> Iterator[bytes]:
    """Decrypt each version into a deflated zip, chunk by chunk, all in memory.

    Plaintext never touches disk: each 1 MiB chunk is decrypted, compressed and sent on.
    """
    stamp = datetime.now(ZoneInfo("Asia/Bangkok")).timetuple()[:6]
    sink = _Sink()
    with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, version in entries:
            info = zipfile.ZipInfo(name, date_time=stamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.file_size = version.size_bytes  # lets zipfile pick zip64 only when needed
            with archive.open(info, "w") as out:
                for chunk in read_version(version):
                    out.write(chunk)
                    if data := sink.take():
                        yield data
            if data := sink.take():
                yield data
    yield sink.take()


# ───────────── Trash ─────────────
class TrashError(ValueError):
    pass


def soft_delete(db: Session, user: User, document: Document, ip: str | None) -> int:
    """Move to the trash: hidden at once, and its share links die in the same transaction."""
    from dbresearch.shares import revoke_for_document  # avoid an import cycle

    document.deleted_at = datetime.now(UTC)
    document.deleted_by = user.id
    revoked = revoke_for_document(db, document.id, user.id)
    audit.record(
        db,
        "document.delete",
        "document",
        document.id,
        actor_id=user.id,
        ip=ip,
        revoked_links=revoked,
    )
    return revoked


def restore(db: Session, user: User, document: Document, ip: str | None) -> int:
    """Back from the trash. Returns how many links the deletion had revoked (they stay dead)."""
    if document.deleted_at is None:
        raise TrashError("Document is not in the trash")
    if document.reference_no and db.scalar(
        select(Document.id).where(
            Document.reference_no == document.reference_no,
            Document.deleted_at.is_(None),
            Document.id != document.id,
        )
    ):
        raise TrashError(
            f"Another live document has the same contract number ({document.reference_no})"
        )
    # soft_delete revokes the links in its own transaction, right after stamping deleted_at;
    # a link revoked by hand earlier has an older revoked_at.
    revoked = (
        db.scalar(
            select(func.count())
            .select_from(ShareLink)
            .where(
                ShareLink.document_id == document.id, ShareLink.revoked_at >= document.deleted_at
            )
        )
        or 0
    )
    document.deleted_at = None
    document.deleted_by = None
    audit.record(
        db,
        "document.restore",
        "document",
        document.id,
        actor_id=user.id,
        ip=ip,
        revoked_links=revoked,
    )
    return revoked


def purge(db: Session, user: User, document: Document, ip: str | None) -> list[str]:
    """Remove a trashed document from the live system (rows + wrapped DEKs).

    Returns the blob keys to delete *after* the caller commits: a failed commit must never
    leave rows pointing at deleted blobs. Backups are kept forever, so this is not erasure.
    """
    if document.deleted_at is None:
        raise TrashError("Only documents in the trash can be purged")
    keys = list(
        db.scalars(
            select(DocumentVersion.storage_key).where(DocumentVersion.document_id == document.id)
        )
    )
    audit.record(
        db,
        "document.purge",
        "document",
        document.id,
        actor_id=user.id,
        ip=ip,
        versions=len(keys),
        reference_no=document.reference_no,
    )
    document.current_version_id = None
    db.flush()
    db.delete(document)  # cascades: versions, pages, sections, links, labels, people, budget
    return keys


def delete_blobs(keys: list[str]) -> None:
    store = get_blobstore()
    for key in keys:
        store.delete(key)


# ───────────── Close a project (ปิดโครงการ) ─────────────
def close_project(
    db: Session,
    user: User,
    document: Document,
    *,
    closed_on: date | None,
    closure_ref: str | None,
    closure_note: str | None,
    ip: str | None,
) -> None:
    """Mark the project closed and archived (or edit the closing details). The caller commits.

    Closing papers are uploaded separately as 'closure' versions; closing works without them
    so a project closed on paper years ago can still be archived."""
    first = document.closed_at is None
    if first:
        document.closed_at = datetime.now(UTC)
        document.closed_by = user.id
    document.closed_on = closed_on
    document.closure_ref = (closure_ref or "").strip() or None
    document.closure_note = (closure_note or "").strip() or None
    audit.record(
        db,
        "document.close" if first else "document.close_update",
        "document",
        document.id,
        actor_id=user.id,
        ip=ip,
        closed_on=closed_on.isoformat() if closed_on else None,
        closure_ref=document.closure_ref,
    )


def reopen_project(db: Session, user: User, document: Document, ip: str | None) -> None:
    """Undo a close: the project is active again. Closing papers stay attached."""
    audit.record(
        db,
        "document.reopen",
        "document",
        document.id,
        actor_id=user.id,
        ip=ip,
        closed_on=document.closed_on.isoformat() if document.closed_on else None,
    )
    document.closed_at = None
    document.closed_by = None
    document.closed_on = None
