"""Explainable, non-numeric quality assessment for repository knowledge.

These labels are evidence diagnostics, not probabilities or claims of human
verification. Every dimension includes the observable rule used to classify it.
"""
from __future__ import annotations

import re
from typing import Any


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def assess_evidence_quality(
    *,
    statement: str,
    evidence_level: str,
    evidence: list[dict[str, Any]],
    contradicting_evidence: list[dict[str, Any]] | None = None,
    freshness_status: str | None = None,
) -> dict[str, Any]:
    """Return dimension labels and their rule explanations without a score."""
    contradicting = contradicting_evidence or []
    usable = [item for item in evidence if item.get("source_id")]
    independent_sources = {str(item["source_id"]) for item in usable}

    if not usable:
        reliability = ("unknown", "No linked source record is available.")
        directness = ("unknown", "No source excerpt can be compared with the statement.")
        corroboration = ("unknown", "No linked evidence sources are available.")
        completeness = ("missing", "The claim has no usable source locator or excerpt.")
    else:
        direct_types = ("github_file", "github_readme", "uploaded_document", "document")
        activity_types = ("github_commit", "github_issue", "github_pull_request", "commit", "issue", "pull_request")
        kinds = {str(item.get("source_type", "")).casefold() for item in usable}
        if any(any(kind.endswith(suffix) for suffix in direct_types) or item.get("file_path") for item in usable for kind in [str(item.get("source_type", "")).casefold()]):
            reliability = ("repository_source", "Evidence links to captured repository content or a document.")
        elif any(any(kind.endswith(suffix) for suffix in activity_types) for kind in kinds):
            reliability = ("recorded_activity", "Evidence records a commit, issue, or pull request; it may establish that activity occurred, not that current code behaves the same way.")
        elif any("analysis" in kind for kind in kinds):
            reliability = ("derived_analysis", "Evidence comes from a derived analysis and should be checked against its underlying source.")
        else:
            reliability = ("source_type_unclassified", "The linked source type has no explicit reliability rule.")

        statement_text = _normalise(statement)
        direct_quotes = [item for item in usable if item.get("quote") and _normalise(str(item["quote"])) in statement_text]
        directness = (
            ("direct_excerpt", "At least one cited excerpt is contained in the statement text.")
            if direct_quotes
            else ("indirect", "The cited excerpt does not exactly appear in the statement; this may be a summary or inference.")
        )
        corroboration = (
            ("cross_source", f"The statement is linked to {len(independent_sources)} distinct source records.")
            if len(independent_sources) > 1
            else ("single_source", "Only one distinct source record supports this statement.")
        )
        complete = [item for item in usable if item.get("quote") and (item.get("file_path") or item.get("source_location") or item.get("source_url"))]
        completeness = (
            ("located_excerpt", "Every linked source has an excerpt and a path, location, or URL.")
            if len(complete) == len(usable)
            else ("partial_locator", "At least one source is missing an excerpt or a path, location, or URL.")
        )

    statuses = {str(item.get("current_validity", "unknown")) for item in usable}
    if freshness_status in {"potentially_stale", "contradicted_by_newer_evidence", "stale"} or statuses.intersection({"changed", "removed"}):
        recency = ("stale", "A newer snapshot changed or removed referenced evidence, or the source was flagged stale.")
    elif statuses and statuses <= {"current_snapshot", "unchanged_in_newer_snapshot", "historical_record"}:
        recency = ("checked", "Referenced evidence is present in the selected snapshot or was confirmed unchanged in a newer snapshot.")
    elif usable:
        recency = ("not_rechecked", "The evidence is tied to a captured snapshot but could not be compared with current repository state.")
    else:
        recency = ("unknown", "No evidence timestamp or current-state comparison is available.")

    consistency = (
        ("contested", "A recorded conflict links to one or more of these evidence sources; keep both sides visible.")
        if contradicting
        else ("no_recorded_conflict", "No linked conflict was recorded; this is not proof that no contradiction exists.")
    )

    if not usable or evidence_level.casefold() == "unknown":
        status = "unknown"
    elif contradicting:
        status = "contested"
    elif recency[0] == "stale":
        status = "stale"
    elif evidence_level.casefold() == "observed" and directness[0] == "direct_excerpt" and recency[0] == "checked" and completeness[0] == "located_excerpt":
        status = "supported"
    else:
        status = "provisional"

    return {
        "status": status,
        "classification": evidence_level.casefold() if evidence_level.casefold() in {"observed", "inferred", "unknown"} else "unknown",
        "verification_status": "unverified",
        "last_verification_at": None,
        "dimensions": {
            "source_reliability": {"status": reliability[0], "reason": reliability[1]},
            "directness": {"status": directness[0], "reason": directness[1]},
            "recency": {"status": recency[0], "reason": recency[1]},
            "corroboration": {"status": corroboration[0], "reason": corroboration[1]},
            "consistency": {"status": consistency[0], "reason": consistency[1]},
            "completeness": {"status": completeness[0], "reason": completeness[1]},
        },
        "supporting_evidence": usable,
        "contradicting_evidence": contradicting,
        "methodology": "qualitative-rules-v1; no aggregate score or probability",
    }
