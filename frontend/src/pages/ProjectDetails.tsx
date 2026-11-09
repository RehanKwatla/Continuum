import * as React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Brain,
  CircleDashed,
  Database,
  ExternalLink,
  FileUp,
  FolderKanban,
  GitBranch,
  Layers,
  ListChecks,
  ScrollText,
  Trash2,
  TriangleAlert,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { ProjectWorkspaceNav } from "@/components/common/ProjectWorkspaceNav";
import { EmptyState, ErrorState } from "@/components/common/States";
import { MetricTile, PageHeader } from "@/components/common/PageHeader";
import { ProjectStatusBadge } from "@/components/common/StatusBadge";
import { Tooltip } from "@/components/common/Tooltip";
import { useToast } from "@/components/ui/toast";
import { useDeleteProject, useProject } from "@/hooks/use-projects";
import { usePageTitle } from "@/hooks/use-page-title";
import { formatDateTime, formatRelative } from "@/lib/format";
import { PROCESSING_STATUS_META, SOURCE_TYPE_META } from "@/lib/source-meta";
import { toErrorMessage } from "@/services/api";
import type { ProcessingStatus, SourceType } from "@/types";

function DefinitionRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-6 border-b border-border/60 py-2.5 last:border-0">
      <span className="shrink-0 text-xs text-muted-foreground">{label}</span>
      <span className="min-w-0 text-right text-xs">{children}</span>
    </div>
  );
}

