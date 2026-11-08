import { api, apiGet, apiPatch, apiPost } from "@/services/api";
import type {
  AuditTrailResponse,
  ClaimDecisionInput,
  ClaimDetail,
  ClaimEditInput,
  ClaimListParams,
  ClaimListResponse,
  ConflictDetail,
  ConflictListParams,
  ConflictListResponse,
  ConflictResolutionInput,
  Handover,
  HandoverListResponse,
  HandoverUpdateInput,
  HandoverVersion,
  OpenQuestionListResponse,
  ProcessingRun,
  ProcessingRunListResponse,
  ProjectMemory,
  ReconstructInput,
  ReviewQueueParams,
  ReviewQueueResponse,
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

// ---------------------------------------------------------------------------
// §3 Human review queue
// ---------------------------------------------------------------------------
export function getReviewQueue(
  projectId: string,
  params: ReviewQueueParams = {},
): Promise<ReviewQueueResponse> {
  return apiGet<ReviewQueueResponse>(`/projects/${projectId}/review-queue`, { params });
}

// ---------------------------------------------------------------------------
// §4, §7 Human approval engine (admin only on the server)
// ---------------------------------------------------------------------------
/** Record one human decision; `approve` is the only path to an approved claim. */
export function reviewClaim(
  projectId: string,
  claimId: string,
  input: ClaimDecisionInput,
): Promise<ClaimDetail> {
  if (input.action === "approve") {
    return apiPost<ClaimDetail>(`/projects/${projectId}/claims/${claimId}/approve`, {
      explanation: input.explanation ?? null,
      request_evidence: input.request_evidence ?? false,
    });
  }
  if (input.action === "reject") {
    return apiPost<ClaimDetail>(`/projects/${projectId}/claims/${claimId}/reject`, {
      explanation: input.explanation ?? null,
      request_evidence: false,
    });
  }
  return apiPost<ClaimDetail>(`/projects/${projectId}/claims/${claimId}/request-clarification`, {
    explanation: input.explanation ?? null,
    request_evidence: input.request_evidence ?? false,
  });
}

/** Correct a claim's statement; the server stores a new revision to re-verify. */
export function editClaim(
  projectId: string,
  claimId: string,
  input: ClaimEditInput,
): Promise<ClaimDetail> {
  return apiPost<ClaimDetail>(`/projects/${projectId}/claims/${claimId}/edit`, input);
}

// ---------------------------------------------------------------------------
// §6 Conflict Resolution Centre
// ---------------------------------------------------------------------------
export function listConflicts(
  projectId: string,
  params: ConflictListParams = {},
): Promise<ConflictListResponse> {
  return apiGet<ConflictListResponse>(`/projects/${projectId}/conflicts`, { params });
}

export function getConflict(projectId: string, conflictId: string): Promise<ConflictDetail> {
  return apiGet<ConflictDetail>(`/projects/${projectId}/conflicts/${conflictId}`);
}

export function resolveConflict(
  projectId: string,
  conflictId: string,
  input: ConflictResolutionInput,
): Promise<ConflictDetail> {
  return apiPost<ConflictDetail>(
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

// ---------------------------------------------------------------------------
// §8–§13 Versioned handover
// ---------------------------------------------------------------------------
/** Generate a fresh draft from the project's approved claims. */
export function generateHandover(projectId: string, title?: string): Promise<Handover> {
  return apiPost<Handover>(`/projects/${projectId}/handovers/generate`, {
    title: title ?? null,
  });
}

export function listHandovers(projectId: string): Promise<HandoverListResponse> {
  return apiGet<HandoverListResponse>(`/projects/${projectId}/handovers`);
}

export function getHandover(projectId: string, handoverId: string): Promise<Handover> {
  return apiGet<Handover>(`/projects/${projectId}/handovers/${handoverId}`);
}

export function listHandoverVersions(
  projectId: string,
  handoverId: string,
): Promise<HandoverVersion[]> {
  return apiGet<HandoverVersion[]>(
    `/projects/${projectId}/handovers/${handoverId}/versions`,
  );
}

export function getHandoverVersion(
  projectId: string,
  handoverId: string,
  versionNumber: number,
): Promise<HandoverVersion> {
  return apiGet<HandoverVersion>(
    `/projects/${projectId}/handovers/${handoverId}/versions/${versionNumber}`,
  );
}

/** Save a reviewer edit; the server always writes a new version. */
export function updateHandover(
  projectId: string,
  handoverId: string,
  input: HandoverUpdateInput,
): Promise<HandoverVersion> {
  return apiPatch<HandoverVersion>(`/projects/${projectId}/handovers/${handoverId}`, input);
}

export function submitHandover(projectId: string, handoverId: string): Promise<HandoverVersion> {
  return apiPost<HandoverVersion>(
    `/projects/${projectId}/handovers/${handoverId}/submit`,
    {},
  );
}

export function approveHandover(
  projectId: string,
  handoverId: string,
  note?: string,
): Promise<HandoverVersion> {
  return apiPost<HandoverVersion>(`/projects/${projectId}/handovers/${handoverId}/approve`, {
    note: note ?? null,
  });
}

export function publishHandover(
  projectId: string,
  handoverId: string,
  note?: string,
): Promise<HandoverVersion> {
  return apiPost<HandoverVersion>(`/projects/${projectId}/handovers/${handoverId}/publish`, {
    note: note ?? null,
  });
}

export function archiveHandover(projectId: string, handoverId: string): Promise<Handover> {
  return apiPost<Handover>(`/projects/${projectId}/handovers/${handoverId}/archive`, {});
}

// ---------------------------------------------------------------------------
// §14 Export (permission is re-checked server-side on every download)
// ---------------------------------------------------------------------------
export type HandoverExportFormat = "md" | "pdf";

/**
 * Download an export through the authenticated client. The bearer token is
 * attached by the shared interceptor, so the file is as protected as the API.
 */
export async function downloadHandover(
  projectId: string,
  handoverId: string,
  format: HandoverExportFormat,
  filename: string,
  versionNumber?: number,
): Promise<void> {
  const response = await api.get(
    `/projects/${projectId}/handovers/${handoverId}/export.${format}`,
    {
      params: versionNumber ? { version: versionNumber } : undefined,
      responseType: "blob",
    },
  );
  const url = URL.createObjectURL(response.data as Blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// §15 Audit trail
// ---------------------------------------------------------------------------
export function getAuditTrail(
  projectId: string,
  params: { action?: string; page?: number; page_size?: number } = {},
): Promise<AuditTrailResponse> {
  return apiGet<AuditTrailResponse>(`/projects/${projectId}/audit`, { params });
}
