"""The claim review state machine (Phase 4 §5).

The transitions below are enforced in backend business logic — never in the UI.
The frontend may *hide* an action, but the service layer is the only thing that
decides whether a transition is legal, and every legal transition is written to
``claim_history`` by the caller.

Design notes
------------
* ``ClaimStatus.VERIFIED`` *is* the approved state (product vocabulary:
  "Approved"). It is the only state that may enter an approved handover.
* A claim that is in an **open conflict** can never be approved directly:
  ``Conflict → Verified`` is not a legal transition, so the reviewer must first
  decide the conflict (which moves the claim to Supported or Uncertain).
* A **rejected** claim can only be re-opened *for review*, never approved in one
  step.
* Editing a claim's statement creates a new revision and moves it to
  ``Pending Review``, so an edited claim can never silently keep its Verified
  status.
"""

from __future__ import annotations

from app.models.enums import ClaimStatus
from app.core.errors import ConflictError

#: Legal transitions. A state may always "transition" to itself (idempotent).
TRANSITIONS: dict[ClaimStatus, frozenset[ClaimStatus]] = {
    ClaimStatus.EXTRACTED: frozenset(
        {
            ClaimStatus.SUPPORTED,
            ClaimStatus.UNCERTAIN,
            ClaimStatus.CONFLICT,
            ClaimStatus.PENDING_REVIEW,
            ClaimStatus.NEEDS_CLARIFICATION,
            ClaimStatus.REJECTED,
        }
    ),
    ClaimStatus.SUPPORTED: frozenset(
        {
            ClaimStatus.UNCERTAIN,
            ClaimStatus.CONFLICT,
            ClaimStatus.PENDING_REVIEW,
            ClaimStatus.NEEDS_CLARIFICATION,
            ClaimStatus.REJECTED,
            ClaimStatus.VERIFIED,
        }
    ),
    ClaimStatus.UNCERTAIN: frozenset(
        {
            ClaimStatus.SUPPORTED,
            ClaimStatus.CONFLICT,
            ClaimStatus.PENDING_REVIEW,
            ClaimStatus.NEEDS_CLARIFICATION,
            ClaimStatus.REJECTED,
            ClaimStatus.VERIFIED,
        }
    ),
    # A claim with an undecided conflict can never jump straight to approved.
    ClaimStatus.CONFLICT: frozenset(
        {
            ClaimStatus.SUPPORTED,
            ClaimStatus.UNCERTAIN,
            ClaimStatus.PENDING_REVIEW,
            ClaimStatus.NEEDS_CLARIFICATION,
            ClaimStatus.REJECTED,
        }
    ),
    ClaimStatus.PENDING_REVIEW: frozenset(
        {
            ClaimStatus.SUPPORTED,
            ClaimStatus.UNCERTAIN,
            ClaimStatus.CONFLICT,
            ClaimStatus.NEEDS_CLARIFICATION,
            ClaimStatus.REJECTED,
            ClaimStatus.VERIFIED,
        }
    ),
    ClaimStatus.NEEDS_CLARIFICATION: frozenset(
        {
            ClaimStatus.SUPPORTED,
            ClaimStatus.UNCERTAIN,
            ClaimStatus.PENDING_REVIEW,
            ClaimStatus.REJECTED,
            ClaimStatus.VERIFIED,
        }
    ),
    # Re-opening a rejected claim sends it back to review, never to approved.
    ClaimStatus.REJECTED: frozenset(
        {
            ClaimStatus.PENDING_REVIEW,
            ClaimStatus.NEEDS_CLARIFICATION,
        }
    ),
    # An approved claim may be re-opened (edit) or its approval revoked.
    ClaimStatus.VERIFIED: frozenset(
        {
            ClaimStatus.PENDING_REVIEW,
            ClaimStatus.REJECTED,
        }
    ),
}

#: Human-facing labels for the review status column (Approved == Verified).
REVIEW_STATUS_LABELS: dict[ClaimStatus, str] = {
    ClaimStatus.EXTRACTED: "Extracted",
    ClaimStatus.SUPPORTED: "Supported",
    ClaimStatus.UNCERTAIN: "Uncertain",
    ClaimStatus.CONFLICT: "Conflict",
    ClaimStatus.PENDING_REVIEW: "Pending review",
    ClaimStatus.NEEDS_CLARIFICATION: "Needs clarification",
    ClaimStatus.REJECTED: "Rejected",
    ClaimStatus.VERIFIED: "Approved",
}


def review_status_label(status: ClaimStatus) -> str:
    return REVIEW_STATUS_LABELS.get(status, str(status))


def can_transition(current: ClaimStatus, target: ClaimStatus) -> bool:
    """True when ``current -> target`` is a legal review transition."""
    if current == target:
        return True
    return target in TRANSITIONS.get(current, frozenset())


def assert_transition(current: ClaimStatus, target: ClaimStatus, *, action: str) -> None:
    """Raise a 409 when the transition is not allowed by the state machine."""
    if can_transition(current, target):
        return
    allowed = sorted(item.value for item in TRANSITIONS.get(current, frozenset()))
    raise ConflictError(
        f"Cannot {action} a claim in state '{current.value}'.",
        details={
            "action": action,
            "from_status": current.value,
            "to_status": target.value,
            "allowed_transitions": allowed,
        },
    )


def allowed_transitions(current: ClaimStatus) -> list[str]:
    return sorted(item.value for item in TRANSITIONS.get(current, frozenset()))
