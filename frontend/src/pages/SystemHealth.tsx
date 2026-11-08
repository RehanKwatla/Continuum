import { Link, useParams } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  Database,
  HeartPulse,
  RefreshCw,
  Server,
  ShieldCheck,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader, PanelSkeleton } from "@/components/common/PageHeader";
import { ProjectWorkspaceNav } from "@/components/common/ProjectWorkspaceNav";
import { EmptyState, ErrorState } from "@/components/common/States";
import { useHealth, useReadiness } from "@/hooks/use-dashboard";
import { useProject } from "@/hooks/use-projects";
import { useSystemHealth } from "@/hooks/use-readiness";
import { formatDateTime, humanise } from "@/lib/format";
import { RUN_STATUS_META } from "@/lib/intelligence-meta";
import type { Tone } from "@/lib/phase5-meta";
import { cn } from "@/lib/utils";
import type { ProcessingRunStatus } from "@/types";

function toneClass(tone: Tone): string {
  switch (tone) {
    case "ok":
      return "text-status-ok";
    case "warn":
      return "text-status-warn";
    case "danger":
      return "text-status-danger";
    case "info":
      return "text-status-info";
    default:
      return "text-muted-foreground";
  }
}

function StatusRow({ label, value, tone }: { label: string; value: string; tone: Tone }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-border/60 py-2.5 last:border-b-0">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={cn("inline-flex items-center gap-1.5 text-xs", toneClass(tone))}>
        <span className={cn("h-1.5 w-1.5 rounded-full", tone === "ok" ? "bg-status-ok" : tone === "danger" ? "bg-status-danger" : "bg-status-warn")} />
        {value}
      </span>
    </div>
  );
}

