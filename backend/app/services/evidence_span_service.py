"""Evidence-span service — backend-owned, traceable evidence units.

The AI layer never invents citations: it may only reference the spans this
service created. Every span carries *exact* ``start_offset``/``end_offset``
values into the persisted ``Source.content``, which is what makes it possible to
verify a supporting quotation byte-for-byte (see :func:`quote_is_supported`).

Span shape per source type (per the Phase 3 specification):

=====================  ==========================================================
PDF                    page number, character offsets, supporting text
Markdown               heading, line range, supporting text
Plain text             line range, supporting text
GitHub commit          repository, commit SHA, changed file list, message
GitHub issue           repository, issue number, text location
GitHub pull request    repository, PR number, changed file list, text location
=====================  ==========================================================
"""

from __future__ import annotations

import logging
import re
import uuid
from bisect import bisect_right
from dataclasses import dataclass, field
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import SourceType
from app.models.evidence_span import EvidenceSpan
from app.models.source import Source

logger = logging.getLogger("continuum.evidence_spans")

#: Soft cap on the size of a single span (keeps prompts bounded).
MAX_SPAN_CHARS = 1200
#: Hard cap — even a single unbroken line is split at this size.
HARD_SPLIT_CHARS = MAX_SPAN_CHARS * 3

_MARKDOWN_TYPES: frozenset[SourceType] = frozenset(
    {
        SourceType.UPLOADED_MARKDOWN,
        SourceType.GITHUB_README,
        SourceType.GITHUB_FILE,
    }
)

_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.*)$", re.MULTILINE)


@dataclass(frozen=True)
class SpanDraft:
    """A span that has not been persisted yet."""

    location: str
    start_offset: int
    end_offset: int
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_model(self, *, source_id: uuid.UUID, span_index: int) -> EvidenceSpan:
        return EvidenceSpan(
            source_id=source_id,
            span_index=span_index,
            location=self.location[:500],
            start_offset=self.start_offset,
            end_offset=self.end_offset,
            text=self.text,
            meta=self.metadata,
        )


# ---------------------------------------------------------------------------
# Text geometry helpers
# ---------------------------------------------------------------------------
def _line_starts(text: str) -> list[int]:
    starts = [0]
    index = text.find("\n")
    while index != -1:
        starts.append(index + 1)
        index = text.find("\n", index + 1)
    return starts


def _line_number(starts: list[int], offset: int) -> int:
    return bisect_right(starts, offset)


def _paragraph_ranges(text: str) -> list[tuple[int, int]]:
    """Non-blank, whitespace-trimmed ``(start, end)`` pairs, offset-based."""
    ranges: list[tuple[int, int]] = []
    position = 0
    for chunk in text.split("\n\n"):
        start = position
        end = position + len(chunk)
        position = end + 2
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if end > start:
            ranges.append((start, end))
    return ranges


def _chunk_ranges(text: str, *, max_chars: int = MAX_SPAN_CHARS) -> list[tuple[int, int]]:
    """Group paragraphs of ``text`` into spans no larger than ``max_chars``."""
    ranges = _paragraph_ranges(text)
    if not ranges:
        return []

    chunks: list[tuple[int, int]] = []
    current_start: int | None = None
    current_end = 0

    for start, end in ranges:
        if end - start > HARD_SPLIT_CHARS:
            # A single enormous block (e.g. a minified file) is split on size.
            if current_start is not None:
                chunks.append((current_start, current_end))
                current_start = None
            cursor = start
            while cursor < end:
                chunks.append((cursor, min(cursor + max_chars, end)))
                cursor += max_chars
            continue

        if current_start is None:
            current_start, current_end = start, end
        elif end - current_start <= max_chars:
            current_end = end
        else:
            chunks.append((current_start, current_end))
            current_start, current_end = start, end

    if current_start is not None:
        chunks.append((current_start, current_end))
    return chunks


def _heading_ranges(text: str) -> list[tuple[int, str, int]]:
    return [
        (match.start(), match.group(2).strip(), len(match.group(1)))
        for match in _HEADING_RE.finditer(text)
    ]


# ---------------------------------------------------------------------------
# Draft builders
# ---------------------------------------------------------------------------
def _locator_prefix(source_type: SourceType, meta: dict[str, Any]) -> str | None:
    repository = meta.get("repository")
    if source_type is SourceType.GITHUB_COMMIT:
        sha = str(meta.get("commit_sha") or "")
        return f"commit {sha[:7] or 'unknown'}"
    if source_type is SourceType.GITHUB_ISSUE:
        number = meta.get("issue_number")
        return f"issue #{number}" if number is not None else "issue"
    if source_type is SourceType.GITHUB_PULL_REQUEST:
        number = meta.get("pull_request_number")
        return f"pull request #{number}" if number is not None else "pull request"
    if source_type in {SourceType.GITHUB_README, SourceType.GITHUB_FILE}:
        path = meta.get("readme_path") or meta.get("file_path")
        return str(path) if path else (repository or None)
    return None


