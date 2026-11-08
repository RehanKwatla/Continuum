import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { queryKeys } from "@/lib/query-keys";
import { useAuth } from "@/contexts/AuthContext";
import { deleteSource, getSource, listSources, uploadSources } from "@/services/sources";
import type { SourceListParams } from "@/types";

export function useSources(projectId: string | undefined, params: SourceListParams = {}) {
  const { status } = useAuth();
  return useQuery({
    queryKey: queryKeys.sources(projectId ?? "", params as Record<string, unknown>),
    queryFn: () => listSources(projectId as string, params),
    enabled: status === "authenticated" && Boolean(projectId),
  });
}

export function useSource(sourceId: string | undefined) {
  const { status } = useAuth();
  return useQuery({
    queryKey: queryKeys.source(sourceId ?? ""),
    queryFn: () => getSource(sourceId as string),
    enabled: status === "authenticated" && Boolean(sourceId),
  });
}

export function useUploadSources(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      files,
      onProgress,
    }: {
      files: File[];
      onProgress?: (percent: number) => void;
    }) => uploadSources(projectId, files, onProgress),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["projects", projectId, "sources"] });
      void client.invalidateQueries({ queryKey: queryKeys.project(projectId) });
      void client.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export function useDeleteSource(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (sourceId: string) => deleteSource(sourceId),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["projects", projectId, "sources"] });
      void client.invalidateQueries({ queryKey: queryKeys.project(projectId) });
      void client.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}