export default function ProjectDetails() {
  const { projectId } = useParams<{ projectId: string }>();
  const project = useProject(projectId);
  usePageTitle(project.data?.name ?? "Project");
  const navigate = useNavigate();
  const { toast } = useToast();
  const deleteProject = useDeleteProject();
  const [confirmOpen, setConfirmOpen] = React.useState(false);

  const handleDelete = async () => {
    if (!projectId) return;
    try {
      await deleteProject.mutateAsync(projectId);
      toast({ title: "Project deleted", variant: "success" });
      navigate("/projects", { replace: true });
    } catch (caught) {
      toast({ title: "Could not delete project", description: toErrorMessage(caught), variant: "error" });
      setConfirmOpen(false);
    }
  };

  if (project.isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-16 w-full" />
        <div className="grid gap-3 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-24 rounded-lg" />
          ))}
        </div>
        <Skeleton className="h-64 rounded-lg" />
      </div>
    );
  }

  if (project.isError) {
    return (
      <div className="space-y-6">
        <PageHeader eyebrow="Project" title="Project unavailable" />
        <ErrorState
          error={project.error}
          title="This project could not be loaded"
          onRetry={() => void project.refetch()}
        />
        <Button variant="outline" size="sm" asChild>
          <Link to="/projects">
            <ArrowLeft className="h-4 w-4" />
            Back to projects
          </Link>
        </Button>
      </div>
    );
  }

  const data = project.data;
  if (!data) return null;

  const totalSources = Object.values(data.source_type_counts).reduce((sum, value) => sum + value, 0);
  const failedCount = data.processing_status_counts.failed ?? 0;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Project"
        title={data.name}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <ProjectStatusBadge status={data.status} />
            <span className="text-xs text-muted-foreground">
              {data.workspace?.name ?? "Workspace"} · created {formatDateTime(data.created_at)}
            </span>
          </span>
        }
        actions={
          <>
            <Button variant="ghost" size="sm" asChild>
              <Link to="/projects">
                <ArrowLeft className="h-4 w-4" />
                Projects
              </Link>
            </Button>
            <Button variant="outline" size="sm" asChild>
              <Link to={`/projects/${data.id}/sources/github`}>
                <GitBranch className="h-4 w-4" />
                Connect GitHub
              </Link>
            </Button>
            <Button size="sm" asChild>
              <Link to={`/projects/${data.id}/sources/upload`}>
                <FileUp className="h-4 w-4" />
                Upload files
              </Link>
            </Button>
          </>
        }
      />

      <ProjectWorkspaceNav projectId={data.id} />

      <div className="grid gap-3 sm:grid-cols-3">
        <MetricTile
          label="Sources"
          value={data.source_count}
          hint={`${totalSources} recorded by type`}
          icon={<Database className="h-4 w-4" />}
        />
        <MetricTile
          label="Repositories"
          value={data.repository_count}
          hint="GitHub repositories linked"
          icon={<GitBranch className="h-4 w-4" />}
        />
        <MetricTile
          label="Failed ingests"
          value={failedCount}
          hint={failedCount ? "Open the source library to review" : "All ingests clean"}
          icon={<CircleDashed className="h-4 w-4" />}
        />
      </div>

      {failedCount > 0 ? (
        <div className="panel flex flex-col items-start gap-3 border-status-danger/35 bg-status-danger/[0.06] p-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs leading-relaxed text-muted-foreground">
            {failedCount} source{failedCount === 1 ? "" : "s"} failed to process. Failures are kept
            with their error message rather than being silently dropped.
          </p>
          <Button variant="outline" size="sm" asChild>
            <Link to={`/projects/${data.id}/sources?processing_status=failed`}>Review failures</Link>
          </Button>
        </div>
      ) : null}

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader>
            <CardTitle className="text-xs font-medium text-muted-foreground">Overview</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs leading-relaxed text-muted-foreground">
              {data.description || "No description has been recorded for this project."}
            </p>
            <div className="mt-4">
              <DefinitionRow label="Workspace">{data.workspace?.name ?? "—"}</DefinitionRow>
              <DefinitionRow label="Departing role">{data.departing_role || "—"}</DefinitionRow>
              <DefinitionRow label="Successor role">{data.successor_role || "—"}</DefinitionRow>
              <DefinitionRow label="Created">{formatDateTime(data.created_at)}</DefinitionRow>
              <DefinitionRow label="Last updated">{formatRelative(data.updated_at)}</DefinitionRow>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle className="text-xs font-medium text-muted-foreground">
              Sources by type
            </CardTitle>
            <Button variant="ghost" size="sm" asChild>
              <Link to={`/projects/${data.id}/sources`}>Library</Link>
            </Button>
          </CardHeader>
          <CardContent>
            {Object.keys(data.source_type_counts).length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No sources yet. Connect a repository or upload documents to begin.
              </p>
            ) : (
              <ul className="space-y-2">
                {Object.entries(data.source_type_counts)
                  .sort((a, b) => b[1] - a[1])
                  .map(([key, value]) => {
                    const meta = SOURCE_TYPE_META[key as SourceType];
                    const Icon = meta?.Icon ?? Layers;
                    return (
                      <li key={key} className="flex items-center justify-between text-xs">
                        <span className="flex items-center gap-2 text-muted-foreground">
                          <Icon className="h-3.5 w-3.5" />
                          {meta?.label ?? key}
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

      <Card>
        <CardHeader>
          <CardTitle className="text-xs font-medium text-muted-foreground">
            Connected repositories
          </CardTitle>
        </CardHeader>
        <CardContent>
          {data.repositories.length === 0 ? (
            <EmptyState
              icon={<GitBranch className="h-4 w-4" />}
              title="No repository connected"
              description="Import commits, issues and pull requests through GitHub OAuth. Access is limited to repositories you authorise."
              action={
                <Button size="sm" asChild>
                  <Link to={`/projects/${data.id}/sources/github`}>Connect a repository</Link>
                </Button>
              }
            />
          ) : (
            <ul className="divide-y divide-border/70">
              {data.repositories.map((repository) => (
                <li key={repository.id} className="flex items-center justify-between gap-4 py-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{repository.full_name}</p>
                    <p className="mt-0.5 truncate text-xs text-muted-foreground">
                      {repository.description || "No description"} ·{" "}
                      {repository.is_private ? "Private" : "Public"}
                      {repository.default_branch ? ` · ${repository.default_branch}` : ""}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className="hidden text-[11px] text-muted-foreground sm:inline">
                      {formatRelative(repository.connected_at)}
                    </span>
                    {repository.html_url ? (
                      <Tooltip label="Open on GitHub">
                        <Button variant="ghost" size="icon" asChild>
                          <a
                            href={repository.html_url}
                            target="_blank"
                            rel="noreferrer noopener"
                            aria-label={`Open ${repository.full_name} on GitHub`}
                          >
                            <ExternalLink className="h-4 w-4" />
                          </a>
                        </Button>
                      </Tooltip>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-xs font-medium text-muted-foreground">
            Processing status
          </CardTitle>
        </CardHeader>
        <CardContent>
          {Object.keys(data.processing_status_counts).length === 0 ? (
            <p className="text-xs text-muted-foreground">Nothing ingested yet.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {Object.entries(data.processing_status_counts).map(([key, value]) => (
                <span
                  key={key}
                  className="inline-flex items-center gap-2 rounded-md border border-border/70 bg-card/40 px-2.5 py-1.5 text-xs"
                >
                  <span className="text-muted-foreground">
                    {PROCESSING_STATUS_META[key as ProcessingStatus]?.label ?? key}
                  </span>
                  <span className="tabular-nums">{value}</span>
                </span>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle className="text-xs font-medium text-muted-foreground">
            Project memory
          </CardTitle>
          <Button variant="ghost" size="sm" asChild>
            <Link to={`/projects/${data.id}/memory`}>Open</Link>
          </Button>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xs leading-relaxed text-muted-foreground">
            Reconstruct project knowledge from this project&apos;s authorised sources. Every claim
            links back to the exact passage it came from, and only a human reviewer can mark a claim{" "}
            <span className="text-foreground">Verified</span>.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" asChild>
              <Link to={`/projects/${data.id}/memory`}>
                <Brain className="h-4 w-4" />
                Memory
              </Link>
            </Button>
            <Button variant="outline" size="sm" asChild>
              <Link to={`/projects/${data.id}/memory/claims`}>
                <ListChecks className="h-4 w-4" />
                Claims
              </Link>
            </Button>
            <Button variant="outline" size="sm" asChild>
              <Link to={`/projects/${data.id}/memory/conflicts`}>
                <TriangleAlert className="h-4 w-4" />
                Conflicts
              </Link>
            </Button>
            <Button variant="outline" size="sm" asChild>
              <Link to={`/projects/${data.id}/handover`}>
                <ScrollText className="h-4 w-4" />
                Handover
              </Link>
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="flex items-center justify-between border-t border-border/70 pt-4">
        <div>
          <p className="text-xs font-medium">Delete this project</p>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            Requires the admin role in this workspace. Sources and repository links are removed.
          </p>
        </div>
        <Button variant="destructive" size="sm" onClick={() => setConfirmOpen(true)}>
          <Trash2 className="h-4 w-4" />
          Delete
        </Button>
      </div>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Delete project?"
        description={
          <>
            <strong className="text-foreground">{data.name}</strong> and all of its{" "}
            {data.source_count} source{data.source_count === 1 ? "" : "s"} will be permanently
            removed. This cannot be undone.
          </>
        }
        confirmLabel="Delete project"
        destructive
        busy={deleteProject.isPending}
        onConfirm={() => void handleDelete()}
      />

      <p className="flex items-center gap-2 text-[11px] text-muted-foreground">
        <FolderKanban className="h-3.5 w-3.5" />
        Project id <span className="mono">{data.id}</span>
      </p>
    </div>
  );
}
