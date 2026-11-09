import { Link, useParams } from "react-router-dom";
import {
  Brain,
  Database,
  HelpCircle,
  Layers,
  Loader2,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  TriangleAlert,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { EmptyState, ErrorState } from "@/components/common/States";
import { MetricTile } from "@/components/common/PageHeader";
import { RunStatusBadge } from "@/components/common/StatusBadge";
import { useProject } from "@/hooks/use-projects";
import { usePageTitle } from "@/hooks/use-page-title";
import { useProjectMemory, useReconstructProject } from "@/hooks/use-memory";
import { CLAIM_STATUS_META, claimTypeMeta } from "@/lib/intelligence-meta";
import { formatDateTime, formatRelative } from "@/lib/format";
import { hasAtLeast } from "@/lib/roles";
import { ApiClientError, toErrorMessage } from "@/services/api";
import type { ClaimStatus } from "@/types";

function numeric(stats: Record<string, unknown>, key: string): number {
  const value = stats[key];
  return typeof value === "number" ? value : 0;
}

function recordCounts(stats: Record<string, unknown>, key: string): Record<string, number> {
  const value = stats[key];
  if (!value || typeof value !== "object") return {};
  return value as Record<string, number>;
}

export default function ProjectMemory() {
  const { projectId } = useParams<{ projectId: string }>();
  const project = useProject(projectId);
  usePageTitle(project.data ? `Project Memory — ${project.data.name}` : "Project Memory");
  const memory = useProjectMemory(projectId);
  const reconstruct = useReconstructProject(projectId ?? "");
  const { toast } = useToast();

  const role = project.data?.workspace?.role ?? null;
  const canReconstruct = hasAtLeast(role, "member");

  const handleReconstruct = async () => {
    try {
      const run = await reconstruct.mutateAsync({});
      toast({
        title: "Reconstruction finished",
        description: `${run.claim_count} claim(s) reconstructed from ${run.source_count} source(s).`,
        variant: run.status === "failed" ? "error" : "success",
      });
    } catch (caught) {
      const notConfigured =
        caught instanceof ApiClientError && caught.code === "ai_not_configured";
      toast({
        title: notConfigured ? "Intelligence layer not configured" : "Reconstruction failed",
        description: toErrorMessage(caught),
        variant: "error",
      });
    }
  };

  if (!projectId) return null;

  if (memory.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-28 w-full rounded-lg" />
        <div className="grid gap-3 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-24 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  if (memory.isError) {
    return (
      <ErrorState
        error={memory.error}
        title="Project memory could not be loaded"
        onRetry={() => void memory.refetch()}
      />
    );
  }

  const data = memory.data;
  if (!data) return null;

  const stats = data.stats ?? {};
  const statusCounts = recordCounts(stats, "by_status");
  const typeCounts = recordCounts(stats, "by_type");
  const lastRun = data.last_run;

  const reconstructButton = (
    <Button
      size="sm"
      onClick={() => void handleReconstruct()}
      disabled={!canReconstruct || reconstruct.isPending}
    >
      {reconstruct.isPending ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : data.reconstructed ? (
        <RefreshCw className="h-4 w-4" />
      ) : (
        <Sparkles className="h-4 w-4" />
      )}
      {data.reconstructed ? "Re-run reconstruction" : "Reconstruct project memory"}
    </Button>
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">
          {data.reconstructed
            ? data.summary ?? "Project memory has been reconstructed from authorised sources."
            : "No reconstruction has run for this project yet. Continuum has not invented any knowledge."}
        </p>
        <div className="flex items-center gap-2">
          {!canReconstruct ? (
            <span className="text-[11px] text-muted-foreground">
              The member role is required to run reconstruction.
            </span>
          ) : null}
          {reconstructButton}
        </div>
      </div>

      {!data.reconstructed ? (
        <EmptyState
          icon={<Brain className="h-4 w-4" />}
          title="Project memory is empty"
          description="Run a reconstruction to extract claims from this project's ingested sources. Every claim will be linked to the exact passage it came from, and no claim becomes Verified without a human reviewer."
          action={
            <Button size="sm" asChild variant="outline">
              <Link to={`/projects/${projectId}/sources`}>
                <Database className="h-4 w-4" />
                Review sources
              </Link>
            </Button>
          }
        />
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MetricTile
              label="Claims"
              value={numeric(stats, "claim_count")}
              hint={`${numeric(stats, "rejected_count")} rejected during validation`}
              icon={<Layers className="h-4 w-4" />}
            />
            <MetricTile
              label="Sources"
              value={numeric(stats, "source_count")}
              hint={`${numeric(stats, "span_count")} evidence spans`}
              icon={<Database className="h-4 w-4" />}
            />
            <MetricTile
              label="Open conflicts"
              value={numeric(stats, "conflict_count")}
              hint={`${numeric(stats, "ownership_changes")} ownership change(s) over time`}
              icon={<TriangleAlert className="h-4 w-4" />}
            />
            <MetricTile
              label="Flagged for review"
              value={numeric(stats, "stale_count") + numeric(stats, "open_question_count")}
              hint={`${numeric(stats, "stale_count")} stale · ${numeric(
                stats,
                "open_question_count",
              )} open question(s)`}
              icon={<HelpCircle className="h-4 w-4" />}
            />
          </div>

          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <Card>
              <CardHeader className="flex-row items-center justify-between space-y-0">
                <CardTitle className="text-xs font-medium text-muted-foreground">
                  Verification status
                </CardTitle>
                <Link
                  to={`/projects/${projectId}/memory/claims`}
                  className="text-[11px] text-primary hover:underline"
                >
                  Browse claims
                </Link>
              </CardHeader>
              <CardContent className="space-y-2.5">
                {(Object.keys(CLAIM_STATUS_META) as ClaimStatus[]).map((status) => {
                  const count = statusCounts[status] ?? 0;
                  const total = numeric(stats, "claim_count") || 1;
                  return (
                    <div key={status}>
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-muted-foreground">
                          {CLAIM_STATUS_META[status].label}
                        </span>
                        <span className="tabular-nums">{count}</span>
                      </div>
                      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-secondary">
                        <div
                          className="h-full rounded-full bg-primary/70"
                          style={{ width: `${Math.round((count / total) * 100)}%` }}
                        />
                      </div>
                      <p className="mt-1 text-[10px] leading-relaxed text-muted-foreground/80">
                        {CLAIM_STATUS_META[status].hint}
                      </p>
                    </div>
                  );
                })}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-xs font-medium text-muted-foreground">
                  Knowledge by category
                </CardTitle>
              </CardHeader>
              <CardContent>
                {Object.keys(typeCounts).length === 0 ? (
                  <p className="text-xs text-muted-foreground">No claims were extracted.</p>
                ) : (
                  <ul className="space-y-2">
                    {Object.entries(typeCounts)
                      .sort((a, b) => b[1] - a[1])
                      .map(([key, value]) => {
                        const meta = claimTypeMeta(key);
                        const Icon = meta.Icon;
                        return (
                          <li key={key} className="flex items-center justify-between text-xs">
                            <span className="flex items-center gap-2 text-muted-foreground">
                              <Icon className="h-3.5 w-3.5" />
                              {meta.label}
                            </span>
                            <span className="tabular-nums">{value}</span>
                          </li>
                        );
                      })}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>

          {lastRun ? (
            <Card>
              <CardHeader className="flex-row items-center justify-between space-y-0">
                <CardTitle className="text-xs font-medium text-muted-foreground">
                  Latest reconstruction run
                </CardTitle>
                <RunStatusBadge status={lastRun.status} />
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex flex-wrap gap-x-6 gap-y-1 text-[11px] text-muted-foreground">
                  <span>Started {formatDateTime(lastRun.started_at)}</span>
                  <span>Finished {formatRelative(lastRun.finished_at)}</span>
                  {lastRun.model_name ? (
                    <span className="font-mono">model {lastRun.model_name}</span>
                  ) : null}
                  {data.version ? <span>memory v{data.version}</span> : null}
                </div>
                {lastRun.error_message ? (
                  <p className="rounded-md border border-status-danger/35 bg-status-danger/[0.06] p-3 text-xs text-muted-foreground">
                    {lastRun.error_message}
                  </p>
                ) : null}
                <p className="text-[11px] text-muted-foreground">
                  {lastRun.claim_count} claims · {lastRun.verified_count} human-verified ·{" "}
                  {lastRun.uncertain_count} uncertain · {lastRun.conflict_count} conflicting
                </p>
              </CardContent>
            </Card>
          ) : null}
        </>
      )}

      <p className="flex items-center gap-2 text-[11px] leading-relaxed text-muted-foreground">
        <ShieldAlert className="h-3.5 w-3.5" />
        Only authorised sources enter the workflow, and derived claims inherit the strictest access
        label of their evidence. A model verdict can never mark a claim Verified.
      </p>
    </div>
  );
}
