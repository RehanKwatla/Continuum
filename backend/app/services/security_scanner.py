"""Secret / sensitive-content scanner.

Runs *before* any content is persisted or handed to a future AI workflow.

Guarantees:
  * no detected secret value is ever logged or returned in full;
  * detected values are redacted in the stored content;
  * a precise, value-free warning is recorded on the source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

REDACTION_TEMPLATE = "[REDACTED:{kind}]"

#: ``(kind, compiled pattern)`` pairs. Order matters: the first matching
#: pattern at a given position wins.
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private_key_block",
        re.compile(
            r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY-----"
            r"[\s\S]{0,8000}?-----END (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY-----"
        ),
    ),
    ("ssh_private_key", re.compile(r"-----BEGIN OPENSSH PRIVATE KEY-----")),
    ("aws_access_key_id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    (
        "aws_secret_access_key",
        re.compile(
            r"(?i)\baws[_\- ]?(?:secret[_\- ]?)?access[_\- ]?key\b\s*[:=]\s*[\"']?([A-Za-z0-9/+=]{40})"
        ),
    ),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,255}\b")),
    ("github_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,255}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,255}\b")),
    ("slack_webhook", re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9/_-]{20,}")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    ("stripe_secret_key", re.compile(r"\bsk_(?:live|test)_[0-9a-zA-Z]{16,}\b")),
    ("npm_token", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{20}T3BlbkFJ[A-Za-z0-9]{20}\b")),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b"),
    ),
    (
        "connection_string",
        re.compile(
            r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp|mssql)"
            r"://[^:\s/@]{1,64}:[^@\s/]{3,128}@[^\s\"']{1,200}"
        ),
    ),
    (
        "bearer_token",
        re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/]{24,}={0,3}"),
    ),
    (
        "generic_secret_assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|apikey|secret|client[_-]?secret|access[_-]?token|"
            r"auth[_-]?token|private[_-]?key|password|passwd|pwd)\b\s*[:=]\s*"
            r"[\"']?([A-Za-z0-9!@#$%^&*()_+\-]{12,})[\"']?"
        ),
    ),
    (
        "env_style_secret",
        re.compile(
            r"(?m)^[ \t]*[A-Z][A-Z0-9_]*"
            r"(?:SECRET|TOKEN|PASSWORD|PASSWD|API_KEY|APIKEY|PRIVATE_KEY|CREDENTIALS)"
            r"[A-Z0-9_]*[ \t]*=[ \t]*\S+"
        ),
    ),
)

#: Sensitive-looking *identifiers* used for warnings only (never redacted blindly).
_SENSITIVE_KEYWORDS = re.compile(
    r"(?i)\b(password|passwd|secret|api[_-]?key|access[_-]?token|private[_-]?key|credential)s?\b"
)


@dataclass(frozen=True)
class SecretFinding:
    """A single detection. Contains no secret material."""

    kind: str
    line_number: int
    masked_preview: str
    match_length: int

    def as_warning(self) -> str:
        return (
            f"Sensitive value detected ({self.kind}) on line {self.line_number} "
            f"was redacted before storage."
        )


@dataclass
class ScanResult:
    findings: list[SecretFinding] = field(default_factory=list)
    redacted_content: str = ""
    mentions_sensitive_keyword: bool = False

    @property
    def has_secrets(self) -> bool:
        return bool(self.findings)

    @property
    def warnings(self) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for finding in self.findings:
            key = finding.kind
            if key in seen:
                continue
            seen.add(key)
            out.append(finding.as_warning())
        return out

    @property
    def summary(self) -> dict[str, object]:
        """Value-free metadata safe to persist in ``Source.metadata``."""
        return {
            "has_secrets": self.has_secrets,
            "secret_types": sorted({f.kind for f in self.findings}),
            "secret_count": len(self.findings),
        }


def mask_secret(value: str, keep: int = 4) -> str:
    """Return a preview that reveals at most ``keep`` leading characters."""
    cleaned = value.strip().strip("'\"")
    if len(cleaned) <= keep:
        return "*" * len(cleaned)
    return f"{cleaned[:keep]}{'*' * min(8, len(cleaned) - keep)}"


def _line_number(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _spans_for(text: str) -> list[tuple[int, int, str]]:
    """Collect non-overlapping ``(start, end, kind)`` spans, earliest first."""
    spans: list[tuple[int, int, str]] = []
    claimed: list[tuple[int, int]] = []

    def overlaps(start: int, end: int) -> bool:
        return any(start < c_end and end > c_start for c_start, c_end in claimed)

    for kind, pattern in _SECRET_PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span()
            if start == end or overlaps(start, end):
                continue
            claimed.append((start, end))
            spans.append((start, end, kind))

    spans.sort(key=lambda item: item[0])
    return spans


def scan_text(text: str) -> ScanResult:
    """Scan ``text`` and return findings plus a redacted copy."""
    if not text:
        return ScanResult(redacted_content=text or "")

    spans = _spans_for(text)
    findings: list[SecretFinding] = []
    output: list[str] = []
    cursor = 0

    for start, end, kind in spans:
        output.append(text[cursor:start])
        raw = text[start:end]
        output.append(REDACTION_TEMPLATE.format(kind=kind))
        findings.append(
            SecretFinding(
                kind=kind,
                line_number=_line_number(text, start),
                masked_preview=mask_secret(raw),
                match_length=len(raw),
            )
        )
        cursor = end

    output.append(text[cursor:])
    return ScanResult(
        findings=findings,
        redacted_content="".join(output),
        mentions_sensitive_keyword=bool(_SENSITIVE_KEYWORDS.search(text)),
    )


def scan_bytes(payload: bytes) -> ScanResult:
    """Best-effort scan of raw bytes (used for binary-ish content)."""
    try:
        decoded = payload.decode("utf-8", errors="ignore")
    except Exception:  # pragma: no cover - defensive
        return ScanResult(redacted_content="")
    return scan_text(decoded)


def contains_private_key_header(payload: bytes) -> bool:
    return b"PRIVATE KEY-----" in payload[:8192]


def redact_lines(text: str, findings: Iterable[SecretFinding]) -> str:
    """Backwards-compatible helper: redact whole lines that contain findings."""
    line_numbers = {finding.line_number for finding in findings}
    if not line_numbers:
        return text
    lines = text.split("\n")
    for number in line_numbers:
        idx = number - 1
        if 0 <= idx < len(lines):
            lines[idx] = REDACTION_TEMPLATE.format(kind="line")
    return "\n".join(lines)