function BreakdownList({ title, data }: { title: string; data: Record<string, number> }) {
  const entries = Object.entries(data);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xs font-medium text-muted-foreground">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {entries.length === 0 ? (
          <p className="text-xs text-muted-foreground">No records.</p>
        ) : (
          <ul className="space-y-1.5">
            {entries.map(([key, value]) => (
              <li key={key} className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">{humanise(key)}</span>
                <span className="font-mono tabular-nums text-foreground">{value}</span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export default function SystemHealth() {
  const { projectId } = useParams<{ projectId: string }>();
  const project = useProject(projectId);
  const health = useHealth();
  const ready = useReadiness();
  const system = useSystemHealth(projectId);

  if (!projectId) return null;

  const data = system.data;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="System health"
        title={project.data?.name ? `System health · ${project.data.name}` : "System health"}
        description="API and database reachability, ingestion and processing status, and recent processing failures for this project. All figures are read from live records."
        actions={
          <>
            <Button variant="ghost" size="sm" asChild>
              <Link to={`/projects/${projectId}`}>
                <ArrowLeft className="h-4 w-4" />
                Project
              </Link>
            </Button>
            <Button size="sm" variant="outline" onClick={() => void system.refetch()} disabled={system.isFetching}>
              <RefreshCw className={cn("h-4 w-4", system.isFetching && "animate-spin")} />
              Refresh
            </Button>
          </>
        }
      />

      <ProjectWorkspaceNav projectId={projectId} />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="flex-row items-center gap-2 space-y-0">
            <Server className="h-3.5 w-3.5 text-muted-foreground" />
            <CardTitle className="text-xs font-medium text-muted-foreground">API service</CardTitle>
          </CardHeader>
          <CardContent>
            {health.isError ? (
              <StatusRow label="API" value="unreachable" tone="danger" />
            ) : health.isLoading ? (
              <PanelSkeleton rows={2} />
            ) : health.data ? (
              <>
                <StatusRow
                  label="Status"
                  value={health.data.status}
                  tone={health.data.status === "ok" ? "ok" : "warn"}
                />
                <StatusRow label="Service" value={health.data.service} tone="info" />
                <StatusRow label="Version" value={health.data.version} tone="info" />
                <StatusRow label="Environment" value={health.data.environment} tone="info" />
              </>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center gap-2 space-y-0">
            <Database className="h-3.5 w-3.5 text-muted-foreground" />
            <CardTitle className="text-xs font-medium text-muted-foreground">
              Database and integrations
            </CardTitle>
          </CardHeader>
          <CardContent>
            {ready.isError ? (
              <StatusRow label="Readiness probe" value="unavailable" tone="danger" />
            ) : ready.isLoading ? (
              <PanelSkeleton rows={2} />
            ) : ready.data ? (
              <>
                <StatusRow
                  label="Readiness"
                  value={ready.data.status}
                  tone={ready.data.status === "ok" ? "ok" : "warn"}
                />
                <StatusRow
                  label="Database"
                  value={ready.data.database}
                  tone={ready.data.database === "ok" ? "ok" : "danger"}
                />
                <StatusRow
                  label="Supabase auth"
                  value={ready.data.supabase_auth_configured ? "configured" : "not configured"}
                  tone={ready.data.supabase_auth_configured ? "ok" : "warn"}
                />
                <StatusRow
                  label="GitHub OAuth"
                  value={ready.data.github_oauth_configured ? "configured" : "not configured"}
                  tone={ready.data.github_oauth_configured ? "ok" : "warn"}
                />
                <StatusRow
                  label="Dev auth"
                  value={ready.data.dev_auth_enabled ? "enabled" : "disabled"}
                  tone={ready.data.dev_auth_enabled ? "warn" : "ok"}
                />
              </>
            ) : null}
          </CardContent>
        </Card>
      </div>

      {system.isError ? (
        <ErrorState
          error={system.error}
          title="Project processing status could not be loaded"
          onRetry={() => void system.refetch()}
        />
      ) : system.isLoading ? (
        <PanelSkeleton rows={4} />
      ) : !data ? (
        <EmptyState icon={<Activity className="h-4 w-4" />} title="Nothing to show" />
      ) : (
        <div className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="panel p-4">
              <p className="label-eyebrow">Database</p>
              <p
                className={cn(
                  "mt-1 font-display text-2xl",
                  data.database === "ok" ? "text-status-ok" : "text-status-danger",
                )}
              >
                {data.database === "ok" ? "Reachable" : "Unavailable"}
              </p>
            </div>
            <div className="panel p-4">
              <p className="label-eyebrow">Overall status</p>
              <p
                className={cn(
                  "mt-1 font-display text-2xl",
                  data.status === "ok" ? "text-status-ok" : "text-status-warn",
                )}
              >
                {data.status}
              </p>
            </div>
            <div className="panel p-4">
              <p className="label-eyebrow">Recent failures</p>
              <p className="mt-1 font-display text-2xl tabular-nums text-status-danger">
                {data.recent_failures.length}
              </p>
            </div>
            <div className="panel p-4">
              <p className="label-eyebrow">Recent runs (window)</p>
              <p className="mt-1 font-display text-2xl tabular-nums text-foreground">
                {data.recent_runs.length}
              </p>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <BreakdownList title="Sources by status" data={data.sources_by_status} />
            <BreakdownList title="Processing runs by status" data={data.processing_runs_by_status} />
            <BreakdownList title="Claims by status" data={data.claims_by_status} />
          </div>

          <Card className={data.recent_failures.length > 0 ? "border-status-danger/30" : undefined}>
            <CardHeader className="flex-row items-center gap-2 space-y-0">
              <AlertTriangle className="h-3.5 w-3.5 text-status-danger" />
              <CardTitle className="text-xs font-medium text-muted-foreground">
                Recent failures and partial runs
              </CardTitle>
            </CardHeader>
            <CardContent>
              {data.recent_failures.length === 0 ? (
                <p className="flex items-center gap-2 text-xs text-muted-foreground">
                  <ShieldCheck className="h-3.5 w-3.5 text-status-ok" />
                  No processing failure recorded in the recent window.
                </p>
              ) : (
                <ul className="space-y-2">
                  {data.recent_failures.map((failure) => (
                    <li
                      key={failure.run_id}
                      className="rounded-md border border-status-danger/30 bg-status-danger/[0.04] p-2.5"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="danger">{humanise(failure.status)}</Badge>
                        <span className="font-mono text-[10px] text-muted-foreground">
                          {failure.run_id.slice(0, 8)}
                        </span>
                        <span className="ml-auto text-[11px] text-muted-foreground">
                          {formatDateTime(failure.created_at)}
                        </span>
                      </div>
                      {failure.error ? (
                        <p className="mt-1.5 text-[11px] leading-relaxed text-foreground/90">
                          {failure.error}
                        </p>
                      ) : null}
                      {failure.errors.length > 0 ? (
                        <ul className="mt-1 space-y-0.5">
                          {failure.errors.slice(0, 5).map((error, index) => (
                            <li key={index} className="text-[11px] leading-relaxed text-muted-foreground">
                              {String(error.message ?? error.code ?? JSON.stringify(error))}
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex-row items-center gap-2 space-y-0">
              <HeartPulse className="h-3.5 w-3.5 text-muted-foreground" />
              <CardTitle className="text-xs font-medium text-muted-foreground">
                Recent processing runs
              </CardTitle>
            </CardHeader>
            <CardContent>
              {data.recent_runs.length === 0 ? (
                <p className="text-xs text-muted-foreground">No processing run recorded yet.</p>
              ) : (
                <ul className="divide-y divide-border/70">
                  {data.recent_runs.map((run) => {
                    const meta = RUN_STATUS_META[run.status as ProcessingRunStatus];
                    return (
                      <li key={run.run_id} className="flex flex-wrap items-center gap-3 py-2.5 text-xs">
                        <Badge variant={meta?.tone ?? "secondary"}>{meta?.label ?? run.status}</Badge>
                        <span className="font-mono text-[10px] text-muted-foreground">
                          {run.run_id.slice(0, 8)}
                        </span>
                        <span className="text-muted-foreground">
                          {run.source_count} sources · {run.claim_count} claims · {run.verified_count} verified
                        </span>
                        <span className="ml-auto text-[11px] text-muted-foreground">
                          {formatDateTime(run.finished_at ?? run.created_at)}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      <p className="text-[11px] leading-relaxed text-muted-foreground">
        This view reads live records only. A project with no ingestion activity shows empty breakdowns
        rather than fabricated numbers.
      </p>
    </div>
  );
}
