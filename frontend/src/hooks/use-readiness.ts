/**
 * TanStack Query hooks for the Phase 5 layer (readiness, successor experience,
 * knowledge risk, evaluation and system health).
 *
 * Every hook reads a real endpoint; no metric is computed in the browser. The
 * server owns access control and the deterministic engines, so a client that
 * guesses a project id still cannot read another tenant's data.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/contexts/AuthContext";
import { queryKeys } from "@/lib/query-keys";
import {
  analyseKnowledgeDependencies,
  compareEvaluationRuns,
  createSuccessorTask,
  deriveSuccessorTasks,
  detectKnowledgeGaps,
  evaluateReadiness,
  getKnowledgeGap,
  getReadiness,
  getReadinessHistory,
  getScorecard,
  getSuccessorExercise,
  getSuccessorTask,
  getSuccessorWorkspace,
  getSystemHealth,
  listEvaluationRuns,
  listKnowledgeDependencies,
  listKnowledgeGaps,
  listSuccessorTasks,
  overrideKnowledgeDependency,
  runEvaluation,
  runSuccessorExercise,
  seedSyntheticProject,
  updateKnowledgeGap,
  updateSuccessorTask,
} from "@/services/readiness";
import type {
  EvaluationKind,
  KnowledgeDependencyOverrideInput,
  KnowledgeGapStatus,
  KnowledgeGapStatusUpdateInput,
  ReadinessEvaluateInput,
  SuccessorTaskCreateInput,
  SuccessorTaskStatus,
  SuccessorTaskStatusUpdateInput,
} from "@/types";

function useAuthed(enabled: boolean) {
  const { status } = useAuth();
  return status === "authenticated" && enabled;
}

/** Invalidate every Phase 5 cache for one project. */
function usePhase5Invalidator(projectId: string) {
  const client = useQueryClient();
  return () => {
    for (const key of [
      "readiness",
      "successor-workspace",
      "successor-tasks",
      "knowledge-dependencies",
      "knowledge-gaps",
      "scorecard",
      "successor-exercise",
      "evaluation",
      "system-health",
    ]) {
      void client.invalidateQueries({ queryKey: ["projects", projectId, key] });
    }
  };
}

// ---------------------------------------------------------------------------
// §2–§3 Readiness
// ---------------------------------------------------------------------------
export function useReadinessOverview(projectId: string | undefined) {
  const enabled = useAuthed(Boolean(projectId));
  return useQuery({
    queryKey: queryKeys.readiness(projectId ?? ""),
    queryFn: () => getReadiness(projectId as string),
    enabled,
  });
}

export function useReadinessHistory(
  projectId: string | undefined,
  params: { limit?: number } = {},
) {
  const enabled = useAuthed(Boolean(projectId));
  return useQuery({
    queryKey: queryKeys.readinessHistory(projectId ?? "", params as Record<string, unknown>),
    queryFn: () => getReadinessHistory(projectId as string, params),
    enabled,
  });
}

export function useEvaluateReadiness(projectId: string) {
  const invalidate = usePhase5Invalidator(projectId);
  return useMutation({
    mutationFn: (input: ReadinessEvaluateInput = {}) => evaluateReadiness(projectId, input),
    onSuccess: invalidate,
  });
}

// ---------------------------------------------------------------------------
// §4 Successor workspace
// ---------------------------------------------------------------------------
export function useSuccessorWorkspace(projectId: string | undefined) {
  const enabled = useAuthed(Boolean(projectId));
  return useQuery({
    queryKey: queryKeys.successorWorkspace(projectId ?? ""),
    queryFn: () => getSuccessorWorkspace(projectId as string),
    enabled,
  });
}

// ---------------------------------------------------------------------------
// §5 Successor task checklist
// ---------------------------------------------------------------------------
export function useSuccessorTasks(
  projectId: string | undefined,
  params: { status?: SuccessorTaskStatus } = {},
) {
  const enabled = useAuthed(Boolean(projectId));
  return useQuery({
    queryKey: queryKeys.successorTasks(projectId ?? "", params as Record<string, unknown>),
    queryFn: () => listSuccessorTasks(projectId as string, params),
    enabled,
  });
}

export function useSuccessorTask(projectId: string | undefined, taskId: string | undefined) {
  const enabled = useAuthed(Boolean(projectId) && Boolean(taskId));
  return useQuery({
    queryKey: queryKeys.successorTask(projectId ?? "", taskId ?? ""),
    queryFn: () => getSuccessorTask(projectId as string, taskId as string),
    enabled,
  });
}

export function useDeriveSuccessorTasks(projectId: string) {
  const invalidate = usePhase5Invalidator(projectId);
  return useMutation({
    mutationFn: () => deriveSuccessorTasks(projectId),
    onSuccess: invalidate,
  });
}

export function useCreateSuccessorTask(projectId: string) {
  const invalidate = usePhase5Invalidator(projectId);
  return useMutation({
    mutationFn: (input: SuccessorTaskCreateInput) => createSuccessorTask(projectId, input),
    onSuccess: invalidate,
  });
}

export function useUpdateSuccessorTask(projectId: string) {
  const invalidate = usePhase5Invalidator(projectId);
  return useMutation({
    mutationFn: ({ taskId, input }: { taskId: string; input: SuccessorTaskStatusUpdateInput }) =>
      updateSuccessorTask(projectId, taskId, input),
    onSuccess: invalidate,
  });
}

