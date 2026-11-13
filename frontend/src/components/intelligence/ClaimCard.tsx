import { Link } from "react-router-dom";
import { AlertOctagon, Star } from "lucide-react";

import { ClaimStatusBadge } from "@/components/common/StatusBadge";
import { Tooltip } from "@/components/common/Tooltip";
import { claimTypeMeta } from "@/lib/intelligence-meta";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ClaimSummary } from "@/types";

/** Compact, linkable summary of one claim. Used by every intelligence listing. */
export function ClaimCard({
  projectId,
  claim,
  className,
}: {
  projectId: string;
  claim: ClaimSummary;
  className?: string;
}) {
  const meta = claimTypeMeta(claim.claim_type);
  const Icon = meta.Icon;

  return (
    <Link
      to={`/projects/${projectId}/memory/claims/${claim.id}`}
      className={cn(
        "block rounded-xl border border-border bg-card p-4 shadow-sm transition-all hover:border-primary/50 hover:bg-card/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60",
        className,
      )}
    >
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-border/80 bg-secondary text-primary font-semibold">
          <Icon className="h-3.5 w-3.5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm leading-relaxed text-foreground">{claim.text}</p>
          <div className="mt-2.5 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
            <ClaimStatusBadge status={claim.status} />
            <span className="uppercase tracking-wide">{meta.label}</span>
            {claim.entity ? <span className="font-mono">· {claim.entity}</span> : null}
            {claim.critical ? (
              <Tooltip label="Flagged as critical">
                <span className="inline-flex items-center gap-1 text-status-danger">
                  <AlertOctagon className="h-3 w-3" />
                  Critical
                </span>
              </Tooltip>
            ) : null}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
            <span>
              {claim.evidence_count} evidence {claim.evidence_count === 1 ? "reference" : "references"}
            </span>
            {claim.author ? <span>Author · {claim.author}</span> : null}
            <span>Source date · {formatDateTime(claim.source_date)}</span>
            {claim.confidence !== null ? (
              <span className="inline-flex items-center gap-1">
                <Star className="h-3 w-3" />
                {Math.round(claim.confidence * 100)}% confidence
              </span>
            ) : null}
          </div>
        </div>
      </div>
    </Link>
  );
}
