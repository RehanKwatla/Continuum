import { apiGet, apiPost } from "@/services/api";
import type { Workspace, WorkspaceCreateInput, WorkspaceSummary } from "@/types";

export function listWorkspaces(): Promise<WorkspaceSummary[]> {
  return apiGet<WorkspaceSummary[]>("/workspaces");
}

export function getWorkspace(workspaceId: string): Promise<Workspace> {
  return apiGet<Workspace>(`/workspaces/${workspaceId}`);
}

export function createWorkspace(payload: WorkspaceCreateInput): Promise<Workspace> {
  return apiPost<Workspace>("/workspaces", payload);
}
