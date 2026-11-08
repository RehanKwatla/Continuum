"""Handover Writer agent.

Given the *approved* claims of a project, produce a structured handover. The
agent may not widen its input: the claim list it is shown is exactly the set of
human-verified claims, and every sentence it returns is passed through
:func:`app.services.handover_validator.validate_handover`, which deletes anything
that cannot be linked back to one of those claims.

The writer can never promote a claim's status — approval only ever happens
through the review endpoint.
"""

from __future__ import annotations

import logging
import time

from app.ai.contracts import (
    HandoverInput,
    HandoverValidation,
    ProcessingError,
    parse_raw_handover,
)
from app.ai.prompts import HANDOVER_SYSTEM, build_handover_prompt
from app.ai.provider import LLMProvider
from app.core.config import settings
from app.core.errors import AppError, RateLimitError, UpstreamError
from app.services.handover_validator import validate_handover

logger = logging.getLogger("continuum.ai.handover")


class HandoverWriterAgent:
    """Generates a claim-linked handover from approved claims only."""

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

    def write(
        self, *, project_name: str, handover_input: HandoverInput
    ) -> tuple[HandoverValidation | None, ProcessingError | None]:
        if not handover_input.claims:
            # Nothing approved yet: an empty, honest document is the correct output.
            return validate_handover(_empty_raw(), approved=handover_input), None

        payload, error = self._call(project_name=project_name, handover_input=handover_input)
        if error is not None:
            return None, error
        raw = parse_raw_handover(payload)
        return validate_handover(raw, approved=handover_input), None

    def _call(
        self, *, project_name: str, handover_input: HandoverInput
    ) -> tuple[dict | None, ProcessingError | None]:
        prompt = build_handover_prompt(
            project_name=project_name, handover_input=handover_input
        )
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.provider.generate_json(
                    system=HANDOVER_SYSTEM, prompt=prompt, temperature=0.0
                )
            except (RateLimitError, UpstreamError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay_seconds * (attempt + 1))
                    continue
                break
            except AppError as exc:
                return None, ProcessingError(
                    stage="handover", code=exc.code, message=exc.message
                )
            if not response.parsed:
                return None, ProcessingError(
                    stage="handover",
                    code="ai_unparsable_response",
                    message="The Handover Writer did not return a JSON object.",
                )
            return response.data, None

        logger.warning("Handover generation failed: %s", last_error)
        return None, ProcessingError(
            stage="handover",
            code=str(getattr(last_error, "code", "ai_request_failed")),
            message=str(getattr(last_error, "message", "The model call failed.")),
        )


class _RawHandoverStub:
    sections: list = []
    summary: str | None = None


def _empty_raw() -> _RawHandoverStub:
    return _RawHandoverStub()
