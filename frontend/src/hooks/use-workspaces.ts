import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { queryKeys } from "@/lib/query-keys";
import { useAuth } from "@/contexts/AuthContext";
import { createWorkspace, getWorkspace, listWorkspaces } from "@/services/workspaces";
import type { WorkspaceCreateInput } from "@/types";

export function useWorkspaces() {
  const { status } = useAuth();
  return useQuery({
    queryKey: queryKeys.workspaces,
    queryFn: listWorkspaces,
    enabled: status === "authenticated",
  });
}

export function useWorkspace(workspaceId: string | undefined) {
  const { status } = useAuth();
  return useQuery({
    queryKey: queryKeys.workspace(workspaceId ?? ""),
    queryFn: () => getWorkspace(workspaceId as string),
    enabled: status === "authenticated" && Boolean(workspaceId),
  });
}

export function useCreateWorkspace() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: WorkspaceCreateInput) => createWorkspace(payload),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.workspaces });
      void client.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}
