/**
 * Phase 5 API calls: handover readiness, successor experience, knowledge risk,
 * evaluation and system health.
 *
 * Nothing here computes a score or a metric — every number comes from the
 * deterministic backend engines, and every response is read straight back from
 * the server. Access control is re-checked server-side on every request; this
 * module only mirrors the documented contract.
 */

import { apiGet, apiPatch, apiPost } from "@/services/api";
import type {
  ContinuityScorecard,
  EvaluationComparison,
  EvaluationKind,
  EvaluationRun,
  EvaluationRunInput,
  EvaluationRunListResponse,
  KnowledgeDependency,
  KnowledgeDependencyListResponse,
  KnowledgeDependencyOverrideInput,
  KnowledgeGap,
  KnowledgeGapListResponse,
  KnowledgeGapStatus,
  KnowledgeGapStatusUpdateInput,
  ReadinessEvaluateInput,
  ReadinessEvaluation,
  ReadinessHistoryResponse,
  ReadinessOverview,
  SuccessorDeriveResponse,
  SuccessorTask,
  SuccessorTaskCreateInput,
  SuccessorTaskListResponse,
  SuccessorTaskStatus,
  SuccessorTaskStatusUpdateInput,
  SuccessorWorkspace,
  SyntheticSeedResponse,
  SystemHealth,
} from "@/types";

// ---------------------------------------------------------------------------
// §2–§3 Handover readiness
// ---------------------------------------------------------------------------
export function getReadiness(projectId: string): Promise<ReadinessOverview> {
  return apiGet<ReadinessOverview>(`/projects/${projectId}/readiness`);
}

/** Run the deterministic readiness engine and persist one immutable snapshot. */
export function evaluateReadiness(
  projectId: string,
  input: ReadinessEvaluateInput = {},
): Promise<ReadinessEvaluation> {
  return apiPost<ReadinessEvaluation>(`/projects/${projectId}/readiness/evaluate`, input);
}

export function getReadinessHistory(
  projectId: string,
  params: { limit?: number } = {},
): Promise<ReadinessHistoryResponse> {
  return apiGet<ReadinessHistoryResponse>(`/projects/${projectId}/readiness/history`, { params });
}

export function getReadinessEvaluation(
  projectId: string,
  evaluationId: string,
): Promise<ReadinessEvaluation> {
  return apiGet<ReadinessEvaluation>(`/projects/${projectId}/readiness/${evaluationId}`);
}

// ---------------------------------------------------------------------------
// §5 Successor task checklist
// ---------------------------------------------------------------------------
export function listSuccessorTasks(
  projectId: string,
  params: { status?: SuccessorTaskStatus } = {},
): Promise<SuccessorTaskListResponse> {
  return apiGet<SuccessorTaskListResponse>(`/projects/${projectId}/successor-tasks`, { params });
}

/** Derive the checklist from approved knowledge. Idempotent on the server. */
export function deriveSuccessorTasks(projectId: string): Promise<SuccessorDeriveResponse> {
  return apiPost<SuccessorDeriveResponse>(`/projects/${projectId}/successor-tasks/derive`, {});
}

export function createSuccessorTask(
  projectId: string,
  input: SuccessorTaskCreateInput,
): Promise<SuccessorTask> {
  return apiPost<SuccessorTask>(`/projects/${projectId}/successor-tasks`, input);
}

export function getSuccessorTask(projectId: string, taskId: string): Promise<SuccessorTask> {
  return apiGet<SuccessorTask>(`/projects/${projectId}/successor-tasks/${taskId}`);
}

export function updateSuccessorTask(
  projectId: string,
  taskId: string,
  input: SuccessorTaskStatusUpdateInput,
): Promise<SuccessorTask> {
  return apiPatch<SuccessorTask>(`/projects/${projectId}/successor-tasks/${taskId}`, input);
}

// ---------------------------------------------------------------------------
// §6 Knowledge dependency analysis
// ---------------------------------------------------------------------------
export function listKnowledgeDependencies(
  projectId: string,
): Promise<KnowledgeDependencyListResponse> {
  return apiGet<KnowledgeDependencyListResponse>(`/projects/${projectId}/knowledge-dependencies`);
}

export function analyseKnowledgeDependencies(
  projectId: string,
): Promise<KnowledgeDependencyListResponse> {
  return apiPost<KnowledgeDependencyListResponse>(
    `/projects/${projectId}/knowledge-dependencies/analyse`,
    {},
  );
}

