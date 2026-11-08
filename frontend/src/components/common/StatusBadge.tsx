import { Badge } from "@/components/ui/badge";
import {
  CLAIM_STATUS_META,
  CONFLICT_STATUS_META,
  FRESHNESS_META,
  RUN_STATUS_META,
  VERDICT_META,
} from "@/lib/intelligence-meta";
import {
  ACCESS_LABEL_META,
  PROCESSING_STATUS_META,
  PROJECT_STATUS_META,
  SOURCE_TYPE_META,
} from "@/lib/source-meta";
import { cn } from "@/lib/utils";
import type {
  AccessLabel,
  ClaimStatus,
  ConflictStatus,
  FreshnessStatus,
  ProcessingRunStatus,
  ProcessingStatus,
  ProjectStatus,
  SourceType,
  VerificationVerdict,
} from "@/types";

type BadgeTone = "ok" | "warn" | "danger" | "info" | "secondary" | "default";

function toneVariant(
  tone: BadgeTone,
): "ok" | "warn" | "danger" | "info" | "secondary" | "default" {
  return tone === "default" ? "default" : tone;
}

export function ClaimStatusBadge({ status }: { status: ClaimStatus }) {
  const meta = CLAIM_STATUS_META[status];
  return <Badge variant={toneVariant(meta.tone)}>{meta.label}</Badge>;
}

export function VerdictBadge({ verdict }: { verdict: VerificationVerdict }) {
  const meta = VERDICT_META[verdict];
  return <Badge variant={toneVariant(meta.tone)}>{meta.label}</Badge>;
}

export function RunStatusBadge({ status }: { status: ProcessingRunStatus }) {
  const meta = RUN_STATUS_META[status];
  return <Badge variant={toneVariant(meta.tone)}>{meta.label}</Badge>;
}

export function ConflictStatusBadge({ status }: { status: ConflictStatus }) {
  const meta = CONFLICT_STATUS_META[status];
  return <Badge variant={toneVariant(meta.tone)}>{meta.label}</Badge>;
}

export function FreshnessBadge({ status }: { status: FreshnessStatus }) {
  const meta = FRESHNESS_META[status];
  return <Badge variant={toneVariant(meta.tone)}>{meta.label}</Badge>;
}

export function ProcessingStatusBadge({ status }: { status: ProcessingStatus }) {
  const meta = PROCESSING_STATUS_META[status];
  return <Badge variant={meta.tone === "secondary" ? "secondary" : meta.tone}>{meta.label}</Badge>;
}

export function ProjectStatusBadge({ status }: { status: ProjectStatus }) {
  const meta = PROJECT_STATUS_META[status];
  return <Badge variant={meta.tone === "secondary" ? "secondary" : meta.tone}>{meta.label}</Badge>;
}

export function AccessLabelBadge({ label }: { label: AccessLabel }) {
  return <Badge variant="outline">{ACCESS_LABEL_META[label]}</Badge>;
}

export function SourceTypeBadge({
  sourceType,
  className,
}: {
  sourceType: SourceType;
  className?: string;
}) {
  const meta = SOURCE_TYPE_META[sourceType];
  const Icon = meta.Icon;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border border-border/80 bg-secondary/60 px-2 py-0.5 text-[11px] font-medium text-secondary-foreground",
        className,
      )}
    >
      <Icon className="h-3 w-3 text-muted-foreground" />
      {meta.label}
    </span>
  );
}
