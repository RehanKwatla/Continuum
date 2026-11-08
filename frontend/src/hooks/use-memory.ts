import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/contexts/AuthContext";
import { queryKeys } from "@/lib/query-keys";
import {
  generateHandover,
  getClaim,
  getHandover,
  getProjectMemory,
  getUncertainty,
  listClaims,
  listConflicts,
  listProcessingRuns,
  listQuestions,
  reconstructProject,
  resolveConflict,
  reviewClaim,
  verifyClaim,
} from "@/services/memory";
import type {
  ClaimListParams,
  ClaimReviewInput,
  ConflictListParams,
  ConflictResolveInput,
  ReconstructInput,
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

export function useConflicts(projectId: string | undefined, params: ConflictListParams = {}) {
  const enabled = useAuthed(Boolean(projectId));
  return useQuery({
    queryKey: queryKeys.conflicts(projectId ?? "", params as Record<string, unknown>),
    queryFn: () => listConflicts(projectId as string, params),
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

export function useHandover(projectId: string | undefined) {
  const enabled = useAuthed(Boolean(projectId));
  return useQuery({
    queryKey: queryKeys.handover(projectId ?? ""),
    queryFn: () => getHandover(projectId as string),
    enabled,
    // A project with no handover yet returns 404 — that is a valid empty state.
    retry: false,
  });
}

/** Invalidate every intelligence-layer cache for a project. */
function useIntelligenceInvalidator(projectId: string) {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: queryKeys.memory(projectId) });
    void client.invalidateQueries({ queryKey: ["projects", projectId, "memory"] });
    void client.invalidateQueries({ queryKey: queryKeys.handover(projectId) });
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

export function useReviewClaim(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ claimId, input }: { claimId: string; input: ClaimReviewInput }) =>
      reviewClaim(projectId, claimId, input),
    onSuccess: (claim) => {
      void client.invalidateQueries({ queryKey: queryKeys.claim(projectId, claim.id) });
      void client.invalidateQueries({ queryKey: ["projects", projectId, "memory"] });
    },
  });
}

export function useResolveConflict(projectId: string) {
  const invalidate = useIntelligenceInvalidator(projectId);
  return useMutation({
    mutationFn: ({ conflictId, input }: { conflictId: string; input: ConflictResolveInput }) =>
      resolveConflict(projectId, conflictId, input),
    onSuccess: invalidate,
  });
}

export function useGenerateHandover(projectId: string) {
  const invalidate = useIntelligenceInvalidator(projectId);
  return useMutation({
    mutationFn: () => generateHandover(projectId),
    onSuccess: invalidate,
  });
}
