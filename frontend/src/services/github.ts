import { apiDelete, apiGet, apiPost } from "@/services/api";
import type {
  GitHubBoundary,
  GitHubConnectResponse,
  GitHubImportInput,
  GitHubImportResponse,
  GitHubRepositoryDetail,
  GitHubRepositoryListResponse,
  GitHubStatus,
} from "@/types";

export function getGitHubStatus(): Promise<GitHubStatus> {
  return apiGet<GitHubStatus>("/github/status");
}

/** Explicit, clearly labelled integration boundary when GitHub is not set up. */
export function getGitHubBoundary(): Promise<GitHubBoundary> {
  return apiGet<GitHubBoundary>("/github/boundary");
}

export function startGitHubConnect(): Promise<GitHubConnectResponse> {
  return apiPost<GitHubConnectResponse>("/github/connect");
}

export function disconnectGitHub(): Promise<null> {
  return apiDelete<null>("/github/disconnect");
}

export function listGitHubRepositories(limit = 100): Promise<GitHubRepositoryListResponse> {
  return apiGet<GitHubRepositoryListResponse>("/github/repositories", { params: { limit } });
}

export function getGitHubRepository(fullName: string): Promise<GitHubRepositoryDetail> {
  return apiGet<GitHubRepositoryDetail>("/github/repository", { params: { full_name: fullName } });
}

export function importGitHubRepository(
  projectId: string,
  payload: GitHubImportInput,
): Promise<GitHubImportResponse> {
  return apiPost<GitHubImportResponse>(`/projects/${projectId}/github/import`, payload);
}
