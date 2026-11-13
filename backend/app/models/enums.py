"""Domain enumerations shared by models, schemas and services."""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    """String enum whose ``str()`` is the value (Python 3.11+ compatible)."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return str(self.value)


class WorkspaceRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    HANDOVER_IN_PROGRESS = "handover_in_progress"
    HANDED_OVER = "handed_over"
    ARCHIVED = "archived"


class SourceType(StrEnum):
    GITHUB_COMMIT = "github_commit"
    GITHUB_ISSUE = "github_issue"
    GITHUB_PULL_REQUEST = "github_pull_request"
    GITHUB_README = "github_readme"
    GITHUB_FILE = "github_file"
    UPLOADED_PDF = "uploaded_pdf"
    UPLOADED_MARKDOWN = "uploaded_markdown"
    UPLOADED_TEXT = "uploaded_text"
    UPLOADED_ZIP_ENTRY = "uploaded_zip_entry"


class ProcessingStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    DUPLICATE = "duplicate"


class AccessLabel(StrEnum):
    WORKSPACE = "workspace"
    PRIVATE = "private"
    PUBLIC = "public"
    RESTRICTED = "restricted"


class ClaimType(StrEnum):
    """Knowledge categories the Extractor may emit.

    The ten Phase 3 categories are listed first; the remaining members are the
    Phase 1/2 contract values retained for backward compatibility.
    """

    DECISION = "decision"
    RESPONSIBILITY = "responsibility"
    OWNERSHIP = "ownership"
    TASK = "task"
    UNFINISHED_WORK = "unfinished_work"
    RISK = "risk"
    DEPENDENCY = "dependency"
    TECHNICAL_CONSTRAINT = "technical_constraint"
    OPERATIONAL_PROCEDURE = "operational_procedure"
    OPEN_QUESTION = "open_question"
    # --- retained Phase 1/2 contract values ---
    ARCHITECTURE = "architecture"
    PROCESS = "process"
    CONSTRAINT = "constraint"
    CONTACT = "contact"
    STATUS = "status"
    OTHER = "other"


#: The ten categories the Phase 3 Extractor is instructed to produce.
EXTRACTABLE_CLAIM_TYPES: tuple[ClaimType, ...] = (
    ClaimType.DECISION,
    ClaimType.RESPONSIBILITY,
    ClaimType.OWNERSHIP,
    ClaimType.TASK,
    ClaimType.UNFINISHED_WORK,
    ClaimType.RISK,
    ClaimType.DEPENDENCY,
    ClaimType.TECHNICAL_CONSTRAINT,
    ClaimType.OPERATIONAL_PROCEDURE,
    ClaimType.OPEN_QUESTION,
)


class ClaimStatus(StrEnum):
    """Review lifecycle of a claim.

    Phase 4 adds the explicit review states the master prompt asks for. The
    human-approved state is still spelled :attr:`VERIFIED` (it is what every
    Phase 3 query and the handover validator already key on); the product
    vocabulary for it is "Approved", exposed as ``review_status`` in the API.

    Only a human reviewer may move a claim to :attr:`VERIFIED`.
    """

    #: Produced by the Extractor before any verification has run.
    EXTRACTED = "Extracted"
    SUPPORTED = "Supported"
    UNCERTAIN = "Uncertain"
    CONFLICT = "Conflict"
    #: Explicitly queued for a human decision.
    PENDING_REVIEW = "Pending Review"
    #: A reviewer asked for more information before deciding.
    NEEDS_CLARIFICATION = "Needs Clarification"
    REJECTED = "Rejected"
    #: The only state that may enter an approved handover. = "Approved".
    VERIFIED = "Verified"


#: The human-approved claim state (product vocabulary: "Approved").
APPROVED_CLAIM_STATE: ClaimStatus = ClaimStatus.VERIFIED

#: Statuses that still await a human decision.
AWAITING_REVIEW_STATUSES: tuple[ClaimStatus, ...] = (
    ClaimStatus.EXTRACTED,
    ClaimStatus.SUPPORTED,
    ClaimStatus.UNCERTAIN,
    ClaimStatus.CONFLICT,
    ClaimStatus.PENDING_REVIEW,
    ClaimStatus.NEEDS_CLARIFICATION,
)


class HandoverLifecycleStatus(StrEnum):
    """Lifecycle of a versioned handover (Phase 4 §12)."""

    DRAFT = "Draft"
    IN_REVIEW = "In Review"
    APPROVED = "Approved"
    PUBLISHED = "Published"
    ARCHIVED = "Archived"


class StatementType(StrEnum):
    """Provenance class of a single handover statement (Phase 4 §10)."""

    ESTABLISHED_FACT = "established_fact"
    UNRESOLVED_QUESTION = "unresolved_question"
    REVIEWER_NOTE = "reviewer_note"
    SUGGESTED_ACTION = "suggested_action"


#: Statement types that must cite at least one approved claim.
EVIDENCE_BACKED_STATEMENT_TYPES: tuple[StatementType, ...] = (
    StatementType.ESTABLISHED_FACT,
)


class ConflictResolution(StrEnum):
    """How a reviewer decided a detected contradiction (Phase 4 §6)."""

    ACCEPT_A = "claim_a_accepted"
    ACCEPT_B = "claim_b_accepted"
    BOTH_VALID_OVER_TIME = "both_valid_in_different_time_periods"
    BOTH_REJECTED = "both_rejected"
    MORE_INFO_REQUIRED = "more_information_required"
    DISMISSED = "dismissed"


#: Resolutions that leave the conflict open (awaiting further input).
OPEN_CONFLICT_RESOLUTIONS: tuple[ConflictResolution, ...] = (
    ConflictResolution.MORE_INFO_REQUIRED,
)


class ReviewDecision(StrEnum):
    """A reviewer's recorded decision on a claim revision (Phase 4 §7)."""

    APPROVE = "approve"
    REJECT = "reject"
    CLARIFICATION = "clarification"
    REQUEST_EVIDENCE = "request_evidence"


