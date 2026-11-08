"""The synthetic public-demo dataset.

This module builds one self-contained Continuum workspace — ``Continuum Demo
Workspace`` / ``Payment Gateway System`` — so a judge can explore the whole
product without signing in.

Everything here is **fabricated demonstration data**:

* no personal information, no real repositories, no access tokens and no
  confidential documents;
* the repository URL points at a non-existent organisation
  (``continuum-demo-synthetic``);
* the environment-variable names are described but their values are explicitly
  *not* recorded, exactly as a real handover should be written.

The seeder is idempotent: it looks the demo workspace/project up by name and
only builds the dataset when it is missing. :func:`reset_demo_data` throws the
synthetic workspace away and rebuilds it, which is the only write the public
demo exposes.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import DEMO_EMAIL
from app.models.audit import AuditLog
from app.models.claim import Claim
from app.models.conflict import Conflict, ConflictClaim
from app.models.enums import (
    AccessLabel,
    ClaimStatus,
    ClaimType,
    ConflictStatus,
    FreshnessStatus,
    HandoverStatus,
    OpenQuestionStatus,
    ProcessingRunStatus,
    ProcessingStatus,
    ProjectStatus,
    SourceType,
    VerificationVerdict,
    WorkspaceRole,
)
from app.models.evidence import Evidence
from app.models.evidence_span import EvidenceSpan
from app.models.handover import Handover, HandoverDocument, HandoverVersion
from app.models.open_question import OpenQuestion
from app.models.phase5 import (
    EvaluationRun,
    KnowledgeDependency,
    KnowledgeGap,
    ReadinessEvaluation,
    SuccessorTask,
)
from app.models.processing_run import ProcessingRun
from app.models.project import Project
from app.models.project_memory import ProjectMemory
from app.models.source import Source
from app.models.user import User
from app.models.verification import Verification
from app.models.workspace import Workspace, WorkspaceMember
from app.services.continuity_service import ContinuityService
from app.services.handover_service import HandoverService
from app.services.knowledge_service import KnowledgeRiskService
from app.services.readiness_service import ReadinessService
from app.services.successor_service import SuccessorService

logger = logging.getLogger("continuum.demo")

DEMO_BANNER_LABEL = "PUBLIC DEMO ENVIRONMENT"
DEMO_DATA_DISCLAIMER = (
    "Everything in this workspace is synthetic demonstration data created for the "
    "Continuum public demo. It is not a real project: it contains no personal "
    "information, no private repositories, no access tokens and no confidential "
    "documents."
)

#: Serialises the first-run build so two concurrent requests cannot race.
_seed_lock = threading.Lock()


@dataclass(frozen=True)
class DemoSeedResult:
    """Identifiers and counts of the synthetic demo workspace."""

    workspace_id: uuid.UUID
    project_id: uuid.UUID
    user_id: uuid.UUID
    workspace_name: str
    project_name: str
    created: bool
    counts: dict[str, int] = field(default_factory=dict)


def demo_workspace_name() -> str:
    return get_settings().public_demo_workspace_name


def demo_project_name() -> str:
    return get_settings().public_demo_project_name


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _days_ago(days: float) -> datetime:
    return _now() - timedelta(days=days)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Synthetic source documents
# ---------------------------------------------------------------------------
README = """# Payment Gateway System

The Payment Gateway System is an in-house service that authorises card payments, captures funds and settles them to merchant accounts.

## Current status
As of this sprint the gateway is live for card authorisation and capture. Refund handling is partially implemented and settlement is still being hardened.

## Scope
The gateway covers card authorisation, capture, refund and settlement. It excludes merchant onboarding and fraud scoring, which are owned by other teams.

## Architecture
The architecture separates the public API edge, an authorisation service, a settlement worker and a webhook dispatcher, which communicate over an internal message queue.

## Technology
The gateway is built with Python 3.12 and FastAPI, stores data in PostgreSQL 16, and runs behind Nginx on a Docker-based deployment pipeline.

## Dependencies
The gateway calls the external Payment Provider API for card authorisation and must tolerate an external service outage without corrupting the ledger.
"""

ADR_TOKENISATION = """# ADR-0007: Store network tokens instead of raw card numbers

## Status
Accepted.

## Context
Storing raw card numbers would place the gateway inside PCI-DSS scope and require a certified card-data environment.

## Decision
The team decided to store only network tokens instead of raw card numbers because it removes the PCI-DSS storage scope from the gateway.

## Consequences
Card data never reaches the gateway database; the token provider becomes a hard runtime dependency.
"""

ADR_LEDGER = """# ADR-0009: Append-only settlement ledger

## Status
Accepted.

## Context
Finance could not reconstruct past settlement totals after reconciliation disputes.

## Decision
Settlement reports were moved to an append-only ledger because reconciliation disputes previously could not be reconstructed.

## Consequences
The ledger is the system of record for settlement and must be backed up separately from the transactional database.
"""

RUNBOOK = """# Runbook: deploying and rolling back the gateway

## Deploy
Deployment is a blue-green release performed by the CI pipeline: build the Docker image, run migrations, shift traffic to the green service and verify the health endpoint.

## Rollback
To roll back a release, shift traffic back to the blue service and revert the migration with the down-migration script; never roll back a forward migration by hand.

## Routine maintenance
The settlement report signing key is rotated every quarter by running the rotate-signing-key task and publishing the new key id to the configuration store.
"""

PULL_REQUEST = """# Pull request #482 - Add retry and backoff to webhook delivery

Webhook delivery retries use exponential backoff with jitter, capped at eight attempts, in order to avoid thundering-herd retries on the payment provider.

The gateway integration with merchant systems uses signed webhooks over HTTPS and an OAuth client-credentials flow for partner APIs.

Refund handling is still in progress: the refund service recognises partial refunds but does not yet reconcile them against the ledger.
"""

ISSUE = """# Issue #511 - Idempotency keys for retried payment requests

Open question: should idempotency keys be scoped per merchant or globally per gateway?

Settlement is blocked waiting on the finance team to confirm the fee schedule before the reconciliation job can be enabled.
"""

COMMIT = """commit d4e5f6a - Add ledger reconciliation worker (feature-flagged)

