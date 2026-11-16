import { useQuery } from "@tanstack/react-query";

import { queryKeys } from "@/lib/query-keys";
import { getDashboard, getHealth, getRepositoryActivity, getRootIndex } from "@/services/dashboard";
import { fetchReadiness } from "@/services/auth";
import { useAuth } from "@/contexts/AuthContext";

export function useDashboard() {
  const { status } = useAuth();
  return useQuery({
    queryKey: queryKeys.dashboard,
    queryFn: getDashboard,
    enabled: status === "authenticated",
  });
}

export function useRepositoryActivity() {
  const { status } = useAuth();
  return useQuery({
    queryKey: ["dashboard", "repository-activity"],
    queryFn: getRepositoryActivity,
    enabled: status === "authenticated",
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
    retry: false,
  });
}

export function useHealth() {
  return useQuery({ queryKey: queryKeys.health, queryFn: getHealth, retry: 1 });
}

export function useReadiness() {
  return useQuery({
    queryKey: queryKeys.serviceReadiness,
    queryFn: fetchReadiness,
    retry: 1,
    staleTime: 30_000,
  });
}

export function useRootIndex() {
  return useQuery({ queryKey: ["root-index"], queryFn: getRootIndex, retry: 1 });
}
