import uuid
from datetime import datetime
from typing import Annotated
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse
from rapidfuzz import fuzz
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from dbresearch import audit, jobs, projects, search
from dbresearch.auth import DB, CurrentUser, client_ip
from dbresearch.documents import (
    MAX_BUNDLE,
    DuplicateUpload,
    TrashError,
    UploadError,
    bundle_names,
    can_edit,
    can_restore,
    close_project,
    read_version,
    reopen_project,
    restore,
    soft_delete,
    store_version,
    zip_versions,
)
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
    ProjectEvent,
    ProjectEventType,
    ProposalProject,
    Tag,
    User,
    VersionPurpose,
)
from dbresearch.schemas import (
    AutofillOut,
    BudgetLineOut,
    CancelIn,
    CategoryOut,
    CloseIn,
    ClosureFileOut,
    DocumentDetail,
    DocumentIds,
    EventOut,
    EventPatch,
    MetadataIn,
    PaperType,
    PersonOut,
    ProposalOut,
    TagOut,
    TrashItem,
    VersionOut,
)
from dbresearch.search import owners as document_owners
from dbresearch.search_text import build as build_search_text
from dbresearch.search_text import compact

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
    versions = db.scalars(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document.id)
        .order_by(DocumentVersion.version_no.desc())
    ).all()
    out.versions = [
        VersionOut.model_validate(v) for v in versions if v.purpose == VersionPurpose.MAIN
    ]
    out.closure_files = [
        closure_file(v, document) for v in versions if v.purpose == VersionPurpose.CLOSURE
    ][::-1]
    if projects.is_proposal(document):
        _proposal_detail(db, document, out, {v.id: v for v in versions})
    if document.closed_by:
        out.closed_by_name = db.scalar(
            select(User.display_name).where(User.id == document.closed_by)
        )
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


def _proposal_detail(db: Session, document: Document, out: DocumentDetail, versions: dict) -> None:
    out.state = db.scalar(select(search.state_expression()).where(Document.id == document.id))
    details = db.get(ProposalProject, document.id)
    if details is not None:
        out.proposal = ProposalOut.model_validate(details)
        if details.outcome_document_id:
            out.proposal.outcome_document_title = db.scalar(
                select(Document.title).where(Document.id == details.outcome_document_id)
            )
    out.papers = [
        closure_file(v, document)
        for v in sorted(versions.values(), key=lambda v: v.version_no)
        if v.purpose == VersionPurpose.PAPER
    ]
    names = dict(db.execute(select(User.id, User.display_name)).all())
    events = db.scalars(
        select(ProjectEvent)
        .where(ProjectEvent.document_id == document.id)
        # By the memo's date; an event without one sits on the day it was recorded.
        .order_by(
            func.coalesce(ProjectEvent.event_on, func.date(ProjectEvent.created_at)),
            ProjectEvent.created_at,
        )
    )
    for event in events:
        item = EventOut(
            id=event.id,
            event_type=event.event_type,
            event_on=event.event_on,
            memo_ref=event.memo_ref,
            details=event.details or {},
            created_at=event.created_at,
            created_by_name=names.get(event.created_by),
        )
        if (version := versions.get(event.version_id)) is not None:
            item.paper = closure_file(version, document)
            item.paper_purpose = version.purpose.value
        out.events.append(item)


def closure_file(version: DocumentVersion, document: Document) -> ClosureFileOut:
    out = ClosureFileOut.model_validate(version)
    found = version.extracted_fields or {}
    out.paper = found.get("kind")
    out.readings = {k: v["value"] for k, v in (found.get("fields") or {}).items()}
    if title := out.readings.get("title"):
        # Low = these papers may belong to another project (wrong file attached).
        names = [t for t in (document.title, document.title_en) if t]
        out.title_match = max(round(fuzz.ratio(compact(title), compact(t)), 1) for t in names)
    return out


