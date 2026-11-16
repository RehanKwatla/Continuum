"""Controlled, synthetic cases for qualitative evidence-quality rules.

These cases are isolated from user repositories and test the classifier only;
they are not end-to-end pipeline measurements or live production results.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EvidenceScenario:
    name: str
    statement: str
    evidence_level: str
    evidence: tuple[dict[str, Any], ...]
    expected_status: str
    freshness_status: str | None = None
    contradicting_evidence: tuple[dict[str, Any], ...] = ()


def _evidence(source_id: str, quote: str, *, path: str | None = "src/app.py", validity: str = "current_snapshot", source_type: str = "github_file") -> dict[str, Any]:
    return {"source_id": source_id, "source_type": source_type, "source_name": path or "Activity record", "file_path": path, "source_location": path, "quote": quote, "current_validity": validity}


EVIDENCE_SCENARIOS: tuple[EvidenceScenario, ...] = (
    EvidenceScenario("complete_consistent", "The API listens on port 8080", "observed", (_evidence("s1", "The API listens on port 8080"),), "supported"),
    EvidenceScenario("inferred_from_indirect_evidence", "The worker likely handles asynchronous jobs", "inferred", (_evidence("s2", "Queue worker subscribes to task events", path="worker.py"), _evidence("s3", "Task events are published after requests", path="api.py")), "provisional"),
    EvidenceScenario("insufficient_evidence", "The service uses a managed database", "unknown", (), "unknown"),
    EvidenceScenario("contradictory_sources", "The database uses PostgreSQL", "observed", (_evidence("s4", "DATABASE_URL=postgresql://...", path=".env.example"),), "contested", contradicting_evidence=({"conflict_id": "synthetic-conflict-1", "status": "open"},)),
    EvidenceScenario("stale_changed_file", "The API listens on port 8080", "observed", (_evidence("s5", "The API listens on port 8080", validity="changed"),), "stale"),
    EvidenceScenario("removed_evidence_file", "The API listens on port 8080", "observed", (_evidence("s6", "The API listens on port 8080", validity="removed"),), "stale"),
    EvidenceScenario("incomplete_source_locator", "The API listens on port 8080", "observed", ({"source_id": "s7", "source_type": "github_file", "quote": "The API listens on port 8080", "current_validity": "current_snapshot"},), "provisional"),
    EvidenceScenario("older_snapshot_unchecked", "The API listens on port 8080", "observed", (_evidence("s8", "The API listens on port 8080", validity="not_rechecked"),), "provisional"),
    EvidenceScenario("inaccessible_evidence", "Deployment uses Kubernetes", "unknown", (), "unknown", freshness_status="source_unavailable"),
    EvidenceScenario("historical_activity_not_current_behavior", "Current code uses the commit's behavior", "observed", (_evidence("s9", "Changed deployment configuration", path=None, validity="not_rechecked", source_type="github_commit"),), "provisional"),
)
