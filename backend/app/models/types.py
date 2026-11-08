"""Reusable column helpers for the ORM layer."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from sqlalchemy import DateTime, Enum as SAEnum, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import mapped_column


def sa_enum(enum_cls: type[Any], name: str, length: int = 32) -> SAEnum:
    """VARCHAR-backed enum (portable, no native PG type to migrate)."""
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        length=length,
        values_callable=lambda enum: [item.value for item in enum],
    )

UuidPK = Annotated[
    uuid.UUID,
    mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    ),
]

UuidFK = Annotated[
    uuid.UUID,
    mapped_column(PGUUID(as_uuid=True), nullable=False),
]

CreatedAt = Annotated[
    datetime,
    mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    ),
]

UpdatedAt = Annotated[
    datetime,
    mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),
]

JsonObject = Annotated[
    dict[str, Any],
    mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False),
]

JsonArray = Annotated[
    list[Any],
    mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False),
]
