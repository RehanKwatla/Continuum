"""Deterministic, offline model provider used **only** by unit tests.

This module never touches the network and must not be confused with the live
Gemini integration path. The Phase 3 rule is explicit: mocked model responses may
appear in unit tests, and mocked tests must never be presented as real model
performance. Live behaviour is exercised through
:class:`app.ai.provider.GeminiProvider` behind ``GEMINI_API_KEY``; this fake
exists so the workflow, validation and persistence logic can be tested without a
key, a network call or a token budget.

Three double flavours are provided:

``FakeProvider``
    Returns scripted or auto-derived JSON. It echoes back only the evidence
    handles it was actually given, so the deterministic validators behave exactly
    as they would against a well-behaved model.
``NotConfiguredFake``
    Mimics an unconfigured deployment: every call raises
    :class:`~app.core.errors.NotConfiguredError` (HTTP 503).
``FailingFake``
    Mimics a provider outage: every call raises
    :class:`~app.core.errors.UpstreamError`.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from app.ai.provider import LLMResponse
from app.ai.prompts import EXTRACTOR_SYSTEM, HANDOVER_SYSTEM, VERIFIER_SYSTEM
from app.core.errors import NotConfiguredError, UpstreamError

Handler = Callable[[str, str], dict[str, Any]]

_HANDLE_RE = re.compile(r"\[(S\d+)\] source=")
_CLAIM_HANDLE_RE = re.compile(r"^\[(C\d+)\]\s*(?:\(([a-z_]+)\))?\s*(.*)$", re.MULTILINE)
_CLAIM_LINE_RE = re.compile(r'^CLAIM:\s*"(.*)"$', re.MULTILINE)


def _parse_span_blocks(prompt: str) -> dict[str, str]:
    """Split an extractor/verifier prompt back into ``{"S1": "<text>"}``.

    Everything outside the ``<evidence>`` block is prompt boilerplate (including
    the trailing ``Return JSON only.`` line): it must be stripped, otherwise the
    last span's text would carry the boilerplate and no verbatim quotation drawn
    from it could ever validate against the stored span.
    """
    scope = prompt.split("</evidence>", 1)[0]
    matches = list(_HANDLE_RE.finditer(scope))
    blocks: dict[str, str] = {}
    for index, match in enumerate(matches):
        label = match.group(1)
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(scope)
        body = scope[start:end]
        # Drop the provenance header line that follows the [S1] marker.
        body = body.split("\n", 1)[1] if "\n" in body else body
        blocks[label] = body.strip()
    return blocks


def _first_sentence(text: str) -> str:
    collapsed = " ".join(text.split())
    match = re.search(r"^(.{12,200}?[.!?])(?:\s|$)", collapsed)
    if match:
        return match.group(1)
    return collapsed[:160]


def auto_extract(prompt: str) -> dict[str, Any]:
    """Derive one evidence-grounded claim per span, deterministically."""
    blocks = _parse_span_blocks(prompt)
    claims: list[dict[str, Any]] = []
    for label, text in blocks.items():
        snippet = _first_sentence(text)
        if len(snippet) < 12:
            continue
        claims.append(
            {
                "text": snippet,
                "claim_type": "other",
                "entity": None,
                "evidence": [label],
                "confidence": 0.8,
                "critical": False,
                "reasoning_summary": "Auto-derived from the cited span (test double).",
            }
        )
    return {"claims": claims}


def auto_verify(prompt: str) -> dict[str, Any]:
    """Support a claim when a cited span is quotable, otherwise return ``none``."""
    blocks = _parse_span_blocks(prompt)
    claim_match = _CLAIM_LINE_RE.search(prompt)
    claim_text = claim_match.group(1) if claim_match else ""
    for text in blocks.values():
        if claim_text and claim_text.casefold() in " ".join(text.split()).casefold():
            return {
                "verdict": "supports",
                "supporting_quote": text[:400],
                "contradicted_by": [],
                "explanation": "The cited span states the claim (test double).",
                "confidence": 0.9,
            }
    if blocks:
        first = next(iter(blocks.values()))
        return {
            "verdict": "none",
            "supporting_quote": None,
            "contradicted_by": [],
            "explanation": "No cited span states the claim (test double).",
            "confidence": 0.4,
        }
    return {"verdict": "none", "supporting_quote": None, "contradicted_by": []}


def auto_handover(prompt: str) -> dict[str, Any]:
    """Emit one linked statement per approved claim handle, plus one unlinked."""
    rows = [
        (match.group(1), match.group(3).strip())
        for match in _CLAIM_HANDLE_RE.finditer(prompt)
    ]
    statements = [
        {"text": f"{text} [{handle}]", "claim_ids": [handle]} for handle, text in rows
    ]
    # A sentence with no approved handle must be rejected by the validator.
    statements.append(
        {
            "text": "The team should celebrate this release with a party.",
            "claim_ids": [],
        }
    )
    return {
        "summary": "Consolidated handover generated from approved claims only.",
        "sections": [{"key": "overview", "title": "Project overview", "statements": statements}],
    }


def auto_respond(system: str, prompt: str) -> dict[str, Any]:
    if system == EXTRACTOR_SYSTEM:
        return auto_extract(prompt)
    if system == VERIFIER_SYSTEM:
        return auto_verify(prompt)
    if system == HANDOVER_SYSTEM:
        return auto_handover(prompt)
    return {}


class FakeProvider:
    """Deterministic :class:`~app.ai.provider.LLMProvider` implementation."""

    name = "fake"

    def __init__(
        self,
        handler: Handler | None = None,
        *,
        model: str = "fake-model-v1",
        payload: dict[str, Any] | None = None,
    ) -> None:
        self._handler = handler
        self._payload = payload
        self.model = model
        self.calls: list[dict[str, Any]] = []

    def generate_json(
        self,
        *,
        system: str,
        prompt: str,
        temperature: float = 0.0,
        max_output_tokens: int | None = None,
    ) -> LLMResponse:
        self.calls.append(
            {
                "system": system,
                "prompt": prompt,
                "temperature": temperature,
                "max_output_tokens": max_output_tokens,
            }
        )
        if self._payload is not None:
            data: dict[str, Any] | None = self._payload
        elif self._handler is not None:
            data = self._handler(system, prompt)
        else:
            data = auto_respond(system, prompt)
        return LLMResponse(
            data=data, raw_text=json.dumps(data, default=str), model=self.model
        )


class NonJsonFake:
    """A provider that ignores JSON mode and returns unparsable text."""

    name = "fake"
    model = "fake-model-nonjson"

    def generate_json(
        self,
        *,
        system: str,
        prompt: str,
        temperature: float = 0.0,
        max_output_tokens: int | None = None,
    ) -> LLMResponse:
        return LLMResponse(data=None, raw_text="I cannot help with that.", model=self.model)


class NotConfiguredFake:
    """Mimics a deployment with no model key configured."""

    name = "fake"
    model = "fake-model-unconfigured"

    def generate_json(
        self,
        *,
        system: str,
        prompt: str,
        temperature: float = 0.0,
        max_output_tokens: int | None = None,
    ) -> LLMResponse:
        raise NotConfiguredError(
            "No model provider is configured (set GEMINI_API_KEY).",
            code="ai_not_configured",
        )


class FailingFake:
    """Mimics a provider outage."""

    name = "fake"
    model = "fake-model-failing"

    def generate_json(
        self,
        *,
        system: str,
        prompt: str,
        temperature: float = 0.0,
        max_output_tokens: int | None = None,
    ) -> LLMResponse:
        raise UpstreamError(
            "The model provider could not be reached.", code="ai_unreachable"
        )
