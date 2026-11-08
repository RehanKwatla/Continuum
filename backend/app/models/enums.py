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
    """Only a human reviewer may move a claim to :attr:`VERIFIED`."""

    SUPPORTED = "Supported"
    UNCERTAIN = "Uncertain"
    CONFLICT = "Conflict"
    VERIFIED = "Verified"


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
