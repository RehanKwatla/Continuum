"""Deterministic staleness detection.

Two signals are used, and both require an actual *relationship* between sources:

1. **File supersession.** A commit or pull request that changed a file also
   described by an older README/document makes that document a candidate for
   review (``README.md`` still describes the file that has since changed).
2. **Newer contradictory evidence.** When two claims disagree about the same
   property and one of them comes from a strictly newer source, the older source
   is marked ``contradicted_by_newer_evidence``.

An old source is **not** stale merely for being old. Nothing here rewrites,
hides or replaces the older information — it only raises a review flag, and the
older source remains fully visible in the memory.
"""

from __future__ import annotations

from datetime import datetime

from app.ai.contracts import (
    ConflictFinding,
    ExtractedClaim,
    SourceContext,
    StaleWarning,
)
from app.models.enums import FreshnessStatus

#: Source types that describe a document a newer change could invalidate.
DOCUMENT_TYPES: frozenset[str] = frozenset(
    {
        "uploaded_pdf",
        "uploaded_markdown",
        "uploaded_text",
        "github_readme",
        "github_file",
    }
)

#: Source types that record a change to a file.
CHANGE_TYPES: frozenset[str] = frozenset({"github_commit", "github_pull_request"})


def _basename(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = str(value).strip().replace("\\", "/").rstrip("/")
    if not cleaned:
        return None
    return cleaned.rsplit("/", 1)[-1].casefold()


def _document_names(source: SourceContext) -> set[str]:
    names = {_basename(source.source_name)}
    for key in ("file_path", "readme_path"):
        names.add(_basename(source.metadata.get(key)))
    return {name for name in names if name}


def _changed_names(source: SourceContext) -> set[str]:
    changed = source.metadata.get("changed_files") or []
    if not isinstance(changed, list):
        return set()
    names = {_basename(str(item)) for item in changed}
    return {name for name in names if name}


class StalenessDetector:
    """Time-aware, relationship-aware staleness detector."""

    def detect(
        self,
        *,
        sources: list[SourceContext],
        claims: list[ExtractedClaim],
        conflicts: list[ConflictFinding],
    ) -> list[StaleWarning]:
        warnings: dict[object, StaleWarning] = {}
        by_id = {source.source_id: source for source in sources}

        self._flag_superseded_documents(sources, warnings)
        self._flag_contradicted_sources(claims, conflicts, by_id, warnings)
        return list(warnings.values())

    # -- rule 1 --------------------------------------------------------
    def _flag_superseded_documents(
        self,
        sources: list[SourceContext],
        warnings: dict[object, StaleWarning],
    ) -> None:
        documents = [source for source in sources if source.source_type in DOCUMENT_TYPES]
        if not documents:
            return

        for change in sources:
            if change.source_type not in CHANGE_TYPES:
                continue
            changed = _changed_names(change)
            if not changed:
                continue
            for document in documents:
                if document.source_id == change.source_id:
                    continue
                overlap = _document_names(document) & changed
                if not overlap:
                    continue
                if not self._is_newer(change.source_date, document.source_date):
                    continue
                self._record(
                    warnings,
                    StaleWarning(
                        source_id=document.source_id,
                        status=FreshnessStatus.POTENTIALLY_STALE,
                        reason=(
                            f"'{sorted(overlap)[0]}' was changed by "
                            f"'{change.source_name}' after this source was written; "
                            "the description may no longer match the code."
                        ),
                        related_source_id=change.source_id,
                    ),
                )

    # -- rule 2 --------------------------------------------------------
    def _flag_contradicted_sources(
        self,
        claims: list[ExtractedClaim],
        conflicts: list[ConflictFinding],
        by_id: dict[object, SourceContext],
        warnings: dict[object, StaleWarning],
    ) -> None:
        claim_index = {claim.local_id: claim for claim in claims}
        for conflict in conflicts:
            if conflict.kind != "value_disagreement" or len(conflict.claim_local_ids) < 2:
                continue
            parties = [
                claim_index[local_id]
                for local_id in conflict.claim_local_ids
                if local_id in claim_index
            ]
            for claim in parties:
                for other in parties:
                    if other.local_id == claim.local_id:
                        continue
                    if not self._newer_claim(other, claim):
                        continue
                    for source_id in claim.source_ids:
                        source = by_id.get(source_id)
                        if source is None:
                            continue
                        self._record(
                            warnings,
                            StaleWarning(
                                source_id=source_id,
                                status=FreshnessStatus.CONTRADICTED_BY_NEWER_EVIDENCE,
                                reason=(
                                    "Newer evidence disagrees with this source about "
                                    f"'{conflict.property_key or conflict.entity or 'a property'}'."
                                ),
                                related_source_id=(
                                    other.source_ids[0] if other.source_ids else None
                                ),
                            ),
                        )

    # -- helpers -------------------------------------------------------
    @staticmethod
    def _is_newer(candidate: datetime | None, baseline: datetime | None) -> bool:
        if candidate is None or baseline is None:
            return False
        return candidate > baseline

    @staticmethod
    def _newer_claim(candidate: ExtractedClaim, baseline: ExtractedClaim) -> bool:
        if candidate.time_context is None:
            return False
        if baseline.time_context is None:
            return True
        return candidate.time_context > baseline.time_context

    @staticmethod
    def _record(
        warnings: dict[object, StaleWarning],
        warning: StaleWarning,
    ) -> None:
        existing = warnings.get(warning.source_id)
        if existing is None:
            warnings[warning.source_id] = warning
            return
        # A contradicted source outranks a merely-superseded one.
        if existing.status is FreshnessStatus.CONTRADICTED_BY_NEWER_EVIDENCE:
            return
        if warning.status is FreshnessStatus.CONTRADICTED_BY_NEWER_EVIDENCE:
            warnings[warning.source_id] = warning
