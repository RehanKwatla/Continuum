/** Central TanStack Query key factory — keeps cache invalidation predictable. */

export const queryKeys = {
  readiness: ["readiness"] as const,
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

  githubStatus: ["github", "status"] as const,
  githubBoundary: ["github", "boundary"] as const,
  githubRepositories: ["github", "repositories"] as const,
  githubRepository: (fullName: string) => ["github", "repository", fullName] as const,
};