def _upload_errors(exc: UploadError) -> JSONResponse:
    if isinstance(exc, DuplicateUpload):
        body = {"detail": str(exc), "document_id": str(exc.document_id)}
        if exc.trashed:
            body |= {"trashed": True, "can_restore": exc.can_restore}
        return JSONResponse(body, status_code=409)
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
    document = db.get(Document, version.document_id)
    if projects.is_proposal(document):
        projects.ensure_proposal(db, document)
    db.commit()
    return document_detail(db, document, user)


# ───────────── Several documents at once (select mode) ─────────────
# Declared before /{document_id} so "zip" and "trash" are not read as ids.
@router.get("/zip")
def download_zip(
    request: Request,
    db: DB,
    user: CurrentUser,
    id: Annotated[list[uuid.UUID], Query(min_length=1, max_length=MAX_BUNDLE)],
):
    """The current version of each `?id=` as one zip, decrypted and compressed on the fly.

    A plain GET so the browser streams it straight to disk. Documents deleted meanwhile are
    left out; 404 only when none is left. One `document.download` audit row per file."""
    wanted = list(dict.fromkeys(id))
    rows = {
        document.id: (document, version)
        for document, version in db.execute(
            select(Document, DocumentVersion)
            .join(DocumentVersion, DocumentVersion.id == Document.current_version_id)
            .where(Document.id.in_(wanted), Document.deleted_at.is_(None))
        )
    }
    found = [rows[i] for i in wanted if i in rows]
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    names = bundle_names((d.reference_no, v.original_filename) for d, v in found)
    ip = client_ip(request)
    for document, version in found:
        audit.record(
            db,
            "document.download",
            "document",
            document.id,
            actor_id=user.id,
            ip=ip,
            version=version.version_no,
            bundle=len(found),
        )
    db.commit()
    today = datetime.now(ZoneInfo("Asia/Bangkok")).date().isoformat()
    return StreamingResponse(
        zip_versions([(name, v) for name, (_, v) in zip(names, found, strict=True)]),
        media_type="application/zip",
        headers={
            "Content-Disposition": content_disposition("attachment", f"documents-{today}.zip"),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/trash", response_model=list[TrashItem])
def my_trash(db: DB, user: CurrentUser):
    """My bin: documents I uploaded or deleted that are in the trash (admins see all of
    them under /admin/trash). Kept until an admin purges them."""
    documents = db.scalars(
        select(Document)
        .where(
            Document.deleted_at.is_not(None),
            or_(Document.uploaded_by == user.id, Document.deleted_by == user.id),
        )
        .order_by(Document.deleted_at.desc())
    ).all()
    return trash_items(db, documents, user)


def trash_items(db: Session, documents, user: User) -> list[TrashItem]:
    names = dict(
        db.execute(
            select(User.id, User.display_name).where(
                User.id.in_({d.deleted_by for d in documents if d.deleted_by})
            )
        ).all()
    )
    owners = document_owners(db, [d.id for d in documents])
    out = []
    for document in documents:
        item = TrashItem.model_validate(document)
        item.owners = owners.get(document.id, [])
        item.deleted_by_name = names.get(document.deleted_by)
        item.can_restore = can_restore(user, document)
        out.append(item)
    return out


def _locked(db: Session, ids: list[uuid.UUID]) -> list[Document]:
    """The documents, row-locked so two people acting at once can't both move them."""
    wanted = list(dict.fromkeys(ids))
    documents = db.scalars(
        select(Document).where(Document.id.in_(wanted)).order_by(Document.id).with_for_update()
    ).all()
    if len(documents) != len(wanted):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return documents


@router.post("/trash")
def trash_many(body: DocumentIds, request: Request, db: DB, user: CurrentUser) -> dict:
    """Move several documents to the trash, all or none (each needs edit rights).

    Their share links stop working in the same transaction."""
    documents = _locked(db, body.ids)
    if any(d.deleted_at is not None for d in documents):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    if not all(can_edit(user, d) for d in documents):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the uploader or an admin can do this")
    ip = client_ip(request)
    revoked = sum(soft_delete(db, user, d, ip) for d in documents)
    db.commit()
    return {"deleted": len(documents), "revoked_links": revoked}


@router.post("/trash/restore")
def restore_many(body: DocumentIds, request: Request, db: DB, user: CurrentUser) -> dict:
    """Take documents back out of the trash, all or none. Old share links stay revoked."""
    documents = _locked(db, body.ids)
    if any(d.deleted_at is None for d in documents):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not in the trash")
    if not all(can_restore(user, d) for d in documents):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the person who deleted it or an admin can restore it"
        )
    ip = client_ip(request)
    try:
        for document in documents:
            restore(db, user, document, ip)
            db.flush()  # the next restore's contract-number check must see this one
    except TrashError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    db.commit()
    return {"restored": len(documents)}


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


@router.post(
    "/{document_id}/closure-files",
    status_code=status.HTTP_201_CREATED,
    response_model=DocumentDetail,
)
def add_closure_file(
    document_id: uuid.UUID,
    request: Request,
    db: DB,
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
):
    """Attach a closing paper (approval memo, meeting resolution). Stored encrypted like any
    version, OCR'd for search; its readings pre-fill the closing form."""
    document = editable_document(db, document_id, user)
    try:
        store_version(
            db,
            user,
            file.file,
            file.filename or "",
            document=document,
            purpose=VersionPurpose.CLOSURE,
            ip=client_ip(request),
        )
    except UploadError as exc:
        db.rollback()
        return _upload_errors(exc)
    db.commit()
    return document_detail(db, document, user)


@router.post("/{document_id}/close", response_model=DocumentDetail)
def close(document_id: uuid.UUID, body: CloseIn, request: Request, db: DB, user: CurrentUser):
    """Close the project and move it to the archive (or edit the closing details)."""
    document = editable_document(db, document_id, user)
    if document.cancelled_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A cancelled project can't be closed")
    first = document.closed_at is None
    close_project(
        db,
        user,
        document,
        closed_on=body.closed_on,
        closure_ref=body.closure_ref,
        closure_note=body.closure_note,
        ip=client_ip(request),
    )
    if projects.is_proposal(document):
        details = projects.ensure_proposal(db, document)
        details.kpi_result = (body.kpi_result or "").strip() or details.kpi_result
        if body.spent_total is not None:
            details.spent_total = body.spent_total
        if first:
            projects.record_decision(
                db,
                user,
                document,
                ProjectEventType.CLOSE,
                event_on=body.closed_on,
                memo_ref=body.closure_ref,
                details={"kpi_result": details.kpi_result} if details.kpi_result else {},
            )
    db.commit()
    return document_detail(db, document, user)


@router.post("/{document_id}/cancel", response_model=DocumentDetail)
def cancel(document_id: uuid.UUID, body: CancelIn, request: Request, db: DB, user: CurrentUser):
    """Cancel a proposal grant (ยกเลิก), or edit the cancellation details."""
    document = editable_document(db, document_id, user)
    if not projects.is_proposal(document):
        raise HTTPException(status.HTTP_409_CONFLICT, "Only proposal grants can be cancelled")
    first = document.cancelled_at is None
    try:
        projects.cancel_project(
            db,
            user,
            document,
            cancelled_on=body.cancelled_on,
            cancel_ref=body.cancel_ref,
            cancel_reason=body.cancel_reason,
            ip=client_ip(request),
        )
    except projects.ProjectError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    if first:
        projects.record_decision(
            db,
            user,
            document,
            ProjectEventType.CANCEL,
            event_on=body.cancelled_on,
            memo_ref=body.cancel_ref,
            details={"reason": document.cancel_reason} if document.cancel_reason else {},
        )
    db.commit()
    return document_detail(db, document, user)


@router.post("/{document_id}/reopen", response_model=DocumentDetail)
def reopen(document_id: uuid.UUID, request: Request, db: DB, user: CurrentUser):
    """Active again: undoes a close or (proposal grants) a cancellation. Papers stay."""
    document = editable_document(db, document_id, user)
    if document.closed_at is None and document.cancelled_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "The project is not closed")
    if document.closed_at is not None:
        reopen_project(db, user, document, client_ip(request))
    else:
        audit.record(
            db,
            "document.reopen",
            "document",
            document.id,
            actor_id=user.id,
            ip=client_ip(request),
            was="cancelled",
        )
        projects.clear_cancel(document)
    if projects.is_proposal(document):
        projects.add_event(db, user, document, ProjectEventType.REOPEN)
    db.commit()
    return document_detail(db, document, user)


