import { apiGet } from "@/services/api";
import { env } from "@/lib/env";
import type { DashboardStats, HealthResponse } from "@/types";

export function getDashboard(): Promise<DashboardStats> {
  return apiGet<DashboardStats>("/dashboard");
}

export function getHealth(): Promise<HealthResponse> {
  return apiGet<HealthResponse>("/health");
}

export interface RootIndex {
  service: string;
  version: string;
  docs: string;
  api: string;
  tagline: string;
}

/**
 * The unversioned root document. ``VITE_API_BASE_URL`` already carries the
 * ``/api/v1`` prefix, so strip it and request ``/`` directly.
 */
export function getRootIndex(): Promise<RootIndex> {
  const root = env.apiBaseUrl.replace(/\/api\/v\d+\/?$/, "") || env.apiBaseUrl;
  return apiGet<RootIndex>("/", { baseURL: root });
}