// ---------------------------------------------------------------------------
// §6 Knowledge dependency analysis
// ---------------------------------------------------------------------------
export function useKnowledgeDependencies(projectId: string | undefined) {
  const enabled = useAuthed(Boolean(projectId));
  return useQuery({
    queryKey: queryKeys.knowledgeDependencies(projectId ?? ""),
    queryFn: () => listKnowledgeDependencies(projectId as string),
    enabled,
  });
}

export function useAnalyseKnowledgeDependencies(projectId: string) {
  const invalidate = usePhase5Invalidator(projectId);
  return useMutation({
    mutationFn: () => analyseKnowledgeDependencies(projectId),
    onSuccess: invalidate,
  });
}

export function useOverrideKnowledgeDependency(projectId: string) {
  const invalidate = usePhase5Invalidator(projectId);
  return useMutation({
    mutationFn: ({
      dependencyId,
      input,
    }: {
      dependencyId: string;
      input: KnowledgeDependencyOverrideInput;
    }) => overrideKnowledgeDependency(projectId, dependencyId, input),
    onSuccess: invalidate,
  });
}

// ---------------------------------------------------------------------------
// §7 Missing knowledge detection
// ---------------------------------------------------------------------------
export function useKnowledgeGaps(
  projectId: string | undefined,
  params: { status?: KnowledgeGapStatus } = {},
) {
  const enabled = useAuthed(Boolean(projectId));
  return useQuery({
    queryKey: queryKeys.knowledgeGaps(projectId ?? "", params as Record<string, unknown>),
    queryFn: () => listKnowledgeGaps(projectId as string, params),
    enabled,
  });
}

export function useKnowledgeGap(projectId: string | undefined, gapId: string | undefined) {
  const enabled = useAuthed(Boolean(projectId) && Boolean(gapId));
  return useQuery({
    queryKey: queryKeys.knowledgeGap(projectId ?? "", gapId ?? ""),
    queryFn: () => getKnowledgeGap(projectId as string, gapId as string),
    enabled,
  });
}

export function useDetectKnowledgeGaps(projectId: string) {
  const invalidate = usePhase5Invalidator(projectId);
  return useMutation({
    mutationFn: () => detectKnowledgeGaps(projectId),
    onSuccess: invalidate,
  });
}

export function useUpdateKnowledgeGap(projectId: string) {
  const invalidate = usePhase5Invalidator(projectId);
  return useMutation({
    mutationFn: ({ gapId, input }: { gapId: string; input: KnowledgeGapStatusUpdateInput }) =>
      updateKnowledgeGap(projectId, gapId, input),
    onSuccess: invalidate,
  });
}

// ---------------------------------------------------------------------------
// §8 Continuity scorecard
// ---------------------------------------------------------------------------
export function useScorecard(projectId: string | undefined) {
  const enabled = useAuthed(Boolean(projectId));
  return useQuery({
    queryKey: queryKeys.scorecard(projectId ?? ""),
    queryFn: () => getScorecard(projectId as string),
    enabled,
  });
}

// ---------------------------------------------------------------------------
// §9–§10 Evaluation framework + successor exercise
// ---------------------------------------------------------------------------
export function useEvaluationRuns(
  projectId: string | undefined,
  params: { kind?: EvaluationKind; page?: number; page_size?: number } = {},
) {
  const enabled = useAuthed(Boolean(projectId));
  return useQuery({
    queryKey: queryKeys.evaluationRuns(projectId ?? "", params as Record<string, unknown>),
    queryFn: () => listEvaluationRuns(projectId as string, params),
    enabled,
  });
}

export function useSuccessorExercise(projectId: string | undefined) {
  const enabled = useAuthed(Boolean(projectId));
  return useQuery({
    queryKey: queryKeys.successorExercise(projectId ?? ""),
    queryFn: () => getSuccessorExercise(projectId as string),
    enabled,
    retry: false,
  });
}

export function useRunSuccessorExercise(projectId: string) {
  const invalidate = usePhase5Invalidator(projectId);
  return useMutation({
    mutationFn: () => runSuccessorExercise(projectId),
    onSuccess: invalidate,
  });
}

export function useRunEvaluation(projectId: string) {
  const invalidate = usePhase5Invalidator(projectId);
  return useMutation({
    mutationFn: (modelVersion?: string) =>
      runEvaluation(projectId, { model_version: modelVersion ?? null }),
    onSuccess: invalidate,
  });
}

export function useEvaluationComparison(
  projectId: string | undefined,
  base: string | undefined,
  candidate: string | undefined,
) {
  const enabled = useAuthed(Boolean(projectId) && Boolean(base) && Boolean(candidate));
  return useQuery({
    queryKey: queryKeys.evaluationComparison(projectId ?? "", base ?? "", candidate ?? ""),
    queryFn: () => compareEvaluationRuns(projectId as string, base as string, candidate as string),
    enabled,
  });
}

/** Seed the ground-truth project's corpus (workspace admins only, §9/§15). */
export function useSeedSyntheticProject(workspaceId: string | undefined) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => seedSyntheticProject(workspaceId as string),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

// ---------------------------------------------------------------------------
// §12 System health
// ---------------------------------------------------------------------------
export function useSystemHealth(projectId: string | undefined) {
  const enabled = useAuthed(Boolean(projectId));
  return useQuery({
    queryKey: queryKeys.systemHealth(projectId ?? ""),
    queryFn: () => getSystemHealth(projectId as string),
    enabled,
    refetchInterval: 30_000,
  });
}