@router.post(
    "/{document_id}/papers", status_code=status.HTTP_201_CREATED, response_model=DocumentDetail
)
def add_paper(
    document_id: uuid.UUID,
    request: Request,
    db: DB,
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
    paper_type: Annotated[PaperType, Form()],
    new_title: Annotated[str | None, Form(max_length=500)] = None,
):
    """Attach a memo to a proposal grant's timeline (closing, cancellation, title or budget
    change). Stored encrypted and OCR'd; what it says pre-fills the next step's form. A title
    change with `new_title` renames the project at once (the old title stays searchable)."""
    document = editable_document(db, document_id, user)
    if not projects.is_proposal(document):
        raise HTTPException(status.HTTP_409_CONFLICT, "Only proposal grants have a timeline")
    purpose = VersionPurpose.CLOSURE if paper_type == "close" else VersionPurpose.PAPER
    try:
        version = store_version(
            db,
            user,
            file.file,
            file.filename or "",
            document=document,
            purpose=purpose,
            ip=client_ip(request),
        )
    except UploadError as exc:
        db.rollback()
        return _upload_errors(exc)
    details = {}
    if paper_type == "title_change" and new_title and new_title.strip():
        details = projects.change_title(db, user, document, new_title, client_ip(request))
    projects.add_event(
        db, user, document, projects.PAPER_EVENTS[paper_type], version=version, details=details
    )
    db.flush()
    document.search_text = build_search_text(db, document)
    db.commit()
    return document_detail(db, document, user)


