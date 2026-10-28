import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select

from dbresearch import audit
from dbresearch.auth import DB, CurrentUser, client_ip
from dbresearch.documents import DuplicateUpload, UploadError, can_edit, read_version, store_version
from dbresearch.models import DocKind, Document, DocumentVersion, FundingType, User
from dbresearch.schemas import DocumentOut, VersionOut

router = APIRouter(prefix="/documents", tags=["documents"])


def live_document(db: DB, document_id: uuid.UUID) -> Document:
    document = db.get(Document, document_id)
    if document is None or document.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return document


def document_out(db: DB, document: Document, user: User) -> DocumentOut:
    versions = db.scalars(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document.id)
        .order_by(DocumentVersion.version_no.desc())
    ).all()
    out = DocumentOut.model_validate(document)
    out.can_edit = can_edit(user, document)
    out.versions = [VersionOut.model_validate(v) for v in versions]
    return out


def _upload_errors(exc: UploadError) -> JSONResponse:
    if isinstance(exc, DuplicateUpload):
        return JSONResponse(
            {"detail": str(exc), "document_id": str(exc.document_id)}, status_code=409
        )
    return JSONResponse({"detail": str(exc)}, status_code=400)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=DocumentOut)
def upload(
    request: Request,
    db: DB,
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
    kind: Annotated[DocKind | None, Form()] = None,
    funding_type: Annotated[FundingType | None, Form()] = None,
):
    try:
        version = store_version(
            db,
            user,
            file.file,
            file.filename or "",
            kind=kind,
            funding_type=funding_type,
            ip=client_ip(request),
        )
    except UploadError as exc:
        db.rollback()
        return _upload_errors(exc)
    db.commit()
    return document_out(db, db.get(Document, version.document_id), user)


@router.post(
    "/{document_id}/versions", status_code=status.HTTP_201_CREATED, response_model=DocumentOut
)
def new_version(
    document_id: uuid.UUID,
    request: Request,
    db: DB,
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
):
    document = live_document(db, document_id)
    if not can_edit(user, document):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the uploader or an admin can do this")
    try:
        store_version(
            db, user, file.file, file.filename or "", document=document, ip=client_ip(request)
        )
    except UploadError as exc:
        db.rollback()
        return _upload_errors(exc)
    db.commit()
    return document_out(db, document, user)


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: uuid.UUID, db: DB, user: CurrentUser):
    return document_out(db, live_document(db, document_id), user)


def content_disposition(disposition: str, filename: str) -> str:
    fallback = filename.encode("ascii", "ignore").decode().replace('"', "") or "document.pdf"
    return f"{disposition}; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename)}"


def stream_version(version: DocumentVersion, inline: bool) -> StreamingResponse:
    return StreamingResponse(
        read_version(version),
        media_type="application/pdf",
        headers={
            "Content-Disposition": content_disposition(
                "inline" if inline else "attachment", version.original_filename
            ),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{document_id}/file")
def download(
    document_id: uuid.UUID,
    request: Request,
    db: DB,
    user: CurrentUser,
    version: int | None = None,
    inline: bool = False,
):
    """The current version, or `?version=N`. `inline=true` opens it in the browser viewer."""
    document = live_document(db, document_id)
    query = select(DocumentVersion).where(DocumentVersion.document_id == document.id)
    if version is None:
        query = query.where(DocumentVersion.id == document.current_version_id)
    else:
        query = query.where(DocumentVersion.version_no == version)
    stored = db.scalar(query)
    if stored is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version not found")
    audit.record(
        db,
        "document.view" if inline else "document.download",
        "document",
        document.id,
        actor_id=user.id,
        ip=client_ip(request),
        version=stored.version_no,
    )
    db.commit()
    return stream_version(stored, inline)