The reconciliation job is disabled in production until the fee schedule is confirmed by finance.
"""

HANDOVER_NOTES = """# Handover notes (draft)

## Ownership
The authorisation service is owned by the departing lead payments engineer, who is responsible for its release approval.

The settlement worker was handed over from the departing engineer to the incoming payments platform engineer as part of this transition.

## Progress
Network token storage was delivered and is live in production for card authorisation.

## Configuration
The successor must supply the environment variables GATEWAY_DB_URL, PROVIDER_API_BASE and LEDGER_SIGNING_KEY_ID; the values themselves are held in the platform secret store and are never documented.

## Risks
Risk: if the reconciliation job is enabled before the fee schedule is confirmed, settlement totals will be wrong and the ledger will need manual correction.
"""


#: ``(key, source_type, source_name, external_id, author, days_ago, freshness, content, spans)``
#: where each span is ``(human_location, exact_substring_of_content)``.
_SOURCES: tuple[dict[str, Any], ...] = (
    {
        "key": "readme",
        "source_type": SourceType.GITHUB_README,
        "source_name": "payment-gateway/README.md",
        "external_id": "README.md",
        "author": "Demo Author",
        "days_ago": 42,
        "freshness": FreshnessStatus.CURRENT,
        "source_url": "https://github.com/continuum-demo-synthetic/payment-gateway/blob/main/README.md",
        "content": README,
        "spans": (
            ("README.md#L3", "The Payment Gateway System is an in-house service that authorises card payments, captures funds and settles them to merchant accounts."),
            ("README.md#L6", "As of this sprint the gateway is live for card authorisation and capture. Refund handling is partially implemented and settlement is still being hardened."),
            ("README.md#L9", "The gateway covers card authorisation, capture, refund and settlement. It excludes merchant onboarding and fraud scoring, which are owned by other teams."),
            ("README.md#L12", "The architecture separates the public API edge, an authorisation service, a settlement worker and a webhook dispatcher, which communicate over an internal message queue."),
            ("README.md#L15", "The gateway is built with Python 3.12 and FastAPI, stores data in PostgreSQL 16, and runs behind Nginx on a Docker-based deployment pipeline."),
            ("README.md#L18", "The gateway calls the external Payment Provider API for card authorisation and must tolerate an external service outage without corrupting the ledger."),
        ),
    },
    {
        "key": "adr_tokenisation",
        "source_type": SourceType.GITHUB_FILE,
        "source_name": "payment-gateway/docs/adr/0007-tokenisation.md",
        "external_id": "docs/adr/0007-tokenisation.md",
        "author": "Demo Author",
        "days_ago": 35,
        "freshness": FreshnessStatus.CURRENT,
        "source_url": "https://github.com/continuum-demo-synthetic/payment-gateway/blob/main/docs/adr/0007-tokenisation.md",
        "content": ADR_TOKENISATION,
        "spans": (
            ("docs/adr/0007-tokenisation.md#L10", "The team decided to store only network tokens instead of raw card numbers because it removes the PCI-DSS storage scope from the gateway."),
            ("docs/adr/0007-tokenisation.md#L13", "Card data never reaches the gateway database; the token provider becomes a hard runtime dependency."),
        ),
    },
    {
        "key": "adr_ledger",
        "source_type": SourceType.GITHUB_FILE,
        "source_name": "payment-gateway/docs/adr/0009-settlement-ledger.md",
        "external_id": "docs/adr/0009-settlement-ledger.md",
        "author": "Demo Author",
        "days_ago": 30,
        "freshness": FreshnessStatus.CURRENT,
        "source_url": "https://github.com/continuum-demo-synthetic/payment-gateway/blob/main/docs/adr/0009-settlement-ledger.md",
        "content": ADR_LEDGER,
        "spans": (
            ("docs/adr/0009-settlement-ledger.md#L10", "Settlement reports were moved to an append-only ledger because reconciliation disputes previously could not be reconstructed."),
        ),
    },
    {
        "key": "runbook",
        "source_type": SourceType.GITHUB_FILE,
        "source_name": "payment-gateway/docs/runbooks/deploy.md",
        "external_id": "docs/runbooks/deploy.md",
        "author": "Demo Author",
        "days_ago": 21,
        "freshness": FreshnessStatus.CURRENT,
        "source_url": "https://github.com/continuum-demo-synthetic/payment-gateway/blob/main/docs/runbooks/deploy.md",
        "content": RUNBOOK,
        "spans": (
            ("docs/runbooks/deploy.md#L4", "Deployment is a blue-green release performed by the CI pipeline: build the Docker image, run migrations, shift traffic to the green service and verify the health endpoint."),
            ("docs/runbooks/deploy.md#L7", "To roll back a release, shift traffic back to the blue service and revert the migration with the down-migration script; never roll back a forward migration by hand."),
            ("docs/runbooks/deploy.md#L10", "The settlement report signing key is rotated every quarter by running the rotate-signing-key task and publishing the new key id to the configuration store."),
        ),
    },
    {
        "key": "pull_request",
        "source_type": SourceType.GITHUB_PULL_REQUEST,
        "source_name": "Push #482 - Add retry and backoff to webhook delivery",
        "external_id": "#482",
        "author": "Demo Author",
        "days_ago": 14,
        "freshness": FreshnessStatus.CURRENT,
        "source_url": "https://github.com/continuum-demo-synthetic/payment-gateway/pull/482",
        "content": PULL_REQUEST,
        "spans": (
            ("pull request #482", "Webhook delivery retries use exponential backoff with jitter, capped at eight attempts, in order to avoid thundering-herd retries on the payment provider."),
            ("pull request #482", "The gateway integration with merchant systems uses signed webhooks over HTTPS and an OAuth client-credentials flow for partner APIs."),
            ("pull request #482", "Refund handling is still in progress: the refund service recognises partial refunds but does not yet reconcile them against the ledger."),
        ),
    },
    {
        "key": "issue",
        "source_type": SourceType.GITHUB_ISSUE,
        "source_name": "Issue #511 - Idempotency keys for retried payment requests",
        "external_id": "#511",
        "author": "Demo Author",
        "days_ago": 9,
        "freshness": FreshnessStatus.POTENTIALLY_STALE,
        "source_url": "https://github.com/continuum-demo-synthetic/payment-gateway/issues/511",
        "content": ISSUE,
        "spans": (
            ("issue #511", "Open question: should idempotency keys be scoped per merchant or globally per gateway?"),
            ("issue #511", "Settlement is blocked waiting on the finance team to confirm the fee schedule before the reconciliation job can be enabled."),
        ),
    },
    {
        "key": "commit",
        "source_type": SourceType.GITHUB_COMMIT,
        "source_name": "commit d4e5f6a - Add ledger reconciliation worker (feature-flagged)",
        "external_id": "d4e5f6a",
        "author": "Demo Author",
        "days_ago": 6,
        "freshness": FreshnessStatus.CURRENT,
        "source_url": "https://github.com/continuum-demo-synthetic/payment-gateway/commit/d4e5f6a",
        "content": COMMIT,
        "spans": (
            ("commit d4e5f6a", "The reconciliation job is disabled in production until the fee schedule is confirmed by finance."),
        ),
    },
    {
        "key": "handover_notes",
        "source_type": SourceType.UPLOADED_MARKDOWN,
        "source_name": "handover-notes.md",
        "external_id": "handover-notes.md",
        "author": "Demo Author",
        "days_ago": 3,
        "freshness": FreshnessStatus.CURRENT,
        "source_url": None,
        "content": HANDOVER_NOTES,
        "spans": (
            ("handover-notes.md#L4", "The authorisation service is owned by the departing lead payments engineer, who is responsible for its release approval."),
            ("handover-notes.md#L6", "The settlement worker was handed over from the departing engineer to the incoming payments platform engineer as part of this transition."),
            ("handover-notes.md#L9", "Network token storage was delivered and is live in production for card authorisation."),
            ("handover-notes.md#L12", "The successor must supply the environment variables GATEWAY_DB_URL, PROVIDER_API_BASE and LEDGER_SIGNING_KEY_ID; the values themselves are held in the platform secret store and are never documented."),
            ("handover-notes.md#L15", "Risk: if the reconciliation job is enabled before the fee schedule is confirmed, settlement totals will be wrong and the ledger will need manual correction."),
        ),
    },
)


# ---------------------------------------------------------------------------
# Synthetic claims
# ---------------------------------------------------------------------------
def _claim(
    text: str,
    claim_type: ClaimType,
    *,
    entity: str | None = None,
    status: ClaimStatus = ClaimStatus.VERIFIED,
    critical: bool = False,
    confidence: float = 0.9,
    reasoning_summary: str | None = None,
    evidence: tuple[tuple[str, str], ...] = (),
    verdict: str | None = None,
) -> dict[str, Any]:
    return {
        "text": text,
        "claim_type": claim_type,
        "entity": entity,
        "status": status,
        "critical": critical,
        "confidence": confidence,
        "reasoning_summary": reasoning_summary,
        "evidence": evidence,
        "verdict": verdict,
    }


#: The approved (human-reviewed) claims. Only these can enter the handover.
_APPROVED_CLAIMS: tuple[dict[str, Any], ...] = (
    _claim(
        "The Payment Gateway System is an in-house service that authorises card payments, captures funds and settles them to merchant accounts.",
        ClaimType.ARCHITECTURE,
        entity="payment_gateway_system",
        critical=True,
        confidence=0.96,
        reasoning_summary="Stated directly in the repository README.",
        evidence=(("readme", "The Payment Gateway System is an in-house service that authorises card payments, captures funds and settles them to merchant accounts."),),
        verdict="supports",
    ),
    _claim(
        "As of this sprint the gateway is live for card authorisation and capture. Refund handling is partially implemented and settlement is still being hardened.",
        ClaimType.STATUS,
        entity="payment_gateway_system",
        confidence=0.82,
        reasoning_summary="Current-status section of the README; partially forward-looking.",
        evidence=(("readme", "As of this sprint the gateway is live for card authorisation and capture. Refund handling is partially implemented and settlement is still being hardened."),),
        verdict="partly",
    ),
    _claim(
        "The gateway covers card authorisation, capture, refund and settlement. It excludes merchant onboarding and fraud scoring, which are owned by other teams.",
        ClaimType.TECHNICAL_CONSTRAINT,
        entity="payment_gateway_system",
        confidence=0.9,
        reasoning_summary="Scope section of the README.",
        evidence=(("readme", "The gateway covers card authorisation, capture, refund and settlement. It excludes merchant onboarding and fraud scoring, which are owned by other teams."),),
    ),
    _claim(
        "The gateway is built with Python 3.12 and FastAPI, stores data in PostgreSQL 16, and runs behind Nginx on a Docker-based deployment pipeline.",
        ClaimType.DEPENDENCY,
        entity="technology_stack",
        confidence=0.93,
        reasoning_summary="Technology section of the README.",
        evidence=(("readme", "The gateway is built with Python 3.12 and FastAPI, stores data in PostgreSQL 16, and runs behind Nginx on a Docker-based deployment pipeline."),),
    ),
    _claim(
        "The team decided to store only network tokens instead of raw card numbers because it removes the PCI-DSS storage scope from the gateway.",
        ClaimType.DECISION,
        entity="card_vault",
        critical=True,
        confidence=0.95,
        reasoning_summary="Architecture decision record ADR-0007 records the decision and its rationale.",
        evidence=(("adr_tokenisation", "The team decided to store only network tokens instead of raw card numbers because it removes the PCI-DSS storage scope from the gateway."),),
        verdict="supports",
    ),
    _claim(
        "Settlement reports were moved to an append-only ledger because reconciliation disputes previously could not be reconstructed.",
        ClaimType.DECISION,
        entity="settlement_ledger",
        confidence=0.9,
        reasoning_summary="Architecture decision record ADR-0009.",
        evidence=(("adr_ledger", "Settlement reports were moved to an append-only ledger because reconciliation disputes previously could not be reconstructed."),),
    ),
    _claim(
        "Webhook delivery retries use exponential backoff with jitter, capped at eight attempts, in order to avoid thundering-herd retries on the payment provider.",
        ClaimType.DECISION,
        entity="retry_policy",
        confidence=0.88,
        reasoning_summary="Recorded in pull request #482.",
        evidence=(("pull_request", "Webhook delivery retries use exponential backoff with jitter, capped at eight attempts, in order to avoid thundering-herd retries on the payment provider."),),
    ),
    _claim(
        "The architecture separates the public API edge, an authorisation service, a settlement worker and a webhook dispatcher, which communicate over an internal message queue.",
        ClaimType.ARCHITECTURE,
        entity="payment_gateway_system",
        confidence=0.94,
        reasoning_summary="Architecture section of the README.",
        evidence=(("readme", "The architecture separates the public API edge, an authorisation service, a settlement worker and a webhook dispatcher, which communicate over an internal message queue."),),
    ),
    _claim(
        "The gateway calls the external Payment Provider API for card authorisation and must tolerate an external service outage without corrupting the ledger.",
        ClaimType.DEPENDENCY,
        entity="payment_provider_api",
        confidence=0.92,
        reasoning_summary="Dependencies section of the README.",
        evidence=(("readme", "The gateway calls the external Payment Provider API for card authorisation and must tolerate an external service outage without corrupting the ledger."),),
    ),
    _claim(
        "The successor must supply the environment variables GATEWAY_DB_URL, PROVIDER_API_BASE and LEDGER_SIGNING_KEY_ID; the values themselves are held in the platform secret store and are never documented.",
        ClaimType.TECHNICAL_CONSTRAINT,
        entity="environment_config",
        confidence=0.9,
        reasoning_summary="Configuration section of the handover notes; no secret value is recorded.",
        evidence=(("handover_notes", "The successor must supply the environment variables GATEWAY_DB_URL, PROVIDER_API_BASE and LEDGER_SIGNING_KEY_ID; the values themselves are held in the platform secret store and are never documented."),),
    ),
    _claim(
        "The gateway integration with merchant systems uses signed webhooks over HTTPS and an OAuth client-credentials flow for partner APIs.",
        ClaimType.DEPENDENCY,
        entity="webhook_integration",
        confidence=0.87,
        reasoning_summary="Described in pull request #482.",
        evidence=(("pull_request", "The gateway integration with merchant systems uses signed webhooks over HTTPS and an OAuth client-credentials flow for partner APIs."),),
    ),
    _claim(
        "Deployment is a blue-green release performed by the CI pipeline: build the Docker image, run migrations, shift traffic to the green service and verify the health endpoint.",
        ClaimType.OPERATIONAL_PROCEDURE,
        entity="deployment",
        confidence=0.95,
        reasoning_summary="Deployment runbook.",
        evidence=(("runbook", "Deployment is a blue-green release performed by the CI pipeline: build the Docker image, run migrations, shift traffic to the green service and verify the health endpoint."),),
        verdict="supports",
    ),
    _claim(
        "To roll back a release, shift traffic back to the blue service and revert the migration with the down-migration script; never roll back a forward migration by hand.",
        ClaimType.OPERATIONAL_PROCEDURE,
        entity="deployment",
        confidence=0.93,
        reasoning_summary="Rollback section of the deployment runbook.",
        evidence=(("runbook", "To roll back a release, shift traffic back to the blue service and revert the migration with the down-migration script; never roll back a forward migration by hand."),),
    ),
    _claim(
        "The settlement report signing key is rotated every quarter by running the rotate-signing-key task and publishing the new key id to the configuration store.",
        ClaimType.OPERATIONAL_PROCEDURE,
        entity="signing_key",
        confidence=0.88,
        reasoning_summary="Routine maintenance section of the runbook.",
        evidence=(("runbook", "The settlement report signing key is rotated every quarter by running the rotate-signing-key task and publishing the new key id to the configuration store."),),
    ),
    _claim(
        "The authorisation service is owned by the departing lead payments engineer, who is responsible for its release approval.",
        ClaimType.OWNERSHIP,
        entity="authorisation_service",
        critical=True,
        confidence=0.9,
        reasoning_summary="Ownership section of the handover notes.",
        evidence=(("handover_notes", "The authorisation service is owned by the departing lead payments engineer, who is responsible for its release approval."),),
    ),
    _claim(
        "The settlement worker was handed over from the departing engineer to the incoming payments platform engineer as part of this transition.",
        ClaimType.OWNERSHIP,
        entity="settlement_worker",
        confidence=0.85,
        reasoning_summary="Ownership section of the handover notes records the transition.",
        evidence=(("handover_notes", "The settlement worker was handed over from the departing engineer to the incoming payments platform engineer as part of this transition."),),
    ),
    _claim(
        "Refund handling is still in progress: the refund service recognises partial refunds but does not yet reconcile them against the ledger.",
        ClaimType.TASK,
        entity="refund_service",
        confidence=0.86,
        reasoning_summary="Stated in pull request #482.",
        evidence=(("pull_request", "Refund handling is still in progress: the refund service recognises partial refunds but does not yet reconcile them against the ledger."),),
    ),
    _claim(
        "Settlement is blocked waiting on the finance team to confirm the fee schedule before the reconciliation job can be enabled.",
        ClaimType.UNFINISHED_WORK,
        entity="settlement_worker",
        confidence=0.88,
        reasoning_summary="Recorded on issue #511.",
        evidence=(("issue", "Settlement is blocked waiting on the finance team to confirm the fee schedule before the reconciliation job can be enabled."),),
    ),
    _claim(
        "Open question: should idempotency keys be scoped per merchant or globally per gateway?",
        ClaimType.OPEN_QUESTION,
        entity="idempotency",
        confidence=0.8,
        reasoning_summary="Raised on issue #511; the sources do not answer it.",
        evidence=(("issue", "Open question: should idempotency keys be scoped per merchant or globally per gateway?"),),
    ),
    _claim(
        "Risk: if the reconciliation job is enabled before the fee schedule is confirmed, settlement totals will be wrong and the ledger will need manual correction.",
        ClaimType.RISK,
        entity="settlement_worker",
        critical=True,
        confidence=0.9,
        reasoning_summary="Risk section of the handover notes.",
        evidence=(("handover_notes", "Risk: if the reconciliation job is enabled before the fee schedule is confirmed, settlement totals will be wrong and the ledger will need manual correction."),),
        verdict="supports",
    ),
    _claim(
        "Network token storage was delivered and is live in production for card authorisation.",
        ClaimType.TASK,
        entity="card_vault",
        confidence=0.85,
        reasoning_summary="Progress section of the handover notes.",
        evidence=(("handover_notes", "Network token storage was delivered and is live in production for card authorisation."),),
    ),
    _claim(
        "The reconciliation job is disabled in production until the fee schedule is confirmed by finance.",
        ClaimType.OPERATIONAL_PROCEDURE,
        entity="settlement_worker",
        confidence=0.84,
        reasoning_summary="Feature flag recorded in commit d4e5f6a.",
        evidence=(("commit", "The reconciliation job is disabled in production until the fee schedule is confirmed by finance."),),
    ),
)

#: Claims still awaiting a human decision (the review queue).
_PENDING_CLAIMS: tuple[dict[str, Any], ...] = (
    _claim(
        "The previous release manager's contact list in the wiki is out of date and should be refreshed.",
        ClaimType.CONTACT,
        entity="release_management",
        status=ClaimStatus.EXTRACTED,
        confidence=0.55,
        reasoning_summary="Mentioned as a to-do; no supporting document was found.",
    ),
    _claim(
        "The staging environment is two migrations behind production.",
        ClaimType.STATUS,
        entity="staging_environment",
        status=ClaimStatus.PENDING_REVIEW,
        confidence=0.6,
        reasoning_summary="Reported informally; needs evidence before approval.",
    ),
    _claim(
        "A mobile SDK integration is referenced in a code comment but has no dedicated documentation.",
        ClaimType.OTHER,
        entity="mobile_sdk",
        status=ClaimStatus.EXTRACTED,
        confidence=0.4,
        reasoning_summary="Only a code comment was found; too weak to approve.",
    ),
    _claim(
        "A proposal to move settlement reconciliation to a nightly batch window is under discussion.",
        ClaimType.DECISION,
        entity="settlement_worker",
        status=ClaimStatus.PENDING_REVIEW,
        confidence=0.5,
        reasoning_summary="Proposal only; the decision has not been made.",
    ),
)

#: Two claims that contradict one another about the database version.
_CONFLICTING_CLAIMS: tuple[dict[str, Any], ...] = (
    _claim(
        "The production gateway database runs PostgreSQL 14.",
        ClaimType.TECHNICAL_CONSTRAINT,
        entity="database",
        status=ClaimStatus.CONFLICT,
        confidence=0.5,
        reasoning_summary="Asserted by an older operations note; no source was retained.",
    ),
    _claim(
        "The production gateway database runs PostgreSQL 16.",
        ClaimType.TECHNICAL_CONSTRAINT,
        entity="database",
        status=ClaimStatus.CONFLICT,
        confidence=0.8,
        reasoning_summary="Matches the README technology section.",
        evidence=(("readme", "The gateway is built with Python 3.12 and FastAPI, stores data in PostgreSQL 16, and runs behind Nginx on a Docker-based deployment pipeline."),),
    ),
)

#: ``(key, claim text, section key)`` — which approved claim backs each section.
_HANDOVER_SECTIONS: tuple[tuple[str, tuple[int, ...]], ...] = (
    ("overview", (0, 1)),
    ("objectives", ()),
    ("current_state", (1, 2)),
    ("decisions", (4, 5, 6)),
    ("responsibilities", (14, 15)),
    ("architecture", (7, 3, 8, 10)),
    ("completed_work", (20,)),
    ("unfinished_work", (16, 17)),
    ("risks", (19,)),
    ("procedures", (11, 12, 13, 21)),
    ("outstanding_issues", (17, 19)),
    ("open_questions", (18,)),
    ("next_actions", (17, 18)),
    ("critical_context", (14, 19)),
)


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------
def get_demo_user(db: Session) -> User | None:
    """The single synthetic principal that owns the demo workspace."""
    return db.execute(select(User).where(User.email == DEMO_EMAIL)).scalar_one_or_none()


def get_demo_workspace(db: Session) -> Workspace | None:
    user = get_demo_user(db)
    if user is None:
        return None
    return db.execute(
        select(Workspace).where(
            Workspace.name == demo_workspace_name(), Workspace.owner_id == user.id
        )
    ).scalar_one_or_none()


def get_demo_project(db: Session) -> Project | None:
    workspace = get_demo_workspace(db)
    if workspace is None:
        return None
    return db.execute(
        select(Project).where(
            Project.workspace_id == workspace.id, Project.name == demo_project_name()
        )
    ).scalar_one_or_none()


def _ensure_demo_user(db: Session) -> User:
    user = get_demo_user(db)
    if user is None:
        user = User(email=DEMO_EMAIL, full_name="Public Demo", supabase_user_id=None)
        db.add(user)
        db.flush()
    return user


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
def ensure_demo_data(db: Session) -> DemoSeedResult:
    """Create the synthetic demo workspace if it does not exist yet."""
    existing = get_demo_workspace(db)
    if existing is not None:
        project = get_demo_project(db)
        if project is not None and _count(db, Claim, project.id) > 0:
            return _result(db, existing, project, created=False)

    with _seed_lock:
        existing = get_demo_workspace(db)
        if existing is not None:
            project = get_demo_project(db)
            if project is not None and _count(db, Claim, project.id) > 0:
                return _result(db, existing, project, created=False)
        return _build(db)


def reset_demo_data(db: Session) -> DemoSeedResult:
    """Throw the synthetic workspace away and rebuild it from scratch."""
    with _seed_lock:
        workspace = get_demo_workspace(db)
        project = get_demo_project(db)
        if workspace is not None and project is not None:
            _purge(db, project_id=project.id, workspace_id=workspace.id)
        elif workspace is not None:
            db.execute(delete(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace.id))
            db.execute(delete(Workspace).where(Workspace.id == workspace.id))
            db.flush()
        return _build(db)


def _count(db: Session, model: Any, project_id: uuid.UUID) -> int:
    from sqlalchemy import func

    return int(
        db.execute(
            select(func.count()).select_from(model).where(model.project_id == project_id)
        ).scalar_one()
    )


def _result(db: Session, workspace: Workspace, project: Project, *, created: bool) -> DemoSeedResult:
    from sqlalchemy import func

    def total(model: Any) -> int:
        return int(
            db.execute(
                select(func.count()).select_from(model).where(model.project_id == project.id)
            ).scalar_one()
        )

    return DemoSeedResult(
        workspace_id=workspace.id,
        project_id=project.id,
        user_id=workspace.owner_id,
        workspace_name=workspace.name,
        project_name=project.name,
        created=created,
        counts={
            "sources": total(Source),
            "claims": total(Claim),
            "conflicts": total(Conflict),
            "successor_tasks": total(SuccessorTask),
            "knowledge_gaps": total(KnowledgeGap),
        },
    )


def _build(db: Session) -> DemoSeedResult:
    """Build the whole synthetic workspace in one transaction."""
    user = _ensure_demo_user(db)

    workspace = Workspace(name=demo_workspace_name(), owner_id=user.id)
    db.add(workspace)
    db.flush()

    db.add(
        WorkspaceMember(
            workspace_id=workspace.id, user_id=user.id, role=WorkspaceRole.OWNER
        )
    )
    project = Project(
        workspace_id=workspace.id,
        name=demo_project_name(),
        description=(
            "Synthetic demonstration project: an in-house card payment gateway being "
            "handed from the departing lead payments engineer to a successor. All "
            "content is fabricated demonstration data."
        ),
        status=ProjectStatus.HANDOVER_IN_PROGRESS,
        departing_role="Lead Payments Engineer",
        successor_role="Payments Platform Engineer",
    )
    db.add(project)
    db.flush()

    run = ProcessingRun(
        project_id=project.id,
        requested_by_id=user.id,
        status=ProcessingRunStatus.COMPLETED,
        model_name="demo-synthetic-seed",
        started_at=_days_ago(3),
        finished_at=_days_ago(3),
    )
    db.add(run)
    db.flush()

    sources, spans = _seed_sources(db, project.id)
    claims = _seed_claims(db, project.id, user.id, run.id, sources, spans)
    conflicting = _seed_conflicting_claims(db, project.id, sources, spans)
    _seed_conflict(db, project.id, run.id, conflicting)
    _seed_open_questions(db, project.id, run.id, claims)
    _seed_project_memory(db, project_id=project.id, run_id=run.id)
    _seed_handover(db, project, user, run.id, claims)
    evaluation = ReadinessService(db).evaluate(
        project.id,
        user_id=user.id,
        workspace_id=workspace.id,
        run_id=run.id,
        source="demo_seed",
    )
    dependencies = KnowledgeRiskService(db).analyse_dependencies(
        project.id, user_id=user.id, workspace_id=workspace.id
    )
    gaps = KnowledgeRiskService(db).detect_gaps(
        project.id,
        requirements=evaluation.requirements or [],
        dependencies=dependencies,
        user_id=user.id,
        workspace_id=workspace.id,
    )
    SuccessorService(db).derive(
        project.id,
        user_id=user.id,
        workspace_id=workspace.id,
        gaps=[
            {
                "gap_key": gap.gap_key,
                "description": gap.description,
                "criticality": gap.criticality.value,
            }
            for gap in gaps
        ],
    )
    ContinuityService(db).run_successor_exercise(
        project.id, user_id=user.id, workspace_id=workspace.id
    )

    run.source_count = len(sources)
    run.claim_count = len(claims) + len(conflicting)
    run.verified_count = len(claims)
    run.uncertain_count = len(conflicting)
    run.conflict_count = 1
    run.open_question_count = 2
    run.stats = {
        "synthetic": True,
        "public_demo": True,
        "note": "Seeded by the Continuum public demo environment.",
    }

    db.flush()
    logger.info(
        "Seeded public demo workspace %s (project %s)", workspace.id, project.id
    )
    return _result(db, workspace, project, created=True)


def _seed_sources(
    db: Session, project_id: uuid.UUID
) -> tuple[dict[str, Source], dict[str, list[EvidenceSpan]]]:
    sources: dict[str, Source] = {}
    spans: dict[str, list[EvidenceSpan]] = {}
    for spec in _SOURCES:
        content: str = spec["content"]
        source = Source(
            project_id=project_id,
            source_type=spec["source_type"],
            source_name=spec["source_name"],
            external_id=spec.get("external_id"),
            content=content,
            meta={"synthetic": True, "public_demo": True},
            author=spec["author"],
            created_at_source=_days_ago(spec["days_ago"]),
            access_label=AccessLabel.WORKSPACE,
            processing_status=ProcessingStatus.COMPLETED,
            content_hash=_hash(f"{spec['source_type'].value}:{content}"),
            freshness=spec.get("freshness", FreshnessStatus.CURRENT),
            freshness_checked_at=_now(),
            mime_type="text/markdown",
            size_bytes=len(content.encode("utf-8")),
            source_url=spec.get("source_url"),
        )
        db.add(source)
        db.flush()
        built: list[EvidenceSpan] = []
        for index, (location, quote) in enumerate(spec["spans"]):
            start = content.index(quote)
            span = EvidenceSpan(
                source_id=source.id,
                span_index=index,
                location=location,
                start_offset=start,
                end_offset=start + len(quote),
                text=quote,
                meta={"synthetic": True},
            )
            db.add(span)
            built.append(span)
        db.flush()
        sources[spec["key"]] = source
        spans[spec["key"]] = built
    return sources, spans


def _seed_claims(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    run_id: uuid.UUID,
    sources: dict[str, Source],
    spans: dict[str, list[EvidenceSpan]],
) -> list[Claim]:
    """Seed approved and pending-review claims, with evidence and verifications."""
    created: list[Claim] = []
    for spec in (*_APPROVED_CLAIMS, *_PENDING_CLAIMS):
        claim = _make_claim(db, project_id, run_id, spec)
        if spec["status"] == ClaimStatus.VERIFIED:
            claim.reviewed_at = _days_ago(2)
            claim.verified_at = _days_ago(2)
            claim.verified_by_id = user_id
            claim.review_note = "Reviewed and approved in the synthetic demonstration dataset."
        db.add(claim)
        db.flush()
        _attach_evidence(db, claim, spec["evidence"], sources, spans)
        if spec["verdict"]:
            quote = spec["evidence"][0][1] if spec["evidence"] else None
            db.add(
                Verification(
                    claim_id=claim.id,
                    run_id=run_id,
                    verdict=VerificationVerdict(spec["verdict"]),
                    supporting_quote=quote,
                    quote_validated=bool(quote),
                    contradicted_by=[],
                    explanation=(
                        "Deterministic demonstration verdict over the cited evidence span."
                    ),
                    confidence=spec["confidence"],
                    model_name="demo-synthetic-seed",
                )
            )
        created.append(claim)
    db.flush()
    return created


def _seed_conflicting_claims(
    db: Session,
    project_id: uuid.UUID,
    sources: dict[str, Source],
    spans: dict[str, list[EvidenceSpan]],
) -> list[Claim]:
    created: list[Claim] = []
    for spec in _CONFLICTING_CLAIMS:
        claim = _make_claim(db, project_id, None, spec)
        db.add(claim)
        db.flush()
        _attach_evidence(db, claim, spec["evidence"], sources, spans)
        created.append(claim)
    db.flush()
    return created


def _make_claim(
    db: Session, project_id: uuid.UUID, run_id: uuid.UUID | None, spec: dict[str, Any]
) -> Claim:
    return Claim(
        project_id=project_id,
        run_id=run_id,
        text=spec["text"],
        claim_type=spec["claim_type"],
        entity=spec.get("entity"),
        status=spec["status"],
        critical=bool(spec.get("critical", False)),
        author="Demo Author",
        confidence=spec.get("confidence"),
        reasoning_summary=spec.get("reasoning_summary"),
        access_label=AccessLabel.WORKSPACE,
        dedup_key=_hash(spec["text"])[:64],
        revision_number=1,
    )


def _attach_evidence(
    db: Session,
    claim: Claim,
    refs: Iterable[tuple[str, str]],
    sources: dict[str, Source],
    spans: dict[str, list[EvidenceSpan]],
) -> None:
    for source_key, quote in refs:
        source = sources[source_key]
        span = next((item for item in spans[source_key] if item.text == quote), None)
        if span is None:
            continue
        db.add(
            Evidence(
                claim_id=claim.id,
                source_id=source.id,
                span_id=span.id,
                source_location=span.location,
                start_offset=span.start_offset,
                end_offset=span.end_offset,
                supporting_quote=quote,
            )
        )


def _seed_conflict(
    db: Session,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    claims: list[Claim],
) -> Conflict:
    conflict = Conflict(
        project_id=project_id,
        run_id=run_id,
        entity="database",
        claim_type=ClaimType.TECHNICAL_CONSTRAINT,
        property_key="postgres_version",
        kind="value_disagreement",
        status=ConflictStatus.OPEN,
        summary=(
            "Two sources disagree about the PostgreSQL major version in use: one "
            "operations note says 14, the repository README says 16."
        ),
    )
    db.add(conflict)
    db.flush()
    for claim in claims:
        db.add(
            ConflictClaim(conflict_id=conflict.id, claim_id=claim.id, relation="contradicts")
        )
    db.flush()
    return conflict


def _seed_open_questions(
    db: Session,
    project_id: uuid.UUID,
    run_id: uuid.UUID,
    claims: list[Claim],
) -> None:
    origin = next(
        (claim for claim in claims if claim.claim_type == ClaimType.OPEN_QUESTION), None
    )
    db.add(
        OpenQuestion(
            project_id=project_id,
            run_id=run_id,
            claim_id=origin.id if origin is not None else None,
            question="Should idempotency keys be scoped per merchant or globally per gateway?",
            context="Raised on issue #511 and never answered by the sources.",
            entity="idempotency",
            dedup_key=_hash("should-idempotency-keys-be-scoped-per-merchant")[:64],
            status=OpenQuestionStatus.OPEN,
            access_label=AccessLabel.WORKSPACE,
        )
    )
    db.add(
        OpenQuestion(
            project_id=project_id,
            run_id=run_id,
            claim_id=None,
            question="When will finance confirm the settlement fee schedule?",
            context="Blocks enabling the ledger reconciliation job.",
            entity="settlement_worker",
            dedup_key=_hash("when-will-finance-confirm-the-fee-schedule")[:64],
            status=OpenQuestionStatus.OPEN,
            access_label=AccessLabel.WORKSPACE,
        )
    )
    db.flush()


def _seed_project_memory(
    db: Session, *, project_id: uuid.UUID, run_id: uuid.UUID
) -> ProjectMemory:
    """Persist the reconstructed-memory aggregate so the memory page is populated.

    Mirrors the shape the reconstruction workflow writes, but every figure is
    counted back out of the synthetic records seeded above.
    """
    claims = list(db.execute(select(Claim).where(Claim.project_id == project_id)).scalars())
    sources = list(db.execute(select(Source).where(Source.project_id == project_id)).scalars())
    span_count = int(
        db.scalar(
            select(func.count())
            .select_from(EvidenceSpan)
            .join(Source, Source.id == EvidenceSpan.source_id)
            .where(Source.project_id == project_id)
        )
        or 0
    )
    run = db.get(ProcessingRun, run_id)

    type_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for claim in claims:
        type_counts[claim.claim_type.value] = type_counts.get(claim.claim_type.value, 0) + 1
        status_counts[claim.status.value] = status_counts.get(claim.status.value, 0) + 1

    conflict_count = int(
        db.scalar(
            select(func.count())
            .select_from(Conflict)
            .where(Conflict.project_id == project_id, Conflict.kind == "value_disagreement")
        )
        or 0
    )
    ownership_changes = int(
        db.scalar(
            select(func.count())
            .select_from(Conflict)
            .where(Conflict.project_id == project_id, Conflict.kind == "changed_over_time")
        )
        or 0
    )
    stale_count = sum(1 for source in sources if source.freshness is not FreshnessStatus.CURRENT)

    stats: dict[str, Any] = {
        "claim_count": len(claims),
        "source_count": len(sources),
        "span_count": span_count,
        "by_type": type_counts,
        "by_status": status_counts,
        "conflict_count": conflict_count,
        "ownership_changes": ownership_changes,
        "stale_count": stale_count,
        "open_question_count": sum(
            1 for claim in claims if claim.claim_type is ClaimType.OPEN_QUESTION
        ),
        "rejected_count": sum(1 for claim in claims if claim.status is ClaimStatus.REJECTED),
        "model": run.model_name if run is not None else "demo-synthetic-seed",
        "synthetic": True,
        "public_demo": True,
    }
    memory = ProjectMemory(
        project_id=project_id,
        last_run_id=run_id,
        version=1,
        generated_at=_now(),
        stats=stats,
        summary=(
            f"Reconstructed {len(claims)} claims from {len(sources)} sources: "
            f"{status_counts.get(ClaimStatus.SUPPORTED.value, 0)} supported, "
            f"{status_counts.get(ClaimStatus.UNCERTAIN.value, 0)} uncertain, "
            f"{status_counts.get(ClaimStatus.CONFLICT.value, 0)} in conflict. "
            f"{conflict_count} open conflict(s), "
            f"{stale_count} source(s) flagged for freshness review."
        ),
    )
    db.add(memory)
    db.flush()
    return memory


def _seed_handover(
    db: Session,
    project: Project,
    user: User,
    run_id: uuid.UUID,
    approved: list[Claim],
) -> None:
    """Build a document from approved claims, then approve and publish it."""
    by_index = {index: claim for index, claim in enumerate(approved)}
    sections: list[dict[str, Any]] = []
    used: list[uuid.UUID] = []
    for key, indices in _HANDOVER_SECTIONS:
        statements: list[dict[str, Any]] = []
        for index in indices:
            claim = by_index[index]
            if claim.id not in used:
                used.append(claim.id)
            statements.append(
                {
                    "statement_id": uuid.uuid4().hex,
                    "text": claim.text,
                    "claim_ids": [str(claim.id)],
                    "claim_revisions": {str(claim.id): claim.revision_number},
                }
            )
        sections.append({"key": key, "statements": statements})

    document = HandoverDocument(
        project_id=project.id,
        run_id=run_id,
        generated_by_id=user.id,
        status=HandoverStatus.VALIDATED,
        sections=sections,
        claim_ids=[str(item) for item in used],
        validation_errors=[],
        summary="Synthetic demonstration handover for the Payment Gateway System.",
        model_name="demo-synthetic-seed",
        meta={"synthetic": True, "public_demo": True},
    )
    db.add(document)
    db.flush()

    service = HandoverService(db)
    handover = service.ensure_handover(
        project, user=user, title=f"{project.name} - Project Handover"
    )
    service.create_version_from_document(handover, user=user, document=document)
    service.submit_for_review(handover, user=user)
    service.approve(
        handover,
        user=user,
        role=WorkspaceRole.OWNER,
        note="Approved as part of the synthetic demonstration dataset.",
    )
    service.publish(
        handover,
        user=user,
        role=WorkspaceRole.OWNER,
        note="Published for the public demo workspace.",
    )


# ---------------------------------------------------------------------------
# Purge (reset)
# ---------------------------------------------------------------------------
def _purge(db: Session, *, project_id: uuid.UUID, workspace_id: uuid.UUID) -> None:
    claim_ids = [
        row for (row,) in db.execute(select(Claim.id).where(Claim.project_id == project_id))
    ]
    source_ids = [
        row for (row,) in db.execute(select(Source.id).where(Source.project_id == project_id))
    ]
    conflict_ids = [
        row for (row,) in db.execute(select(Conflict.id).where(Conflict.project_id == project_id))
    ]
    handover_ids = [
        row for (row,) in db.execute(select(Handover.id).where(Handover.project_id == project_id))
    ]
    run_ids = [
        row
        for (row,) in db.execute(
            select(ProcessingRun.id).where(ProcessingRun.project_id == project_id)
        )
    ]

    if conflict_ids:
        db.execute(delete(ConflictClaim).where(ConflictClaim.conflict_id.in_(conflict_ids)))
    if claim_ids:
        db.execute(delete(Verification).where(Verification.claim_id.in_(claim_ids)))
        db.execute(delete(Evidence).where(Evidence.claim_id.in_(claim_ids)))
        db.execute(delete(ConflictClaim).where(ConflictClaim.claim_id.in_(claim_ids)))
        db.execute(delete(SuccessorTask).where(SuccessorTask.origin_claim_id.in_(claim_ids)))
    if source_ids:
        db.execute(delete(Evidence).where(Evidence.source_id.in_(source_ids)))
        db.execute(delete(EvidenceSpan).where(EvidenceSpan.source_id.in_(source_ids)))
    if handover_ids:
        db.execute(
            delete(HandoverVersion).where(HandoverVersion.handover_id.in_(handover_ids))
        )
    if run_ids:
        db.execute(delete(EvaluationRun).where(EvaluationRun.project_id == project_id))

    db.execute(delete(OpenQuestion).where(OpenQuestion.project_id == project_id))
    db.execute(delete(Conflict).where(Conflict.project_id == project_id))
    db.execute(delete(HandoverDocument).where(HandoverDocument.project_id == project_id))
    db.execute(delete(Handover).where(Handover.project_id == project_id))
    db.execute(delete(Claim).where(Claim.project_id == project_id))
    db.execute(delete(SuccessorTask).where(SuccessorTask.project_id == project_id))
    db.execute(delete(KnowledgeGap).where(KnowledgeGap.project_id == project_id))
    db.execute(
        delete(KnowledgeDependency).where(KnowledgeDependency.project_id == project_id)
    )
    db.execute(
        delete(ReadinessEvaluation).where(ReadinessEvaluation.project_id == project_id)
    )
    db.execute(delete(EvaluationRun).where(EvaluationRun.project_id == project_id))
    db.execute(delete(ProjectMemory).where(ProjectMemory.project_id == project_id))
    db.execute(delete(Source).where(Source.project_id == project_id))
    db.execute(delete(ProcessingRun).where(ProcessingRun.project_id == project_id))
    db.execute(delete(AuditLog).where(AuditLog.workspace_id == workspace_id))
    db.execute(delete(Project).where(Project.id == project_id))
    db.execute(delete(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id))
    db.execute(delete(Workspace).where(Workspace.id == workspace_id))
    db.flush()


__all__ = [
    "DEMO_BANNER_LABEL",
    "DEMO_DATA_DISCLAIMER",
    "DemoSeedResult",
    "demo_project_name",
    "demo_workspace_name",
    "ensure_demo_data",
    "get_demo_project",
    "get_demo_user",
    "get_demo_workspace",
    "reset_demo_data",
]
