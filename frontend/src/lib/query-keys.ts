/** Central TanStack Query key factory — keeps cache invalidation predictable. */

export const queryKeys = {
  /** Service readiness probe (`/ready`), distinct from per-project handover readiness. */
  serviceReadiness: ["readiness"] as const,
  health: ["health"] as const,
  session: ["session"] as const,

  workspaces: ["workspaces"] as const,
  workspace: (workspaceId: string) => ["workspaces", workspaceId] as const,

  projects: (params?: Record<string, unknown>) => ["projects", params ?? {}] as const,
  project: (projectId: string) => ["projects", projectId] as const,

  sources: (projectId: string, params?: Record<string, unknown>) =>
    ["projects", projectId, "sources", params ?? {}] as const,
  source: (sourceId: string) => ["sources", sourceId] as const,

  dashboard: ["dashboard"] as const,

  memory: (projectId: string) => ["projects", projectId, "memory"] as const,
  processingRuns: (projectId: string, params?: Record<string, unknown>) =>
    ["projects", projectId, "memory", "runs", params ?? {}] as const,
  claims: (projectId: string, params?: Record<string, unknown>) =>
    ["projects", projectId, "memory", "claims", params ?? {}] as const,
  claim: (projectId: string, claimId: string) =>
    ["projects", projectId, "memory", "claims", claimId] as const,
  reviewQueue: (projectId: string, params?: Record<string, unknown>) =>
    ["projects", projectId, "memory", "review-queue", params ?? {}] as const,
  conflicts: (projectId: string, params?: Record<string, unknown>) =>
    ["projects", projectId, "memory", "conflicts", params ?? {}] as const,
  conflict: (projectId: string, conflictId: string) =>
    ["projects", projectId, "memory", "conflicts", conflictId] as const,
  questions: (projectId: string, params?: Record<string, unknown>) =>
    ["projects", projectId, "memory", "questions", params ?? {}] as const,
  uncertainty: (projectId: string) => ["projects", projectId, "memory", "uncertainty"] as const,
  handovers: (projectId: string) => ["projects", projectId, "handovers"] as const,
  handover: (projectId: string, handoverId: string) =>
    ["projects", projectId, "handovers", handoverId] as const,
  handoverVersions: (projectId: string, handoverId: string) =>
    ["projects", projectId, "handovers", handoverId, "versions"] as const,
  audit: (projectId: string, params?: Record<string, unknown>) =>
    ["projects", projectId, "audit", params ?? {}] as const,

  githubStatus: ["github", "status"] as const,
  githubBoundary: ["github", "boundary"] as const,
  githubRepositories: ["github", "repositories"] as const,
  githubRepository: (fullName: string) => ["github", "repository", fullName] as const,

  // Phase 5 — readiness, successor experience, knowledge risk, evaluation.
  readiness: (projectId: string) => ["projects", projectId, "readiness"] as const,
  readinessHistory: (projectId: string, params?: Record<string, unknown>) =>
    ["projects", projectId, "readiness", "history", params ?? {}] as const,
  readinessEvaluation: (projectId: string, evaluationId: string) =>
    ["projects", projectId, "readiness", evaluationId] as const,
  successorWorkspace: (projectId: string) =>
    ["projects", projectId, "successor-workspace"] as const,
  successorTasks: (projectId: string, params?: Record<string, unknown>) =>
    ["projects", projectId, "successor-tasks", params ?? {}] as const,
  successorTask: (projectId: string, taskId: string) =>
    ["projects", projectId, "successor-tasks", taskId] as const,
  knowledgeDependencies: (projectId: string) =>
    ["projects", projectId, "knowledge-dependencies"] as const,
  knowledgeDependency: (projectId: string, dependencyId: string) =>
    ["projects", projectId, "knowledge-dependencies", dependencyId] as const,
  knowledgeGaps: (projectId: string, params?: Record<string, unknown>) =>
    ["projects", projectId, "knowledge-gaps", params ?? {}] as const,
  knowledgeGap: (projectId: string, gapId: string) =>
    ["projects", projectId, "knowledge-gaps", gapId] as const,
  scorecard: (projectId: string) => ["projects", projectId, "scorecard"] as const,
  successorExercise: (projectId: string) =>
    ["projects", projectId, "successor-exercise"] as const,
  evaluationRuns: (projectId: string, params?: Record<string, unknown>) =>
    ["projects", projectId, "evaluation", "runs", params ?? {}] as const,
  evaluationRun: (projectId: string, runId: string) =>
    ["projects", projectId, "evaluation", "runs", runId] as const,
  evaluationComparison: (projectId: string, base: string, candidate: string) =>
    ["projects", projectId, "evaluation", "compare", base, candidate] as const,
  systemHealth: (projectId: string) => ["projects", projectId, "system-health"] as const,
};