class VerificationVerdict(StrEnum):
    SUPPORTS = "supports"
    PARTLY = "partly"
    NONE = "none"


class ConflictStatus(StrEnum):
    """Lifecycle of a detected contradiction between two claims."""

    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class FreshnessStatus(StrEnum):
    """Deterministic staleness assessment for a source."""

    CURRENT = "current"
    POTENTIALLY_STALE = "potentially_stale"
    CONTRADICTED_BY_NEWER_EVIDENCE = "contradicted_by_newer_evidence"


class OpenQuestionStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class ProcessingRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class HandoverStatus(StrEnum):
    GENERATED = "generated"
    VALIDATED = "validated"
    FAILED = "failed"


class GitHubSubjectType(StrEnum):
    USER = "user"
    ISSUE = "issue"
    PULL_REQUEST = "pull_request"


# ---------------------------------------------------------------------------
# Repository Intelligence (public Git provider ingestion)
# ---------------------------------------------------------------------------
class RepositoryVisibility(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"


class RepositoryIngestionStatus(StrEnum):
    """Persisted lifecycle of one repository snapshot ingestion.

    The status *is* the current stage, so progress reported to the frontend is
    always the real backend state rather than an invented percentage.
    """

    QUEUED = "queued"
    VALIDATING = "validating"
    FETCHING_METADATA = "fetching_metadata"
    FETCHING_BRANCHES = "fetching_branches"
    FETCHING_TREE = "fetching_tree"
    FETCHING_FILES = "fetching_files"
    FETCHING_COMMITS = "fetching_commits"
    FETCHING_ISSUES = "fetching_issues"
    FETCHING_PULL_REQUESTS = "fetching_pull_requests"
    SAVING_SNAPSHOT = "saving_snapshot"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


#: Statuses in which an ingestion job is still running (or waiting to run).
ACTIVE_REPOSITORY_INGESTION_STATUSES: tuple[RepositoryIngestionStatus, ...] = (
    RepositoryIngestionStatus.QUEUED,
    RepositoryIngestionStatus.VALIDATING,
    RepositoryIngestionStatus.FETCHING_METADATA,
    RepositoryIngestionStatus.FETCHING_BRANCHES,
    RepositoryIngestionStatus.FETCHING_TREE,
    RepositoryIngestionStatus.FETCHING_FILES,
    RepositoryIngestionStatus.FETCHING_COMMITS,
    RepositoryIngestionStatus.FETCHING_ISSUES,
    RepositoryIngestionStatus.FETCHING_PULL_REQUESTS,
    RepositoryIngestionStatus.SAVING_SNAPSHOT,
)

#: Statuses after which no further stage will run.
TERMINAL_REPOSITORY_INGESTION_STATUSES: tuple[RepositoryIngestionStatus, ...] = (
    RepositoryIngestionStatus.COMPLETED,
    RepositoryIngestionStatus.PARTIALLY_COMPLETED,
    RepositoryIngestionStatus.FAILED,
    RepositoryIngestionStatus.CANCELLED,
)


GITHUB_SOURCE_TYPES: tuple[SourceType, ...] = (
    SourceType.GITHUB_COMMIT,
    SourceType.GITHUB_ISSUE,
    SourceType.GITHUB_PULL_REQUEST,
    SourceType.GITHUB_README,
    SourceType.GITHUB_FILE,
)

UPLOAD_SOURCE_TYPES: tuple[SourceType, ...] = (
    SourceType.UPLOADED_PDF,
    SourceType.UPLOADED_MARKDOWN,
    SourceType.UPLOADED_TEXT,
    SourceType.UPLOADED_ZIP_ENTRY,
)


# ---------------------------------------------------------------------------
# Phase 5 — readiness, successor experience, knowledge risk and evaluation
# ---------------------------------------------------------------------------
class ReadinessDimension(StrEnum):
    """The six weighted dimensions of the Handover Readiness Engine (§2)."""

    PROJECT_CONTEXT = "project_context"
    IMPORTANT_DECISIONS = "important_decisions"
    TECHNICAL_DEPENDENCIES = "technical_dependencies"
    OWNERSHIP_CLARITY = "ownership_clarity"
    UNFINISHED_WORK = "unfinished_work"
    RISKS_OPERATIONS = "risks_and_operations"


class RequirementCriticality(StrEnum):
    """How much a single readiness requirement matters to the score."""

    CRITICAL = "critical"
    IMPORTANT = "important"
    OPTIONAL = "optional"


class RequirementCompletion(StrEnum):
    """Deterministic completion assessment for one readiness requirement."""

    COMPLETE = "Complete"
    PARTIAL = "Partial"
    MISSING = "Missing"
    UNCERTAIN = "Uncertain"
    BLOCKED = "Blocked"


#: Completion values used by the deterministic scoring formula (§3).
#: ``Blocked`` and ``Missing`` earn no credit; ``Uncertain`` earns partial credit
#: so an evidence-backed-but-unreviewed requirement is never silently discarded.
COMPLETION_VALUES: dict["RequirementCompletion", float] = {
    RequirementCompletion.COMPLETE: 1.0,
    RequirementCompletion.PARTIAL: 0.5,
    RequirementCompletion.UNCERTAIN: 0.25,
    RequirementCompletion.MISSING: 0.0,
    RequirementCompletion.BLOCKED: 0.0,
}

#: Requirement weights used when combining requirements inside a dimension.
CRITICALITY_WEIGHTS: dict["RequirementCriticality", float] = {
    RequirementCriticality.CRITICAL: 3.0,
    RequirementCriticality.IMPORTANT: 2.0,
    RequirementCriticality.OPTIONAL: 1.0,
}


class ReadinessBand(StrEnum):
    """Product presentation band for the overall readiness score (§3)."""

    STRONG = "strong"
    MOSTLY_READY = "mostly_ready"
    NEEDS_REVIEW = "needs_review"
    NOT_READY = "not_ready"


class SuccessorTaskPriority(StrEnum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class SuccessorTaskStatus(StrEnum):
    NOT_STARTED = "Not Started"
    IN_PROGRESS = "In Progress"
    BLOCKED = "Blocked"
    COMPLETED = "Completed"


class DependencyRiskStatus(StrEnum):
    """Risk that critical knowledge rests with a single person (§6)."""

    LOW = "Low"
    MODERATE = "Moderate"
    HIGH = "High"
    UNKNOWN = "Unknown"


class KnowledgeGapStatus(StrEnum):
    """Lifecycle of a detected missing-knowledge gap (§7)."""

    OPEN = "Open"
    IN_PROGRESS = "In Progress"
    RESOLVED = "Resolved"
    ACCEPTED_RISK = "Accepted Risk"


class EvaluationKind(StrEnum):
    """What an :class:`EvaluationRun` row records."""

    METRICS = "metrics"
    SUCCESSOR_EXERCISE = "successor_exercise"


class ExerciseOutcome(StrEnum):
    """Result of one successor readiness-exercise question (§10)."""

    COMPLETED = "completed"
    BLOCKED = "blocked"
    MISSING_INFORMATION = "missing_information"
