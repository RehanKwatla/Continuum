import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  CheckCircle2,
  CircleDot,
  Clock3,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tooltip } from "@/components/common/Tooltip";
import { PageHeader, PanelSkeleton } from "@/components/common/PageHeader";
import { ProjectWorkspaceNav } from "@/components/common/ProjectWorkspaceNav";
import { EmptyState, ErrorState } from "@/components/common/States";
import { useProject } from "@/hooks/use-projects";
import { usePageTitle } from "@/hooks/use-page-title";
import { useReviewQueue } from "@/hooks/use-memory";
import {
  CLAIM_STATUS_META,
  REVIEW_QUEUE_FILTERS,
  REVIEW_QUEUE_ORDERS,
  VERDICT_META,
  claimTypeMeta,
} from "@/lib/intelligence-meta";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ReviewQueueFilter, ReviewQueueOrder, VerificationVerdict } from "@/types";

const PAGE_SIZE = 20;

function AiVerdictBadge({ verdict }: { verdict: string | null }) {
  const meta = verdict ? VERDICT_META[verdict as VerificationVerdict] : null;
  return (
    <Tooltip label="AI verification is an evidence assessment. It is not an approval.">
      <Badge variant={meta?.tone ?? "secondary"} className="gap-1">
        <Sparkles className="h-3 w-3" />
        AI: {meta?.label ?? "not verified"}
      </Badge>
    </Tooltip>
  );
}

function HumanReviewBadge({ status }: { status: string }) {
  const meta = CLAIM_STATUS_META[status as keyof typeof CLAIM_STATUS_META];
  return (
    <Tooltip label="Human approval is an explicit reviewer decision.">
      <Badge variant={meta?.tone ?? "secondary"} className="gap-1">
        <ShieldCheck className="h-3 w-3" />
        Human: {meta?.label ?? status}
      </Badge>
    </Tooltip>
  );
}

