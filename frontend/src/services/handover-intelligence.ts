import { apiGet, apiPost } from "@/services/api";

export type SuccessorHandover = {
  role: string;
  snapshot_id: string;
  snapshot_commit: string | null;
  snapshot_branch: string;
  source_coverage: {
    files_processed: number;
    files_discovered: number;
    has_code_analysis: boolean;
    has_history_analysis: boolean;
    has_knowledge_analysis: boolean;
    knowledge_unit_count: number;
  };
  sections: Array<{ key: string; title: string; items: Array<{ title?: string; text?: string; content?: string; evidence_level?: string; evidence?: Array<{ label?: string; file_path?: string; url?: string }> }> }>;
  tasks: Array<{ id: string; title: string; description: string; category: string; priority: string; status: string; evidence: Array<{ label?: string; url?: string }> }>;
  readiness: { status: string; dimensions: Array<{ dimension: string; status: string; explanation: string }>; blockers: Array<{ title: string; description: string }> };
  onboarding: Array<{ phase: string; title: string; objective: string; status: string; completion_criteria: string }>;
  limitations: string[];
};

export type SavedSuccessorHandover = { id: string; role: string; version: number; status: string; snapshot_id: string };
export type SuccessorVerification = { id: string; activity_type: string; status: string; result: string; verified_at: string | null };

export function getSuccessorHandover(projectId: string, role: string): Promise<SuccessorHandover> {
  return apiGet<SuccessorHandover>(`/projects/${projectId}/handover-intelligence`, { params: { role } });
}

export function createSuccessorHandover(projectId: string, role: string): Promise<SavedSuccessorHandover> {
  return apiPost<SavedSuccessorHandover>(`/projects/${projectId}/handover-intelligence`, undefined, { params: { role } });
}

export function transitionSuccessorHandover(projectId: string, packageId: string, action: "submit" | "approve"): Promise<SavedSuccessorHandover> {
  return apiPost<SavedSuccessorHandover>(`/projects/${projectId}/handover-intelligence/versions/${packageId}/${action}`, {});
}

export function getSuccessorVerification(projectId: string, packageId: string): Promise<SuccessorVerification[]> {
  return apiGet<SuccessorVerification[]>(`/projects/${projectId}/handover-intelligence/versions/${packageId}/verification`);
}

export function recordSuccessorVerification(projectId: string, packageId: string, activityType: string, result: string): Promise<SuccessorVerification> {
  return apiPost<SuccessorVerification>(`/projects/${projectId}/handover-intelligence/versions/${packageId}/verification`, {
    activity_type: activityType, status: "verified", result, evidence: [], user_confirmed: true,
  });
}

export async function downloadSuccessorHandoverPdf(projectId: string, packageId: string): Promise<void> {
  const response = await apiGet<Blob>(`/projects/${projectId}/handover-intelligence/versions/${packageId}/export.pdf`, { responseType: "blob" });
  const url = URL.createObjectURL(response);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `successor-handover-${packageId}.pdf`;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function downloadSuccessorHandover(projectId: string, role: string): Promise<void> {
  const response = await apiGet<Blob>(`/projects/${projectId}/handover-intelligence/export.md`, {
    params: { role },
    responseType: "blob",
  });
  const url = URL.createObjectURL(response);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `successor-handover-${role}.md`;
  anchor.click();
  URL.revokeObjectURL(url);
}
