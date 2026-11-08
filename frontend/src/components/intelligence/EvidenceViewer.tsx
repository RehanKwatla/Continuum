import { Link } from "react-router-dom";
import { ExternalLink, Quote } from "lucide-react";

import { Button } from "@/components/ui/button";
import { AccessLabelBadge, SourceTypeBadge } from "@/components/common/StatusBadge";
import { Tooltip } from "@/components/common/Tooltip";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { EvidenceRef } from "@/types";

function OffsetNote({ evidence }: { evidence: EvidenceRef }) {
  if (evidence.start_offset === null && evidence.end_offset === null) return null;
  const start = evidence.start_offset ?? "?";
  const end = evidence.end_offset ?? "?";
  return (
    <span className="font-mono text-[10px] text-muted-foreground">
      chars {start}–{end}
    </span>
  );
}

/** One traceable passage: source, exact location and the verbatim supporting quote. */
export function EvidenceCard({ evidence, className }: { evidence: EvidenceRef; className?: string }) {
  return (
    <article className={cn("rounded-lg border border-border bg-card/40 p-4", className)}>
      <header className="flex flex-wrap items-center gap-2">
        {evidence.source_type ? <SourceTypeBadge sourceType={evidence.source_type} /> : null}
        <span className="min-w-0 flex-1 truncate text-sm text-foreground">
          {evidence.source_name ?? "Unknown source"}
        </span>
        {evidence.access_label ? <AccessLabelBadge label={evidence.access_label} /> : null}
        <Tooltip label="Open the source">
          <Button variant="ghost" size="icon" asChild>
            <Link
              to={`/sources/${evidence.source_id}`}
              aria-label={`Open source ${evidence.source_name ?? evidence.source_id}`}
            >
              <ExternalLink className="h-4 w-4" />
            </Link>
          </Button>
        </Tooltip>
      </header>

      {evidence.source_location ? (
        <p className="mt-2 font-mono text-[11px] text-muted-foreground">{evidence.source_location}</p>
      ) : null}

      {evidence.supporting_quote ? (
        <blockquote className="mt-3 flex gap-2.5 rounded-md border border-border/70 bg-secondary/40 p-3">
          <Quote className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[hsl(var(--status-info))]" />
          <p className="whitespace-pre-wrap text-xs leading-relaxed text-foreground/90">
            {evidence.supporting_quote}
          </p>
        </blockquote>
      ) : (
        <p className="mt-3 text-xs text-muted-foreground">
          No verbatim passage was stored for this reference.
        </p>
      )}

      <footer className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
        {evidence.author ? <span>Author · {evidence.author}</span> : null}
        <span>Source date · {formatDateTime(evidence.source_date)}</span>
        <OffsetNote evidence={evidence} />
        {evidence.span_id ? (
          <span className="font-mono opacity-70">span {evidence.span_id.slice(0, 8)}</span>
        ) : null}
      </footer>
    </article>
  );
}

export function EvidenceList({ evidence }: { evidence: EvidenceRef[] }) {
  if (evidence.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-border px-3 py-4 text-xs text-muted-foreground">
        No evidence is attached to this claim. A claim without traceable evidence cannot be
        approved.
      </p>
    );
  }
  return (
    <div className="space-y-3">
      {evidence.map((item) => (
        <EvidenceCard key={item.id} evidence={item} />
      ))}
    </div>
  );
}
