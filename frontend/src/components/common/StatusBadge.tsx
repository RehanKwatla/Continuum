import { Badge } from "@/components/ui/badge";
import {
  ACCESS_LABEL_META,
  PROCESSING_STATUS_META,
  PROJECT_STATUS_META,
  SOURCE_TYPE_META,
} from "@/lib/source-meta";
import { cn } from "@/lib/utils";
import type { AccessLabel, ProcessingStatus, ProjectStatus, SourceType } from "@/types";

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
