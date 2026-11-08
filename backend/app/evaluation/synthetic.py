"""Synthetic evaluation project seeding (Phase 5 §9, §15).

Creates the **inputs** of the ground-truth project as real rows: a workspace
project plus its source documents, a GitHub commit, a README, an issue and one
restricted document. It does **not** create claims — those must come out of the
real reconstruction pipeline, which is exactly what the evaluation measures.

The builder is used by the API (a non-production, admin-gated endpoint) and by
the test suite, so the dataset is exercised through the same code path the
product uses.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.evaluation.ground_truth import GROUND_TRUTH_PROJECT_NAME
from app.models.enums import AccessLabel, ProcessingStatus, SourceType
from app.models.project import Project
from app.models.source import Source


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


#: The synthetic source corpus, in ingestion order.
SYNTHETIC_SOURCES: tuple[dict[str, Any], ...] = (
    {
        "source_type": SourceType.UPLOADED_MARKDOWN,
        "source_name": "architecture-notes.md",
        "author": "alice",
        "created_at_source": _utc(2024, 2, 10),
        "content": (
            "# Architecture Notes\n\n"
            "## Database\n\n"
            "The production database is PostgreSQL 13.\n\n"
            "## Payments\n\n"
            "The payments module is owned by Alice.\n"
        ),
    },
    {
        "source_type": SourceType.GITHUB_COMMIT,
        "source_name": "commit 9f8c2ab",
        "author": "bob",
        "external_id": "9f8c2ab1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7",
        "created_at_source": _utc(2024, 6, 1),
        "metadata": {
            "repository": "acme/payments",
            "commit_sha": "9f8c2ab1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7",
            "changed_files": ["README.md", "scripts/release.sh"],
            "author": "bob",
        },
        "content": (
            "The production database is PostgreSQL 15.\n\n"
            "The payments module is owned by Bob.\n\n"
            "The legacy invoices table still needs to be migrated.\n"
        ),
    },
    {
        "source_type": SourceType.GITHUB_README,
        "source_name": "README.md",
        "author": "alice",
        "created_at_source": _utc(2024, 1, 5),
        "metadata": {"repository": "acme/payments", "readme_path": "README.md"},
        "content": (
            "# Payments Service\n\n"
            "## Deployment\n\n"
            "Deployment runs the release script on the release host.\n"
        ),
    },
    {
        "source_type": SourceType.GITHUB_ISSUE,
        "source_name": "issue #412",
        "author": "carol",
        "external_id": "412",
        "created_at_source": _utc(2024, 7, 15),
        "metadata": {"repository": "acme/payments", "issue_number": 412, "state": "open"},
        "content": (
            "Retries: the webhook retry cap is three attempts.\n\n"
            "Which team owns the fraud scoring service?\n"
        ),
    },
    {
        "source_type": SourceType.UPLOADED_MARKDOWN,
        "source_name": "restricted-credentials.md",
        "author": "alice",
        "created_at_source": _utc(2024, 3, 2),
        "access_label": AccessLabel.RESTRICTED,
        "content": (
            "# Restricted Credentials\n\n"
            "The production signing key must be rotated every 90 days.\n"
        ),
    },
)


def seed_synthetic_evaluation_project(
    db: Session, *, workspace_id: uuid.UUID, name: str | None = None
) -> Project:
    """Create the ground-truth project and its source corpus.

    Returns the persisted :class:`~app.models.project.Project`. The caller owns
    the surrounding transaction.
    """
    project = Project(workspace_id=workspace_id, name=name or GROUND_TRUTH_PROJECT_NAME)
    db.add(project)
    db.flush()

    for spec in SYNTHETIC_SOURCES:
        spec = dict(spec)
        db.add(
            Source(
                project_id=project.id,
                source_type=spec["source_type"],
                source_name=spec["source_name"],
                external_id=spec.get("external_id"),
                content=spec["content"],
                meta=dict(spec.get("metadata") or {}),
                author=spec.get("author"),
                created_at_source=spec.get("created_at_source"),
                access_label=spec.get("access_label", AccessLabel.WORKSPACE),
                processing_status=ProcessingStatus.COMPLETED,
            )
        )
    db.flush()
    return project


__all__ = ["SYNTHETIC_SOURCES", "seed_synthetic_evaluation_project"]
