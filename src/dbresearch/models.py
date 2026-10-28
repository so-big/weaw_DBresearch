"""SQLAlchemy models. Source of truth for the schema in docs/DESIGN.md §3.

Everything special (generated columns, partial / trigram indexes, the deferrable circular FK)
is declared here, so `alembic check` can prove that models and migrations agree.
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    REAL,
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    Numeric,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, INET, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
}

NOW = text("now()")
NEW_UUID = text("gen_random_uuid()")
EMPTY_JSON = text("'{}'::jsonb")
EMPTY_TEXT_ARRAY = text("'{}'::text[]")


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)
    type_annotation_map = {
        datetime: DateTime(timezone=True),
        date: Date,
        uuid.UUID: Uuid,
        str: Text,
        dict[str, Any]: JSONB,
        list[str]: ARRAY(Text),
        bytes: LargeBinary,
    }


def pg_enum(cls: type[enum.Enum], name: str) -> Enum:
    """Native PostgreSQL enum that stores the Python enum's *values* ('admin', not 'ADMIN')."""
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, server_default=NEW_UUID)


def created_at() -> Mapped[datetime]:
    return mapped_column(server_default=NOW)


# ───────────── Enums ─────────────
class UserRole(enum.StrEnum):
    ADMIN = "admin"
    USER = "user"


