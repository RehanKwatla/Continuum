"""Extractor agent.

Turns the evidence spans of one authorised source into validated claims. The
agent itself is thin: it builds the prompt, calls the *provider* (never a vendor
SDK), and hands the raw JSON to :class:`~app.services.claim_validation.ClaimValidator`,
which is what actually decides whether a claim may exist.

Failures are contained: a provider error on one source is reported as a
:class:`ProcessingError` and the workflow moves on to the next source.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field

from app.ai.contracts import (
    EvidenceChunk,
    ExtractedClaim,
    ProcessingError,
    RawClaim,
    SourceContext,
    parse_raw_claims,
)
from app.ai.prompts import EXTRACTOR_SYSTEM, build_extractor_prompt
from app.ai.provider import LLMProvider
from app.core.config import settings
from app.core.errors import AppError, RateLimitError, UpstreamError
from app.models.enums import AccessLabel
from app.services.claim_validation import ClaimRejection, ClaimValidator

logger = logging.getLogger("continuum.ai.extractor")


@dataclass
class ExtractionOutcome:
    claims: list[ExtractedClaim] = field(default_factory=list)
    rejections: list[ClaimRejection] = field(default_factory=list)
    error: ProcessingError | None = None
    model_name: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class ExtractorAgent:
    """Extracts atomic, evidence-backed claims from a source's spans."""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        max_spans_per_prompt: int | None = None,
        max_claims_per_source: int | None = None,
        max_retries: int | None = None,
        retry_delay_seconds: float = 0.8,
    ) -> None:
        self.provider = provider
        self.max_spans_per_prompt = max(1, max_spans_per_prompt or settings.ai_max_spans_per_prompt)
        self.max_claims_per_source = max(1, max_claims_per_source or settings.ai_max_claims_per_source)
        self.max_retries = max(0, max_retries if max_retries is not None else settings.ai_max_retries)
        self.retry_delay_seconds = retry_delay_seconds

    # -- public API ----------------------------------------------------
    def extract(
        self,
        *,
        project_id: uuid.UUID,
        project_name: str,
        source: SourceContext,
        chunks: list[EvidenceChunk],
        span_access: dict[uuid.UUID, AccessLabel],
    ) -> ExtractionOutcome:
        outcome = ExtractionOutcome()
        if not chunks:
            return outcome
        outcome.model_name = self.provider.model

        validator = ClaimValidator()
        lookup = {chunk.label: chunk for chunk in chunks}

        for batch in self._batches(chunks):
            payload, error = self._call(
                project_name=project_name, source=source, chunks=batch
            )
            if error is not None:
                outcome.error = error
                return outcome

            for raw in parse_raw_claims(payload):
                if len(outcome.claims) >= self.max_claims_per_source:
                    outcome.error = ProcessingError(
                        stage="extract_claims",
                        code="claim_cap_reached",
                        message=(
                            f"Source produced more than {self.max_claims_per_source} "
                            "claims; the remainder were discarded."
                        ),
                        source_id=source.source_id,
                    )
                    break
                claim, rejection = self._validate(
                    raw,
                    project_id=project_id,
                    lookup=lookup,
                    span_access=span_access,
                    validator=validator,
                )
                if rejection is not None:
                    outcome.rejections.append(rejection)
                elif claim is not None:
                    outcome.claims.append(claim)
        return outcome

    # -- internals -----------------------------------------------------
    def _validate(
        self,
        raw: RawClaim,
        *,
        project_id: uuid.UUID,
        lookup: dict[str, EvidenceChunk],
        span_access: dict[uuid.UUID, AccessLabel],
        validator: ClaimValidator,
    ) -> tuple[ExtractedClaim | None, ClaimRejection | None]:
        return validator.validate(
            raw, project_id=project_id, lookup=lookup, span_access=span_access
        )

    def _batches(self, chunks: list[EvidenceChunk]) -> list[list[EvidenceChunk]]:
        size = self.max_spans_per_prompt
        return [chunks[index : index + size] for index in range(0, len(chunks), size)]

    def _call(
        self,
        *,
        project_name: str,
        source: SourceContext,
        chunks: list[EvidenceChunk],
    ) -> tuple[dict | None, ProcessingError | None]:
        prompt = build_extractor_prompt(
            project_name=project_name,
            source_name=source.source_name,
            source_type=source.source_type,
            chunks=chunks,
        )
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.provider.generate_json(
                    system=EXTRACTOR_SYSTEM, prompt=prompt, temperature=0.0
                )
            except (RateLimitError, UpstreamError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay_seconds * (attempt + 1))
                    continue
                break
            except AppError as exc:
                return None, ProcessingError(
                    stage="extract_claims",
                    code=exc.code,
                    message=exc.message,
                    source_id=source.source_id,
                )
            if not response.parsed:
                return None, ProcessingError(
                    stage="extract_claims",
                    code="ai_unparsable_response",
                    message="The model did not return a JSON object.",
                    source_id=source.source_id,
                )
            return response.data, None

        message = getattr(last_error, "message", None) or "The model call failed."
        code = getattr(last_error, "code", "ai_request_failed")
        logger.warning("Extraction failed for source %s: %s", source.source_id, message)
        return None, ProcessingError(
            stage="extract_claims",
            code=str(code),
            message=str(message),
            source_id=source.source_id,
        )
