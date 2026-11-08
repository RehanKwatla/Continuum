"""Evidence schemas (shared with the Phase 3 Verifier)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EvidenceCreate(BaseModel):
    claim_id: uuid.UUID
    source_id: uuid.UUID
    source_location: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    supporting_quote: str | None = None


class EvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    claim_id: uuid.UUID
    source_id: uuid.UUID
    source_location: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    supporting_quote: str | None = None
    created_at: datetime


class EvidenceBundle(BaseModel):
    """Evidence grouped per claim, as the Handover Writer will consume it."""

    claim_id: uuid.UUID
    supporting: list[EvidenceRead] = Field(default_factory=list)
    contradicting: list[EvidenceRead] = Field(default_factory=list)
