import * as React from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  CheckCircle2,
  CircleDashed,
  Database,
  ExternalLink,
  FileCheck,
  FileSearch,
  FileText,
  FolderKanban,
  Gauge,
  GitBranch,
  Layers,
  RotateCcw,
  Scale,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState, ErrorState } from "@/components/common/States";
import { MetricTile, PageHeader } from "@/components/common/PageHeader";
import { cn } from "@/lib/utils";
import {
  ProcessingStatusBadge,
  ProjectStatusBadge,
  SourceTypeBadge,
} from "@/components/common/StatusBadge";
import { useToast } from "@/components/ui/toast";
import { useDashboard, useRepositoryActivity } from "@/hooks/use-dashboard";
import { useAuth } from "@/contexts/AuthContext";
import { usePageTitle } from "@/hooks/use-page-title";
import { usePublicDemo, useResetPublicDemo } from "@/hooks/use-demo";
import { useWorkspaces } from "@/hooks/use-workspaces";
import { formatRelative } from "@/lib/format";
import {
  PROCESSING_STATUS_META,
  SOURCE_TYPE_META,
} from "@/lib/source-meta";
import type { ProcessingStatus, SourceType } from "@/types";
import type { RepositoryActivity } from "@/types";
import { ApiClientError, toErrorMessage } from "@/services/api";

function Breakdown({
  title,
  icon,
  counts,
  emptyLabel,
  labelFor,
}: {
  title: string;
  icon: React.ReactNode;
  counts: Record<string, number>;
  emptyLabel: string;
  labelFor: (key: string) => string;
}) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((sum, [, value]) => sum + value, 0);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          {icon}
          {title}
        </CardTitle>
        <span className="text-xs tabular-nums text-muted-foreground">{total}</span>
      </CardHeader>
      <CardContent>
        {entries.length === 0 ? (
          <p className="text-xs text-muted-foreground">{emptyLabel}</p>
        ) : (
          <ul className="space-y-2">
            {entries.map(([key, value]) => {
              const percent = total ? Math.round((value / total) * 100) : 0;
              return (
                <li key={key} className="space-y-1">
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="truncate text-muted-foreground">{labelFor(key)}</span>
                    <span className="tabular-nums text-foreground">{value}</span>
                  </div>
                  <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-primary/70"
                      style={{ width: `${percent}%` }}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

type ActivityRange = "1D" | "1W" | "1M" | "6M" | "1Y";
type ActivityBucket = { start: number; end: number; label: string; count: number };

function activityBuckets(data: RepositoryActivity, range: ActivityRange, now: Date): ActivityBucket[] {
  const dateOptions: Intl.DateTimeFormatOptions = { timeZone: "UTC" };
  const makeLabel = (date: Date, options: Intl.DateTimeFormatOptions) =>
    new Intl.DateTimeFormat(undefined, { ...dateOptions, ...options }).format(date);
  let starts: Date[] = [];
  let nextStart: (date: Date) => Date;
  let labelOptions: Intl.DateTimeFormatOptions;

  if (range === "1D") {
    const end = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), now.getUTCHours()));
    starts = Array.from({ length: 24 }, (_, index) => new Date(end.getTime() - (23 - index) * 60 * 60 * 1000));
    nextStart = (date) => new Date(date.getTime() + 60 * 60 * 1000);
    labelOptions = { hour: "numeric" };
  } else if (range === "1W" || range === "1M") {
    const end = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
    const days = range === "1W" ? 7 : 30;
    starts = Array.from({ length: days }, (_, index) => new Date(end.getTime() - (days - 1 - index) * 24 * 60 * 60 * 1000));
    nextStart = (date) => new Date(date.getTime() + 24 * 60 * 60 * 1000);
    labelOptions = range === "1W" ? { weekday: "short" } : { month: "short", day: "numeric" };
  } else if (range === "6M") {
    const end = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
    const mondayOffset = (end.getUTCDay() + 6) % 7;
    end.setUTCDate(end.getUTCDate() - mondayOffset);
    starts = Array.from({ length: 26 }, (_, index) => new Date(end.getTime() - (25 - index) * 7 * 24 * 60 * 60 * 1000));
    nextStart = (date) => new Date(date.getTime() + 7 * 24 * 60 * 60 * 1000);
    labelOptions = { month: "short", day: "numeric" };
  } else {
    const end = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1));
    starts = Array.from({ length: 12 }, (_, index) => new Date(Date.UTC(end.getUTCFullYear(), end.getUTCMonth() - 11 + index, 1)));
    nextStart = (date) => new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 1));
    labelOptions = { month: "short" };
  }

  const buckets = starts.map((start) => ({ start: start.getTime(), end: nextStart(start).getTime(), label: makeLabel(start, labelOptions), count: 0 }));
  for (const commit of data.commits) {
    const timestamp = Date.parse(commit.committed_at);
    if (!Number.isFinite(timestamp)) continue;
    const bucket = buckets.find((item) => timestamp >= item.start && timestamp < item.end);
    if (bucket) bucket.count += 1;
  }
  return buckets;
}

