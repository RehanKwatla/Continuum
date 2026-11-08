import type { WorkspaceRole } from "@/types";

const RANK: Record<WorkspaceRole, number> = {
  viewer: 1,
  member: 2,
  admin: 3,
  owner: 4,
};

/** True when `role` is at least `required`. The server is the real authority. */
export function hasAtLeast(role: WorkspaceRole | null | undefined, required: WorkspaceRole): boolean {
  if (!role) return false;
  return RANK[role] >= RANK[required];
}
