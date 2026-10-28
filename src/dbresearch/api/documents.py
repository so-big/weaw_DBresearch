import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from dbresearch import audit, jobs
from dbresearch.auth import DB, CurrentUser, client_ip
from dbresearch.documents import DuplicateUpload, UploadError, can_edit, read_version, store_version
from dbresearch.metadata import MetadataError, ReferenceTaken, apply_metadata
from dbresearch.models import (
    BudgetLine,
    Category,
    CategoryGroup,
    DocKind,
    DocStatus,
    Document,
    DocumentCategory,
    DocumentPerson,
    DocumentTag,
    DocumentVersion,
    FundingType,
    OcrStatus,
    Person,
    Tag,
    User,
)
from dbresearch.schemas import (
    AutofillOut,
    BudgetLineOut,
    CategoryOut,
    DocumentDetail,
    MetadataIn,
    PersonOut,
    TagOut,
    VersionOut,
)

router = APIRouter(prefix="/documents", tags=["documents"])


def live_document(db: Session, document_id: uuid.UUID) -> Document:
    document = db.get(Document, document_id)
    if document is None or document.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return document


def editable_document(db: Session, document_id: uuid.UUID, user: User) -> Document:
    document = live_document(db, document_id)
    if not can_edit(user, document):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the uploader or an admin can do this")
    return document


def document_detail(db: Session, document: Document, user: User) -> DocumentDetail:
    out = DocumentDetail.model_validate(document)
    out.can_edit = can_edit(user, document)
    out.versions = [
        VersionOut.model_validate(v)
        for v in db.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.version_no.desc())
        )
    ]
    out.categories = [
        CategoryOut(id=c.id, name_th=c.name_th, group_key=key, source=source)
        for c, key, source in db.execute(
            select(Category, CategoryGroup.key, DocumentCategory.source)
            .join(DocumentCategory, DocumentCategory.category_id == Category.id)
            .join(CategoryGroup, CategoryGroup.id == Category.group_id)
            .where(DocumentCategory.document_id == document.id)
            .order_by(CategoryGroup.sort, Category.sort)
        )
    ]
    out.tags = [
        TagOut(name=name, source=source)
        for name, source in db.execute(
            select(Tag.name, DocumentTag.source)
            .join(DocumentTag, DocumentTag.tag_id == Tag.id)
            .where(DocumentTag.document_id == document.id)
            .order_by(Tag.name)
        )
    ]
    out.people = [
        PersonOut(
            id=p.id,
            prefix_th=p.prefix_th,
            name_th=p.name_th,
            name_en=p.name_en,
            role=link.role,
            share_pct=link.share_pct,
            unit=link.unit,
        )
        for p, link in db.execute(
            select(Person, DocumentPerson)
            .join(DocumentPerson, DocumentPerson.person_id == Person.id)
            .where(DocumentPerson.document_id == document.id)
            .order_by(DocumentPerson.role, DocumentPerson.share_pct.desc().nulls_last())
        )
    ]
    out.budget_lines = [
        BudgetLineOut.model_validate(line)
        for line in db.scalars(
            select(BudgetLine)
            .where(BudgetLine.document_id == document.id)
            .order_by(BudgetLine.sort)
        )
    ]
    return out


def _upload_errors(exc: UploadError) -> JSONResponse:
    if isinstance(exc, DuplicateUpload):
        return JSONResponse(
            {"detail": str(exc), "document_id": str(exc.document_id)}, status_code=409
        )
    return JSONResponse({"detail": str(exc)}, status_code=400)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=DocumentDetail)
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
    return document_detail(db, db.get(Document, version.document_id), user)


@router.post(
    "/{document_id}/versions", status_code=status.HTTP_201_CREATED, response_model=DocumentDetail
)
def new_version(
    document_id: uuid.UUID,
    request: Request,
    db: DB,
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
):
    document = editable_document(db, document_id, user)
    try:
        store_version(
            db, user, file.file, file.filename or "", document=document, ip=client_ip(request)
        )
    except UploadError as exc:
        db.rollback()
        return _upload_errors(exc)
    db.commit()
    return document_detail(db, document, user)


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(document_id: uuid.UUID, db: DB, user: CurrentUser):
    return document_detail(db, live_document(db, document_id), user)


@router.get("/{document_id}/autofill", response_model=AutofillOut)
def autofill(document_id: uuid.UUID, db: DB, user: CurrentUser):
    """Auto-fill suggestions for the current version (the review screen's input)."""
    document = live_document(db, document_id)
    version = db.get(DocumentVersion, document.current_version_id)
    return AutofillOut(
        status=document.status,
        ocr_status=version.ocr_status if version else None,
        version_no=version.version_no if version else None,
        suggestions=version.extracted_fields if version else None,
    )


@router.put("/{document_id}/metadata", response_model=DocumentDetail)
def save_metadata(
    document_id: uuid.UUID, body: MetadataIn, request: Request, db: DB, user: CurrentUser
):
    """Confirm the review (first time) or edit later. Marks the document ready."""
    document = editable_document(db, document_id, user)
    try:
        apply_metadata(db, user, document, body, client_ip(request))
    except ReferenceTaken as exc:
        db.rollback()
        return JSONResponse(
            {"detail": str(exc), "document_id": str(exc.document_id)}, status_code=409
        )
    except MetadataError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    db.commit()
    return document_detail(db, document, user)


@router.post("/{document_id}/reprocess", status_code=status.HTTP_202_ACCEPTED)
def reprocess(document_id: uuid.UUID, request: Request, db: DB, user: CurrentUser) -> dict:
    """Run auto-fill again on the current version (e.g. after a template was tuned).

    Saved metadata is untouched; only the suggestions are refreshed."""
    document = editable_document(db, document_id, user)
    version = db.get(DocumentVersion, document.current_version_id)
    version.ocr_status = OcrStatus.PENDING
    if document.status != DocStatus.READY:
        document.status = DocStatus.PROCESSING
    jobs.enqueue(db, "ocr", version_id=version.id)
    audit.record(
        db,
        "document.reprocess",
        "document",
        document.id,
        actor_id=user.id,
        ip=client_ip(request),
        version=version.version_no,
    )
    db.commit()
    return {"status": "queued"}


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
