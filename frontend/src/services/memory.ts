import { apiGet, apiPost } from "@/services/api";
import type {
  ClaimDetail,
  ClaimListParams,
  ClaimListResponse,
  ClaimReviewInput,
  ConflictListParams,
  ConflictListResponse,
  ConflictResolveInput,
  ConflictSummary,
  HandoverRead,
  OpenQuestionListResponse,
  ProcessingRun,
  ProcessingRunListResponse,
  ProjectMemory,
  ReconstructInput,
  UncertaintyResponse,
} from "@/types";

/** Trigger a reconstruction run. The server still applies the access filter. */
export function reconstructProject(
  projectId: string,
  input: ReconstructInput = {},
): Promise<ProcessingRun> {
  return apiPost<ProcessingRun>(`/projects/${projectId}/memory/reconstruct`, input);
}

export function getProjectMemory(projectId: string): Promise<ProjectMemory> {
  return apiGet<ProjectMemory>(`/projects/${projectId}/memory`);
}

export function listProcessingRuns(
  projectId: string,
  params: { page?: number; page_size?: number } = {},
): Promise<ProcessingRunListResponse> {
  return apiGet<ProcessingRunListResponse>(`/projects/${projectId}/processing-runs`, { params });
}

export function listClaims(
  projectId: string,
  params: ClaimListParams = {},
): Promise<ClaimListResponse> {
  return apiGet<ClaimListResponse>(`/projects/${projectId}/claims`, { params });
}

export function getClaim(projectId: string, claimId: string): Promise<ClaimDetail> {
  return apiGet<ClaimDetail>(`/projects/${projectId}/claims/${claimId}`);
}

/** Re-run the Verifier for a claim. Never approves a claim. */
export function verifyClaim(projectId: string, claimId: string): Promise<ClaimDetail> {
  return apiPost<ClaimDetail>(`/projects/${projectId}/claims/${claimId}/verify`);
}

/** Human review (admin only). Only `approve` may produce a Verified claim. */
export function reviewClaim(
  projectId: string,
  claimId: string,
  input: ClaimReviewInput,
): Promise<ClaimDetail> {
  return apiPost<ClaimDetail>(`/projects/${projectId}/claims/${claimId}/review`, input);
}

export function listConflicts(
  projectId: string,
  params: ConflictListParams = {},
): Promise<ConflictListResponse> {
  return apiGet<ConflictListResponse>(`/projects/${projectId}/conflicts`, { params });
}

export function resolveConflict(
  projectId: string,
  conflictId: string,
  input: ConflictResolveInput,
): Promise<ConflictSummary> {
  return apiPost<ConflictSummary>(
    `/projects/${projectId}/conflicts/${conflictId}/resolve`,
    input,
  );
}

export function listQuestions(
  projectId: string,
  params: { status?: "open" | "resolved"; page?: number; page_size?: number } = {},
): Promise<OpenQuestionListResponse> {
  return apiGet<OpenQuestionListResponse>(`/projects/${projectId}/questions`, { params });
}

export function getUncertainty(projectId: string): Promise<UncertaintyResponse> {
  return apiGet<UncertaintyResponse>(`/projects/${projectId}/uncertainty`);
}

export function generateHandover(projectId: string): Promise<HandoverRead> {
  return apiPost<HandoverRead>(`/projects/${projectId}/handover/generate`);
}

export function getHandover(projectId: string): Promise<HandoverRead> {
  return apiGet<HandoverRead>(`/projects/${projectId}/handover`);
}
