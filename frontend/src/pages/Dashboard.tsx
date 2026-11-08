import * as React from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  CircleDashed,
  Database,
  FolderKanban,
  GitBranch,
  Layers,
  Plus,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState, ErrorState } from "@/components/common/States";
import { MetricTile, PageHeader } from "@/components/common/PageHeader";
import {
  ProcessingStatusBadge,
  ProjectStatusBadge,
  SourceTypeBadge,
} from "@/components/common/StatusBadge";
import { WorkspaceCreateDialog } from "@/components/common/WorkspaceCreateDialog";
import { useDashboard } from "@/hooks/use-dashboard";
import { useWorkspaces } from "@/hooks/use-workspaces";
import { formatRelative } from "@/lib/format";
import {
  PROCESSING_STATUS_META,
  SOURCE_TYPE_META,
  SOURCE_TYPE_ORDER,
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

export default function Dashboard() {
  const dashboard = useDashboard();
  const workspaces = useWorkspaces();
  const [createWorkspaceOpen, setCreateWorkspaceOpen] = React.useState(false);

  const hasWorkspaces = (workspaces.data?.length ?? 0) > 0;
  const isEmptyAccount =
    workspaces.isSuccess && !hasWorkspaces && (dashboard.data?.total_projects ?? 0) === 0;

  const header = (
    <PageHeader
      eyebrow="Overview"
      title="Dashboard"
      description="Live totals computed from PostgreSQL. Every number below is read from the API — nothing here is mocked."
      actions={
        <>
          <Button variant="outline" size="sm" onClick={() => setCreateWorkspaceOpen(true)}>
            <Layers className="h-4 w-4" />
            New workspace
          </Button>
          <Button size="sm" asChild>
            <Link to="/projects/new">
              <Plus className="h-4 w-4" />
              New project
            </Link>
          </Button>
        </>
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

      {isEmptyAccount ? (
        <Card className="border-primary/25 bg-primary/[0.04]">
          <CardHeader>
            <CardTitle className="text-sm">Start with a workspace</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="max-w-xl text-xs leading-relaxed text-muted-foreground">
              Projects are always created inside a workspace, and the backend verifies your
              membership on every request. Create one to begin connecting sources.
            </p>
            <Button size="sm" onClick={() => setCreateWorkspaceOpen(true)}>
              <Layers className="h-4 w-4" />
              Create workspace
            </Button>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MetricTile
          label="Projects"
          value={data.total_projects}
          hint={`${data.total_workspaces} workspace${data.total_workspaces === 1 ? "" : "s"}`}
          icon={<FolderKanban className="h-4 w-4" />}
        />
        <MetricTile
          label="Connected sources"
          value={data.total_sources}
          hint="Normalised and stored in PostgreSQL"
          icon={<Database className="h-4 w-4" />}
        />
        <MetricTile
          label="Repositories"
          value={data.total_connected_repositories}
          hint="GitHub repositories linked to projects"
          icon={<GitBranch className="h-4 w-4" />}
        />
        <MetricTile
          label="Processing completed"
          value={data.processing_status_counts.completed ?? 0}
          hint={
            (data.processing_status_counts.failed ?? 0) > 0
              ? `${data.processing_status_counts.failed} failed — review in the source library`
              : "No failed ingests"
          }
          icon={<CircleDashed className="h-4 w-4" />}
        />
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <Breakdown
          title="Sources by type"
          icon={<Layers className="h-3.5 w-3.5" />}
          counts={data.source_type_counts}
          emptyLabel="No sources ingested yet. Connect a repository or upload documents."
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

      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle className="text-xs font-medium text-muted-foreground">
            Recent projects
          </CardTitle>
          <Button variant="ghost" size="sm" asChild>
            <Link to="/projects">
              All projects
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </Button>
        </CardHeader>
        <CardContent>
          {data.recent_projects.length === 0 ? (
            <EmptyState
              icon={<FolderKanban className="h-4 w-4" />}
              title="No projects yet"
              description="Create a project to group the sources that describe a piece of work."
              action={
                <Button size="sm" asChild>
                  <Link to="/projects/new">
                    <Plus className="h-4 w-4" />
                    New project
                  </Link>
                </Button>
              }
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
                        {project.description || "No description"}
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

      <Card>
        <CardHeader>
          <CardTitle className="text-xs font-medium text-muted-foreground">
            Recent ingestion activity
          </CardTitle>
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

      <Card className="border-dashed">
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle className="text-xs font-medium text-muted-foreground">
            Project memory
          </CardTitle>
          <Badge variant="secondary">Upcoming</Badge>
        </CardHeader>
        <CardContent className="space-y-2">
          <p className="text-xs leading-relaxed text-muted-foreground">
            The following capabilities are part of Phase 3 and are not implemented in this build.
            The typed contracts they will use already exist.
          </p>
          <ul className="grid gap-1.5 sm:grid-cols-3">
            {data.upcoming.map((item) => (
              <li
                key={item}
                className="flex items-center gap-2 rounded-md border border-border/70 bg-card/40 px-2.5 py-2 text-[11px] text-muted-foreground"
              >
                <CircleDashed className="h-3.5 w-3.5" />
                {item}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <WorkspaceCreateDialog open={createWorkspaceOpen} onOpenChange={setCreateWorkspaceOpen} />
    </div>
  );
}
