"""The Handover Readiness requirement catalog (Phase 5 §2).

This module is deliberately *data*, not model output. Every readiness
requirement is declared here with the exact claim categories, keywords and
source types that can satisfy it. The scoring engine
(:mod:`app.services.readiness_service`) evaluates these declarations
deterministically — an LLM never decides a requirement's status or a score.

Design notes
------------
* Only **approved** claims (``ClaimStatus.VERIFIED``) can satisfy an
  evidence-backed requirement. Extracted but unapproved claims never earn
  credit; they surface as ``Uncertain`` instead, so knowledge that exists but
  has not been reviewed is visible rather than silently counted.
* A requirement whose supporting claims are part of an *open* conflict is
  ``Blocked`` — a contradiction must be resolved before it can count.
* Requirements are never dropped to improve a score. A requirement that cannot
  be satisfied stays in the catalog as ``Missing`` and is surfaced by the
  Missing Knowledge engine (§7).
* ``missing_information`` documents what a Missing/Partial result means, and is
  copied into evaluation output so a reader is never left guessing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.enums import (
    ClaimType,
    ReadinessDimension,
    RequirementCriticality,
    SourceType,
)

# ---------------------------------------------------------------------------
# Presentation bands (§3) and default dimension weights (§2)
# ---------------------------------------------------------------------------
#: Overall readiness length is presented as a band. These thresholds are the
#: initial product defaults and are configurable per evaluation.
DEFAULT_BANDS: tuple[tuple[float, str], ...] = (
    (90.0, "strong"),
    (75.0, "mostly_ready"),
    (50.0, "needs_review"),
    (0.0, "not_ready"),
)

#: Default dimension weights. They must sum to 100.
DEFAULT_WEIGHTS: dict[ReadinessDimension, float] = {
    ReadinessDimension.PROJECT_CONTEXT: 15.0,
    ReadinessDimension.IMPORTANT_DECISIONS: 15.0,
    ReadinessDimension.TECHNICAL_DEPENDENCIES: 20.0,
    ReadinessDimension.OWNERSHIP_CLARITY: 15.0,
    ReadinessDimension.UNFINISHED_WORK: 15.0,
    ReadinessDimension.RISKS_OPERATIONS: 20.0,
}

#: Human-readable dimension labels (used by the API and the UI).
DIMENSION_LABELS: dict[ReadinessDimension, str] = {
    ReadinessDimension.PROJECT_CONTEXT: "Project context",
    ReadinessDimension.IMPORTANT_DECISIONS: "Important decisions",
    ReadinessDimension.TECHNICAL_DEPENDENCIES: "Technical dependencies",
    ReadinessDimension.OWNERSHIP_CLARITY: "Ownership clarity",
    ReadinessDimension.UNFINISHED_WORK: "Unfinished work",
    ReadinessDimension.RISKS_OPERATIONS: "Risks and operational procedures",
}

#: The formula, recorded verbatim on every evaluation so a score is auditable.
SCORING_FORMULA = (
    "dimension_score = 100 * SUM(criticality_weight(req) * completion_value(req)) "
    "/ SUM(criticality_weight(req))  -- over the dimension's requirements; "
    "overall_score = SUM(dimension_score * dimension_weight / 100)  -- over the six "
    "dimensions. criticality weights: critical=3, important=2, optional=1. "
    "completion values: Complete=1.0, Partial=0.5, Uncertain=0.25, Missing=0.0, "
    "Blocked=0.0. Only human-approved claims satisfy an evidence-backed requirement."
)


@dataclass(frozen=True)
class RequirementSpec:
    """One declarative readiness requirement."""

    requirement_id: str
    dimension: ReadinessDimension
    description: str
    criticality: RequirementCriticality
    #: Approved claim categories that can satisfy the requirement.
    claim_types: tuple[ClaimType, ...] = ()
    #: If set, a claim must contain at least one of these (case-insensitive).
    keywords: tuple[str, ...] = ()
    #: How many approved claims are needed for a ``Complete`` result.
    min_approved: int = 1
    #: Whether the supporting claims must cite at least one evidence row.
    require_evidence: bool = True
    #: Sources of these types satisfy the requirement even without a claim
    #: (used where availability of a reference — not a reviewed statement — is
    #: what matters, e.g. a connected repository).
    source_types: tuple[SourceType, ...] = ()
    #: What a Missing/Partial result means for the successor.
    missing_information: str = ""
    #: A concrete, non-binding suggestion for closing the gap (§7).
    suggested_resolution: str = ""
    #: Missing-knowledge category used when this requirement is not satisfied.
    gap_category: str = "other"
    #: Free-form notes copied into the evaluation for auditability.
    notes: str = ""
    extra: dict[str, object] = field(default_factory=dict)


def _r(
    requirement_id: str,
    dimension: ReadinessDimension,
    description: str,
    criticality: RequirementCriticality,
    *,
    claim_types: tuple[ClaimType, ...] = (),
    keywords: tuple[str, ...] = (),
    min_approved: int = 1,
    require_evidence: bool = True,
    source_types: tuple[SourceType, ...] = (),
    missing_information: str = "",
    suggested_resolution: str = "",
    gap_category: str = "other",
) -> RequirementSpec:
    return RequirementSpec(
        requirement_id=requirement_id,
        dimension=dimension,
        description=description,
        criticality=criticality,
        claim_types=claim_types,
        keywords=keywords,
        min_approved=min_approved,
        require_evidence=require_evidence,
        source_types=source_types,
        missing_information=missing_information,
        suggested_resolution=suggested_resolution,
        gap_category=gap_category,
    )


_CT = ClaimType
_D = ReadinessDimension
_CRIT = RequirementCriticality.CRITICAL
_IMP = RequirementCriticality.IMPORTANT
_OPT = RequirementCriticality.OPTIONAL

_GITHUB_SOURCES: tuple[SourceType, ...] = (
    SourceType.GITHUB_COMMIT,
    SourceType.GITHUB_ISSUE,
    SourceType.GITHUB_PULL_REQUEST,
    SourceType.GITHUB_README,
    SourceType.GITHUB_FILE,
)

#: The complete requirement catalog, in display order.
REQUIREMENTS: tuple[RequirementSpec, ...] = (
    # -- 1. Project context ------------------------------------------------
    _r(
        "ctx.purpose",
        _D.PROJECT_CONTEXT,
        "The project's purpose is documented.",
        _CRIT,
        claim_types=(_CT.ARCHITECTURE, _CT.STATUS),
        missing_information=(
            "No approved statement explains what the project is for, so a successor "
            "cannot confirm they are working on the right problem."
        ),
        suggested_resolution="Approve a statement describing the project's purpose.",
        gap_category="project_context",
    ),
    _r(
        "ctx.current_state",
        _D.PROJECT_CONTEXT,
        "The project's current state is described.",
        _IMP,
        claim_types=(_CT.STATUS, _CT.PROCESS, _CT.ARCHITECTURE),
        missing_information="The successor has no approved description of where the project stands today.",
        suggested_resolution="Approve a statement describing the current project state.",
        gap_category="project_context",
    ),
    _r(
        "ctx.scope",
        _D.PROJECT_CONTEXT,
        "The project's scope and boundaries are described.",
        _IMP,
        claim_types=(_CT.ARCHITECTURE, _CT.TECHNICAL_CONSTRAINT, _CT.PROCESS),
        missing_information="Nothing records what is in and out of scope for the project.",
        suggested_resolution="Approve statements describing the project's scope and exclusions.",
        gap_category="project_context",
    ),
    _r(
        "ctx.tech_stack",
        _D.PROJECT_CONTEXT,
        "The technology stack is identified.",
        _IMP,
        claim_types=(_CT.DEPENDENCY, _CT.TECHNICAL_CONSTRAINT, _CT.ARCHITECTURE),
        missing_information="The languages, frameworks or platforms are not documented.",
        suggested_resolution="Approve statements identifying the technology stack.",
        gap_category="project_context",
    ),
    # -- 2. Important decisions -------------------------------------------
    _r(
        "decisions.documented",
        _D.IMPORTANT_DECISIONS,
        "At least one important project decision is documented.",
        _CRIT,
        claim_types=(_CT.DECISION,),
        missing_information="No approved decision is recorded, so a successor cannot tell why the project is built this way.",
        suggested_resolution="Review and approve the project's key decisions.",
        gap_category="decisions",
    ),
    _r(
        "decisions.breadth",
        _D.IMPORTANT_DECISIONS,
        "More than one important decision is documented.",
        _IMP,
        claim_types=(_CT.DECISION,),
        min_approved=2,
        missing_information="Only a single decision is documented; a handover normally needs several.",
        suggested_resolution="Approve the remaining significant decisions.",
        gap_category="decisions",
    ),
    _r(
        "decisions.rationale",
        _D.IMPORTANT_DECISIONS,
        "At least one decision records its rationale.",
        _IMP,
        claim_types=(_CT.DECISION,),
        keywords=("because", "so that", "in order to", "due to", "rationale", "reason", "trade-off", "tradeoff"),
        missing_information="Decisions are recorded without the reasoning behind them.",
        suggested_resolution="Approve a decision statement that explains why the choice was made.",
        gap_category="decisions",
    ),
    # -- 3. Technical dependencies ----------------------------------------
    _r(
        "tech.architecture",
        _D.TECHNICAL_DEPENDENCIES,
        "The architecture is documented.",
        _CRIT,
        claim_types=(_CT.ARCHITECTURE, _CT.TECHNICAL_CONSTRAINT),
        missing_information="The system architecture is not documented in approved knowledge.",
        suggested_resolution="Approve architecture statements (components, data flow, storage).",
        gap_category="architecture",
    ),
    _r(
        "tech.repository",
        _D.TECHNICAL_DEPENDENCIES,
        "Repository references are available.",
        _IMP,
        claim_types=(_CT.DEPENDENCY,),
        keywords=("repo", "repository", "github", "gitlab", "bitbucket"),
        require_evidence=False,
        source_types=_GITHUB_SOURCES,
        missing_information="No repository reference is available to the successor.",
        suggested_resolution="Connect the project's repository or document where the code lives.",
        gap_category="repository",
    ),
    _r(
        "tech.external_services",
        _D.TECHNICAL_DEPENDENCIES,
        "External services are identified.",
        _CRIT,
        claim_types=(_CT.DEPENDENCY,),
        keywords=("service", "api", "external", "third-party", "third party", "stripe", "payment", "gemini", "supabase", "sendgrid", "twilio", "aws", "s3"),
        missing_information="External services the project depends on are not identified.",
        suggested_resolution="Approve statements naming each external service the project calls.",
        gap_category="integrations",
    ),
    _r(
        "tech.environment_config",
        _D.TECHNICAL_DEPENDENCIES,
        "Required environment configuration is described without exposing secrets.",
        _IMP,
        claim_types=(_CT.TECHNICAL_CONSTRAINT, _CT.DEPENDENCY),
        keywords=("env", "environment", "config", "configur", "variable", "secret", "credential"),
        missing_information="The environment variables or configuration a successor must supply are not documented.",
        suggested_resolution="Approve a statement listing the required configuration keys (never their values).",
        gap_category="configuration",
    ),
    _r(
        "tech.integrations",
        _D.TECHNICAL_DEPENDENCIES,
        "Important integrations are identified.",
        _IMP,
        claim_types=(_CT.DEPENDENCY,),
        keywords=("integration", "webhook", "oauth", "connector", "pipeline", "sync"),
        missing_information="The project's integrations with other systems are not identified.",
        suggested_resolution="Approve statements describing each external integration.",
        gap_category="integrations",
    ),
    _r(
        "tech.deployment",
        _D.TECHNICAL_DEPENDENCIES,
        "Deployment dependencies are documented.",
        _CRIT,
        claim_types=(_CT.DEPENDENCY, _CT.OPERATIONAL_PROCEDURE),
        keywords=("deploy", "hosting", "render", "vercel", "docker", "ci", "cd", "pipeline", "release"),
        missing_information="What the project needs in order to be deployed is not documented.",
        suggested_resolution="Approve statements describing the deployment targets and their dependencies.",
        gap_category="deployment",
    ),
    # -- 4. Ownership clarity ---------------------------------------------
    _r(
        "owner.modules_owned",
        _D.OWNERSHIP_CLARITY,
        "Critical modules have an identified owner where evidence establishes one.",
        _CRIT,
        claim_types=(_CT.OWNERSHIP, _CT.RESPONSIBILITY),
        missing_information="No approved statement establishes who owns any part of the project.",
        suggested_resolution="Approve the ownership or responsibility statements supported by evidence.",
        gap_category="ownership",
    ),
    _r(
        "owner.unowned_flagged",
        _D.OWNERSHIP_CLARITY,
        "Responsibilities without an established owner are flagged rather than assumed.",
        _IMP,
        missing_information="Responsibilities exist that no approved ownership statement covers.",
        suggested_resolution="Either approve an ownership statement for each uncovered area, or accept the risk explicitly.",
        gap_category="ownership",
    ),
    _r(
        "owner.changes_visible",
        _D.OWNERSHIP_CLARITY,
        "Ownership changes are visible.",
        _OPT,
        claim_types=(_CT.OWNERSHIP, _CT.RESPONSIBILITY),
        keywords=("took over", "handed over", "transfer", "reassigned", "now owned", "onboard", "succeeded"),
        missing_information="No record of ownership changing hands is available.",
        suggested_resolution="Approve statements recording ownership transitions.",
        gap_category="ownership",
    ),
    _r(
        "owner.evidence_backed",
        _D.OWNERSHIP_CLARITY,
        "Unsupported ownership assumptions are not accepted.",
        _CRIT,
        claim_types=(_CT.OWNERSHIP, _CT.RESPONSIBILITY),
        missing_information="At least one approved ownership statement cites no supporting evidence.",
        suggested_resolution="Attach evidence to the ownership statements, or remove the claim if it cannot be supported.",
        gap_category="ownership",
    ),
    # -- 5. Unfinished work -----------------------------------------------
    _r(
        "work.tasks_visible",
        _D.UNFINISHED_WORK,
        "Unfinished tasks are visible.",
        _IMP,
        claim_types=(_CT.TASK, _CT.UNFINISHED_WORK),
        missing_information=(
            "No unfinished work is recorded. This is treated as incomplete evidence, "
            "not as proof that nothing is outstanding."
        ),
        suggested_resolution="Approve the statements describing outstanding work.",
        gap_category="unfinished_work",
    ),
    _r(
        "work.in_progress",
        _D.UNFINISHED_WORK,
        "Work currently in progress is described.",
        _IMP,
        claim_types=(_CT.TASK, _CT.UNFINISHED_WORK, _CT.PROCESS),
        keywords=("in progress", "ongoing", "wip", "pending", "unfinished", "not yet", "remaining", "still"),
        missing_information="It is unclear what work is actively in progress.",
        suggested_resolution="Approve statements describing the work currently underway.",
        gap_category="unfinished_work",
    ),
    _r(
        "work.open_questions",
        _D.UNFINISHED_WORK,
        "Unresolved questions are identified.",
        _IMP,
        claim_types=(_CT.OPEN_QUESTION,),
        missing_information="No unresolved questions are recorded, which is itself a knowledge gap.",
        suggested_resolution="Approve the open questions collected during review.",
        gap_category="open_questions",
    ),
    _r(
        "work.blockers",
        _D.UNFINISHED_WORK,
        "Known blockers on unfinished work are recorded.",
        _OPT,
        claim_types=(_CT.UNFINISHED_WORK, _CT.RISK, _CT.TASK),
        keywords=("blocked", "blocker", "waiting on", "depends on", "stuck"),
        missing_information="Nothing records whether outstanding work is blocked.",
        suggested_resolution="Approve statements identifying blockers, or record explicitly that none are known.",
        gap_category="unfinished_work",
    ),
    # -- 6. Risks and operational procedures ------------------------------
    _r(
        "risk.risks_documented",
        _D.RISKS_OPERATIONS,
        "Critical risks are documented.",
        _CRIT,
        claim_types=(_CT.RISK,),
        missing_information="No risk is documented, so a successor cannot prepare for known failure modes.",
        suggested_resolution="Approve the risk statements identified during review.",
        gap_category="risks",
    ),
    _r(
        "ops.runbook",
        _D.RISKS_OPERATIONS,
        "Operational procedures are available.",
        _CRIT,
        claim_types=(_CT.OPERATIONAL_PROCEDURE,),
        missing_information="No operating procedure is documented.",
        suggested_resolution="Approve runbook and operating-procedure statements.",
        gap_category="operations",
    ),
    _r(
        "ops.deployment_procedure",
        _D.RISKS_OPERATIONS,
        "A deployment procedure is documented.",
        _IMP,
        claim_types=(_CT.OPERATIONAL_PROCEDURE, _CT.DEPENDENCY),
        keywords=("deploy", "release", "ship", "publish"),
        missing_information="No deployment procedure is documented.",
        suggested_resolution="Approve the deployment procedure.",
        gap_category="deployment",
    ),
    _r(
        "ops.rollback_procedure",
        _D.RISKS_OPERATIONS,
        "A rollback procedure is documented.",
        _IMP,
        claim_types=(_CT.OPERATIONAL_PROCEDURE, _CT.RISK),
        keywords=("rollback", "roll back", "revert", "restore", "back out", "backout"),
        missing_information="No rollback procedure is documented.",
        suggested_resolution="Approve a rollback procedure, or record explicitly that none exists.",
        gap_category="rollback",
    ),
    _r(
        "ops.incident_procedure",
        _D.RISKS_OPERATIONS,
        "An incident or escalation procedure is documented.",
        _OPT,
        claim_types=(_CT.OPERATIONAL_PROCEDURE, _CT.RISK),
        keywords=("incident", "on-call", "oncall", "escalat", "alert", "outage", "postmortem"),
        missing_information="Nothing describes what to do when the project breaks in production.",
        suggested_resolution="Approve an incident and escalation procedure.",
        gap_category="operations",
    ),
)

#: Index by id for quick lookup.
REQUIREMENTS_BY_ID: dict[str, RequirementSpec] = {r.requirement_id: r for r in REQUIREMENTS}

#: Requirements grouped by dimension, preserving catalog order.
REQUIREMENTS_BY_DIMENSION: dict[ReadinessDimension, tuple[RequirementSpec, ...]] = {
    dimension: tuple(r for r in REQUIREMENTS if r.dimension is dimension)
    for dimension in ReadinessDimension
}


def default_weights() -> dict[str, float]:
    """Default weights keyed by dimension *value* (JSON-friendly)."""
    return {dimension.value: weight for dimension, weight in DEFAULT_WEIGHTS.items()}


def band_for_score(score: float, bands: tuple[tuple[float, str], ...] = DEFAULT_BANDS) -> str:
    """Map a 0–100 score to its presentation band."""
    for threshold, name in bands:
        if score >= threshold:
            return name
    return bands[-1][1]


__all__ = [
    "DEFAULT_BANDS",
    "DEFAULT_WEIGHTS",
    "DIMENSION_LABELS",
    "REQUIREMENTS",
    "REQUIREMENTS_BY_DIMENSION",
    "REQUIREMENTS_BY_ID",
    "SCORING_FORMULA",
    "RequirementSpec",
    "band_for_score",
    "default_weights",
]
