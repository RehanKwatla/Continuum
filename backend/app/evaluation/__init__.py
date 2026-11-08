"""Reproducible evaluation framework (Phase 5 §9).

The framework is built from three parts, kept deliberately separate:

``ground_truth``
    A hand-authored, declarative description of what a correct pipeline should
    produce for one synthetic project. It is *data*, never model output.
``metrics``
    Pure functions that compare real database state against that dataset and
    return precision/recall/accuracy style results.
``service``
    Loads the observations from PostgreSQL, applies the metrics, persists an
    :class:`~app.models.phase5.EvaluationRun` and compares runs for regressions.

Nothing here generates a number the database cannot substantiate.
"""

from __future__ import annotations

from app.evaluation.ground_truth import (
    GROUND_TRUTH,
    GROUND_TRUTH_VERSION,
    GroundTruthClaim,
    GroundTruthConflict,
    GroundTruthDataset,
    GroundTruthGap,
)

__all__ = [
    "GROUND_TRUTH",
    "GROUND_TRUTH_VERSION",
    "GroundTruthClaim",
    "GroundTruthConflict",
    "GroundTruthDataset",
    "GroundTruthGap",
]
