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
  ConflictResolution,
  ConflictStatus,
  FreshnessStatus,
  HandoverLifecycleStatus,
  ProcessingRunStatus,
  StatementType,
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
  Extracted: {
    label: "Extracted",
    tone: "secondary",
    hint: "Captured from a source but not yet assessed by the verifier.",
  },
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
  "Pending Review": {
    label: "Pending review",
    tone: "info",
    hint: "Queued for a human decision. AI verification is not an approval.",
  },
  "Needs Clarification": {
    label: "Needs clarification",
    tone: "warn",
    hint: "A reviewer asked for clarification or additional evidence before deciding.",
  },
  Rejected: {
    label: "Rejected",
    tone: "danger",
    hint: "A reviewer rejected this claim. It can never enter an approved handover.",
  },
  Verified: {
    label: "Approved",
    tone: "ok",
    hint: "Approved by a human reviewer. Only a human can approve a claim.",
  },
};

/** The order review-queue filters and explorer chips are shown in. */
export const CLAIM_STATUS_ORDER: ClaimStatus[] = [
  "Extracted",
  "Supported",
  "Uncertain",
  "Conflict",
  "Pending Review",
  "Needs Clarification",
  "Rejected",
  "Verified",
];

/** Filters offered by the human review queue (§3). */
export const REVIEW_QUEUE_FILTERS: Array<{ value: string; label: string; hint: string }> = [
  { value: "all", label: "All", hint: "Every claim in the project." },
  { value: "pending", label: "Pending review", hint: "Waiting for a human decision." },
  { value: "supported", label: "Supported", hint: "The verifier found supporting evidence." },
  { value: "uncertain", label: "Uncertain", hint: "Evidence was insufficient." },
  { value: "conflict", label: "Conflict", hint: "Contradicted by another claim." },
  { value: "critical", label: "Critical claims", hint: "Flagged as critical to the handover." },
  { value: "clarification", label: "Needs clarification", hint: "Awaiting more information." },
  { value: "rejected", label: "Rejected", hint: "Rejected by a reviewer." },
  { value: "approved", label: "Approved", hint: "Human-approved; eligible for the handover." },
];

export const REVIEW_QUEUE_ORDERS: Array<{ value: string; label: string }> = [
  { value: "critical", label: "Criticality" },
  { value: "recent", label: "Most recent" },
  { value: "oldest", label: "Oldest" },
  { value: "verification", label: "Verification status" },
];

/** Lifecycle presentation for a versioned handover (§12). */
export const HANDOVER_STATUS_META: Record<HandoverLifecycleStatus, { label: string; tone: Tone }> = {
  Draft: { label: "Draft", tone: "secondary" },
  "In Review": { label: "In review", tone: "info" },
  Approved: { label: "Approved", tone: "ok" },
  Published: { label: "Published", tone: "ok" },
  Archived: { label: "Archived", tone: "secondary" },
};

/** Provenance class of a handover statement (§10). */
export const STATEMENT_TYPE_META: Record<StatementType, { label: string; tone: Tone; hint: string }> =
  {
    established_fact: {
      label: "Established fact",
      tone: "ok",
      hint: "Backed by at least one human-approved claim.",
    },
    unresolved_question: {
      label: "Unresolved question",
      tone: "warn",
      hint: "Still unknown from the available evidence.",
    },
    reviewer_note: {
      label: "Reviewer note",
      tone: "info",
      hint: "Authored by a reviewer, not an established project fact.",
    },
    suggested_action: {
      label: "Suggested action",
      tone: "secondary",
      hint: "A recommendation derived from approved project context.",
    },
  };

/** The five reviewer outcomes for a contradiction (§6). */
export const CONFLICT_RESOLUTION_OPTIONS: Array<{
  value: ConflictResolution;
  label: string;
  hint: string;
  requiresChoice: boolean;
}> = [
  {
    value: "claim_a_accepted",
    label: "Claim A is accepted",
    hint: "Claim A stands; claim B becomes Uncertain.",
    requiresChoice: true,
  },
  {
    value: "claim_b_accepted",
    label: "Claim B is accepted",
    hint: "Claim B stands; claim A becomes Uncertain.",
    requiresChoice: true,
  },
  {
    value: "both_valid_in_different_time_periods",
    label: "Both are valid in different time periods",
    hint: "Not a contradiction: the value changed over time. Both are kept.",
    requiresChoice: false,
  },
  {
    value: "both_rejected",
    label: "Both are rejected",
    hint: "Neither statement is reliable; both claims are preserved as Rejected.",
    requiresChoice: false,
  },
  {
    value: "more_information_required",
    label: "More information is required",
    hint: "The conflict stays open until further evidence is available.",
    requiresChoice: false,
  },
];

export const CONFLICT_RESOLUTION_LABELS: Record<string, string> = Object.fromEntries(
  CONFLICT_RESOLUTION_OPTIONS.map((option) => [option.value, option.label]),
);

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
