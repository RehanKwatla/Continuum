"""Verifier agent.

Determines whether a claim is genuinely supported by the evidence it cites. The
model proposes a verdict; application code decides whether that verdict is
admissible:

* the quotation must be found **verbatim** in the cited span text
  (:func:`app.services.evidence_span_service.quote_is_supported`) — a paraphrase
  fails and the verdict collapses to ``none``;
* contracted span handles are resolved by the backend, so a fabricated
  contradiction reference is dropped;
* **a verdict never approves a claim.** ``supports`` maps to *Supported*;
  only a human reviewer can reach *Verified*.
"""

from __future__ import annotations

import logging
import time

from app.ai.contracts import (
    EvidenceChunk,
    ExtractedClaim,
    ProcessingError,
    VerificationResult,
    parse_raw_verification,
)
from app.ai.prompts import VERIFIER_SYSTEM, build_verifier_prompt
from app.ai.provider import LLMProvider
from app.core.config import settings
from app.core.errors import AppError, RateLimitError, UpstreamError
from app.models.enums import VerificationVerdict
from app.services.evidence_span_service import quote_is_supported

logger = logging.getLogger("continuum.ai.verifier")

_QUOTE_REJECTION_NOTE = (
    "The proposed supporting quotation could not be found verbatim in the cited "
    "evidence, so the verdict was downgraded to unsupported."
)


class VerifierAgent:
    """Verifies one claim against the exact spans it cites."""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        max_retries: int | None = None,
        retry_delay_seconds: float = 0.8,
    ) -> None:
        self.provider = provider
        self.max_retries = max(0, max_retries if max_retries is not None else settings.ai_max_retries)
        self.retry_delay_seconds = retry_delay_seconds

    def verify(
        self, *, claim: ExtractedClaim, chunks: list[EvidenceChunk]
    ) -> tuple[VerificationResult | None, ProcessingError | None]:
        if not chunks:
            # No evidence to check against: the claim stays Uncertain.
            return (
                VerificationResult(
                    claim_local_id=claim.local_id,
                    verdict=VerificationVerdict.NONE,
                    explanation="The claim cites no retrievable evidence span.",
                    model_name=None,
                ),
                None,
            )

        payload, error = self._call(claim=claim, chunks=chunks)
        if error is not None:
            return None, error

        raw = parse_raw_verification(payload)
        if raw is None:
            return None, ProcessingError(
                stage="verify_claims",
                code="ai_unparsable_response",
                message="The Verifier did not return a JSON verdict.",
            )

        verdict = self._normalise_verdict(raw.verdict)
        span_texts = [chunk.text for chunk in chunks]
        lookup = {chunk.label: chunk for chunk in chunks}

        quote = raw.supporting_quote
        quote_validated = False
        explanation = raw.explanation
        if verdict is not VerificationVerdict.NONE:
            if quote and quote_is_supported(quote, span_texts):
                quote_validated = True
            else:
                # A verdict that cannot be quoted is not admissible.
                verdict = VerificationVerdict.NONE
                quote = None
                explanation = (
                    f"{_QUOTE_REJECTION_NOTE} {explanation or ''}".strip()
                )

        contradicted = [
            lookup[handle].span_id
            for handle in raw.contradicted_by
            if handle in lookup
        ]

        return (
            VerificationResult(
                claim_local_id=claim.local_id,
                verdict=verdict,
                supporting_quote=quote if quote_validated else None,
                quote_validated=quote_validated,
                contradicted_by=contradicted,
                explanation=explanation,
                confidence=raw.confidence,
                model_name=self.provider.model,
            ),
            None,
        )

    # -- internals -----------------------------------------------------
    @staticmethod
    def _normalise_verdict(raw: str) -> VerificationVerdict:
        cleaned = (raw or "").strip().lower()
        for member in VerificationVerdict:
            if member.value == cleaned:
                return member
        return VerificationVerdict.NONE

    def _call(
        self, *, claim: ExtractedClaim, chunks: list[EvidenceChunk]
    ) -> tuple[dict | None, ProcessingError | None]:
        prompt = build_verifier_prompt(claim=claim, chunks=chunks)
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.provider.generate_json(
                    system=VERIFIER_SYSTEM, prompt=prompt, temperature=0.0
                )
            except (RateLimitError, UpstreamError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay_seconds * (attempt + 1))
                    continue
                break
            except AppError as exc:
                return None, ProcessingError(
                    stage="verify_claims", code=exc.code, message=exc.message
                )
            if not response.parsed:
                return None, ProcessingError(
                    stage="verify_claims",
                    code="ai_unparsable_response",
                    message="The Verifier returned a non-JSON response.",
                )
            return response.data, None

        logger.warning("Verification failed: %s", last_error)
        return None, ProcessingError(
            stage="verify_claims",
            code=str(getattr(last_error, "code", "ai_request_failed")),
            message=str(getattr(last_error, "message", "The model call failed.")),
        )
