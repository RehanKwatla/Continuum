"""Model provider abstraction.

The agent workflow never talks to a vendor SDK directly — it depends on the
:class:`LLMProvider` protocol so the model can be swapped (Gemini today,
anything else tomorrow) without rewriting a single agent.

Configuration is pinned through environment variables
(``GEMINI_API_KEY`` / ``GEMINI_MODEL`` / ``GEMINI_API_BASE_URL``); no model
identifier is hard-coded in agent code and **no key is ever placed in a prompt**.

If no provider is configured the call raises :class:`NotConfiguredError`
(HTTP 503). Continuum does not fabricate model output to paper over a missing
key — an unconfigured deployment reports that it is unconfigured.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.config import settings
from app.core.errors import NotConfiguredError, RateLimitError, UpstreamError

logger = logging.getLogger("continuum.ai.provider")

MAX_ERROR_SNIPPET = 300


@dataclass
class LLMResponse:
    """A single structured completion."""

    data: dict[str, Any] | None
    raw_text: str
    model: str

    @property
    def parsed(self) -> bool:
        return self.data is not None


class LLMProvider(Protocol):
    """Minimal contract every model adapter must satisfy."""

    name: str
    model: str

    def generate_json(
        self,
        *,
        system: str,
        prompt: str,
        temperature: float = 0.0,
        max_output_tokens: int | None = None,
    ) -> LLMResponse:
        """Return a JSON object produced by the model for ``prompt``."""


def _extract_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        feedback = payload.get("promptFeedback") or {}
        raise UpstreamError(
            f"The model returned no candidates ({feedback.get('blockReason') or 'unknown'}).",
            code="ai_empty_response",
        )
    parts = ((candidates[0].get("content") or {}).get("parts")) or []
    return "".join(part.get("text", "") for part in parts)


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


class GeminiProvider:
    """Google Gemini REST adapter (structured JSON mode).

    Uses the public ``generateContent`` endpoint over httpx rather than a vendor
    SDK, so the dependency surface stays small and the adapter stays testable.
    """

    name = "gemini"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.gemini_api_key
        self.model = model or settings.gemini_model
        self.base_url = (base_url or settings.gemini_api_base_url).rstrip("/")
        self.timeout = timeout or settings.gemini_timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def generate_json(
        self,
        *,
        system: str,
        prompt: str,
        temperature: float = 0.0,
        max_output_tokens: int | None = None,
    ) -> LLMResponse:
        if not self.api_key:
            raise NotConfiguredError(
                "No model provider is configured (set GEMINI_API_KEY).",
                code="ai_not_configured",
            )

        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens or settings.gemini_max_output_tokens,
                "responseMimeType": "application/json",
            },
        }
        url = f"{self.base_url}/models/{self.model}:generateContent"

        try:
            response = httpx.post(
                url,
                params={"key": self.api_key},
                json=body,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise UpstreamError(
                "The model provider could not be reached.", code="ai_unreachable"
            ) from exc

        if response.status_code == 429:
            raise RateLimitError(
                "The model provider rate limit was reached. Try again shortly.",
                code="ai_rate_limited",
            )
        if response.status_code >= 400:
            logger.warning("Gemini request failed with status %s", response.status_code)
            raise UpstreamError(
                f"The model provider rejected the request ({response.status_code}): "
                f"{response.text[:MAX_ERROR_SNIPPET]}",
                code="ai_request_failed",
            )

        raw_text = _extract_text(response.json())
        try:
            data = json.loads(_strip_code_fence(raw_text))
        except (json.JSONDecodeError, TypeError):
            # A model that ignores JSON mode must not silently pass for success.
            logger.warning("Model returned non-JSON output; treating as failure.")
            return LLMResponse(data=None, raw_text=raw_text, model=self.model)

        if not isinstance(data, dict):
            return LLMResponse(data=None, raw_text=raw_text, model=self.model)
        return LLMResponse(data=data, raw_text=raw_text, model=self.model)


def get_provider() -> LLMProvider:
    """Return the configured provider, or raise if none is configured."""
    provider = GeminiProvider()
    if not provider.configured:
        raise NotConfiguredError(
            "The intelligence layer is not configured. Set GEMINI_API_KEY on the server.",
            code="ai_not_configured",
        )
    return provider
