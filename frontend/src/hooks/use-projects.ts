import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { queryKeys } from "@/lib/query-keys";
import { useAuth } from "@/contexts/AuthContext";
import {
  createProject,
  deleteProject,
  getProject,
  listProjects,
  updateProject,
} from "@/services/projects";
import type {
  ProjectCreateInput,
  ProjectListParams,
  ProjectUpdateInput,
} from "@/types";

export function useProjects(params: ProjectListParams = {}) {
  const { status } = useAuth();
  return useQuery({
    queryKey: queryKeys.projects(params as Record<string, unknown>),
    queryFn: () => listProjects(params),
    enabled: status === "authenticated",
  });
}

export function useProject(projectId: string | undefined) {
  const { status } = useAuth();
  return useQuery({
    queryKey: queryKeys.project(projectId ?? ""),
    queryFn: () => getProject(projectId as string),
    enabled: status === "authenticated" && Boolean(projectId),
  });
}

export function useCreateProject() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: ProjectCreateInput) => createProject(payload),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["projects"] });
      void client.invalidateQueries({ queryKey: queryKeys.dashboard });
      void client.invalidateQueries({ queryKey: queryKeys.workspaces });
    },
  });
}

export function useUpdateProject(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: ProjectUpdateInput) => updateProject(projectId, payload),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["projects"] });
      void client.invalidateQueries({ queryKey: queryKeys.project(projectId) });
      void client.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}

export function useDeleteProject() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string) => deleteProject(projectId),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["projects"] });
      void client.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}