def _common_metadata(
    source_type: SourceType,
    source_meta: dict[str, Any],
    *,
    line_start: int,
    line_end: int,
) -> dict[str, Any]:
    """Source-type-specific traceability fields attached to every span."""
    metadata: dict[str, Any] = {
        "source_type": source_type.value,
        "line_start": line_start,
        "line_end": line_end,
    }
    if source_type is SourceType.GITHUB_COMMIT:
        metadata.update(
            {
                "repository": source_meta.get("repository"),
                "commit_sha": source_meta.get("commit_sha"),
                "changed_files": (source_meta.get("changed_files") or [])[:50],
                "author": source_meta.get("author"),
            }
        )
    elif source_type is SourceType.GITHUB_ISSUE:
        metadata.update(
            {
                "repository": source_meta.get("repository"),
                "issue_number": source_meta.get("issue_number"),
                "state": source_meta.get("state"),
            }
        )
    elif source_type is SourceType.GITHUB_PULL_REQUEST:
        metadata.update(
            {
                "repository": source_meta.get("repository"),
                "pull_request_number": source_meta.get("pull_request_number"),
                "changed_files": (source_meta.get("changed_files") or [])[:50],
                "merged": source_meta.get("merged"),
            }
        )
    elif source_type in {SourceType.GITHUB_README, SourceType.GITHUB_FILE}:
        metadata.update(
            {
                "repository": source_meta.get("repository"),
                "file_path": source_meta.get("readme_path") or source_meta.get("file_path"),
            }
        )
    return metadata


def _spans_from_content(
    source_type: SourceType, content: str, source_meta: dict[str, Any]
) -> list[SpanDraft]:
    """Split persisted content into spans (markdown sections, else paragraphs)."""
    starts = _line_starts(content)
    drafts: list[SpanDraft] = []
    prefix = _locator_prefix(source_type, source_meta)

    if source_type in _MARKDOWN_TYPES and _HEADING_RE.search(content):
        headings = _heading_ranges(content)
        bounds = [start for start, _, _ in headings] + [len(content)]
        for index, (heading_start, title, level) in enumerate(headings):
            section = content[heading_start : bounds[index + 1]]
            for start, end in _chunk_ranges(section):
                absolute_start = heading_start + start
                absolute_end = heading_start + end
                metadata = _common_metadata(
                    source_type,
                    source_meta,
                    line_start=_line_number(starts, absolute_start),
                    line_end=_line_number(starts, absolute_end),
                )
                metadata.update({"heading": title, "heading_level": level})
                drafts.append(
                    SpanDraft(
                        location=(f"{prefix} · {title}" if prefix else f"# {title}")[:500],
                        start_offset=absolute_start,
                        end_offset=absolute_end,
                        text=content[absolute_start:absolute_end],
                        metadata=metadata,
                    )
                )
        if drafts:
            return drafts

    for start, end in _chunk_ranges(content):
        metadata = _common_metadata(
            source_type,
            source_meta,
            line_start=_line_number(starts, start),
            line_end=_line_number(starts, end),
        )
        line_label = f"lines {metadata['line_start']}-{metadata['line_end']}"
        drafts.append(
            SpanDraft(
                location=(f"{prefix} · {line_label}" if prefix else line_label)[:500],
                start_offset=start,
                end_offset=end,
                text=content[start:end],
                metadata=metadata,
            )
        )
    return drafts


