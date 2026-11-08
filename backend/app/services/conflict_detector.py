"""Deterministic conflict detection.

Conflicts are found by application code, never by an LLM. The detector groups
claims by *(entity, claim type)* and then compares the **same property** across
claims:

``"Database version is PostgreSQL 13"`` vs ``"… PostgreSQL 15"``
    → the value token (``13``/``15``) has the same anchor word (``postgresql``),
      so the two statements disagree about one property → **conflict**.

``"Webhook retries are capped at 3 attempts"`` vs ``"… timeout is 30 seconds"``
    → the values have different anchors (``retries`` vs ``timeout``), so these are
      two different properties, not a contradiction → **not a conflict**.

Ownership is treated specially. ``"Alice owned payments in January"`` and
``"Bob owns payments in September"`` are a *change over time*, not a
disagreement, so the detector records an informational ``changed_over_time``
finding and does **not** mark the claims as conflicting. Only owners claimed for
the same period count as a conflict.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from app.ai.contracts import ConflictFinding, ExtractedClaim
from app.models.enums import ClaimType

#: Claim types whose values can be compared for disagreement.
COMPARABLE_TYPES: frozenset[ClaimType] = frozenset(
    {
        ClaimType.TECHNICAL_CONSTRAINT,
        ClaimType.DEPENDENCY,
        ClaimType.DECISION,
        ClaimType.ARCHITECTURE,
        ClaimType.CONSTRAINT,
        ClaimType.STATUS,
        ClaimType.OPERATIONAL_PROCEDURE,
        ClaimType.OWNERSHIP,
        ClaimType.RESPONSIBILITY,
    }
)

#: Types where a difference is an ownership change rather than a contradiction.
OWNERSHIP_TYPES: frozenset[ClaimType] = frozenset(
    {ClaimType.OWNERSHIP, ClaimType.RESPONSIBILITY}
)

#: Two ownership claims this far apart are a change over time, not a conflict.
OWNERSHIP_TIME_WINDOW_DAYS = 20

_VALUE_DISAGREEMENT = "value_disagreement"
_CHANGED_OVER_TIME = "changed_over_time"

_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._@/-]*")
#: Version-like or plain numeric values ("1.2.3", "13", "18").
_VALUE_SCAN_RE = re.compile(r"\d+(?:[._]\d+)*")
_CAPITALISED_RE = re.compile(r"\b[A-Z][a-z]{2,}\b")
_QUOTED_RE = re.compile(r"[\"'`]([^\"'`]{2,80})[\"'`]")
#: Single-letter prefixes accepted before a version ("v18", "r2").
_VERSION_PREFIXES = frozenset({"v", "r"})

_NUMBER_WORDS: dict[str, str] = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
}

_STOPWORDS: frozenset[str] = frozenset(
    """
    the a an and or but if then than that this these those is are was were be been being
    to of in on at for with from by as it its into about over under again more most
    must should will would can could may might shall do does did done not no nor only
    own owns owned owner ownership responsible responsibility maintain maintains
    maintainer lead leads manage manages managed handle handles handle in charge by
    have has had there their them they we our you your he she his her who whom which
    when where why how all any both each few some such too very just about after
    before between during same different version versions currently now also per
    """.split()
)

_MONTHS: frozenset[str] = frozenset(
    """
    january february march april may june july august september october november december
    jan feb mar apr jun jul aug sep sept oct nov dec
    """.split()
)


@dataclass(frozen=True)
class _Value:
    """A value token together with the property anchor it belongs to."""

    value: str
    anchor: str


def _tokens(text: str) -> list[str]:
    """Word tokens, case-folded, with number words normalised to digits."""
    tokens: list[str] = []
    for match in _WORD_RE.finditer(text):
        token = match.group(0).casefold()
        if token in _NUMBER_WORDS:
            token = _NUMBER_WORDS[token]
        tokens.append(token)
    return tokens


def _distinctive_tokens(text: str) -> set[str]:
    return {
        token
        for token in _tokens(text)
        if token not in _STOPWORDS and len(token) > 2 and not token.isdigit()
    }


def _anchor_before(text: str, end: int) -> str:
    """Last meaningful word before ``end`` — the property a value belongs to."""
    tokens = _tokens(text[:end])
    for token in reversed(tokens):
        if len(token) < 2 or token in _STOPWORDS or token.isdigit():
            continue
        return token
    return ""


def _scan_values(text: str) -> list[tuple[str, int]]:
    """``(value, offset)`` pairs for numeric/version-like runs in ``text``."""
    found: list[tuple[str, int]] = []
    for match in _VALUE_SCAN_RE.finditer(text):
        start = match.start()
        prefix = 0
        if start > 0 and text[start - 1].isalnum():
            if (
                start >= 2
                and text[start - 1].casefold() in _VERSION_PREFIXES
                and not text[start - 2].isalnum()
            ):
                prefix = 1
            else:
                continue  # part of an identifier such as "abc123"
        found.append((match.group(0), start - prefix))
    for match in _WORD_RE.finditer(text):
        token = match.group(0).casefold()
        if token in _NUMBER_WORDS:
            found.append((_NUMBER_WORDS[token], match.start()))
    return found


def _extract_values(text: str) -> list[_Value]:
    """Value tokens paired with the property anchor each one belongs to."""
    values: list[_Value] = [
        _Value(value=value, anchor=_anchor_before(text, offset))
        for value, offset in _scan_values(text)
    ]
    for quoted in _QUOTED_RE.findall(text):
        index = text.find(quoted)
        values.append(_Value(value=quoted.strip().casefold(), anchor=_anchor_before(text, index)))
    return values


def _property_key(claim: ExtractedClaim, anchor: str) -> str:
    entity = (claim.entity or "").strip().casefold()
    if entity and anchor and anchor not in entity:
        return f"{entity} · {anchor}"[:200]
    return (entity or anchor or claim.claim_type.value)[:200]


def _subjects(text: str, entity: str | None) -> set[str]:
    """People/teams named as the subject of an ownership statement."""
    entity_tokens = {token for token in _tokens(entity or "")}
    subjects: set[str] = set()
    for match in _CAPITALISED_RE.finditer(text):
        candidate = match.group(0)
        lowered = candidate.casefold()
        if lowered in _MONTHS or lowered in _STOPWORDS or lowered in entity_tokens:
            continue
        if match.start() == 0:  # sentence-initial capitalisation is not a name
            continue
        subjects.add(lowered)
    for handle in re.findall(r"@([A-Za-z0-9-]{2,})", text):
        subjects.add(handle.casefold())
    for team in ("team", "squad", "guild", "group"):
        if team in _tokens(text):
            subjects.add(team)
    return subjects


def _days_apart(left: datetime | None, right: datetime | None) -> int | None:
    if left is None or right is None:
        return None
    return abs((left.date() - right.date()).days)


class ConflictDetector:
    """Deterministic, time-aware contradiction detector."""

    def __init__(self, *, ownership_window_days: int = OWNERSHIP_TIME_WINDOW_DAYS) -> None:
        self.ownership_window_days = ownership_window_days

    def detect(self, claims: list[ExtractedClaim]) -> list[ConflictFinding]:
        findings: list[ConflictFinding] = []
        for group in self._groups(claims):
            findings.extend(self._compare_group(group))
        return findings

    # -- internals -----------------------------------------------------
    @staticmethod
    def _groups(claims: list[ExtractedClaim]) -> list[list[ExtractedClaim]]:
        buckets: dict[tuple[str, str], list[ExtractedClaim]] = {}
        for claim in claims:
            if claim.claim_type not in COMPARABLE_TYPES:
                continue
            entity = (claim.entity or "").strip().casefold()
            buckets.setdefault((entity, claim.claim_type.value), []).append(claim)
        return [group for group in buckets.values() if len(group) > 1]

    def _compare_group(self, group: list[ExtractedClaim]) -> list[ConflictFinding]:
        findings: list[ConflictFinding] = []
        reported: set[tuple[int, int]] = set()

        for left_index, left in enumerate(group):
            for right_index in range(left_index + 1, len(group)):
                right = group[right_index]
                if (left_index, right_index) in reported:
                    continue
                finding = self._compare_pair(left, right)
                if finding is not None:
                    reported.add((left_index, right_index))
                    findings.append(finding)
        return findings

    def _compare_pair(
        self, left: ExtractedClaim, right: ExtractedClaim
    ) -> ConflictFinding | None:
        if right.dedup_key == left.dedup_key:
            return None

        shared = _distinctive_tokens(left.text) & _distinctive_tokens(right.text)
        if left.claim_type in OWNERSHIP_TYPES:
            return self._compare_ownership(left, right, shared)

        left_values = _extract_values(left.text)
        right_values = _extract_values(right.text)
        if not left_values or not right_values:
            return None

        for candidate_left in left_values:
            for candidate_right in right_values:
                if not candidate_left.anchor or candidate_left.anchor != candidate_right.anchor:
                    continue
                if candidate_left.value == candidate_right.value:
                    continue
                if not shared and left.entity != right.entity:
                    continue
                return ConflictFinding(
                    entity=left.entity or right.entity,
                    claim_type=left.claim_type,
                    property_key=_property_key(left, candidate_left.anchor),
                    kind=_VALUE_DISAGREEMENT,
                    summary=(
                        f'"{left.text}" conflicts with "{right.text}" '
                        f"(both describe '{candidate_left.anchor}' but give "
                        f"'{candidate_left.value}' vs '{candidate_right.value}')."
                    ),
                    claim_local_ids=[left.local_id, right.local_id],
                    values={
                        str(left.local_id): candidate_left.value,
                        str(right.local_id): candidate_right.value,
                    },
                    time_contexts=self._time_contexts(left, right),
                )
        return None

    def _compare_ownership(
        self, left: ExtractedClaim, right: ExtractedClaim, shared: set[str]
    ) -> ConflictFinding | None:
        left_subjects = _subjects(left.text, left.entity)
        right_subjects = _subjects(right.text, right.entity)
        if not left_subjects or not right_subjects:
            return None
        if left_subjects & right_subjects:
            # Same owner stated twice: agreement, not a conflict.
            return None

        gap = _days_apart(left.time_context, right.time_context)
        if gap is not None and gap >= self.ownership_window_days:
            # Ownership changed between the two records: informational only.
            return ConflictFinding(
                entity=left.entity or right.entity,
                claim_type=left.claim_type,
                property_key=_property_key(left, "owner"),
                kind=_CHANGED_OVER_TIME,
                summary=(
                    "Ownership changed over time rather than conflicting: "
                    f'"{left.text}" ({self._date(left)}) predates '
                    f'"{right.text}" ({self._date(right)}).'
                ),
                claim_local_ids=[left.local_id, right.local_id],
                values={
                    str(left.local_id): ", ".join(sorted(left_subjects)),
                    str(right.local_id): ", ".join(sorted(right_subjects)),
                },
                time_contexts=self._time_contexts(left, right),
            )

        return ConflictFinding(
            entity=left.entity or right.entity,
            claim_type=left.claim_type,
            property_key=_property_key(left, "owner"),
            kind=_VALUE_DISAGREEMENT,
            summary=(
                "Two ownership statements with no separation in time disagree: "
                f'"{left.text}" vs "{right.text}".'
            ),
            claim_local_ids=[left.local_id, right.local_id],
            values={
                str(left.local_id): ", ".join(sorted(left_subjects)),
                str(right.local_id): ", ".join(sorted(right_subjects)),
            },
            time_contexts=self._time_contexts(left, right),
        )

    @staticmethod
    def _date(claim: ExtractedClaim) -> str:
        return claim.time_context.date().isoformat() if claim.time_context else "undated"

    @staticmethod
    def _time_contexts(left: ExtractedClaim, right: ExtractedClaim) -> dict[str, str]:
        return {
            str(left.local_id): ConflictDetector._date(left),
            str(right.local_id): ConflictDetector._date(right),
        }