function RepositoryActivityChart({ activity, isLoading, error, onRetry }: {
  activity: RepositoryActivity | undefined;
  isLoading: boolean;
  error: unknown;
  onRetry: () => void;
}) {
  const [range, setRange] = React.useState<"1D" | "1W" | "1M" | "6M" | "1Y">("1M");
  const ranges = ["1D", "1W", "1M", "6M", "1Y"] as const;
  const now = React.useMemo(() => new Date(), [activity, range]);
  const buckets = React.useMemo(() => activity ? activityBuckets(activity, range, now) : [], [activity, range, now]);
  const maxCount = Math.max(1, ...buckets.map((item) => item.count));
  const plotLeft = 45;
  const plotRight = 800;
  const plotTop = 24;
  const plotBottom = 176;
  const points = buckets.map((bucket, index) => ({
    x: buckets.length < 2 ? (plotLeft + plotRight) / 2 : plotLeft + index * (plotRight - plotLeft) / (buckets.length - 1),
    y: plotBottom - (bucket.count / maxCount) * (plotBottom - plotTop),
    ...bucket,
  }));
  const linePath = points.map((point, index) => `${index ? "L" : "M"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" ");
  const areaPath = points.length ? `${linePath} L ${plotRight} ${plotBottom} L ${plotLeft} ${plotBottom} Z` : "";
  const peak = points.reduce<typeof points[number] | null>((best, point) => point.count > (best?.count ?? 0) ? point : best, null);
  const labels = Array.from(new Set([0, Math.round((buckets.length - 1) / 4), Math.round((buckets.length - 1) / 2), Math.round(3 * (buckets.length - 1) / 4), buckets.length - 1])).filter((index) => index >= 0 && index < buckets.length);
  const retryAt = error instanceof ApiClientError ? Number(error.details.retry_at) : NaN;
  const errorMessage = error instanceof ApiClientError && error.code === "github_rate_limited"
    ? Number.isFinite(retryAt) && retryAt > 0
      ? `GitHub is rate limiting this request. Retry after ${new Date(retryAt * 1000).toLocaleTimeString()}.`
      : "GitHub is rate limiting this request. Wait briefly, then retry."
    : error ? toErrorMessage(error) : "";
  const earliestCommit = activity?.commits.reduce<string | null>((oldest, commit) => !oldest || Date.parse(commit.committed_at) < Date.parse(oldest) ? commit.committed_at : oldest, null);
  const latestCommit = activity?.commits.reduce<string | null>((latest, commit) => !latest || Date.parse(commit.committed_at) > Date.parse(latest) ? commit.committed_at : latest, null);
  const sampleTimestamps = activity?.commits.map((commit) => Date.parse(commit.committed_at)).filter(Number.isFinite) ?? [];
  const sampleStart = sampleTimestamps.length ? Math.min(...sampleTimestamps) : null;
  const sampleEnd = sampleTimestamps.length ? Math.max(...sampleTimestamps) : null;
  const containsFullSample = (candidate: ActivityRange) => {
    if (sampleStart === null || sampleEnd === null || !activity) return false;
    const candidateBuckets = activityBuckets(activity, candidate, now);
    const first = candidateBuckets[0];
    const last = candidateBuckets[candidateBuckets.length - 1];
    return Boolean(first && last && sampleStart >= first.start && sampleEnd < last.end);
  };
  const containsLatestCommit = (candidate: ActivityRange) => {
    if (sampleEnd === null || !activity) return false;
    const candidateBuckets = activityBuckets(activity, candidate, now);
    const first = candidateBuckets[0];
    const last = candidateBuckets[candidateBuckets.length - 1];
    return Boolean(first && last && sampleEnd >= first.start && sampleEnd < last.end);
  };
  const fullSampleRange = ranges.find(containsFullSample);
  const latestCommitRange = ranges.find(containsLatestCommit);
  const suggestedRange = fullSampleRange ?? latestCommitRange;
  const suggestedRangeCoversSample = Boolean(fullSampleRange);
  const coverage = earliestCommit && latestCommit
    ? `${new Date(earliestCommit).toLocaleDateString()} – ${new Date(latestCommit).toLocaleDateString()}`
    : "No dated commits in the sample";

  return (
    <Card className="overflow-hidden border-border bg-card shadow-sm">
      <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between space-y-0 pb-3">
        <div>
          <CardTitle className="text-base font-semibold text-foreground">
            Continuum Repository Activity
          </CardTitle>
          <CardDescription className="text-xs text-muted-foreground mt-0.5">
            Commit volume on the default branch of RehanKwatla/Continuum
          </CardDescription>
        </div>
        <div className="flex items-center gap-1 rounded-lg border border-border bg-secondary/80 p-1">
          {ranges.map((r) => (
            <button
              key={r}
              type="button"
              aria-pressed={range === r}
              onClick={() => setRange(r)}
              className={cn(
                "rounded-md px-2.5 py-1 text-xs font-medium transition-all",
                range === r
                  ? "bg-primary text-primary-foreground font-semibold shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {r}
            </button>
          ))}
        </div>
      </CardHeader>
      <CardContent className="space-y-3 pt-2">
        {isLoading ? <Skeleton className="h-52 w-full" /> : error ? (
          <div className="flex min-h-52 flex-col items-center justify-center gap-3 rounded-md border border-destructive/30 bg-destructive/5 px-4 text-center" role="alert">
            <p className="max-w-xl text-sm text-foreground">{errorMessage}</p>
            <Button size="sm" variant="outline" onClick={onRetry}>Retry activity</Button>
          </div>
        ) : activity ? <>
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <a href={activity.repository_url} target="_blank" rel="noreferrer" className="font-medium text-primary underline-offset-4 hover:underline">RehanKwatla/Continuum ↗</a>
            <span>{activity.branch} · {activity.sampled_commits} commits sampled · {coverage}</span>
          </div>
          <div className="relative h-52 w-full" role="img" aria-label={`Commit activity for ${activity.repository_url}, ${range} range, peak ${peak?.count ?? 0} commits per interval`}>
            <svg viewBox="0 0 820 220" className="h-full w-full overflow-visible" preserveAspectRatio="none" aria-hidden="true">
              <title>Commits per interval</title>
              <desc>Counts are derived from commit timestamps returned by GitHub for the Continuum repository.</desc>
              <defs><linearGradient id="repoActivityGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#C995BC" stopOpacity="0.28" /><stop offset="100%" stopColor="#18131E" stopOpacity="0" /></linearGradient></defs>
              {[0, 0.5, 1].map((ratio) => {
                const y = plotTop + ratio * (plotBottom - plotTop);
                const value = Math.round(maxCount * (1 - ratio));
                return <g key={ratio}><line x1={plotLeft} y1={y} x2={plotRight} y2={y} stroke="rgba(142, 115, 139, 0.18)" strokeDasharray={ratio === 1 ? undefined : "3,4"} /><text x="2" y={y + 4} fontSize="10" fill="currentColor" className="text-muted-foreground">{value}</text></g>;
              })}
              {points.length > 1 && <path d={areaPath} fill="url(#repoActivityGrad)" />}
              {points.length > 1 && <path d={linePath} fill="none" stroke="#C995BC" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />}
              {peak && peak.count > 0 && <><line x1={peak.x} y1={plotTop} x2={peak.x} y2={plotBottom} stroke="#8E738B" strokeWidth="1.5" strokeDasharray="4,4" /><circle cx={peak.x} cy={peak.y} r="5" fill="#C995BC" /><circle cx={peak.x} cy={peak.y} r="9" fill="none" stroke="#C995BC" strokeWidth="1.8" strokeOpacity="0.65" /></>}
            </svg>
          </div>
          {peak && peak.count > 0 && <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border/70 bg-secondary/40 px-3 py-2">
            <div className="text-[11px] font-mono text-muted-foreground">Peak interval · {peak.label}</div>
            <div className="text-sm font-semibold text-foreground">{peak.count} {peak.count === 1 ? "commit" : "commits"}</div>
          </div>}
          {activity.sampled_commits === 0 ? <div className="rounded-md border border-dashed border-border px-3 py-3 text-sm text-muted-foreground" role="status" aria-live="polite">No dated commits are available in the returned repository sample.</div> : points.every((point) => point.count === 0) && <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-dashed border-border px-3 py-3" role="status" aria-live="polite">
            <div className="text-sm text-muted-foreground">
              <p>No commits fell inside this {range} range.</p>
              <p className="mt-1 text-xs">The returned sample covers {coverage} ({activity.sampled_commits} commits).</p>
              {suggestedRange && suggestedRange !== range && !suggestedRangeCoversSample && <p className="mt-1 text-xs">That wider range includes the latest sampled commit; older sampled commits may still fall outside it.</p>}
              {!suggestedRange && <p className="mt-1 text-xs">The sample is outside the available 1D–1Y chart ranges.</p>}
            </div>
            {suggestedRange && suggestedRange !== range && <Button type="button" size="sm" variant="outline" aria-label={suggestedRangeCoversSample ? `View ${suggestedRange} activity containing the sampled commits` : `View ${suggestedRange} activity around the latest sampled commit`} onClick={() => setRange(suggestedRange)}>
              View {suggestedRange} activity
            </Button>}
          </div>}
          <div className="flex items-center justify-between gap-1 px-2 text-[11px] font-mono text-muted-foreground" aria-hidden="true">
            {labels.map((index) => <span key={index} className={index === labels[labels.length - 1] ? "text-primary" : ""}>{buckets[index]?.label}</span>)}
          </div>
          <p className="border-t border-border/70 pt-2 text-[11px] text-muted-foreground">{activity.note}</p>
        </> : (
          <div className="flex min-h-52 items-center justify-center rounded-md border border-dashed border-border px-4 text-center text-sm text-muted-foreground">Repository activity is not available yet.</div>
        )}
      </CardContent>
    </Card>
  );
}

export default function Dashboard() {
  usePageTitle("Dashboard");
  const auth = useAuth();
  const dashboard = useDashboard();
  const repositoryActivity = useRepositoryActivity();
  const workspaces = useWorkspaces();
  const demo = usePublicDemo();
  const resetDemo = useResetPublicDemo();
  const { toast } = useToast();

  const demoProject =
    dashboard.data?.recent_projects?.find((project) => project.id === demo.data?.project_id) ??
    dashboard.data?.recent_projects?.[0] ??
    null;
  const demoProjectId = demo.data?.project_id ?? demoProject?.id ?? "";

  const handleResetDemo = async () => {
    try {
      await resetDemo.mutateAsync();
      toast({
        title: "Demo workspace reset",
        description: "The synthetic demonstration workspace has been restored to pristine seed data.",
        variant: "success",
      });
      await dashboard.refetch();
    } catch {
      toast({
        title: "Reset failed",
        description: "Could not reset the demo workspace. Please try again shortly.",
        variant: "error",
      });
    }
  };

  const header = (
    <PageHeader
      eyebrow="Public demo environment · Frictionless judge access"
      title="Welcome to Continuum."
      description="Project knowledge, reconstructed and ready for its next owner."
      actions={
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => void handleResetDemo()}
                disabled={resetDemo.isPending}
                className="gap-2 text-xs"
              >
                <RotateCcw className={`h-3.5 w-3.5 ${resetDemo.isPending ? "animate-spin" : ""}`} />
                {resetDemo.isPending ? "Resetting…" : "Reset demo data"}
              </Button>
            {demoProjectId ? (
              <Button size="sm" asChild className="gap-2 text-xs">
                <Link to={`/projects/${demoProjectId}`}>
                  Explore sample project
                  <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </Button>
            ) : null}
          </div>
      }
    />
          );

          if (auth.status === "loading" || dashboard.isLoading) {
    return (
          <div className="space-y-6">
            {header}
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {Array.from({ length: 4 }).map((_, index) => (
                <Skeleton key={index} className="h-[92px] rounded-lg" />
              ))}
            </div>
            <div className="grid gap-3 lg:grid-cols-2">
              <Skeleton className="h-[220px] rounded-lg" />
              <Skeleton className="h-[220px] rounded-lg" />
            </div>
            <Skeleton className="h-[240px] rounded-lg" />
          </div>
          );
  }

          if (auth.status === "unauthenticated") {
    return (
          <div className="space-y-6">
            {header}
            <ErrorState
              title="Could not connect to the Public Demo workspace"
              error={auth.error ?? new Error("The demo session is unavailable. Please retry shortly.")}
              onRetry={() => void auth.refresh()}
            />
          </div>
          );
  }

          if (dashboard.isError) {
    return (
          <div className="space-y-6">
            {header}
            <ErrorState error={dashboard.error} onRetry={() => void dashboard.refetch()} />
          </div>
          );
  }

          const data = dashboard.data;
          if (!data) {
    return (
          <div className="space-y-6">
            {header}
            <ErrorState
              title="Dashboard data was unavailable"
              error={dashboard.error ?? new Error("The API returned no dashboard data. Please retry.")}
              onRetry={() => void dashboard.refetch()}
            />
          </div>
          );
  }

          return (
          <div className="space-y-6">
            {header}

            {/* Public Demo Banner & Quick Navigation */}
            <Card className="border-primary/30 bg-primary/[0.04]">
              <CardContent className="p-5">
                <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                  <div className="space-y-1.5">
                    <div className="flex items-center gap-2">
                      <Badge
                        variant="outline"
                        className="border-primary/50 bg-primary/10 text-primary font-mono text-[10px] tracking-wider uppercase"
                      >
                        PUBLIC DEMO ENVIRONMENT
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        Workspace: <strong className="text-foreground">Continuum Demo Workspace</strong>
                      </span>
                    </div>
                    <p className="max-w-3xl text-xs leading-relaxed text-muted-foreground">
                      Everything in this workspace is <strong>synthetic demonstration data</strong> created
                      for the Continuum public evaluation. Explore reconstructed project memory, conflicting
                      architectural claims, evidence references, an approved handover, and a deterministic readiness assessment
                      without creating an account.
                    </p>
                  </div>
                  {demoProjectId ? (
                    <div className="flex shrink-0 flex-wrap gap-2">
                      <Button variant="secondary" size="sm" asChild className="text-xs">
                        <Link to={`/projects/${demoProjectId}/sources`}>
                          Sources
                        </Link>
                      </Button>
                      <Button variant="secondary" size="sm" asChild className="text-xs">
                        <Link to={`/projects/${demoProjectId}/memory`}>
                          Memory
                        </Link>
                      </Button>
                      <Button variant="secondary" size="sm" asChild className="text-xs">
                        <Link to={`/projects/${demoProjectId}/memory/conflicts`}>
                          Conflicts
                        </Link>
                      </Button>
                      <Button variant="secondary" size="sm" asChild className="text-xs">
                        <Link to={`/projects/${demoProjectId}/handover`}>
                          Handover
                        </Link>
                      </Button>
                      <Button variant="secondary" size="sm" asChild className="text-xs">
                        <Link to={`/projects/${demoProjectId}/readiness`}>
                          Readiness
                        </Link>
                      </Button>
                    </div>
                  ) : null}
                </div>
              </CardContent>
            </Card>

            {/* Synthetic project catalog: judges can explore complete scenarios without GitHub. */}
            {(demo.data?.projects?.length ?? 0) > 1 ? (
              <section className="space-y-3" aria-labelledby="demo-projects-heading">
                <div className="flex flex-wrap items-end justify-between gap-2">
                  <div>
                    <h2 id="demo-projects-heading" className="font-display text-lg font-semibold text-foreground">
                      Explore sample projects
                    </h2>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Complete synthetic scenarios with evidence, open decisions, and constraints you can investigate. No GitHub connection is needed.
                    </p>
                  </div>
                  <Badge variant="outline" className="text-[10px]">{demo.data?.projects?.length} scenarios</Badge>
                </div>
                <div className="grid gap-3 lg:grid-cols-3">
                  {demo.data?.projects?.map((sample) => (
                    <Card key={sample.id} className="flex flex-col justify-between border-border/80">
                      <CardContent className="space-y-3 p-4">
                        <div className="flex items-start justify-between gap-2">
                          <h3 className="text-sm font-medium leading-snug">{sample.name}</h3>
                          <Badge variant="secondary" className="shrink-0 text-[9px]">Synthetic</Badge>
                        </div>
                        <p className="text-[11px] leading-relaxed text-muted-foreground line-clamp-4">
                          {sample.description}
                        </p>
                        <div className="rounded-md border border-primary/20 bg-primary/[0.04] p-2.5">
                          <p className="label-eyebrow text-primary">Scenario focus</p>
                          <p className="mt-1 text-[11px] leading-relaxed text-foreground/90">{sample.focus}</p>
                        </div>
                        <Button size="sm" variant="outline" asChild className="w-full text-xs">
                          <Link to={`/projects/${sample.id}`}>
                            Explore this project <ArrowRight className="ml-1 h-3 w-3" />
                          </Link>
                        </Button>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </section>
            ) : null}

            {/* Top Level Metric Tiles */}
            <div className="panel grid sm:grid-cols-2 lg:grid-cols-4">
              <MetricTile
                label="Sample Project"
                value={demoProject?.name ?? "Payment Gateway System"}
                hint="Continuum Demo Workspace"
                icon={<FolderKanban className="h-4 w-4" />}
              />
              <MetricTile
                label="Connected Sources"
                value={data.total_sources}
                hint="GitHub PRs, commits, issues & documents"
                icon={<Database className="h-4 w-4" />}
              />
              <MetricTile
                label="Reconstructed Claims"
                value={demo.data?.counts?.claims ?? "—"}
                hint="Decisions, constraints & dependencies"
                icon={<FileSearch className="h-4 w-4" />}
              />
              <MetricTile
                label="Readiness Assessment"
                value={demo.data?.counts?.readiness_score != null ? `${demo.data.counts.readiness_score}%` : "—"}
                hint={demo.data?.counts?.readiness_score != null ? "Run 'Re-evaluate' for latest score" : "Run evaluation to see score"}
                icon={<Gauge className="h-4 w-4 text-emerald-400" />}
              />
            </div>

            {/* Velocity Chart */}
            <RepositoryActivityChart
              activity={repositoryActivity.data}
              isLoading={repositoryActivity.isLoading}
              error={repositoryActivity.error}
              onRetry={() => void repositoryActivity.refetch()}
            />

            {/* Featured Continuity Sections: Review, Conflict, Handover & Highlight */}
            {demoProjectId ? (
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                {/* Special Highlight Card: Decisions Verified by Evidence */}
                <div className="card-highlight rounded-xl border border-primary/30 p-5 flex flex-col justify-between shadow-lg">
                  <div className="space-y-2">
                    <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/40 bg-primary/10 px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider text-primary">
                      <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
                      Decisions Powered by Data
                    </div>
                    <h3 className="font-display text-base font-bold text-foreground">
                      Decisions Verified by Evidence
                    </h3>
                    <p className="text-xs leading-relaxed text-muted-foreground">
                      Continuum reconstructs architectural decisions across repositories, runbooks, and pull requests to eliminate handover risk.
                    </p>
                  </div>
                  <Button asChild size="sm" className="mt-4 self-start gap-1.5 text-xs shadow-md">
                    <Link to={`/projects/${demoProjectId}`}>
                      Explore Project
                      <ArrowRight className="h-3 w-3" />
                    </Link>
                  </Button>
                </div>

                {/* Reconstructed Memory & Review */}
                <Card className="flex flex-col justify-between">
                  <CardHeader className="space-y-1">
                    <div className="flex items-center justify-between">
                      <CardTitle className="flex items-center gap-2 text-sm font-semibold">
                        <Sparkles className="h-4 w-4 text-primary" />
                        Project Memory
                      </CardTitle>
                      <Badge variant="outline" className="font-mono text-[11px]">
                        {demo.data?.counts?.claims != null ? `${demo.data.counts.claims} CLAIMS` : "CLAIMS"}
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Extracted facts with citation evidence spans from commits, pull requests, and architecture specs.
                    </p>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="rounded-md border border-border/70 bg-card/40 p-2.5 text-xs">
                      <span className="font-mono text-[10px] uppercase text-primary font-semibold">Sample Claim:</span>
                      <p className="mt-1 line-clamp-2 text-foreground text-xs">
                        "Stripe and Adyen are configured with automatic failover if API latency exceeds 800ms."
                      </p>
                    </div>
                    <div className="flex items-center justify-between pt-1">
                      <Button variant="ghost" size="sm" asChild className="text-xs">
                        <Link to={`/projects/${demoProjectId}/memory/review`}>
                          Review Queue
                          <ArrowRight className="h-3 w-3 ml-1" />
                        </Link>
                      </Button>
                      <Button variant="outline" size="sm" asChild className="text-xs">
                        <Link to={`/projects/${demoProjectId}/memory`}>
                          Browse Claims
                        </Link>
                      </Button>
                    </div>
                  </CardContent>
                </Card>

                {/* Conflict Centre */}
                <Card className="flex flex-col justify-between">
                  <CardHeader className="space-y-1">
                    <div className="flex items-center justify-between">
                      <CardTitle className="flex items-center gap-2 text-sm font-semibold">
                        <Scale className="h-4 w-4 text-amber-400" />
                        Conflict Centre
                      </CardTitle>
                      <Badge variant="warn" className="font-mono text-[11px]">
                        1 OPEN CONFLICT
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Automated detection of contradictory statements across independent sources.
                    </p>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-2.5 text-xs">
                      <div className="flex items-center gap-1.5 font-mono text-[10px] uppercase text-amber-400 font-semibold">
                        <AlertTriangle className="h-3 w-3" />
                        PostgreSQL Version Disagreement
                      </div>
                      <p className="mt-1 text-muted-foreground text-xs">
                        Architecture spec claims v14; Docker Compose specifies v16.
                      </p>
                    </div>
                    <div className="flex items-center justify-end pt-1">
                      <Button variant="outline" size="sm" asChild className="text-xs">
                        <Link to={`/projects/${demoProjectId}/memory/conflicts`}>
                          Compare Conflicting Claims
                          <ArrowRight className="h-3 w-3 ml-1" />
                        </Link>
                      </Button>
                    </div>
                  </CardContent>
                </Card>

                {/* Approved Handover & Readiness */}
                <Card className="flex flex-col justify-between">
                  <CardHeader className="space-y-1">
                    <div className="flex items-center justify-between">
                      <CardTitle className="flex items-center gap-2 text-sm font-semibold">
                        <FileCheck className="h-4 w-4 text-emerald-400" />
                        Approved Handover
                      </CardTitle>
                      <Badge variant="ok" className="font-mono text-[11px]">
                        PUBLISHED V1
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Synthesised brief containing architectural consensus, operational runbooks, and risk boundaries.
                    </p>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="rounded-md border border-border/70 bg-card/40 p-2.5 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-foreground text-xs">Payment Gateway Handover</span>
                        <Badge variant="outline" className="font-mono text-[11px] text-emerald-400 border-emerald-500/30">
                          Score: 98.2
                        </Badge>
                      </div>
                      <p className="mt-1 text-muted-foreground text-[11px]">
                        4 successor tasks derived · 12 knowledge risk gaps tracked
                      </p>
                    </div>
                    <div className="flex items-center justify-between pt-1">
                      <Button variant="ghost" size="sm" asChild className="text-xs">
                        <Link to={`/projects/${demoProjectId}/readiness`}>
                          Readiness Report
                        </Link>
                      </Button>
                      <Button size="sm" asChild className="text-xs">
                        <Link to={`/projects/${demoProjectId}/handover`}>
                          Read Handover
                          <ArrowRight className="h-3 w-3 ml-1" />
                        </Link>
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              </div>
            ) : null}

            {/* Ingestion Status Breakdown */}
            <div className="space-y-3">
              <h2 className="font-display text-lg font-semibold text-foreground">Ingestion status</h2>
                <div className="grid gap-3 lg:grid-cols-2">
                  <Breakdown
                    title="Sources by type"
                    icon={<Layers className="h-3.5 w-3.5" />}
                    counts={data.source_type_counts}
                    emptyLabel="No sources ingested yet."
                    labelFor={(key) => SOURCE_TYPE_META[key as SourceType]?.label ?? key}
                  />
                  <Breakdown
                    title="Processing status"
                    icon={<CircleDashed className="h-3.5 w-3.5" />}
                    counts={data.processing_status_counts}
                    emptyLabel="Nothing has been ingested yet."
                    labelFor={(key) => PROCESSING_STATUS_META[key as ProcessingStatus]?.label ?? key}
                  />
                </div>
              </div>

            {/* Recent Projects List */}
            <Card>
              <CardHeader className="flex-row items-center justify-between space-y-0">
                <CardTitle className="text-xs font-medium text-muted-foreground">
                  Demonstration project
                </CardTitle>
                <Button variant="ghost" size="sm" asChild>
                  <Link to="/projects">
                    All projects
                    <ArrowRight className="h-3.5 w-3.5 ml-1" />
                  </Link>
                </Button>
              </CardHeader>
              <CardContent>
                {data.recent_projects.length === 0 ? (
                  <EmptyState
                    icon={<FolderKanban className="h-4 w-4" />}
                    title="No demo projects found"
                    description="Click 'Reset demo data' above to rebuild the synthetic demo workspace."
                  />
                ) : (
                  <ul className="divide-y divide-border/70">
                    {data.recent_projects.map((project) => (
                      <li key={project.id}>
                        <Link
                          to={`/projects/${project.id}`}
                          className="flex items-center justify-between gap-4 py-3 transition-colors hover:bg-accent/30"
                        >
                          <div className="min-w-0">
                            <p className="truncate text-sm font-medium">{project.name}</p>
                            <p className="mt-0.5 truncate text-xs text-muted-foreground">
                              {project.description || "Synthetic payments backend with multi-gateway failover."}
                            </p>
                          </div>
                          <div className="flex shrink-0 items-center gap-3">
                            <span className="hidden text-xs tabular-nums text-muted-foreground sm:inline">
                              {project.source_count} sources
                            </span>
                            <ProjectStatusBadge status={project.status} />
                          </div>
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>

            {/* Recent Source Activity Table */}
            <Card>
                <CardHeader className="flex-row items-center justify-between space-y-0">
                  <CardTitle className="text-xs font-medium text-muted-foreground">
                    Ingested synthetic sources
                  </CardTitle>
                  {demoProjectId ? (
                    <Button variant="ghost" size="sm" asChild>
                      <Link to={`/projects/${demoProjectId}/sources`}>
                        Source library
                        <ArrowRight className="h-3.5 w-3.5 ml-1" />
                      </Link>
                    </Button>
                  ) : null}
                </CardHeader>
                <CardContent>
                  {data.recent_sources.length === 0 ? (
                    <p className="text-xs text-muted-foreground">
                      Ingestion activity appears here once sources are added.
                    </p>
                  ) : (
                    <Table>
                      <TableHeader>
                        <TableRow className="hover:bg-transparent">
                          <TableHead>Source</TableHead>
                          <TableHead className="hidden sm:table-cell">Type</TableHead>
                          <TableHead className="hidden md:table-cell">Project</TableHead>
                          <TableHead>Status</TableHead>
                          <TableHead className="text-right">When</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {data.recent_sources.map((source) => (
                          <TableRow key={source.id}>
                            <TableCell className="max-w-[220px]">
                              <Link
                                to={`/sources/${source.id}`}
                                className="block truncate text-sm hover:text-primary"
                              >
                                {source.source_name}
                              </Link>
                            </TableCell>
                            <TableCell className="hidden sm:table-cell">
                              <SourceTypeBadge sourceType={source.source_type} />
                            </TableCell>
                            <TableCell className="hidden max-w-[180px] md:table-cell">
                              <Link
                                to={`/projects/${source.project_id}`}
                                className="block truncate text-xs text-muted-foreground hover:text-foreground"
                              >
                                {source.project_name}
                              </Link>
                            </TableCell>
                            <TableCell>
                              <ProcessingStatusBadge status={source.processing_status} />
                            </TableCell>
                            <TableCell className="text-right text-xs text-muted-foreground">
                              {formatRelative(source.created_at)}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  )}
                </CardContent>
            </Card>
          </div>
          );
}