@router.patch("/{document_id}/events/{event_id}", response_model=DocumentDetail)
def edit_event(
    document_id: uuid.UUID,
    event_id: uuid.UUID,
    body: EventPatch,
    request: Request,
    db: DB,
    user: CurrentUser,
):
    """Correct an event's date, memo no. or note (as read from the memo)."""
    document = editable_document(db, document_id, user)
    try:
        projects.update_event(db, user, document, event_id, body, client_ip(request))
    except projects.ProjectError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    db.commit()
    return document_detail(db, document, user)


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(document_id: uuid.UUID, db: DB, user: CurrentUser):
    return document_detail(db, live_document(db, document_id), user)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: uuid.UUID, request: Request, db: DB, user: CurrentUser) -> None:
    """Move to the trash (uploader or admin). Share links stop working immediately."""
    soft_delete(db, user, editable_document(db, document_id, user), client_ip(request))
    db.commit()


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
            # A PDF opened on our origin must not run scripts with our cookies.
            "Content-Security-Policy": "sandbox",
        },
    )


@router.get("/{document_id}/file")
def download(
    document_id: uuid.UUID,
    request: Request,
    db: DB,
    user: CurrentUser,
    version: int | None = None,
    closure: int | None = None,
    paper: int | None = None,
    inline: bool = False,
):
    """The current version, `?version=N`, or closing paper `?closure=N`. `inline=true` opens
    it in the browser viewer."""
    document = live_document(db, document_id)
    query = select(DocumentVersion).where(DocumentVersion.document_id == document.id)
    if closure is not None:
        query = query.where(
            DocumentVersion.purpose == VersionPurpose.CLOSURE,
            DocumentVersion.version_no == closure,
        )
    elif paper is not None:
        query = query.where(
            DocumentVersion.purpose == VersionPurpose.PAPER, DocumentVersion.version_no == paper
        )
    elif version is None:
        query = query.where(DocumentVersion.id == document.current_version_id)
    else:
        query = query.where(
            DocumentVersion.purpose == VersionPurpose.MAIN, DocumentVersion.version_no == version
        )
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
        **({"closure_file": True} if closure is not None else {}),
        **({"paper": True} if paper is not None else {}),
    )
    db.commit()
    return stream_version(stored, inline)