export default function ReviewQueue() {
  const { projectId } = useParams<{ projectId: string }>();
  const project = useProject(projectId);
  usePageTitle(project.data ? `Review Queue — ${project.data.name}` : "Review Queue");
  const [params, setParams] = useSearchParams();

  const filter = (params.get("filter") as ReviewQueueFilter) || "all";
  const order = (params.get("order") as ReviewQueueOrder) || "recent";
  const page = Math.max(1, Number.parseInt(params.get("page") ?? "1", 10) || 1);

  const queue = useReviewQueue(projectId, {
    status: filter === "all" ? undefined : filter,
    order,
    page,
    page_size: PAGE_SIZE,
  });

  if (!projectId) return null;

  const update = (next: Record<string, string | null>) => {
    const merged = new URLSearchParams(params);
    for (const [key, value] of Object.entries(next)) {
      if (value === null || value === "") merged.delete(key);
      else merged.set(key, value);
    }
    setParams(merged, { replace: true });
  };

  const meta = queue.data?.meta;
  const items = queue.data?.items ?? [];
  const activeFilter = REVIEW_QUEUE_FILTERS.find((entry) => entry.value === filter);

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Human Review"
        title="Review queue"
        description="AI verdicts assess evidence. Only an explicit reviewer decision records human approval — the two are shown separately and are never conflated."
      />
      <ProjectWorkspaceNav projectId={projectId} />

      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-[11px] text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <Sparkles className="h-3 w-3 text-[hsl(var(--status-info))]" />
          AI verdict — evidence assessment
        </span>
        <span className="inline-flex items-center gap-1.5">
          <CheckCircle2 className="h-3 w-3 text-[hsl(var(--status-ok))]" />
          Human approval — explicit decision
        </span>
        <span className="ml-auto tabular-nums">
          {meta ? `${meta.total} claim${meta.total === 1 ? "" : "s"}` : ""}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-b border-border/70 pb-3">
        <div className="flex flex-wrap gap-1.5">
          {REVIEW_QUEUE_FILTERS.map((entry) => (
            <button
              key={entry.value}
              type="button"
              onClick={() => update({ filter: entry.value, page: null })}
              aria-pressed={filter === entry.value}
              className={cn(
                "rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors",
                filter === entry.value
                  ? "bg-secondary text-foreground"
                  : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
              )}
            >
              {entry.label}
            </button>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <CircleDot className="h-3.5 w-3.5 text-muted-foreground" />
          <Select value={order} onValueChange={(value) => update({ order: value, page: null })}>
            <SelectTrigger className="h-8 w-44 text-xs" aria-label="Sort the review queue">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {REVIEW_QUEUE_ORDERS.map((entry) => (
                <SelectItem key={entry.value} value={entry.value} className="text-xs">
                  {entry.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {filter !== "all" && activeFilter ? (
        <p className="text-[11px] text-muted-foreground">{activeFilter.hint}</p>
      ) : null}

      {queue.isLoading ? (
        <PanelSkeleton rows={4} />
      ) : queue.isError ? (
        <ErrorState
          error={queue.error}
          title="The review queue could not be loaded"
          onRetry={() => void queue.refetch()}
        />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<CheckCircle2 className="h-4 w-4" />}
          title="Nothing in this view"
          description="No claims match the current filter. Reconstruct the project or choose another filter."
        />
      ) : (
        <div className="space-y-3">
          {items.map((item) => {
            const type = claimTypeMeta(item.category);
            const TypeIcon = type.Icon;
            return (
              <article
                key={item.id}
                className="panel space-y-3 border border-border p-4 transition-colors hover:border-primary/40"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 max-w-3xl space-y-2">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge variant="outline" className="gap-1">
                        <TypeIcon className="h-3 w-3" />
                        {type.label}
                      </Badge>
                      {item.critical ? <Badge variant="danger">Critical</Badge> : null}
                      <AiVerdictBadge verdict={item.ai_verdict} />
                      <HumanReviewBadge status={item.status} />
                      {item.revision_number > 1 ? (
                        <Badge variant="secondary">rev {item.revision_number}</Badge>
                      ) : null}
                    </div>
                    <p className="text-sm leading-relaxed">{item.text}</p>
                  </div>
                  <Button size="sm" variant="outline" asChild>
                    <Link to={`/projects/${projectId}/memory/claims/${item.id}`}>
                      Inspect claim
                    </Link>
                  </Button>
                </div>

                <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-border/70 pt-2 text-[11px] text-muted-foreground">
                  <span>
                    {item.evidence_count} evidence source{item.evidence_count === 1 ? "" : "s"}
                  </span>
                  {item.conflict_status === "open" ? (
                    <span className="inline-flex items-center gap-1 text-[hsl(var(--status-danger))]">
                      <AlertTriangle className="h-3 w-3" />
                      Open conflict — cannot be approved
                    </span>
                  ) : null}
                  {item.stale_warning ? (
                    <span className="inline-flex items-center gap-1 text-[hsl(var(--status-warn))]">
                      <Clock3 className="h-3 w-3" />
                      Source may be stale
                    </span>
                  ) : null}
                  <span>Extracted {formatDateTime(item.created_at)}</span>
                  {item.source_references.slice(0, 3).map((reference) => (
                    <span key={reference} className="max-w-64 truncate" title={reference}>
                      {reference}
                    </span>
                  ))}
                </div>
              </article>
            );
          })}
        </div>
      )}

      {meta && meta.total_pages > 1 ? (
        <div className="flex items-center justify-between border-t border-border/70 pt-3">
          <span className="text-[11px] text-muted-foreground">
            Page {meta.page} of {meta.total_pages}
          </span>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={!meta.has_previous}
              onClick={() => update({ page: String(meta.page - 1) })}
            >
              Previous
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={!meta.has_next}
              onClick={() => update({ page: String(meta.page + 1) })}
            >
              Next
            </Button>
          </div>
        </div>
      ) : null}

      <span className="sr-only">{project.data?.name}</span>
    </div>
  );
}
