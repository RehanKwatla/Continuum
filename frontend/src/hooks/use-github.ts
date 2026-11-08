import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { queryKeys } from "@/lib/query-keys";
import { useAuth } from "@/contexts/AuthContext";
import {
  disconnectGitHub,
  getGitHubBoundary,
  getGitHubRepository,
  getGitHubStatus,
  importGitHubRepository,
  listGitHubRepositories,
  startGitHubConnect,
} from "@/services/github";
import type { GitHubImportInput } from "@/types";

export function useGitHubStatus() {
  const { status } = useAuth();
  return useQuery({
    queryKey: queryKeys.githubStatus,
    queryFn: getGitHubStatus,
    enabled: status === "authenticated",
  });
}

export function useGitHubBoundary() {
  return useQuery({
    queryKey: queryKeys.githubBoundary,
    queryFn: getGitHubBoundary,
    retry: 1,
  });
}

export function useGitHubRepositories(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.githubRepositories,
    queryFn: () => listGitHubRepositories(100),
    enabled,
    retry: 1,
  });
}

export function useGitHubRepository(fullName: string | null) {
  return useQuery({
    queryKey: queryKeys.githubRepository(fullName ?? ""),
    queryFn: () => getGitHubRepository(fullName as string),
    enabled: Boolean(fullName),
    retry: 1,
  });
}

export function useStartGitHubConnect() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: startGitHubConnect,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.githubStatus });
    },
  });
}

export function useDisconnectGitHub() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: disconnectGitHub,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["github"] });
    },
  });
}

export function useImportGitHubRepository(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: GitHubImportInput) => importGitHubRepository(projectId, payload),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["projects", projectId, "sources"] });
      void client.invalidateQueries({ queryKey: queryKeys.project(projectId) });
      void client.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
}
