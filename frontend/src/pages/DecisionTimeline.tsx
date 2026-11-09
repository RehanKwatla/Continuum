import * as React from "react";
import { Link, useParams } from "react-router-dom";
import { CalendarClock, Gavel } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState, ErrorState } from "@/components/common/States";
import { PageHeader, PanelSkeleton } from "@/components/common/PageHeader";
import { ClaimStatusBadge } from "@/components/common/StatusBadge";
import { useClaims } from "@/hooks/use-memory";
import { usePageTitle } from "@/hooks/use-page-title";
import { claimTypeMeta } from "@/lib/intelligence-meta";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

type TimelineOrder = "timeline" | "recent";

function groupByDay<T extends { source_date: string | null }>(items: T[]) {
  const groups = new Map<string, T[]>();
  for (const item of items) {
    const key = item.source_date ? item.source_date.slice(0, 10) : "undated";
    const bucket = groups.get(key);
    if (bucket) bucket.push(item);
    else groups.set(key, [item]);
  }
  return Array.from(groups.entries());
}

export default function DecisionTimeline() {
  const { projectId } = useParams<{ projectId: string }>();
  usePageTitle("Decision Timeline");
  const [decisionsOnly, setDecisionsOnly] = React.useState(true);
  const [order, setOrder] = React.useState<TimelineOrder>("timeline");

  const claims = useClaims(projectId, {
    category: decisionsOnly ? "decision" : undefined,
    order,
    page_size: 100,
  });

  if (!projectId) return null;

  const groups = groupByDay(claims.data?.items ?? []);

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Decision Timeline"
        title="How the project evolved"
        description="Claims ordered by the date of the source that supports them — decisions first by default. Only dated sources appear in sequence."
      />

      <div className="flex flex-wrap items-center gap-2">
        <div className="inline-flex rounded-md border border-border p-0.5">
          <Button
            size="sm"
            variant={decisionsOnly ? "secondary" : "ghost"}
            className="h-7 rounded-sm px-3 text-xs"
            onClick={() => setDecisionsOnly(true)}
          >
            <Gavel className="h-3.5 w-3.5" />
            Decisions
          </Button>
          <Button
            size="sm"
            variant={!decisionsOnly ? "secondary" : "ghost"}
            className="h-7 rounded-sm px-3 text-xs"
            onClick={() => setDecisionsOnly(false)}
          >
            All claims
          </Button>
        </div>
        <div className="inline-flex rounded-md border border-border p-0.5">
          <Button
            size="sm"
            variant={order === "timeline" ? "secondary" : "ghost"}
            className="h-7 rounded-sm px-3 text-xs"
            onClick={() => setOrder("timeline")}
          >
            Oldest first
          </Button>
          <Button
            size="sm"
            variant={order === "recent" ? "secondary" : "ghost"}
            className="h-7 rounded-sm px-3 text-xs"
            onClick={() => setOrder("recent")}
          >
            Newest first
          </Button>
        </div>
      </div>

      {claims.isLoading ? (
        <PanelSkeleton rows={5} />
      ) : claims.isError ? (
        <ErrorState
          error={claims.error}
          title="The timeline could not be loaded"
          onRetry={() => void claims.refetch()}
        />
      ) : groups.length === 0 ? (
        <EmptyState
          icon={<CalendarClock className="h-4 w-4" />}
          title={decisionsOnly ? "No decisions extracted yet" : "No claims to place on the timeline"}
          description="Run a reconstruction, or switch to all claims if decisions have not been identified."
          action={
            decisionsOnly ? (
              <Button size="sm" variant="outline" onClick={() => setDecisionsOnly(false)}>
                Show all claims
              </Button>
            ) : undefined
          }
        />
      ) : (
        <ol className="relative space-y-6 border-l border-border pl-6">
          {groups.map(([day, items], index) => (
            <li key={day} className="relative">
              <span
                className={cn(
                  "absolute -left-[30px] flex h-6 w-6 items-center justify-center rounded-full border bg-card text-[10px] font-medium",
                  index === 0 ? "border-primary text-primary" : "border-border text-muted-foreground",
                )}
              >
                {items.length}
              </span>
              <p className="label-eyebrow">
                {day === "undated" ? "Undated sources" : formatDate(day)}
              </p>
              <div className="mt-2 space-y-2">
                {items.map((claim) => {
                  const meta = claimTypeMeta(claim.claim_type);
                  const Icon = meta.Icon;
                  return (
                    <Card key={claim.id}>
                      <CardContent className="p-4">
                        <div className="flex items-start gap-3">
                          <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                          <div className="min-w-0 flex-1">
                            <p className="text-sm leading-relaxed text-foreground">{claim.text}</p>
                            <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                              <ClaimStatusBadge status={claim.status} />
                              <span className="uppercase tracking-wide">{meta.label}</span>
                              {claim.entity ? (
                                <span className="font-mono">· {claim.entity}</span>
                              ) : null}
                              <span>
                                {claim.evidence_count} evidence ref
                                {claim.evidence_count === 1 ? "" : "s"}
                              </span>
                              <Link
                                to={`/projects/${projectId}/memory/claims/${claim.id}`}
                                className="text-primary hover:underline"
                              >
                                Open →
                              </Link>
                            </div>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