export function getKnowledgeDependency(
  projectId: string,
  dependencyId: string,
): Promise<KnowledgeDependency> {
  return apiGet<KnowledgeDependency>(
    `/projects/${projectId}/knowledge-dependencies/${dependencyId}`,
  );
}

/** A reviewer override is audited and never overwrites the computed risk. */
export function overrideKnowledgeDependency(
  projectId: string,
  dependencyId: string,
  input: KnowledgeDependencyOverrideInput,
): Promise<KnowledgeDependency> {
  return apiPost<KnowledgeDependency>(
    `/projects/${projectId}/knowledge-dependencies/${dependencyId}/override`,
    input,
  );
}

// ---------------------------------------------------------------------------
// §7 Missing knowledge detection
// ---------------------------------------------------------------------------
export function listKnowledgeGaps(
  projectId: string,
  params: { status?: KnowledgeGapStatus } = {},
): Promise<KnowledgeGapListResponse> {
  return apiGet<KnowledgeGapListResponse>(`/projects/${projectId}/knowledge-gaps`, { params });
}

/** Detect gaps by comparing readiness requirements against approved knowledge. */
export function detectKnowledgeGaps(projectId: string): Promise<KnowledgeGapListResponse> {
  return apiPost<KnowledgeGapListResponse>(`/projects/${projectId}/knowledge-gaps/detect`, {});
}

export function getKnowledgeGap(projectId: string, gapId: string): Promise<KnowledgeGap> {
  return apiGet<KnowledgeGap>(`/projects/${projectId}/knowledge-gaps/${gapId}`);
}

export function updateKnowledgeGap(
  projectId: string,
  gapId: string,
  input: KnowledgeGapStatusUpdateInput,
): Promise<KnowledgeGap> {
  return apiPatch<KnowledgeGap>(`/projects/${projectId}/knowledge-gaps/${gapId}`, input);
}

// ---------------------------------------------------------------------------
// §8 Continuity scorecard
// ---------------------------------------------------------------------------
export function getScorecard(projectId: string): Promise<ContinuityScorecard> {
  return apiGet<ContinuityScorecard>(`/projects/${projectId}/scorecard`);
}

// ---------------------------------------------------------------------------
// §4 Successor readiness workspace
// ---------------------------------------------------------------------------
export function getSuccessorWorkspace(projectId: string): Promise<SuccessorWorkspace> {
  return apiGet<SuccessorWorkspace>(`/projects/${projectId}/successor-workspace`);
}

// ---------------------------------------------------------------------------
// §10 Successor readiness exercise
// ---------------------------------------------------------------------------
export function runSuccessorExercise(projectId: string): Promise<EvaluationRun> {
  return apiPost<EvaluationRun>(`/projects/${projectId}/successor-exercise`, {});
}

export function getSuccessorExercise(projectId: string): Promise<EvaluationRun> {
  return apiGet<EvaluationRun>(`/projects/${projectId}/successor-exercise`);
}

// ---------------------------------------------------------------------------
// §9 Evaluation framework
// ---------------------------------------------------------------------------
export function runEvaluation(
  projectId: string,
  input: EvaluationRunInput = {},
): Promise<EvaluationRun> {
  return apiPost<EvaluationRun>(`/projects/${projectId}/evaluation/runs`, input);
}

export function listEvaluationRuns(
  projectId: string,
  params: { kind?: EvaluationKind; page?: number; page_size?: number } = {},
): Promise<EvaluationRunListResponse> {
  return apiGet<EvaluationRunListResponse>(`/projects/${projectId}/evaluation/runs`, { params });
}

export function compareEvaluationRuns(
  projectId: string,
  base: string,
  candidate: string,
): Promise<EvaluationComparison> {
  return apiGet<EvaluationComparison>(`/projects/${projectId}/evaluation/compare`, {
    params: { base, candidate },
  });
}

export function getEvaluationRun(projectId: string, runId: string): Promise<EvaluationRun> {
  return apiGet<EvaluationRun>(`/projects/${projectId}/evaluation/runs/${runId}`);
}

/** Seed the ground-truth project's source corpus (workspace admins only). */
export function seedSyntheticProject(workspaceId: string): Promise<SyntheticSeedResponse> {
  return apiPost<SyntheticSeedResponse>(
    `/workspaces/${workspaceId}/evaluation/synthetic-project`,
    {},
  );
}

// ---------------------------------------------------------------------------
// §12 System health
// ---------------------------------------------------------------------------
export function getSystemHealth(projectId: string): Promise<SystemHealth> {
  return apiGet<SystemHealth>(`/projects/${projectId}/system-health`);
}
