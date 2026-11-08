"""Versioned handover engine (Phase 4 §8–§14).

The engine consumes **only** human-approved claims. It never approves a claim,
never changes a claim's status and never bypasses the approval service: the set
of facts it can use is whatever the reviewers have approved, and nothing more.

Content model
-------------
A :class:`Handover` is the logical document for a project; its content lives in
immutable :class:`HandoverVersion` rows. Generating, editing, approving and
publishing all append a version or flip a lifecycle flag — an existing version's
content is never overwritten, and a published version is never replaced.

Provenance
----------
Every statement carries a ``statement_type`` and, for anything presented as a
project fact, the approved claim ids (and the exact claim revision) it came from.
The application — not the model and not the browser — decides what is
evidence-backed:

* statement types are assigned from the section, never taken from the request;
* a claim id that is not (still) approved is dropped and reported;
* an edited factual statement that loses its support is flagged ``unsupported``
  rather than being silently labelled as evidence-backed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.prompts import NOT_ESTABLISHED_PLACEHOLDER, SECTION_STATEMENT_TYPES
from app.ai.provider import LLMProvider
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.models.audit import AuditLog
from app.models.claim import Claim
from app.models.enums import (
    ClaimStatus,
    HandoverLifecycleStatus,
    StatementType,
    WorkspaceRole,
)
from app.models.evidence import Evidence
from app.models.handover import Handover, HandoverDocument, HandoverVersion
from app.models.project import Project
from app.models.source import Source
from app.models.user import User
from app.schemas.phase4 import (
    HandoverDetail,
    HandoverSectionInput,
    HandoverSectionModel,
    HandoverStatementModel,
    HandoverUpdateRequest,
    HandoverVersionRead,
    ReviewerNoteModel,
)
from app.services.handover_validator import (
    section_titles,
    statement_type_for_section,
    validate_edited_statement,
)

#: Roles allowed to approve or publish a handover.
PUBLISHER_ROLES: frozenset[WorkspaceRole] = frozenset(
    {WorkspaceRole.OWNER, WorkspaceRole.ADMIN}
)

_FACT = StatementType.ESTABLISHED_FACT.value
_SECTION_TITLES: dict[str, str] = section_titles()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean(text: str) -> str:
    return " ".join(text.split())


class HandoverService:
    """Creates, versions, validates and exports a project's handover."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def list(self, project_id: uuid.UUID) -> list[Handover]:
        return list(
            self.db.execute(
                select(Handover)
                .where(Handover.project_id == project_id)
                .order_by(Handover.created_at.desc())
            ).scalars().all()
        )

    def count(self, project_id: uuid.UUID) -> int:
        return int(
            self.db.execute(
                select(func.count()).select_from(Handover).where(Handover.project_id == project_id)
            ).scalar_one()
        )

    def get(self, project_id: uuid.UUID, handover_id: uuid.UUID) -> Handover:
        handover = self.db.get(Handover, handover_id)
        if handover is None or handover.project_id != project_id:
            raise NotFoundError("Handover not found.")
        return handover

    def latest(self, project_id: uuid.UUID) -> Handover | None:
        return self.db.execute(
            select(Handover)
            .where(Handover.project_id == project_id)
            .order_by(Handover.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    def version(self, handover: Handover, version_number: int) -> HandoverVersion | None:
        return self.db.execute(
            select(HandoverVersion)
            .where(
                HandoverVersion.handover_id == handover.id,
                HandoverVersion.version_number == version_number,
            )
            .limit(1)
        ).scalar_one_or_none()

    def current_version(self, handover: Handover) -> HandoverVersion | None:
        if handover.current_version <= 0:
            return None
        return self.version(handover, handover.current_version)

    def versions(self, handover: Handover) -> list[HandoverVersion]:
        return list(
            self.db.execute(
                select(HandoverVersion)
                .where(HandoverVersion.handover_id == handover.id)
                .order_by(HandoverVersion.version_number.desc())
            ).scalars().all()
        )

    def published_version(self, handover: Handover) -> HandoverVersion | None:
        return self.db.execute(
            select(HandoverVersion)
            .where(
                HandoverVersion.handover_id == handover.id,
                HandoverVersion.status == HandoverLifecycleStatus.PUBLISHED,
            )
            .order_by(HandoverVersion.version_number.desc())
            .limit(1)
        ).scalar_one_or_none()

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------
    def detail(self, handover: Handover, *, include_current: bool = True) -> HandoverDetail:
        current = self.current_version(handover) if include_current else None
        return HandoverDetail(
            id=handover.id,
            project_id=handover.project_id,
            title=handover.title,
            status=handover.status,
            current_version=handover.current_version,
            created_by_id=handover.created_by_id,
            created_at=handover.created_at,
            updated_at=handover.updated_at,
            current=self.version_payload(current) if current is not None else None,
        )

    def version_payload(self, version: HandoverVersion) -> HandoverVersionRead:
        notes = [
            ReviewerNoteModel.model_validate(item)
            for item in (version.reviewer_notes or [])
            if isinstance(item, dict)
        ]
        sections = [
            HandoverSectionModel.model_validate(item)
            for item in (version.structured_content or [])
            if isinstance(item, dict)
        ]
        return HandoverVersionRead(
            id=version.id,
            handover_id=version.handover_id,
            version_number=version.version_number,
            status=version.status,
            summary=version.summary,
            model_name=version.model_name,
            generated_by_id=version.generated_by_id,
            approved_by_id=version.approved_by_id,
            approved_at=version.approved_at,
            included_claim_ids=[item for item in (version.included_claim_ids or [])],
            claim_revisions=dict(version.claim_revisions or {}),
            validation_errors=[
                item for item in (version.validation_errors or []) if isinstance(item, dict)
            ],
            reviewer_notes=notes,
            sections=sections,
            created_at=version.created_at,
        )

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------
    def ensure_handover(self, project: Project, *, user: User, title: str | None = None) -> Handover:
        existing = self.latest(project.id)
        if existing is not None:
            if title and title.strip():
                existing.title = title.strip()[:300]
            return existing
        handover = Handover(
            project_id=project.id,
            title=(title or f"{project.name} — Project Handover")[:300],
            status=HandoverLifecycleStatus.DRAFT,
            current_version=0,
            created_by_id=user.id,
        )
        self.db.add(handover)
        self.db.flush()
        return handover

    def create_version_from_document(
        self,
        handover: Handover,
        *,
        user: User,
        document: HandoverDocument,
    ) -> HandoverVersion:
        """Seed a new draft version from a freshly generated document."""
        sections = self._sections_from_document(document)
        claim_ids: list[uuid.UUID] = []
        revisions: dict[str, int] = {}
        for section in sections:
            for statement in section["statements"]:
                for raw in statement["claim_ids"]:
                    cid = uuid.UUID(raw) if isinstance(raw, str) else raw
                    if cid not in claim_ids:
                        claim_ids.append(cid)
                revisions.update(statement.get("claim_revisions") or {})
        return self._append_version(
            handover,
            user=user,
            sections=sections,
            included_claim_ids=claim_ids,
            claim_revisions=revisions,
            validation_errors=[
                {**item, "source": "generation"}
                for item in (document.validation_errors or [])
                if isinstance(item, dict)
            ],
            reviewer_notes=[],
            summary=document.summary,
            model_name=document.model_name,
            document_id=document.id,
            status=HandoverLifecycleStatus.DRAFT,
        )

    def generate(
        self,
        project: Project,
        *,
        user: User,
        provider: LLMProvider,
        title: str | None = None,
    ) -> tuple[Handover, HandoverVersion]:
        """Generate a fresh draft handover from the project's **approved** claims.

        The fact set is fixed by the approval service: this method reads only
        human-approved claims (through the deterministic validator) and never
        writes to a claim or changes a claim's status.
        """
        from app.services.memory_service import MemoryService

        document = MemoryService(self.db).generate_handover(
            project, user=user, provider=provider
        )
        handover = self.ensure_handover(project, user=user, title=title)
        version = self.create_version_from_document(handover, user=user, document=document)
        self._audit(
            handover,
            user=user,
            action="handover_generated",
            resource_type="handover_version",
            resource_id=version.id,
            metadata={
                "version_number": version.version_number,
                "document_id": str(document.id),
                "claim_count": len(version.included_claim_ids or []),
                "validation_errors": len(version.validation_errors or []),
            },
        )
        self.db.commit()
        self.db.refresh(version)
        return handover, version

    def save_reviewer_edit(
        self, handover: Handover, *, user: User, payload: HandoverUpdateRequest
    ) -> HandoverVersion:
        """Apply a reviewer's edit as a **new** version (never an overwrite).

        Editing a published handover starts a new draft revision; the published
        version itself is left exactly as it was.
        """
        sections, claim_ids, revisions, errors = self._normalise_sections(
            handover.project_id, payload.sections
        )
        previous = self.current_version(handover)
        notes = list((previous.reviewer_notes if previous else []) or [])
        for text in payload.reviewer_notes:
            cleaned = _clean(text)
            if not cleaned:
                continue
            notes.append(
                ReviewerNoteModel(
                    id=uuid.uuid4().hex,
                    text=cleaned,
                    author_id=user.id,
                    created_at=_now(),
                ).model_dump(mode="json")
            )

        if payload.title and payload.title.strip():
            handover.title = payload.title.strip()[:300]

        version = self._append_version(
            handover,
            user=user,
            sections=sections,
            included_claim_ids=claim_ids,
            claim_revisions=revisions,
            validation_errors=errors,
            reviewer_notes=notes,
            summary=(_clean(payload.summary) if payload.summary else None),
            model_name=previous.model_name if previous else None,
            document_id=previous.document_id if previous else None,
            status=HandoverLifecycleStatus.DRAFT,
        )
        self._audit(
            handover,
            user=user,
            action="handover_edited",
            resource_type="handover_version",
            resource_id=version.id,
            metadata={
                "version_number": version.version_number,
                "note": payload.note or "",
                "validation_errors": len(errors),
            },
        )
        self.db.commit()
        self.db.refresh(version)
        return version

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def submit_for_review(self, handover: Handover, *, user: User) -> HandoverVersion:
        version = self._require_current(handover)
        if version.status is not HandoverLifecycleStatus.DRAFT:
            raise ConflictError("Only a draft handover can be submitted for review.")
        version.status = HandoverLifecycleStatus.IN_REVIEW
        handover.status = HandoverLifecycleStatus.IN_REVIEW
        self._audit(
            handover,
            user=user,
            action="handover_submitted",
            resource_type="handover_version",
            resource_id=version.id,
            metadata={"version_number": version.version_number},
        )
        self.db.commit()
        self.db.refresh(version)
        return version

    def approve(
        self, handover: Handover, *, user: User, role: WorkspaceRole, note: str | None = None
    ) -> HandoverVersion:
        """Approve the current version. Only a human reviewer may do this."""
        if role not in PUBLISHER_ROLES:
            raise ForbiddenError(
                "Only a workspace owner or admin may approve a handover."
            )
        version = self._require_current(handover)
        if version.status not in {
            HandoverLifecycleStatus.DRAFT,
            HandoverLifecycleStatus.IN_REVIEW,
        }:
            raise ConflictError(
                f"A handover in state '{version.status.value}' cannot be approved."
            )
        problems = self.validate_version(version)
        if problems:
            raise ValidationAppError(
                "This handover cannot be approved yet: "
                + "; ".join(item["message"] for item in problems[:3]),
                code="handover_validation_failed",
                details={"problems": problems},
            )
        version.status = HandoverLifecycleStatus.APPROVED
        version.approved_by_id = user.id
        version.approved_at = _now()
        handover.status = HandoverLifecycleStatus.APPROVED
        self._audit(
            handover,
            user=user,
            action="handover_approved",
            resource_type="handover_version",
            resource_id=version.id,
            metadata={"version_number": version.version_number, "note": note or ""},
        )
        self.db.commit()
        self.db.refresh(version)
        return version

    def publish(
        self, handover: Handover, *, user: User, role: WorkspaceRole, note: str | None = None
    ) -> HandoverVersion:
        if role not in PUBLISHER_ROLES:
            raise ForbiddenError(
                "Only a workspace owner or admin may publish a handover."
            )
        version = self._require_current(handover)
        if version.status is HandoverLifecycleStatus.PUBLISHED:
            raise ConflictError("This version has already been published.")
        if version.status is not HandoverLifecycleStatus.APPROVED:
            raise ConflictError(
                "A handover must be approved by a reviewer before it can be published."
            )
        problems = self.validate_version(version)
        if problems:
            raise ValidationAppError(
                "This handover cannot be published yet: "
                + "; ".join(item["message"] for item in problems[:3]),
                code="handover_validation_failed",
                details={"problems": problems},
            )
        version.status = HandoverLifecycleStatus.PUBLISHED
        handover.status = HandoverLifecycleStatus.PUBLISHED
        self._audit(
            handover,
            user=user,
            action="handover_published",
            resource_type="handover_version",
            resource_id=version.id,
            metadata={"version_number": version.version_number, "note": note or ""},
        )
        self.db.commit()
        self.db.refresh(version)
        return version

    def archive(self, handover: Handover, *, user: User) -> Handover:
        handover.status = HandoverLifecycleStatus.ARCHIVED
        self._audit(
            handover,
            user=user,
            action="handover_archived",
            resource_type="handover",
            resource_id=handover.id,
            metadata={},
        )
        self.db.commit()
        return handover

    # ------------------------------------------------------------------
    # Deterministic validation (§10)
    # ------------------------------------------------------------------
    def validate_version(self, version: HandoverVersion) -> list[dict[str, Any]]:
        """Re-check a stored version against the *current* approved claims.

        A version is only approvable/publishable when every factual statement is
        still backed by an approved claim at the exact revision that was
        recorded — an edit to a claim since then invalidates the link.
        """
        approved = self.approved_claims(version.handover.project_id)
        approved_ids = set(approved)
        problems: list[dict[str, Any]] = []

        for section in version.structured_content or []:
            if not isinstance(section, dict):
                continue
            key = str(section.get("key", ""))
            for statement in section.get("statements", []) or []:
                if not isinstance(statement, dict):
                    continue
                stype = statement.get("statement_type")
                text = str(statement.get("text", ""))
                claim_ids = [
                    uuid.UUID(str(item))
                    for item in (statement.get("claim_ids") or [])
                    if _is_uuid(str(item))
                ]
                if statement.get("unsupported"):
                    problems.append(
                        {
                            "code": "unsupported_statement",
                            "section": key,
                            "text": text[:200],
                            "message": f"'{text[:60]}...' is not backed by an approved claim.",
                        }
                    )
                    continue
                if stype != _FACT:
                    continue
                if not claim_ids:
                    problems.append(
                        {
                            "code": "missing_citation",
                            "section": key,
                            "text": text[:200],
                            "message": f"A factual statement in '{key}' cites no approved claim.",
                        }
                    )
                    continue
                for claim_id in claim_ids:
                    if claim_id not in approved_ids:
                        problems.append(
                            {
                                "code": "claim_not_approved",
                                "section": key,
                                "message": (
                                    f"A statement in '{key}' cites a claim that is no longer approved."
                                ),
                            }
                        )
                        continue
                    recorded = (version.claim_revisions or {}).get(str(claim_id))
                    if recorded is not None and recorded != approved[claim_id]:
                        problems.append(
                            {
                                "code": "claim_revision_changed",
                                "section": key,
                                "message": (
                                    f"A claim cited in '{key}' has been edited since this "
                                    "handover was generated and must be reviewed again."
                                ),
                            }
                        )
        return problems

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------
    def approved_claims(self, project_id: uuid.UUID) -> dict[uuid.UUID, int]:
        """``{claim_id: revision_number}`` for every approved claim."""
        rows = self.db.execute(
            select(Claim.id, Claim.revision_number).where(
                Claim.project_id == project_id, Claim.status == ClaimStatus.VERIFIED
            )
        ).all()
        return {claim_id: revision for claim_id, revision in rows}

    def evidence_index(
        self, claim_ids: list[uuid.UUID], *, include_restricted: bool = False
    ) -> dict[uuid.UUID, list[dict[str, Any]]]:
        """Evidence references per claim, newest first.

        Restricted sources are excluded unless ``include_restricted`` is set, so
        restricted source material can never leak into an exported document.
        """
        if not claim_ids:
            return {}
        query = (
            select(Evidence, Source)
            .join(Source, Source.id == Evidence.source_id)
            .where(Evidence.claim_id.in_(claim_ids))
            .order_by(Evidence.created_at)
        )
        index: dict[uuid.UUID, list[dict[str, Any]]] = {claim_id: [] for claim_id in claim_ids}
        for evidence, source in self.db.execute(query).all():
            if source is None:
                continue
            if not include_restricted and str(source.access_label.value) == "restricted":
                continue
            index.setdefault(evidence.claim_id, []).append(
                {
                    "source_name": source.source_name,
                    "source_type": str(source.source_type.value),
                    "location": evidence.source_location,
                    "quote": evidence.supporting_quote,
                    "author": source.author,
                    "source_date": (
                        source.created_at_source or source.created_at
                    ).isoformat()
                    if (source.created_at_source or source.created_at)
                    else None,
                    "restricted": str(source.access_label.value) == "restricted",
                }
            )
        return index

    # ------------------------------------------------------------------
    # Rendering (§14)
    # ------------------------------------------------------------------
    def render_markdown(
        self, handover: Handover, version: HandoverVersion, *, project: Project
    ) -> str:
        """Render a version as Markdown, preserving references and notes."""
        evidence = self.evidence_index(
            [item for item in (version.included_claim_ids or []) if _is_uuid(str(item))]
        )
        lines: list[str] = [
            f"# {handover.title}",
            "",
            f"- Project: {project.name}",
            f"- Version: {version.version_number}",
            f"- Status: {version.status.value}",
            f"- Generated: {version.created_at.isoformat()}",
            f"- Approved by: {version.approved_by_id or 'not yet approved'}",
            f"- Approved at: {version.approved_at.isoformat() if version.approved_at else '—'}",
            "",
        ]
        if version.summary:
            lines.extend([version.summary, ""])

        for section in version.structured_content or []:
            if not isinstance(section, dict) or section.get("removed"):
                continue
            lines.extend([f"## {section.get('title', 'Section')}", ""])
            statements = [s for s in (section.get("statements") or []) if isinstance(s, dict)]
            if not statements:
                lines.extend(
                    [f"_{section.get('placeholder') or NOT_ESTABLISHED_PLACEHOLDER}_", ""]
                )
                continue
            for statement in statements:
                text = str(statement.get("text", "")).strip()
                refs = [str(item) for item in (statement.get("claim_ids") or [])]
                stype = statement.get("statement_type")
                label = {
                    StatementType.REVIEWER_NOTE.value: "Reviewer note",
                    StatementType.SUGGESTED_ACTION.value: "Suggested action",
                    StatementType.UNRESOLVED_QUESTION.value: "Unresolved question",
                }.get(stype)
                prefix = f"**{label}:** " if label else ""
                suffix = f" _[claims: {', '.join(refs)}]_" if refs else ""
                flag = " _(flagged: not evidence-backed)_" if statement.get("unsupported") else ""
                lines.append(f"- {prefix}{text}{suffix}{flag}")
                for ref in refs:
                    for item in evidence.get(uuid.UUID(ref), []):
                        location = f" — {item['location']}" if item.get("location") else ""
                        lines.append(f"    - Evidence: {item['source_name']}{location}")
            lines.append("")

        notes = [item for item in (version.reviewer_notes or []) if isinstance(item, dict)]
        if notes:
            lines.extend(["## Reviewer notes", ""])
            for item in notes:
                lines.append(f"- {item.get('text', '')}")
            lines.append("")

        if version.validation_errors:
            lines.extend(["## Validation log", ""])
            for item in version.validation_errors:
                if not isinstance(item, dict):
                    continue
                lines.append(f"- `{item.get('code', 'issue')}`: {item.get('message', '')}")
            lines.append("")

        lines.extend(
            [
                "## Approval",
                "",
                (
                    "This handover was approved by a reviewer and contains only "
                    "human-approved claims."
                    if version.status
                    in {HandoverLifecycleStatus.APPROVED, HandoverLifecycleStatus.PUBLISHED}
                    else "This handover is a draft. It is not approved and must not be "
                    "treated as an agreed record until a reviewer approves it."
                ),
                "",
            ]
        )
        return "\n".join(lines)

    def render_pdf(
        self, handover: Handover, version: HandoverVersion, *, project: Project
    ) -> bytes:
        """Render a version as a simple, readable PDF (PyMuPDF)."""
        import pymupdf

        markdown = self.render_markdown(handover, version, project=project)
        document = pymupdf.open()
        page = document.new_page()
        width, height = page.rect.width, page.rect.height
        x, y = 56.0, 64.0
        max_width = width - 112
        body_font = 10.5
        for raw_line in markdown.splitlines():
            text = raw_line.replace("**", "").replace("_", "").replace("`", "")
            if not text.strip():
                y += body_font
                continue
            bold = raw_line.startswith("#")
            size = 17 if raw_line.startswith("# ") else 13 if raw_line.startswith("## ") else body_font
            font = "hebo" if bold else "helv"
            for wrapped in _wrap(text, max_width, size):
                if y > height - 56:
                    page = document.new_page()
                    y = 64.0
                page.insert_text((x, y), wrapped, fontname=font, fontsize=size)
                y += size * 1.45
            y += 3
        payload = document.tobytes()
        document.close()
        return payload

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _require_current(self, handover: Handover) -> HandoverVersion:
        version = self.current_version(handover)
        if version is None:
            raise NotFoundError("This handover has no version yet.")
        return version

    def _append_version(
        self,
        handover: Handover,
        *,
        user: User,
        sections: list[dict[str, Any]],
        included_claim_ids: list[uuid.UUID],
        claim_revisions: dict[str, int],
        validation_errors: list[dict[str, Any]],
        reviewer_notes: list[dict[str, Any]],
        summary: str | None,
        model_name: str | None,
        document_id: uuid.UUID | None,
        status: HandoverLifecycleStatus,
    ) -> HandoverVersion:
        handover.current_version += 1
        version = HandoverVersion(
            handover_id=handover.id,
            version_number=handover.current_version,
            document_id=document_id,
            structured_content=sections,
            included_claim_ids=[str(item) for item in included_claim_ids],
            claim_revisions=claim_revisions,
            validation_errors=validation_errors,
            reviewer_notes=reviewer_notes,
            status=status,
            generated_by_id=user.id,
            summary=summary,
            model_name=model_name,
            meta={},
        )
        # A new draft always re-opens the document for review.
        handover.status = HandoverLifecycleStatus.DRAFT
        self.db.add(version)
        project = self.db.get(Project, handover.project_id)
        self.db.add(
            AuditLog(
                user_id=user.id,
                workspace_id=project.workspace_id if project else None,
                action="handover_version_created",
                resource_type="handover_version",
                resource_id=version.id,
                meta={
                    "project_id": str(handover.project_id),
                    "version_number": version.version_number,
                    "claim_count": len(included_claim_ids),
                    "validation_errors": len(validation_errors),
                },
            )
        )
        self.db.flush()
        return version

    def _sections_from_document(self, document: HandoverDocument) -> list[dict[str, Any]]:
        """Convert a generated document's sections into version content."""
        sections: list[dict[str, Any]] = []
        for raw in document.sections or []:
            if not isinstance(raw, dict):
                continue
            key = str(raw.get("key", "")).strip().lower()
            if key not in _SECTION_TITLES:
                continue
            statements: list[dict[str, Any]] = []
            for item in raw.get("statements", []) or []:
                if not isinstance(item, dict):
                    continue
                text = _clean(str(item.get("text", "")))
                if not text:
                    continue
                claim_ids = [str(cid) for cid in (item.get("claim_ids") or [])]
                statements.append(
                    {
                        "statement_id": str(item.get("statement_id") or uuid.uuid4().hex),
                        "text": text,
                        "statement_type": str(
                            item.get("statement_type") or statement_type_for_section(key)
                        ),
                        "claim_ids": claim_ids,
                        "claim_revisions": dict(item.get("claim_revisions") or {}),
                        "original_text": None,
                        "reviewer_edited": False,
                        "unsupported": bool(item.get("unsupported", False)),
                    }
                )
            sections.append(
                {
                    "key": key,
                    "title": str(raw.get("title") or _SECTION_TITLES[key]),
                    "statements": statements,
                    "not_established": bool(raw.get("not_established", not statements)),
                    "placeholder": raw.get("placeholder")
                    or (NOT_ESTABLISHED_PLACEHOLDER if not statements else None),
                    "removed": False,
                }
            )
        return sections

    def _normalise_sections(
        self, project_id: uuid.UUID, sections: list[HandoverSectionInput]
    ) -> tuple[list[dict[str, Any]], list[uuid.UUID], dict[str, int], list[dict[str, Any]]]:
        """Server-authoritative normalisation of a reviewer's edit.

        The browser may reorder, retitle, remove or rewrite; it may not decide
        what counts as evidence-backed. Claim ids are re-resolved against the
        approved set, statement types are re-derived from the section, and any
        factual statement that is no longer supported is flagged.
        """
        approved = self.approved_claims(project_id)
        approved_ids = set(approved)
        content: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        used: list[uuid.UUID] = []
        revisions: dict[str, int] = {}
        seen: set[str] = set()

        for item in sections:
            key = (item.key or "").strip().lower()
            if key not in _SECTION_TITLES:
                errors.append(
                    {
                        "code": "unknown_section",
                        "section": key or "(missing)",
                        "message": "Section key is not part of the handover template.",
                    }
                )
                continue
            if key in seen:
                errors.append(
                    {
                        "code": "duplicate_section",
                        "section": key,
                        "message": "Each section may appear only once.",
                    }
                )
                continue
            seen.add(key)

            title = _clean(item.title or "") or _SECTION_TITLES[key]
            default_type = statement_type_for_section(key)
            statements: list[dict[str, Any]] = []
            for statement in item.statements:
                text = _clean(statement.text)
                if not text:
                    continue
                claimed = list(dict.fromkeys(statement.claim_ids))
                kept = [cid for cid in claimed if cid in approved_ids]
                dropped = [cid for cid in claimed if cid not in approved_ids]
                if dropped:
                    errors.append(
                        {
                            "code": "claim_not_approved",
                            "section": key,
                            "message": (
                                "Dropped references to claims that are not approved: "
                                + ", ".join(str(cid) for cid in dropped)
                            ),
                        }
                    )

                unsupported = False
                if default_type == _FACT:
                    ok, reason = validate_edited_statement(
                        text, claim_ids=kept, approved_ids=approved_ids
                    )
                    if not ok:
                        unsupported = True
                        errors.append(
                            {
                                "code": "unsupported_statement",
                                "section": key,
                                "text": text[:200],
                                "message": (
                                    f"A factual statement in '{key}' is not backed by an "
                                    f"approved claim: {reason}"
                                ),
                            }
                        )

                statement_revisions = {
                    str(cid): approved[cid] for cid in kept
                }
                original = statement.original_text
                reviewer_edited = bool(original) or not statement.statement_id
                statements.append(
                    {
                        "statement_id": statement.statement_id or uuid.uuid4().hex,
                        "text": text,
                        "statement_type": default_type,
                        "claim_ids": [str(cid) for cid in kept],
                        "claim_revisions": statement_revisions,
                        "original_text": original,
                        "reviewer_edited": reviewer_edited,
                        "unsupported": unsupported,
                    }
                )
                for cid in kept:
                    if cid not in used:
                        used.append(cid)
                    revisions[str(cid)] = approved[cid]

            content.append(
                {
                    "key": key,
                    "title": title,
                    "statements": statements,
                    "not_established": not statements,
                    "placeholder": None if statements else NOT_ESTABLISHED_PLACEHOLDER,
                    "removed": bool(item.removed),
                }
            )

        return content, used, revisions, errors

    def _audit(
        self,
        handover: Handover,
        *,
        user: User,
        action: str,
        resource_type: str,
        resource_id: uuid.UUID | None,
        metadata: dict[str, Any],
    ) -> None:
        project = self.db.get(Project, handover.project_id)
        self.db.add(
            AuditLog(
                user_id=user.id,
                workspace_id=project.workspace_id if project else None,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                meta={"project_id": str(handover.project_id), **metadata},
            )
        )


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def _wrap(text: str, max_width: float, size: float) -> list[str]:
    """Greedy word wrap using an approximate character width."""
    per_char = size * 0.5
    capacity = max(20, int(max_width / per_char))
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        if len(current) + 1 + len(word) <= capacity:
            current = f"{current} {word}"
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines
