import {
  Activity,
  BookOpen,
  CircleDashed,
  Contact,
  Gavel,
  GitFork,
  HelpCircle,
  KeyRound,
  ListChecks,
  Lock,
  Network,
  Tag,
  TriangleAlert,
  UserCheck,
  Workflow,
  type LucideIcon,
} from "lucide-react";

import type {
  ClaimStatus,
  ClaimType,
  ConflictKind,
  ConflictStatus,
  FreshnessStatus,
  ProcessingRunStatus,
  VerificationVerdict,
} from "@/types";

type Tone = "ok" | "warn" | "danger" | "info" | "secondary" | "default";

/** Presentation metadata for the ten extractable claim categories + retained values. */
export const CLAIM_TYPE_META: Record<ClaimType, { label: string; Icon: LucideIcon }> = {
  decision: { label: "Decision", Icon: Gavel },
  responsibility: { label: "Responsibility", Icon: UserCheck },
  ownership: { label: "Ownership", Icon: KeyRound },
  task: { label: "Task", Icon: ListChecks },
  unfinished_work: { label: "Unfinished work", Icon: CircleDashed },
  risk: { label: "Risk", Icon: TriangleAlert },
  dependency: { label: "Dependency", Icon: GitFork },
  technical_constraint: { label: "Technical constraint", Icon: Lock },
  operational_procedure: { label: "Operational procedure", Icon: BookOpen },
  open_question: { label: "Open question", Icon: HelpCircle },
  architecture: { label: "Architecture", Icon: Network },
  process: { label: "Process", Icon: Workflow },
  constraint: { label: "Constraint", Icon: Lock },
  contact: { label: "Contact", Icon: Contact },
  status: { label: "Status", Icon: Activity },
  other: { label: "Other", Icon: Tag },
};

/** The ten categories the Extractor targets, in display order. */
export const CLAIM_TYPE_ORDER: ClaimType[] = [
  "decision",
  "responsibility",
  "ownership",
  "task",
  "unfinished_work",
  "risk",
  "dependency",
  "technical_constraint",
  "operational_procedure",
  "open_question",
];

export const CLAIM_STATUS_META: Record<ClaimStatus, { label: string; tone: Tone; hint: string }> = {
  Supported: {
    label: "Supported",
    tone: "info",
    hint: "A model verdict found supporting evidence. Not yet human-verified.",
  },
  Uncertain: {
    label: "Uncertain",
    tone: "warn",
    hint: "Evidence was insufficient or the claim is awaiting review.",
  },
  Conflict: {
    label: "Conflict",
    tone: "danger",
    hint: "Another claim contradicts this one. A reviewer must decide.",
  },
  Verified: {
    label: "Verified",
    tone: "ok",
    hint: "Approved by a human reviewer. Only a human can verify a claim.",
  },
};

export const VERDICT_META: Record<VerificationVerdict, { label: string; tone: Tone }> = {
  supports: { label: "Supports", tone: "ok" },
  partly: { label: "Partly", tone: "warn" },
  none: { label: "No support", tone: "danger" },
};

export const RUN_STATUS_META: Record<ProcessingRunStatus, { label: string; tone: Tone }> = {
  pending: { label: "Pending", tone: "secondary" },
  running: { label: "Running", tone: "info" },
  completed: { label: "Completed", tone: "ok" },
  partial: { label: "Partial", tone: "warn" },
  failed: { label: "Failed", tone: "danger" },
};

export const CONFLICT_STATUS_META: Record<ConflictStatus, { label: string; tone: Tone }> = {
  open: { label: "Open", tone: "danger" },
  resolved: { label: "Resolved", tone: "ok" },
  dismissed: { label: "Dismissed", tone: "secondary" },
};

export const CONFLICT_KIND_META: Record<string, { label: string; hint: string }> = {
  value_disagreement: {
    label: "Value disagreement",
    hint: "Two claims assert different values for the same property at the same time.",
  },
  changed_over_time: {
    label: "Changed over time",
    hint: "Newer evidence supersedes older evidence. Recorded, not treated as a contradiction.",
  },
};

export const FRESHNESS_META: Record<FreshnessStatus, { label: string; tone: Tone }> = {
  current: { label: "Current", tone: "ok" },
  potentially_stale: { label: "Potentially stale", tone: "warn" },
  contradicted_by_newer_evidence: { label: "Contradicted by newer evidence", tone: "danger" },
};

export function claimTypeMeta(value: string): { label: string; Icon: LucideIcon } {
  return CLAIM_TYPE_META[value as ClaimType] ?? { label: value, Icon: Tag };
}
