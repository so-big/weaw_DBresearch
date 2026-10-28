"""Request/response models shared by the API routers."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from dbresearch.models import UserRole, UserStatus


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
