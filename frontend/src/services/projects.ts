import { apiDelete, apiGet, apiPatch, apiPost } from "@/services/api";
import type {
  Page,
  Project,
  ProjectCreateInput,
  ProjectListParams,
  ProjectSummary,
  ProjectUpdateInput,
} from "@/types";

export function listProjects(params: ProjectListParams = {}): Promise<Page<ProjectSummary>> {
  return apiGet<Page<ProjectSummary>>("/projects", { params });
}

export function getProject(projectId: string): Promise<Project> {
  return apiGet<Project>(`/projects/${projectId}`);
}

export function createProject(payload: ProjectCreateInput): Promise<Project> {
  return apiPost<Project>("/projects", payload);
}

export function updateProject(projectId: string, payload: ProjectUpdateInput): Promise<Project> {
  return apiPatch<Project>(`/projects/${projectId}`, payload);
}

export function deleteProject(projectId: string): Promise<null> {
  return apiDelete<null>(`/projects/${projectId}`);
}
