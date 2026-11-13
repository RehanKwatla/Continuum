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
import { useDashboard } from "@/hooks/use-dashboard";
import { usePageTitle } from "@/hooks/use-page-title";
import { usePublicDemo, useResetPublicDemo } from "@/hooks/use-demo";
import { useWorkspaces } from "@/hooks/use-workspaces";
import { formatRelative } from "@/lib/format";
import {
  PROCESSING_STATUS_META,
  SOURCE_TYPE_META,
} from "@/lib/source-meta";
import type { ProcessingStatus, SourceType } from "@/types";

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

function VelocityChart({ score }: { score: number | string }) {
  const [range, setRange] = React.useState<"1D" | "1W" | "1M" | "6M" | "1Y">("1M");
  const ranges = ["1D", "1W", "1M", "6M", "1Y"] as const;

  return (
    <Card className="overflow-hidden border-border bg-card shadow-sm">
      <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between space-y-0 pb-3">
        <div>
          <CardTitle className="text-base font-semibold text-foreground">
            Continuity &amp; Verification Velocity
          </CardTitle>
          <CardDescription className="text-xs text-muted-foreground mt-0.5">
            Deterministic claim verification rate, evidence linkage, and handover maturity trajectory
          </CardDescription>
        </div>
        <div className="flex items-center gap-1 rounded-lg border border-border bg-secondary/80 p-1">
          {ranges.map((r) => (
            <button
              key={r}
              type="button"
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
      <CardContent className="pt-2">
        <div className="relative h-52 w-full">
          <svg viewBox="0 0 820 220" className="h-full w-full overflow-visible" preserveAspectRatio="none">
            <defs>
              <linearGradient id="velocityGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#C995BC" stopOpacity="0.30" />
                <stop offset="65%" stopColor="#8E738B" stopOpacity="0.08" />
                <stop offset="100%" stopColor="#18131E" stopOpacity="0.0" />
              </linearGradient>
              <filter id="velocityGlow" x="-20%" y="-20%" width="140%" height="140%">
                <feGaussianBlur stdDeviation="4" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            {/* Grid horizontal guidelines */}
            <line x1="20" y1="30" x2="800" y2="30" stroke="rgba(142, 115, 139, 0.14)" strokeDasharray="3,3" />
            <line x1="20" y1="85" x2="800" y2="85" stroke="rgba(142, 115, 139, 0.14)" strokeDasharray="3,3" />
            <line x1="20" y1="140" x2="800" y2="140" stroke="rgba(142, 115, 139, 0.14)" strokeDasharray="3,3" />
            <line x1="20" y1="195" x2="800" y2="195" stroke="rgba(142, 115, 139, 0.22)" />

            {/* Area fill under curve */}
            <path
              d="M 20 65 Q 60 75, 110 110 T 200 130 T 290 145 T 380 135 T 470 142 T 560 115 T 650 135 T 740 120 T 800 60 L 800 195 L 20 195 Z"
              fill="url(#velocityGrad)"
            />

            {/* Stroke path */}
            <path
              d="M 20 65 Q 60 75, 110 110 T 200 130 T 290 145 T 380 135 T 470 142 T 560 115 T 650 135 T 740 120 T 800 60"
              fill="none"
              stroke="#C995BC"
              strokeWidth="2.6"
              filter="url(#velocityGlow)"
              strokeLinecap="round"
            />

            {/* Vertical dashed checkpoint guideline at peak */}
            <line
              x1="560"
              y1="20"
              x2="560"
              y2="195"
              stroke="#8E738B"
              strokeWidth="1.5"
              strokeDasharray="4,4"
              strokeOpacity="0.7"
            />

            {/* Checkpoint node circle */}
            <circle cx="560" cy="115" r="5" fill="#C995BC" filter="url(#velocityGlow)" />
            <circle cx="560" cy="115" r="9" fill="none" stroke="#C995BC" strokeWidth="1.8" strokeOpacity="0.6" />
          </svg>

          {/* Floating glass tooltip */}
          <div className="absolute left-[64%] top-[14px] rounded-lg border border-border/80 bg-card/95 px-3 py-2 shadow-xl backdrop-blur-md">
            <div className="text-[11px] font-mono text-muted-foreground">Active Milestone • Handover Verified</div>
            <div className="mt-1 flex items-center gap-2">
              <span className="text-sm font-bold text-foreground">{score}% Verified</span>
              <span className="rounded bg-emerald-500/15 border border-emerald-500/30 px-1.5 py-0.5 text-[11px] font-medium text-emerald-400">
                +3.5%
              </span>
            </div>
          </div>
        </div>

        {/* Month labels */}
        <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground/80 font-mono px-2">
          <span>Jan</span><span>Feb</span><span>Mar</span><span>Apr</span><span>May</span>
          <span className="font-bold text-primary">Jun</span>
          <span>Jul</span><span>Aug</span><span>Sep</span><span>Oct</span><span>Nov</span><span>Dec</span>
        </div>
      </CardContent>
    </Card>
  );
}

export default function Dashboard() {
  usePageTitle("Dashboard");
  const dashboard = useDashboard();
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

          if (dashboard.isLoading) {
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

          if (dashboard.isError) {
    return (
          <div className="space-y-6">
            {header}
            <ErrorState error={dashboard.error} onRetry={() => void dashboard.refetch()} />
          </div>
          );
  }

          const data = dashboard.data;
          if (!data) return null;

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
            <VelocityChart score={demo.data?.counts?.readiness_score ?? "98.2"} />

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
