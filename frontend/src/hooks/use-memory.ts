import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/contexts/AuthContext";
import { queryKeys } from "@/lib/query-keys";
import {
  approveHandover,
  archiveHandover,
  editClaim,
  generateHandover,
  getAuditTrail,
  getClaim,
  getConflict,
  getHandover,
  getProjectMemory,
  getReviewQueue,
  getUncertainty,
  listClaims,
  listConflicts,
  listHandoverVersions,
  listHandovers,
  listProcessingRuns,
  listQuestions,
  publishHandover,
  reconstructProject,
  resolveConflict,
  reviewClaim,
  submitHandover,
  updateHandover,
  verifyClaim,
} from "@/services/memory";
import type {
  ClaimDecisionInput,
  ClaimEditInput,
  ClaimListParams,
  ConflictListParams,
  ConflictResolutionInput,
  HandoverUpdateInput,
  ReconstructInput,
  ReviewQueueParams,
} from "@/types";

function useAuthed(enabled: boolean) {
  const { status } = useAuth();
  return status === "authenticated" && enabled;
}

export function useProjectMemory(projectId: string | undefined) {
  const enabled = useAuthed(Boolean(projectId));
  return useQuery({
    queryKey: queryKeys.memory(projectId ?? ""),
    queryFn: () => getProjectMemory(projectId as string),
    enabled,
  });
}

export function useProcessingRuns(
  projectId: string | undefined,
  params: { page?: number; page_size?: number } = {},
) {
  const enabled = useAuthed(Boolean(projectId));
  return useQuery({
    queryKey: queryKeys.processingRuns(projectId ?? "", params as Record<string, unknown>),
    queryFn: () => listProcessingRuns(projectId as string, params),
    enabled,
  });
}

export function useClaims(projectId: string | undefined, params: ClaimListParams = {}) {
  const enabled = useAuthed(Boolean(projectId));
  return useQuery({
    queryKey: queryKeys.claims(projectId ?? "", params as Record<string, unknown>),
    queryFn: () => listClaims(projectId as string, params),
    enabled,
    placeholderData: (previous) => previous,
  });
}

export function useClaim(projectId: string | undefined, claimId: string | undefined) {
  const enabled = useAuthed(Boolean(projectId) && Boolean(claimId));
  return useQuery({
    queryKey: queryKeys.claim(projectId ?? "", claimId ?? ""),
    queryFn: () => getClaim(projectId as string, claimId as string),
    enabled,
  });
}

/** §3 The human review queue. */
export function useReviewQueue(projectId: string | undefined, params: ReviewQueueParams = {}) {
  const enabled = useAuthed(Boolean(projectId));
  return useQuery({
    queryKey: queryKeys.reviewQueue(projectId ?? "", params as Record<string, unknown>),
    queryFn: () => getReviewQueue(projectId as string, params),
    enabled,
    placeholderData: (previous) => previous,
  });
}

export function useConflicts(projectId: string | undefined, params: ConflictListParams = {}) {
  const enabled = useAuthed(Boolean(projectId));
  return useQuery({
    queryKey: queryKeys.conflicts(projectId ?? "", params as Record<string, unknown>),
    queryFn: () => listConflicts(projectId as string, params),
    enabled,
  });
}

/** §6 One contradiction with the evidence behind both sides. */
export function useConflict(projectId: string | undefined, conflictId: string | undefined) {
  const enabled = useAuthed(Boolean(projectId) && Boolean(conflictId));
  return useQuery({
    queryKey: queryKeys.conflict(projectId ?? "", conflictId ?? ""),
    queryFn: () => getConflict(projectId as string, conflictId as string),
    enabled,
  });
}

export function useQuestions(
  projectId: string | undefined,
  params: { status?: "open" | "resolved"; page?: number; page_size?: number } = {},
) {
  const enabled = useAuthed(Boolean(projectId));
  return useQuery({
    queryKey: queryKeys.questions(projectId ?? "", params as Record<string, unknown>),
    queryFn: () => listQuestions(projectId as string, params),
    enabled,
  });
}

export function useUncertainty(projectId: string | undefined) {
  const enabled = useAuthed(Boolean(projectId));
  return useQuery({
    queryKey: queryKeys.uncertainty(projectId ?? ""),
    queryFn: () => getUncertainty(projectId as string),
    enabled,
  });
}

// ---------------------------------------------------------------------------
// §8–§13 Handover
// ---------------------------------------------------------------------------
export function useHandovers(projectId: string | undefined) {
  const enabled = useAuthed(Boolean(projectId));
  return useQuery({
    queryKey: queryKeys.handovers(projectId ?? ""),
    queryFn: () => listHandovers(projectId as string),
    enabled,
  });
}

export function useHandover(
  projectId: string | undefined,
  handoverId: string | undefined,
) {
  const enabled = useAuthed(Boolean(projectId) && Boolean(handoverId));
  return useQuery({
    queryKey: queryKeys.handover(projectId ?? "", handoverId ?? ""),
    queryFn: () => getHandover(projectId as string, handoverId as string),
    enabled,
  });
}

export function useHandoverVersions(
  projectId: string | undefined,
  handoverId: string | undefined,
) {
  const enabled = useAuthed(Boolean(projectId) && Boolean(handoverId));
  return useQuery({
    queryKey: queryKeys.handoverVersions(projectId ?? "", handoverId ?? ""),
    queryFn: () => listHandoverVersions(projectId as string, handoverId as string),
    enabled,
  });
}

