"""GitHub OAuth connection model.

Access tokens are Fernet-encrypted at rest and are never returned by the API.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.types import CreatedAt, UuidFK, UuidPK


class GitHubConnection(Base):
    __tablename__ = "github_connections"

    id: Mapped[UuidPK]
    user_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    github_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    github_login: Mapped[str | None] = mapped_column(String(120), nullable=True)
    github_avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    encrypted_access_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_type: Mapped[str] = mapped_column(String(32), nullable=False, default="bearer")
    scopes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    connected_at: Mapped[CreatedAt]
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship()  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<GitHubConnection user={self.user_id} login={self.github_login}>"