class UserStatus(enum.StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class FundingType(enum.StrEnum):
    EXTERNAL = "external"
    INTERNAL = "internal"


class DocKind(enum.StrEnum):
    CONTRACT = "contract"
    GRANT = "grant"


class DocStatus(enum.StrEnum):
    PROCESSING = "processing"
    NEEDS_REVIEW = "needs_review"
    READY = "ready"
    FAILED = "failed"


class BudgetLineType(enum.StrEnum):
    ITEM = "item"
    INSTALLMENT = "installment"


class OcrStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class PersonRole(enum.StrEnum):
    OWNER = "owner"
    CO_INVESTIGATOR = "co_investigator"
    PARTY = "party"
    SIGNER = "signer"


class LabelSource(enum.StrEnum):
    MANUAL = "manual"
    AUTO = "auto"


class ShareAccess(enum.StrEnum):
    PUBLIC = "public"
    PASSWORD = "password"


class ShareEvent(enum.StrEnum):
    OPEN = "open"
    VIEW = "view"
    DOWNLOAD = "download"
    BAD_PASSWORD = "bad_password"
    DENIED = "denied"


class JobState(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


# ───────────── Accounts ─────────────
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    display_name: Mapped[str]
    role: Mapped[UserRole] = mapped_column(
        pg_enum(UserRole, "user_role"), server_default=UserRole.USER.value
    )
    status: Mapped[UserStatus] = mapped_column(
        pg_enum(UserStatus, "user_status"), server_default=UserStatus.ACTIVE.value
    )
    last_login_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = mapped_column(server_default=NOW)


class AuthIdentity(Base):
    """One way to log in. Local password now; college SSO is added by the IT team later."""

    __tablename__ = "auth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "subject"),
        CheckConstraint("provider <> 'local' OR password_hash IS NOT NULL", name="local_password"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str]
    subject: Mapped[str]
    password_hash: Mapped[str | None]
    created_at: Mapped[datetime] = created_at()


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[bytes] = mapped_column(unique=True)
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = created_at()
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None]


# ───────────── People named in documents ─────────────
class Person(Base):
    __tablename__ = "people"
    __table_args__ = (
        CheckConstraint("name_th IS NOT NULL OR name_en IS NOT NULL", name="has_name"),
        Index(
            "people_name_th_trgm",
            "name_th",
            postgresql_using="gin",
            postgresql_ops={"name_th": "gin_trgm_ops"},
        ),
        Index(
            "people_name_en_trgm",
            "name_en",
            postgresql_using="gin",
            postgresql_ops={"name_en": "gin_trgm_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    prefix_th: Mapped[str | None]
    name_th: Mapped[str | None]
    name_en: Mapped[str | None]
    affiliation: Mapped[str | None]
    email: Mapped[str | None] = mapped_column(CITEXT)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_at()


# ───────────── Documents (one PDF = one contract package) ─────────────
class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from",
            name="effective_range",
        ),
        Index(
            "documents_live_idx",
            "kind",
            "funding_type",
            "fiscal_year",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # One live document per contract no.; a re-upload becomes a new version instead.
        Index(
            "documents_ref_uniq",
            "reference_no",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND reference_no IS NOT NULL"),
        ),
        Index(
            "documents_ref_seq_idx",
            "ref_year_be",
            "ref_series",
            "ref_seq",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "documents_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
        Index(
            "documents_ref_trgm",
            "reference_no",
            postgresql_using="gin",
            postgresql_ops={"reference_no": "gin_trgm_ops"},
        ),
        Index(
            "documents_text_trgm",
            "search_text",
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    kind: Mapped[DocKind] = mapped_column(pg_enum(DocKind, "doc_kind"))
    funding_type: Mapped[FundingType] = mapped_column(pg_enum(FundingType, "funding_type"))
    title: Mapped[str]  # main title as written (Thai, or English when that's all there is)
    title_en: Mapped[str | None]
    # Contract no., normalised (uppercase, no spaces): R + B.E. year + series + running no.
    reference_no: Mapped[str | None]
    ref_year_be: Mapped[int | None] = mapped_column(
        Integer,
        Computed(r"(substring(reference_no FROM '^R(\d{4})[A-Z]\d+$'))::integer", persisted=True),
    )
    ref_series: Mapped[str | None] = mapped_column(
        Text, Computed(r"substring(reference_no FROM '^R\d{4}([A-Z])\d+$')", persisted=True)
    )
    ref_seq: Mapped[int | None] = mapped_column(
        Integer,
        Computed(r"(substring(reference_no FROM '^R\d{4}[A-Z](\d+)$'))::integer", persisted=True),
    )
    document_date: Mapped[date | None]
    effective_from: Mapped[date | None]
    effective_to: Mapped[date | None]
    # Gregorian fiscal year (Oct–Sep). From the document text when stated, else from document_date.
    fiscal_year: Mapped[int | None]
    budget_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    extra: Mapped[dict[str, Any]] = mapped_column(server_default=EMPTY_JSON)
    status: Mapped[DocStatus] = mapped_column(
        pg_enum(DocStatus, "doc_status"), server_default=DocStatus.PROCESSING.value
    )
    # Circular with document_versions → created after both tables, deferred to commit time.
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "document_versions.id",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
            name="fk_documents_current_version_id_document_versions",
        )
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # Normalised text with ALL whitespace removed: search is space-insensitive (DESIGN §5).
    search_text: Mapped[str] = mapped_column(server_default=text("''"))
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = mapped_column(server_default=NOW)
    deleted_at: Mapped[datetime | None]
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class BudgetLine(Base):
    """Budget breakdown, typed manually (items for internal, installments for external)."""

    __tablename__ = "budget_lines"
    __table_args__ = (CheckConstraint("amount >= 0", name="amount_non_negative"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    line_type: Mapped[BudgetLineType] = mapped_column(pg_enum(BudgetLineType, "budget_line_type"))
    group_label: Mapped[str | None]
    label: Mapped[str]
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    due_date: Mapped[date | None]
    condition: Mapped[str | None]
    sort: Mapped[int] = mapped_column(server_default=text("0"))


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version_no"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    version_no: Mapped[int]
    storage_key: Mapped[str] = mapped_column(unique=True)  # BlobStore key (random, no filename)
    original_filename: Mapped[str]
    mime_type: Mapped[str]
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256_plain: Mapped[bytes]
    page_count: Mapped[int | None]
    wrapped_dek: Mapped[bytes]  # DEK encrypted by the KEK
    kek_id: Mapped[str]
    ocr_status: Mapped[OcrStatus] = mapped_column(
        pg_enum(OcrStatus, "ocr_status"), server_default=OcrStatus.PENDING.value
    )
    extracted_fields: Mapped[dict[str, Any] | None]
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_at()


class DocumentSection(Base):
    """A detected part of the PDF: the contract body or an attachment (เอกสารแนบหมายเลข N)."""

    __tablename__ = "document_sections"
    __table_args__ = (CheckConstraint("page_to >= page_from", name="page_range"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE")
    )
    attachment_no: Mapped[int | None]  # NULL = main body; not unique within a PDF
    heading: Mapped[str | None]
    page_from: Mapped[int]
    page_to: Mapped[int]
    template_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("extraction_templates.id"))
    match_score: Mapped[float | None] = mapped_column(REAL)


class DocumentPage(Base):
    __tablename__ = "document_pages"

    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), primary_key=True
    )
    page_no: Mapped[int] = mapped_column(primary_key=True)  # position in this PDF (1..n)
    printed_page_no: Mapped[int | None]  # 'หน้า N' from the footer
    text: Mapped[str]
    words: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    checkboxes: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ocr_confidence: Mapped[float | None] = mapped_column(REAL)


class DocumentPerson(Base):
    __tablename__ = "document_people"
    __table_args__ = (CheckConstraint("share_pct BETWEEN 0 AND 100", name="share_pct_range"),)

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("people.id"), primary_key=True)
    role: Mapped[PersonRole] = mapped_column(pg_enum(PersonRole, "person_role"), primary_key=True)
    share_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    unit: Mapped[str | None]


# ───────────── Categories (ADMIN) + free tags (USER) ─────────────
class CategoryGroup(Base):
    __tablename__ = "category_groups"

    id: Mapped[uuid.UUID] = uuid_pk()
    key: Mapped[str] = mapped_column(unique=True)
    name_th: Mapped[str]
    name_en: Mapped[str | None]
    aliases: Mapped[list[str]] = mapped_column(server_default=EMPTY_TEXT_ARRAY)
    multi: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    sort: Mapped[int] = mapped_column(server_default=text("0"))


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("group_id", "name_th"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("category_groups.id"))
    name_th: Mapped[str]
    name_en: Mapped[str | None]
    aliases: Mapped[list[str]] = mapped_column(server_default=EMPTY_TEXT_ARRAY)
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    sort: Mapped[int] = mapped_column(server_default=text("0"))


class DocumentCategory(Base):
    __tablename__ = "document_categories"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id"), primary_key=True)
    source: Mapped[LabelSource] = mapped_column(
        pg_enum(LabelSource, "label_source"), server_default=LabelSource.MANUAL.value
    )


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str]
    normalized: Mapped[str] = mapped_column(unique=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class DocumentTag(Base):
    __tablename__ = "document_tags"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tags.id"), primary_key=True)
    source: Mapped[LabelSource] = mapped_column(
        pg_enum(LabelSource, "label_source"), server_default=LabelSource.MANUAL.value
    )


# ───────────── Auto-fill templates (one per section type) ─────────────
class ExtractionTemplate(Base):
    __tablename__ = "extraction_templates"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(unique=True)
    attachment_no: Mapped[int | None]
    kind: Mapped[DocKind | None] = mapped_column(pg_enum(DocKind, "doc_kind"))
    funding_type: Mapped[FundingType | None] = mapped_column(pg_enum(FundingType, "funding_type"))
    match_rules: Mapped[dict[str, Any]]
    field_rules: Mapped[dict[str, Any]]
    checkbox_groups: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    priority: Mapped[int] = mapped_column(server_default=text("0"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(server_default=NOW)


# ───────────── Share links ─────────────
class ShareLink(Base):
    __tablename__ = "share_links"
    __table_args__ = (
        CheckConstraint(
            "(access = 'password') = (password_hash IS NOT NULL)", name="password_matches_access"
        ),
        CheckConstraint("expires_at > created_at", name="expires_after_created"),
        CheckConstraint(
            "max_downloads IS NULL OR max_downloads > 0", name="max_downloads_positive"
        ),
        Index("share_links_active_idx", "expires_at", postgresql_where=text("revoked_at IS NULL")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("document_versions.id"))
    token_hash: Mapped[bytes] = mapped_column(unique=True)
    access: Mapped[ShareAccess] = mapped_column(pg_enum(ShareAccess, "share_access"))
    password_hash: Mapped[str | None]
    allow_download: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    max_downloads: Mapped[int | None]
    download_count: Mapped[int] = mapped_column(server_default=text("0"))
    failed_attempts: Mapped[int] = mapped_column(server_default=text("0"))
    expires_at: Mapped[datetime]
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_at()
    revoked_at: Mapped[datetime | None]
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None]


class ShareAccessLog(Base):
    __tablename__ = "share_access_log"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    share_link_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("share_links.id", ondelete="CASCADE")
    )
    event: Mapped[ShareEvent] = mapped_column(pg_enum(ShareEvent, "share_event"))
    reason: Mapped[str | None]
    at: Mapped[datetime] = mapped_column(server_default=NOW)
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None]


Index("share_log_link_idx", ShareAccessLog.share_link_id, ShareAccessLog.at.desc())


# ───────────── Audit, settings, jobs ─────────────
class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str]
    entity_type: Mapped[str]
    entity_id: Mapped[uuid.UUID | None]
    details: Mapped[dict[str, Any]] = mapped_column(server_default=EMPTY_JSON)
    ip: Mapped[str | None] = mapped_column(INET)
    at: Mapped[datetime] = mapped_column(server_default=NOW)


Index("audit_entity_idx", AuditEvent.entity_type, AuditEvent.entity_id, AuditEvent.at.desc())


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[dict[str, Any]]


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("jobs_queue_idx", "run_after", postgresql_where=text("state = 'queued'")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    kind: Mapped[str]
    payload: Mapped[dict[str, Any]]
    state: Mapped[JobState] = mapped_column(
        pg_enum(JobState, "job_state"), server_default=JobState.QUEUED.value
    )
    attempts: Mapped[int] = mapped_column(server_default=text("0"))
    run_after: Mapped[datetime] = mapped_column(server_default=NOW)
    last_error: Mapped[str | None]
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = mapped_column(server_default=NOW)
