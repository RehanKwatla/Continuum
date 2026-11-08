"""LangGraph orchestration for project-memory reconstruction.

The graph mirrors the Phase 3 specification exactly::

    access_filter → prepare_source_spans → extract_claims → validate_claims
    → verify_claims → detect_conflicts → detect_stale_information
    → persist_project_memory → create_open_questions → prepare_handover_input

Conditional edges cover the failure modes the specification calls out:

============================  =================================================
insufficient source data      no authorised sources, or no evidence spans
unavailable model             the provider is not configured (``NotConfigured``)
invalid claim / missing       every claim rejected ⇒ verification is skipped
evidence
verification failure          no claim could be verified ⇒ claims stay Uncertain
============================  =================================================

Failures are isolated per source inside the nodes, so one unreadable source never
restarts or invalidates the rest of the run.
"""

from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.ai.provider import LLMProvider
from app.workflow.nodes import WorkflowNodes
from app.workflow.state import (
    STATUS_FAILED,
    ReconstructionState,
)

logger = logging.getLogger("continuum.workflow.graph")

GRAPH_NAME = "continuum_project_memory_reconstruction"


def _coerce(state: ReconstructionState | dict) -> ReconstructionState:
    """LangGraph may hand a node a plain mapping; always work on the model."""
    if isinstance(state, ReconstructionState):
        return state
    return ReconstructionState.model_validate(state)


def _wrap(fn):
    """Adapt a bound node method to LangGraph's callable contract."""

    def run(state):
        return fn(_coerce(state))

    run.__name__ = getattr(fn, "__name__", "node")
    return run


def _wrap_router(fn):
    def route(state) -> str:
        return fn(_coerce(state))

    route.__name__ = getattr(fn, "__name__", "router")
    return route


def build_reconstruction_graph(db: Session, provider: LLMProvider):
    """Build and compile the reconstruction graph bound to a session/provider."""
    nodes = WorkflowNodes(db, provider)
    graph = StateGraph(ReconstructionState)

    graph.add_node("access_filter", _wrap(nodes.access_filter))
    graph.add_node("prepare_source_spans", _wrap(nodes.prepare_source_spans))
    graph.add_node("extract_claims", _wrap(nodes.extract_claims))
    graph.add_node("validate_claims", _wrap(nodes.validate_claims))
    graph.add_node("verify_claims", _wrap(nodes.verify_claims))
    graph.add_node("detect_conflicts", _wrap(nodes.detect_conflicts))
    graph.add_node("detect_stale_information", _wrap(nodes.detect_stale_information))
    graph.add_node("persist_project_memory", _wrap(nodes.persist_project_memory))
    graph.add_node("create_open_questions", _wrap(nodes.create_open_questions))
    graph.add_node("prepare_handover_input", _wrap(nodes.prepare_handover_input))

    graph.add_edge(START, "access_filter")
    graph.add_conditional_edges(
        "access_filter",
        _wrap_router(_route_after_access_filter),
        {"authorised": "prepare_source_spans", "stop": END},
    )
    graph.add_conditional_edges(
        "prepare_source_spans",
        _wrap_router(_route_after_spans),
        {"has_evidence": "extract_claims", "stop": END},
    )
    graph.add_edge("extract_claims", "validate_claims")
    graph.add_conditional_edges(
        "validate_claims",
        _wrap_router(_route_after_validate),
        {"has_claims": "verify_claims", "no_claims": "persist_project_memory"},
    )
    graph.add_conditional_edges(
        "verify_claims",
        _wrap_router(_route_after_verify),
        {
            "verified": "detect_conflicts",
            "verification_failed": "detect_conflicts",
            "no_claims": "persist_project_memory",
        },
    )
    graph.add_edge("detect_conflicts", "detect_stale_information")
    graph.add_edge("detect_stale_information", "persist_project_memory")
    graph.add_edge("persist_project_memory", "create_open_questions")
    graph.add_edge("create_open_questions", "prepare_handover_input")
    graph.add_edge("prepare_handover_input", END)

    return graph.compile(name=GRAPH_NAME)


# ---------------------------------------------------------------------------
# Routers
#
# Routers only *decide an edge*. They must not mutate the state: LangGraph keeps
# the value returned by a node, so a status written here would be silently lost.
# Terminal statuses are therefore set by the nodes themselves.
# ---------------------------------------------------------------------------
def _route_after_access_filter(state: ReconstructionState) -> str:
    if state.workflow_status == STATUS_FAILED:
        return "stop"
    if not state.source_records:
        return "stop"
    return "authorised"


def _route_after_spans(state: ReconstructionState) -> str:
    return "has_evidence" if state.evidence_records else "stop"


def _route_after_validate(state: ReconstructionState) -> str:
    return "has_claims" if state.extracted_claims else "no_claims"


def _route_after_verify(state: ReconstructionState) -> str:
    if not state.extracted_claims:
        return "no_claims"
    if state.verification_results:
        return "verified"
    return "verification_failed"
