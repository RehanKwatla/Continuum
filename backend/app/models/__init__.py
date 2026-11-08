"""ORM models package — importing it registers every table on ``Base.metadata``."""

from app.models.audit import AuditLog
from app.models.claim import Claim
from app.models.claim_history import ClaimHistory
from app.models.claim_revision import ClaimDecision, ClaimRevision
from app.models.conflict import Conflict, ConflictClaim
from app.models.enums import (
    AccessLabel,
    ClaimStatus,
    ClaimType,
    ConflictResolution,
    ConflictStatus,
    DependencyRiskStatus,
    EvaluationKind,
    ExerciseOutcome,
    FreshnessStatus,
    GitHubSubjectType,
    HandoverLifecycleStatus,
    HandoverStatus,
    KnowledgeGapStatus,
    OpenQuestionStatus,
    ProcessingRunStatus,
    ProcessingStatus,
    ProjectStatus,
    ReadinessBand,
    ReadinessDimension,
    RequirementCompletion,
    RequirementCriticality,
    ReviewDecision,
    SourceType,
    StatementType,
    SuccessorTaskPriority,
    SuccessorTaskStatus,
    VerificationVerdict,
    WorkspaceRole,
)
from app.models.evidence import Evidence
from app.models.evidence_span import EvidenceSpan
from app.models.github_connection import GitHubConnection
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
from app.models.project_repository import ProjectRepository
from app.models.source import Source
from app.models.user import User
from app.models.verification import Verification
from app.models.workspace import Workspace, WorkspaceMember

__all__ = [
    "AccessLabel",
    "AuditLog",
    "Claim",
    "ClaimDecision",
    "ClaimHistory",
    "ClaimRevision",
    "ClaimStatus",
    "ClaimType",
    "Conflict",
    "ConflictClaim",
    "ConflictResolution",
    "ConflictStatus",
    "DependencyRiskStatus",
    "EvaluationKind",
    "EvaluationRun",
    "Evidence",
    "EvidenceSpan",
    "ExerciseOutcome",
    "FreshnessStatus",
    "GitHubConnection",
    "GitHubSubjectType",
    "Handover",
    "HandoverDocument",
    "HandoverLifecycleStatus",
    "HandoverStatus",
    "HandoverVersion",
    "KnowledgeDependency",
    "KnowledgeGap",
    "KnowledgeGapStatus",
    "OpenQuestion",
    "OpenQuestionStatus",
    "ProcessingRun",
    "ProcessingRunStatus",
    "ProcessingStatus",
    "Project",
    "ProjectMemory",
    "ProjectRepository",
    "ProjectStatus",
    "ReadinessBand",
    "ReadinessDimension",
    "ReadinessEvaluation",
    "RequirementCompletion",
    "RequirementCriticality",
    "ReviewDecision",
    "Source",
    "SourceType",
    "StatementType",
    "SuccessorTask",
    "SuccessorTaskPriority",
    "SuccessorTaskStatus",
    "User",
    "Verification",
    "VerificationVerdict",
    "Workspace",
    "WorkspaceMember",
    "WorkspaceRole",
]
