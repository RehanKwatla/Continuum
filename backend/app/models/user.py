"""User model. Identity is ultimately owned by Supabase Auth."""

from __future__ import annotations

import uuid

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.types import CreatedAt, UuidPK


class User(Base):
    __tablename__ = "users"

    id: Mapped[UuidPK]
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Supabase Auth user id (`sub` claim). Null for development-only identities.
    supabase_user_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    created_at: Mapped[CreatedAt]

    memberships: Mapped[list["WorkspaceMember"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    owned_workspaces: Mapped[list["Workspace"]] = relationship(  # noqa: F821
        back_populates="owner"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<User {self.id} {self.email}>"