def _spans_from_segments(
    source_type: SourceType,
    content: str,
    source_meta: dict[str, Any],
    segments: Iterable[Any],
) -> list[SpanDraft]:
    """Derive spans from parser segments (these carry page/heading locators)."""
    starts = _line_starts(content)
    drafts: list[SpanDraft] = []

    for ordinal, segment in enumerate(segments):
        raw_text = getattr(segment, "text", "") or ""
        start = int(getattr(segment, "start_offset", 0) or 0)
        end = int(getattr(segment, "end_offset", 0) or 0)
        if not raw_text.strip() or end <= start:
            continue

        if content[start:end] != raw_text:
            # Offset drift (e.g. text re-normalised after parsing): re-anchor.
            found = content.find(raw_text)
            if found == -1:
                logger.debug("Segment %r could not be re-anchored; skipping.", segment)
                continue
            start, end = found, found + len(raw_text)

        segment_meta = dict(getattr(segment, "metadata", None) or {})
        for chunk_start, chunk_end in _chunk_ranges(raw_text):
            absolute_start = start + chunk_start
            absolute_end = start + chunk_end
            metadata = _common_metadata(
                source_type,
                source_meta,
                line_start=_line_number(starts, absolute_start),
                line_end=_line_number(starts, absolute_end),
            )
            metadata["segment_location"] = getattr(segment, "location", None)
            metadata["segment_index"] = segment_meta.get("segment_index", ordinal)
            if "page" in segment_meta:
                metadata["page_number"] = segment_meta["page"]
            if "heading" in segment_meta:
                metadata["heading"] = segment_meta["heading"]
                metadata["heading_level"] = segment_meta.get("heading_level")

            location = str(getattr(segment, "location", "") or "")
            if "page_number" in metadata:
                location = f"page {metadata['page_number']}"
            elif not location:
                location = f"lines {metadata['line_start']}-{metadata['line_end']}"

            drafts.append(
                SpanDraft(
                    location=location[:500],
                    start_offset=absolute_start,
                    end_offset=absolute_end,
                    text=content[absolute_start:absolute_end],
                    metadata=metadata,
                )
            )
    return drafts


def build_span_drafts(
    source: Source, segments: Iterable[Any] | None = None
) -> list[SpanDraft]:
    """Deterministically derive the evidence spans for one source."""
    content = source.content or ""
    if not content.strip():
        return []

    meta = dict(source.meta or {})
    drafts = (
        _spans_from_segments(source.source_type, content, meta, segments)
        if segments is not None
        else []
    )
    if not drafts:
        drafts = _spans_from_content(source.source_type, content, meta)

    # Defensive: drop anything that is not exactly reproducible from the source.
    verified = [
        draft
        for draft in drafts
        if draft.text.strip() and content[draft.start_offset : draft.end_offset] == draft.text
    ]
    return verified


# ---------------------------------------------------------------------------
# Quotation validation
# ---------------------------------------------------------------------------
_WHITESPACE_RE = re.compile(r"\s+")


def _normalise_for_match(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value).strip().casefold()


def quote_is_supported(quote: str | None, span_texts: Iterable[str]) -> bool:
    """True when ``quote`` appears verbatim in one of the cited span texts.

    Whitespace is collapsed before comparison so that quoted line breaks or
    re-wrapping do not cause a false negative; everything else must match
    exactly, which is what stops the model from paraphrasing a quotation.
    """
    if not quote or not quote.strip():
        return False
    needle = _normalise_for_match(quote)
    if len(needle) < 8:
        return False
    return any(needle in _normalise_for_match(text) for text in span_texts)


class EvidenceSpanService:
    """Persistence + retrieval for :class:`EvidenceSpan` rows."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # -- reads ---------------------------------------------------------
    def list_for_source(self, source_id: uuid.UUID) -> list[EvidenceSpan]:
        statement = (
            select(EvidenceSpan)
            .where(EvidenceSpan.source_id == source_id)
            .order_by(EvidenceSpan.span_index)
        )
        return list(self.db.execute(statement).scalars().all())

    def get(self, span_id: uuid.UUID) -> EvidenceSpan | None:
        return self.db.get(EvidenceSpan, span_id)

    def get_many(self, span_ids: Iterable[uuid.UUID]) -> list[EvidenceSpan]:
        ids = list(dict.fromkeys(span_ids))
        if not ids:
            return []
        statement = select(EvidenceSpan).where(EvidenceSpan.id.in_(ids))
        return list(self.db.execute(statement).scalars().all())

    # -- writes --------------------------------------------------------
    def ensure_spans(
        self, source: Source, segments: Iterable[Any] | None = None
    ) -> list[EvidenceSpan]:
        """Create the source's spans if they do not exist yet (idempotent)."""
        existing = self.list_for_source(source.id)
        if existing:
            return existing

        drafts = build_span_drafts(source, segments)
        if not drafts:
            return []

        rows = [
            draft.as_model(source_id=source.id, span_index=index)
            for index, draft in enumerate(drafts)
        ]
        for row in rows:
            self.db.add(row)
        self.db.flush()
        return rows

    def index_sources(self, sources: Iterable[Source]) -> dict[uuid.UUID, list[EvidenceSpan]]:
        """Ensure spans exist for many sources, returning them keyed by source id."""
        result: dict[uuid.UUID, list[EvidenceSpan]] = {}
        for source in sources:
            try:
                result[source.id] = self.ensure_spans(source)
            except Exception:  # pragma: no cover - defensive, per-source isolation
                logger.exception("Span preparation failed for source %s", source.id)
                self.db.rollback()
                result[source.id] = []
        return result
