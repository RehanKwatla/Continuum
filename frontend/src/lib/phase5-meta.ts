/**
 * Presentation metadata for the Phase 5 layer.
 *
 * These maps only choose a label and a colour tone — they never invent a value.
 * Every number they decorate comes from the deterministic backend engines.
 */

import type {
  DependencyRiskStatus,
  KnowledgeGapStatus,
  ReadinessBand,
  RequirementCompletion,
  RequirementCriticality,
  SuccessorTaskOrigin,
  SuccessorTaskPriority,
  SuccessorTaskStatus,
  WorkspaceClaimItem,
  WorkspaceTaskItem,
} from "@/types";

export type Tone = "ok" | "warn" | "danger" | "info" | "secondary" | "default";

/** §3 Presentation bands. Labels mirror the backend band labels. */
export const BAND_META: Record<ReadinessBand, { label: string; tone: Tone; hint: string }> = {
  strong: {
    label: "Strong handover readiness",
    tone: "ok",
    hint: "90–100. The approved knowledge covers the requirements with few gaps.",
  },
  mostly_ready: {
    label: "Mostly ready, some gaps",
    tone: "info",
    hint: "75–89. Usable, but some requirements are only partly covered.",
  },
  needs_review: {
    label: "Needs additional review",
    tone: "warn",
    hint: "50–74. Material gaps remain before the handover is dependable.",
  },
  not_ready: {
    label: "Not ready",
    tone: "danger",
    hint: "0–49. Critical knowledge is missing or unsupported.",
  },
};

export const COMPLETION_META: Record<RequirementCompletion, { label: string; tone: Tone }> = {
  Complete: { label: "Complete", tone: "ok" },
  Partial: { label: "Partial", tone: "warn" },
  Uncertain: { label: "Uncertain", tone: "info" },
  Missing: { label: "Missing", tone: "danger" },
  Blocked: { label: "Blocked", tone: "danger" },
};

export const CRITICALITY_META: Record<RequirementCriticality, { label: string; tone: Tone }> = {
  critical: { label: "Critical", tone: "danger" },
  important: { label: "Important", tone: "warn" },
  optional: { label: "Optional", tone: "secondary" },
};

export const TASK_PRIORITY_META: Record<SuccessorTaskPriority, { label: string; tone: Tone }> = {
  High: { label: "High", tone: "danger" },
  Medium: { label: "Medium", tone: "warn" },
  Low: { label: "Low", tone: "secondary" },
};

export const TASK_STATUS_META: Record<SuccessorTaskStatus, { label: string; tone: Tone }> = {
  "Not Started": { label: "Not started", tone: "secondary" },
  "In Progress": { label: "In progress", tone: "info" },
  Blocked: { label: "Blocked", tone: "danger" },
  Completed: { label: "Completed", tone: "ok" },
};

export const TASK_ORIGIN_META: Record<SuccessorTaskOrigin, { label: string; tone: Tone; hint: string }> =
  {
    derived: {
      label: "From approved knowledge",
      tone: "ok",
      hint: "Derived directly from an approved claim — an established obligation.",
    },
    suggested: {
      label: "Suggested action",
      tone: "info",
      hint: "An AI/system recommendation, not an established obligation.",
    },
    manual: {
      label: "Added by the successor",
      tone: "secondary",
      hint: "Authored by a person in the successor workspace.",
    },
  };

export const RISK_STATUS_META: Record<DependencyRiskStatus, { label: string; tone: Tone }> = {
  Low: { label: "Low", tone: "ok" },
  Moderate: { label: "Moderate", tone: "warn" },
  High: { label: "High", tone: "danger" },
  Unknown: { label: "Unknown", tone: "secondary" },
};

export const GAP_STATUS_META: Record<KnowledgeGapStatus, { label: string; tone: Tone }> = {
  Open: { label: "Open", tone: "danger" },
  "In Progress": { label: "In progress", tone: "info" },
  Resolved: { label: "Resolved", tone: "ok" },
  "Accepted Risk": { label: "Accepted risk", tone: "warn" },
};

/** Narrow a workspace section item to its claim-backed shape (§4 sections A–I). */
export function isWorkspaceClaimItem(
  item: WorkspaceClaimItem | WorkspaceTaskItem,
): item is WorkspaceClaimItem {
  return (item as WorkspaceClaimItem).claim_id !== undefined;
}

/** The tone for a 0–100 readiness score, using the documented bands. */
export function scoreTone(score: number | null | undefined): Tone {
  if (score === null || score === undefined) return "secondary";
  if (score >= 90) return "ok";
  if (score >= 75) return "info";
  if (score >= 50) return "warn";
  return "danger";
}
