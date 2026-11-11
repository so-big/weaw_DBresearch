"""Request/response models shared by the API routers.

Years are Gregorian internally; `*_be` fields carry the Buddhist-era value for display.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, computed_field

from dbresearch.models import (
    BudgetLineType,
    DocKind,
    DocStatus,
    FundingSource,
    FundingType,
    LabelSource,
    OcrStatus,
    PersonRole,
    ProjectEventType,
    ProposalOutcome,
    ShareAccess,
    ShareEvent,
    UserRole,
    UserStatus,
)

BE_OFFSET = 543

# INET columns come back as ipaddress objects; the API shows them as text.
IpText = Annotated[str | None, BeforeValidator(lambda v: None if v is None else str(v))]


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=500)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    role: UserRole
    status: UserStatus
    last_login_at: datetime | None


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version_no: int
    original_filename: str
    size_bytes: int
    page_count: int | None
    ocr_status: OcrStatus
    uploaded_by: uuid.UUID
    created_at: datetime


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: DocKind | None
    funding_type: FundingType | None
    funding_source: FundingSource | None = None
    funder_name: str | None = None
    title: str
    title_en: str | None
    reference_no: str | None
    document_date: date | None
    effective_from: date | None
    effective_to: date | None
    fiscal_year: int | None
    budget_total: Decimal | None
    status: DocStatus
    uploaded_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    closed_on: date | None = None
    closed_at: datetime | None = None
    closure_ref: str | None = None
    closure_note: str | None = None
    cancelled_on: date | None = None
    cancelled_at: datetime | None = None
    cancel_ref: str | None = None
    cancel_reason: str | None = None
    can_edit: bool = False
    versions: list[VersionOut] = []

    @computed_field
    @property
    def fiscal_year_be(self) -> int | None:
        return self.fiscal_year + BE_OFFSET if self.fiscal_year else None


# ───────────── Review / metadata ─────────────
class CategoryChoice(BaseModel):
    category_id: uuid.UUID
    source: LabelSource = LabelSource.MANUAL


class TagChoice(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    source: LabelSource = LabelSource.MANUAL


class PersonIn(BaseModel):
    person_id: uuid.UUID | None = None  # reuse an existing person
    prefix_th: str | None = Field(None, max_length=100)
    name_th: str | None = Field(None, max_length=200)
    name_en: str | None = Field(None, max_length=200)
    role: PersonRole
    share_pct: Decimal | None = Field(None, ge=0, le=100)
    unit: str | None = Field(None, max_length=300)


class BudgetLineIn(BaseModel):
    line_type: BudgetLineType
    group_label: str | None = Field(None, max_length=200)
    label: str = Field(min_length=1, max_length=300)
    amount: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    percent: Decimal | None = Field(None, ge=0, le=100)
    due_date: date | None = None
    condition: str | None = Field(None, max_length=1000)


class MetadataIn(BaseModel):
    """Everything the review screen confirms. Years are Gregorian; the UI converts พ.ศ."""

    title: str = Field(min_length=1, max_length=500)
    title_en: str | None = Field(None, max_length=500)
    kind: DocKind
    # Needed except for programme papers ('other'); set from funding_source when given.
    funding_type: FundingType | None = None
    funding_source: FundingSource | None = None
    funder_name: str | None = Field(None, max_length=300)
    reference_no: str | None = Field(None, max_length=50)
    document_date: date | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    fiscal_year: int | None = Field(None, ge=1950, le=2200)
    budget_total: Decimal | None = Field(None, ge=0, max_digits=14, decimal_places=2)
    categories: list[CategoryChoice] = []
    tags: list[TagChoice] = []
    people: list[PersonIn] = []
    budget_lines: list[BudgetLineIn] | None = None  # None = keep the existing lines
    proposal: "ProposalIn | None" = None  # proposal-development grants only


class ProposalIn(BaseModel):
    """The fields only a proposal-development grant has (DESIGN §11)."""

    request_ref: str | None = Field(None, max_length=200)
    research_area: str | None = Field(None, max_length=300)
    kpi_target: str | None = Field(None, max_length=2000)
    kpi_due: date | None = None
    kpi_result: str | None = Field(None, max_length=2000)
    spent_total: Decimal | None = Field(None, ge=0, max_digits=14, decimal_places=2)
    outcome: ProposalOutcome | None = None
    outcome_funder: str | None = Field(None, max_length=300)
    outcome_document_id: uuid.UUID | None = None


class ProposalOut(ProposalIn):
    model_config = ConfigDict(from_attributes=True)

    outcome_document_title: str | None = None


class EventOut(BaseModel):
    id: uuid.UUID
    event_type: ProjectEventType
    event_on: date | None
    memo_ref: str | None
    details: dict
    created_at: datetime
    created_by_name: str | None = None
    paper: "ClosureFileOut | None" = None  # the memo, with what the system read from it
    paper_purpose: str | None = None  # 'main' | 'closure' | 'paper' (which file link to use)


class CancelIn(BaseModel):
    """Cancel a project (ยกเลิก). The date is the approval date on the cancellation memo."""

    cancelled_on: date | None = None
    cancel_ref: str | None = Field(None, max_length=200)
    cancel_reason: str | None = Field(None, max_length=2000)


class EventPatch(BaseModel):
    event_on: date | None = None
    memo_ref: str | None = Field(None, max_length=200)
    note: str | None = Field(None, max_length=2000)


PaperType = Literal["title_change", "budget_change", "close", "cancel", "other"]


class CategoryOut(BaseModel):
    id: uuid.UUID
    name_th: str
    group_key: str
    source: LabelSource


class TagOut(BaseModel):
    name: str
    source: LabelSource


class PersonOut(BaseModel):
    id: uuid.UUID
    prefix_th: str | None
    name_th: str | None
    name_en: str | None
    role: PersonRole
    share_pct: Decimal | None
    unit: str | None


class BudgetLineOut(BudgetLineIn):
    model_config = ConfigDict(from_attributes=True)


class ClosureFileOut(BaseModel):
    """A closing paper (approval memo, meeting resolution) attached to a closed project."""

    model_config = ConfigDict(from_attributes=True)

    version_no: int
    original_filename: str
    size_bytes: int
    page_count: int | None
    ocr_status: OcrStatus
    created_at: datetime
    paper: str | None = None  # 'memo' | 'resolution' as read from the scan
    readings: dict = {}  # suggestions: memo_date, meeting_date, memo_no, title, owner, …
    title_match: float | None = None  # 0–100: does its title match the contract's?


class DocumentDetail(DocumentOut):
    categories: list[CategoryOut] = []
    tags: list[TagOut] = []
    people: list[PersonOut] = []
    budget_lines: list[BudgetLineOut] = []
    closed_by_name: str | None = None
    closure_files: list[ClosureFileOut] = []
    # Proposal-development grants (DESIGN §11)
    state: str | None = None  # active / overdue / closed / cancelled
    proposal: ProposalOut | None = None
    events: list[EventOut] = []
    papers: list[ClosureFileOut] = []  # cancellation / change memos


class CloseIn(BaseModel):
    """Close the project (ปิดโครงการ). The date is the approval date on the closing papers."""

    closed_on: date | None = None
    closure_ref: str | None = Field(None, max_length=200)
    closure_note: str | None = Field(None, max_length=2000)
    # Proposal grants: what was delivered and spent (stored on the project).
    kpi_result: str | None = Field(None, max_length=2000)
    spent_total: Decimal | None = Field(None, ge=0, max_digits=14, decimal_places=2)


class CategoryNew(BaseModel):
    """A category option any user adds while reviewing (DESIGN §10: no admin approval)."""

    group_id: uuid.UUID
    name_th: str = Field(min_length=1, max_length=200)


class AutofillOut(BaseModel):
    status: DocStatus
    ocr_status: OcrStatus | None
    version_no: int | None
    suggestions: dict | None  # the extracted_fields payload (DESIGN §6)


# ───────────── Search / pickers ─────────────
class DocumentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    title_en: str | None
    kind: DocKind | None
    funding_type: FundingType | None
    reference_no: str | None
    fiscal_year: int | None
    status: DocStatus
    uploaded_by: uuid.UUID
    updated_at: datetime
    closed_on: date | None = None
    closed_at: datetime | None = None
    funding_source: FundingSource | None = None
    budget_total: Decimal | None = None
    cancelled_at: datetime | None = None
    # Proposal grants
    state: str | None = None
    kpi_due: date | None = None
    department: str | None = None
    request_ref: str | None = None  # request memo no. (proposal grants)
    owners: list[str] = []
    snippet: str | None = None  # match wrapped in [[ ]] for highlighting

    @computed_field
    @property
    def fiscal_year_be(self) -> int | None:
        return self.fiscal_year + BE_OFFSET if self.fiscal_year else None


class TrashItem(DocumentSummary):
    deleted_at: datetime
    deleted_by: uuid.UUID | None
    deleted_by_name: str | None = None
    can_restore: bool = False


class DocumentIds(BaseModel):
    """Several documents at once (select mode): move to the trash or restore."""

    ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class SearchOut(BaseModel):
    items: list[DocumentSummary]
    total: int
    page: int
    page_size: int
    facets: dict | None = None


class CategoryOption(BaseModel):
    id: uuid.UUID
    name_th: str
    name_en: str | None
    active: bool


class CategoryGroupOut(BaseModel):
    id: uuid.UUID
    key: str
    name_th: str
    name_en: str | None
    multi: bool
    options: list[CategoryOption]


class PersonBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prefix_th: str | None
    name_th: str | None
    name_en: str | None


# ───────────── Share links ─────────────
class ShareCreate(BaseModel):
    access: ShareAccess = ShareAccess.PUBLIC
    ttl_hours: int | None = Field(None, ge=1, le=24 * 365)  # default from settings (24 h)
    # False only hides the guest's download button: the viewer can still save and print.
    # The web app no longer offers it (2026-11-11); kept for older links and API callers.
    allow_download: bool = True
    max_downloads: int | None = Field(None, ge=1, le=1000)  # file opens, view or download
    version_no: int | None = None  # pin a version; default = always the latest
    note: str | None = Field(None, max_length=300)


class ShareOut(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    access: ShareAccess
    allow_download: bool
    max_downloads: int | None
    download_count: int
    failed_attempts: int
    expires_at: datetime
    created_at: datetime
    created_by: uuid.UUID
    created_by_name: str | None = None
    revoked_at: datetime | None
    note: str | None
    state: str


class ShareCreated(ShareOut):
    """Returned once: the token and password are never retrievable again."""

    token: str
    path: str  # '/s/<token>' — the frontend prefixes its own origin
    password: str | None


class ShareLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event: ShareEvent
    reason: str | None
    at: datetime
    ip: IpText
    user_agent: str | None
    user_name: str | None = None  # who it was, when they were logged in


class GuestInfo(BaseModel):
    """Until a password link is unlocked only the first three fields are filled in."""

    expires_at: datetime
    requires_password: bool
    unlocked: bool
    title: str | None = None
    filename: str | None = None
    pages: int | None = None
    size_bytes: int | None = None
    allow_download: bool | None = None
    downloads_left: int | None = None


class UnlockIn(BaseModel):
    password: str = Field(min_length=1, max_length=100)


class PasswordOut(BaseModel):
    password: str


MetadataIn.model_rebuild()
EventOut.model_rebuild()
