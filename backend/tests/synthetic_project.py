"""Synthetic project dataset for the Phase 3 intelligence tests.

The dataset is deliberately small but exercises every signal the specification
asks about: several GitHub artefacts, a README, technical documentation, a
conflicting database-version reference, an ownership hand-over in time,
documentation a newer commit has superseded, plus an unfinished task and an open
question.

Two things happen here and nowhere else:

* :func:`create_tenant` / :func:`seed_synthetic_project` write **real rows** into
  PostgreSQL (no model is involved), so the deterministic parts of the pipeline —
  evidence spans, claim validation, conflict and staleness detection,
  persistence — can be tested exactly.
* :func:`typed_respond` is a **test double** handler for
  :class:`tests.fake_provider.FakeProvider`. It derives claims from the prompt the
  backend actually sent, so it can only ever cite evidence handles that exist. It
  is never used against a live model.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.ai.prompts import EXTRACTOR_SYSTEM
from app.models.enums import AccessLabel, ProcessingStatus, SourceType, WorkspaceRole
from app.models.project import Project
from app.models.source import Source
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember

from fake_provider import _first_sentence, _parse_span_blocks, auto_respond


def utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Personas / tenants
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Tenant:
    user: User
    workspace: Workspace
    project: Project
    role: WorkspaceRole


def create_tenant(
    db: Session,
    *,
    role: WorkspaceRole = WorkspaceRole.ADMIN,
    email: str | None = None,
    project_name: str = "Handover Project",
) -> Tenant:
    """Create a user, workspace, membership and project directly in the DB."""
    email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
    user = User(email=email, full_name="Test User", supabase_user_id=None)
    db.add(user)
    db.flush()

    workspace = Workspace(name=f"Workspace {email}", owner_id=user.id)
    db.add(workspace)
    db.flush()

    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role=role))
    project = Project(workspace_id=workspace.id, name=project_name)
    db.add(project)
    db.flush()
    return Tenant(user=user, workspace=workspace, project=project, role=role)


def add_member(
    db: Session, workspace: Workspace, *, role: WorkspaceRole, email: str | None = None
) -> User:
    email = email or f"member-{uuid.uuid4().hex[:8]}@example.com"
    user = User(email=email, full_name="Member", supabase_user_id=None)
    db.add(user)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role=role))
    db.flush()
    return user


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
def create_source(
    db: Session,
    project_id: uuid.UUID,
    *,
    source_type: SourceType,
    source_name: str,
    content: str,
    author: str | None = None,
    created_at_source: datetime | None = None,
    metadata: dict[str, Any] | None = None,
    access_label: AccessLabel = AccessLabel.WORKSPACE,
    external_id: str | None = None,
) -> Source:
    source = Source(
        project_id=project_id,
        source_type=source_type,
        source_name=source_name,
        external_id=external_id,
        content=content,
        meta=dict(metadata or {}),
        author=author,
        created_at_source=created_at_source,
        access_label=access_label,
        processing_status=ProcessingStatus.COMPLETED,
    )
    db.add(source)
    db.flush()
    return source


PIPELINE_SOURCES: tuple[dict[str, Any], ...] = (
    {
        "key": "architecture",
        "source_type": SourceType.UPLOADED_MARKDOWN,
        "source_name": "architecture-notes.md",
        "author": "alice",
        "created_at_source": utc(2024, 2, 10),
        "content": (
            "# Architecture Notes\n\n"
            "## Database\n\n"
            "The production database is PostgreSQL 13.\n\n"
            "## Payments\n\n"
            "The payments module is owned by Alice.\n"
        ),
    },
    {
        "key": "commit",
        "source_type": SourceType.GITHUB_COMMIT,
        "source_name": "commit 9f8c2ab",
        "author": "bob",
        "created_at_source": utc(2024, 6, 1),
        "external_id": "9f8c2ab1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7",
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
        "key": "readme",
        "source_type": SourceType.GITHUB_README,
        "source_name": "README.md",
        "author": "alice",
        "created_at_source": utc(2024, 1, 5),
        "metadata": {"repository": "acme/payments", "readme_path": "README.md"},
        "content": (
            "# Payments Service\n\n"
            "## Deployment\n\n"
            "Deployment runs the release script on the release host.\n"
        ),
    },
    {
        "key": "issue",
        "source_type": SourceType.GITHUB_ISSUE,
        "source_name": "issue #412",
        "author": "carol",
        "created_at_source": utc(2024, 7, 15),
        "external_id": "412",
        "metadata": {"repository": "acme/payments", "issue_number": 412, "state": "open"},
        "content": (
            "Retries: the webhook retry cap is three attempts.\n\n"
            "Which team owns the fraud scoring service?\n"
        ),
    },
)


def seed_synthetic_project(db: Session, project_id: uuid.UUID) -> dict[str, uuid.UUID]:
    """Insert the synthetic sources and return a ``{key: source_id}`` mapping."""
    ids: dict[str, uuid.UUID] = {}
    for spec in PIPELINE_SOURCES:
        spec = dict(spec)
        key = spec.pop("key")
        source = create_source(db, project_id, **spec)
        ids[key] = source.id
    db.flush()
    return ids


# ---------------------------------------------------------------------------
# Deterministic test double: a "well behaved model"
# ---------------------------------------------------------------------------
#: ``needle in span text`` → the claim the fake model reports. The claim texts
#: differ from the span wording on purpose for some entries, so the tests can
#: exercise both the *supported* and the *unsupported* verification paths.
_RULES: tuple[tuple[str, dict[str, Any]], ...] = (
    (
        "postgresql 13",
        {
            "text": "The production database is PostgreSQL 13.",
            "claim_type": "technical_constraint",
            "entity": "database",
            "critical": True,
            "reasoning_summary": "The source states the database version.",
        },
    ),
    (
        "postgresql 15",
        {
            "text": "The production database is PostgreSQL 15.",
            "claim_type": "technical_constraint",
            "entity": "database",
            "critical": True,
            "reasoning_summary": "The source states the database version.",
        },
    ),
    (
        "owned by alice",
        {
            "text": "The payments module is owned by Alice.",
            "claim_type": "ownership",
            "entity": "payments",
            "reasoning_summary": "The source names the owner of the module.",
        },
    ),
    (
        "owned by bob",
        {
            "text": "The payments module is owned by Bob.",
            "claim_type": "ownership",
            "entity": "payments",
            "reasoning_summary": "The source names the owner of the module.",
        },
    ),
    (
        "three attempts",
        {
            "text": "Webhook retries are capped at three attempts.",
            "claim_type": "technical_constraint",
            "entity": "payment_webhook",
            "critical": True,
            "reasoning_summary": "The source describes the retry cap.",
        },
    ),
    (
        "legacy invoices table",
        {
            "text": "The legacy invoices table still needs to be migrated.",
            "claim_type": "unfinished_work",
            "entity": "invoices",
            "reasoning_summary": "The source describes remaining work.",
        },
    ),
    (
        "which team owns",
        {
            "text": "Which team owns the fraud scoring service?",
            "claim_type": "open_question",
            "entity": "fraud_scoring",
            "reasoning_summary": "The source asks a question it does not answer.",
        },
    ),
)


def typed_extract(prompt: str) -> dict[str, Any]:
    """Emit the scripted claims for the spans present in ``prompt``.

    A "well behaved" model extracts *every* fact a span states, not just the
    first one it notices, so all matching rules for a span are reported.
    """
    claims: list[dict[str, Any]] = []
    for label, text in _parse_span_blocks(prompt).items():
        collapsed = " ".join(text.split())
        low = collapsed.casefold()
        matched = [rule for needle, rule in _RULES if needle in low]
        if matched:
            for rule in matched:
                claims.append(
                    {
                        **rule,
                        "evidence": [label],
                        "confidence": 0.9,
                        "critical": rule.get("critical", False),
                    }
                )
            continue
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


def typed_respond(system: str, prompt: str) -> dict[str, Any]:
    """Dispatch the test double: scripted extraction, auto everything else."""
    if system == EXTRACTOR_SYSTEM:
        return typed_extract(prompt)
    return auto_respond(system, prompt)
