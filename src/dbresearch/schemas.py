"""Request/response models shared by the API routers.

Years are Gregorian internally; `*_be` fields carry the Buddhist-era value for display.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, computed_field

from dbresearch.models import (
    BudgetLineType,
    DocKind,
    DocStatus,
    FundingType,
    LabelSource,
    OcrStatus,
    PersonRole,
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
    funding_type: FundingType
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


class DocumentDetail(DocumentOut):
    categories: list[CategoryOut] = []
    tags: list[TagOut] = []
    people: list[PersonOut] = []
    budget_lines: list[BudgetLineOut] = []


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
    allow_download: bool = True  # False = view-only (best effort)
    max_downloads: int | None = Field(None, ge=1, le=1000)
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


class GuestInfo(BaseModel):
    title: str
    filename: str
    pages: int | None
    size_bytes: int
    expires_at: datetime
    requires_password: bool
    unlocked: bool
    allow_download: bool
    downloads_left: int | None


class UnlockIn(BaseModel):
    password: str = Field(min_length=1, max_length=100)


class PasswordOut(BaseModel):
    password: str