// ---------------------------------------------------------------------------
// §15 Audit trail
// ---------------------------------------------------------------------------
export function useAuditTrail(
  projectId: string | undefined,
  params: { action?: string; page?: number; page_size?: number } = {},
) {
  const enabled = useAuthed(Boolean(projectId));
  return useQuery({
    queryKey: queryKeys.audit(projectId ?? "", params as Record<string, unknown>),
    queryFn: () => getAuditTrail(projectId as string, params),
    enabled,
    placeholderData: (previous) => previous,
  });
}

/** Invalidate every intelligence-layer cache for a project. */
function useIntelligenceInvalidator(projectId: string) {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: queryKeys.memory(projectId) });
    void client.invalidateQueries({ queryKey: ["projects", projectId, "memory"] });
    void client.invalidateQueries({ queryKey: ["projects", projectId, "handovers"] });
    void client.invalidateQueries({ queryKey: ["projects", projectId, "audit"] });
  };
}

export function useReconstructProject(projectId: string) {
  const invalidate = useIntelligenceInvalidator(projectId);
  return useMutation({
    mutationFn: (input: ReconstructInput = {}) => reconstructProject(projectId, input),
    onSuccess: invalidate,
  });
}

export function useVerifyClaim(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (claimId: string) => verifyClaim(projectId, claimId),
    onSuccess: (claim) => {
      void client.invalidateQueries({ queryKey: queryKeys.claim(projectId, claim.id) });
      void client.invalidateQueries({ queryKey: ["projects", projectId, "memory"] });
    },
  });
}

/** §4, §7 Record a human decision. The server owns the approval rules. */
export function useReviewClaim(projectId: string) {
  const client = useQueryClient();
  const invalidate = useIntelligenceInvalidator(projectId);
  return useMutation({
    mutationFn: ({ claimId, input }: { claimId: string; input: ClaimDecisionInput }) =>
      reviewClaim(projectId, claimId, input),
    onSuccess: (claim) => {
      void client.invalidateQueries({ queryKey: queryKeys.claim(projectId, claim.id) });
      void invalidate();
    },
  });
}

/** §4 A reviewer's correction, stored as a new revision that needs re-verification. */
export function useEditClaim(projectId: string) {
  const client = useQueryClient();
  const invalidate = useIntelligenceInvalidator(projectId);
  return useMutation({
    mutationFn: ({ claimId, input }: { claimId: string; input: ClaimEditInput }) =>
      editClaim(projectId, claimId, input),
    onSuccess: (claim) => {
      void client.invalidateQueries({ queryKey: queryKeys.claim(projectId, claim.id) });
      void invalidate();
    },
  });
}

/** §6 Record a conflict decision. */
export function useResolveConflict(projectId: string) {
  const client = useQueryClient();
  const invalidate = useIntelligenceInvalidator(projectId);
  return useMutation({
    mutationFn: ({
      conflictId,
      input,
    }: {
      conflictId: string;
      input: ConflictResolutionInput;
    }) => resolveConflict(projectId, conflictId, input),
    onSuccess: (conflict) => {
      void client.invalidateQueries({
        queryKey: queryKeys.conflict(projectId, conflict.id),
      });
      void invalidate();
    },
  });
}

/** §8 Generate a new draft handover from the project's approved claims. */
export function useGenerateHandover(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (title?: string) => generateHandover(projectId, title),
    onSuccess: (handover) => {
      void client.invalidateQueries({ queryKey: queryKeys.handovers(projectId) });
      void client.invalidateQueries({ queryKey: queryKeys.handover(projectId, handover.id) });
      void client.invalidateQueries({ queryKey: queryKeys.audit(projectId, {}) });
    },
  });
}

/** §11 Save a reviewer edit; the server writes a new immutable version. */
export function useUpdateHandover(projectId: string, handoverId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: HandoverUpdateInput) =>
      updateHandover(projectId, handoverId, input),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.handover(projectId, handoverId) });
      void client.invalidateQueries({ queryKey: queryKeys.handoverVersions(projectId, handoverId) });
      void client.invalidateQueries({ queryKey: ["projects", projectId, "handovers"] });
    },
  });
}

/** §12 Lifecycle transitions. Each one records an audit entry. */
export function useHandoverLifecycle(projectId: string, handoverId: string) {
  const client = useQueryClient();
  const refresh = () => {
    void client.invalidateQueries({ queryKey: queryKeys.handover(projectId, handoverId) });
    void client.invalidateQueries({ queryKey: queryKeys.handoverVersions(projectId, handoverId) });
    void client.invalidateQueries({ queryKey: ["projects", projectId, "handovers"] });
    void client.invalidateQueries({ queryKey: ["projects", projectId, "audit"] });
  };
  const submit = useMutation({
    mutationFn: () => submitHandover(projectId, handoverId),
    onSuccess: refresh,
  });
  const approve = useMutation({
    mutationFn: (note?: string) => approveHandover(projectId, handoverId, note),
    onSuccess: refresh,
  });
  const publish = useMutation({
    mutationFn: (note?: string) => publishHandover(projectId, handoverId, note),
    onSuccess: refresh,
  });
  const archive = useMutation({
    mutationFn: () => archiveHandover(projectId, handoverId),
    onSuccess: refresh,
  });
  return { submit, approve, publish, archive };
}
