"""Authentication / identity schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str | None = None
    created_at: datetime


class AuthSessionResponse(BaseModel):
    """Returned after a successful token verification / user synchronisation."""

    user: UserProfile
    auth_provider: str
    is_dev_session: bool = False
    is_demo_session: bool = False
