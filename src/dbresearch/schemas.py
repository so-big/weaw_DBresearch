"""Request/response models shared by the API routers.

Years are Gregorian internally; `*_be` fields carry the Buddhist-era value for display.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from dbresearch.models import DocKind, DocStatus, FundingType, OcrStatus, UserRole, UserStatus

BE_OFFSET = 543


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
