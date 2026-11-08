"""Generic data-access repository."""

from __future__ import annotations

import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Thin, typed wrapper around a SQLAlchemy session for one model."""

    model: type[ModelT]

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, entity_id: uuid.UUID) -> ModelT | None:
        return self.db.get(self.model, entity_id)

    def list(self, *, limit: int | None = None, offset: int = 0) -> list[ModelT]:
        statement = select(self.model).offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.db.execute(statement).scalars().all())

    def add(self, entity: ModelT) -> ModelT:
        self.db.add(entity)
        return entity

    def flush(self) -> None:
        self.db.flush()

    def commit(self) -> None:
        self.db.commit()

    def refresh(self, entity: ModelT) -> ModelT:
        self.db.refresh(entity)
        return entity

    def delete(self, entity: ModelT) -> None:
        self.db.delete(entity)

    def count(self, *criteria: Any) -> int:
        from sqlalchemy import func

        statement = select(func.count()).select_from(self.model)
        if criteria:
            statement = statement.where(*criteria)
        return int(self.db.execute(statement).scalar_one())
