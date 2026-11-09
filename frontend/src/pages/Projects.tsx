import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ChevronLeft, ChevronRight, FolderKanban, Plus, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { EmptyState, ErrorState } from "@/components/common/States";
import { PageHeader, TableSkeleton } from "@/components/common/PageHeader";
import { ProjectStatusBadge } from "@/components/common/StatusBadge";
import { WorkspaceCreateDialog } from "@/components/common/WorkspaceCreateDialog";
import { useProjects } from "@/hooks/use-projects";
import { usePageTitle } from "@/hooks/use-page-title";
import { useWorkspaces } from "@/hooks/use-workspaces";
import { formatRelative, pluralise } from "@/lib/format";
import { PROJECT_STATUS_META } from "@/lib/source-meta";
import type { ProjectStatus } from "@/types";

const ALL = "__all__";
const PAGE_SIZE = 20;

export default function Projects() {
  usePageTitle("Projects");
  const [search, setSearch] = React.useState("");
  const [searchParams] = useSearchParams();
  const [workspaceId, setWorkspaceId] = React.useState<string>(
    searchParams.get("workspace_id") ?? ALL,
  );
  const [status, setStatus] = React.useState<string>(ALL);
  const [page, setPage] = React.useState(1);
  const [createWorkspaceOpen, setCreateWorkspaceOpen] = React.useState(false);

  const workspaces = useWorkspaces();

  const params = React.useMemo(
    () => ({
      search: search.trim() || undefined,
      workspace_id: workspaceId === ALL ? undefined : workspaceId,
      status: status === ALL ? undefined : (status as ProjectStatus),
      page,
      page_size: PAGE_SIZE,
    }),
    [search, workspaceId, status, page],
  );

  const projects = useProjects(params);

  React.useEffect(() => {
    setPage(1);
  }, [search, workspaceId, status]);

  React.useEffect(() => {
    const fromUrl = searchParams.get("workspace_id");
    if (fromUrl) setWorkspaceId(fromUrl);
  }, [searchParams]);

  const workspaceNames = React.useMemo(() => {
    const map = new Map<string, string>();
    for (const workspace of workspaces.data ?? []) map.set(workspace.id, workspace.name);
    return map;
  }, [workspaces.data]);

  const header = (
    <PageHeader
      eyebrow="Workspace"
      title="Projects"
      description="Each project groups the repositories and documents that describe one piece of work."
      actions={
        <>
          {workspaces.isSuccess && (workspaces.data?.length ?? 0) === 0 ? (
            <Button variant="outline" size="sm" onClick={() => setCreateWorkspaceOpen(true)}>
              Create workspace
            </Button>
          ) : null}
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

  return (
    <div className="space-y-6">
      {header}

      <Card className="p-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search projects"
              className="pl-8"
              aria-label="Search projects"
            />
          </div>
          <Select value={workspaceId} onValueChange={setWorkspaceId}>
            <SelectTrigger className="sm:w-[200px]" aria-label="Filter by workspace">
              <SelectValue placeholder="All workspaces" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All workspaces</SelectItem>
              {(workspaces.data ?? []).map((workspace) => (
                <SelectItem key={workspace.id} value={workspace.id}>
                  {workspace.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="sm:w-[190px]" aria-label="Filter by status">
              <SelectValue placeholder="Any status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>Any status</SelectItem>
              {(Object.keys(PROJECT_STATUS_META) as ProjectStatus[]).map((key) => (
                <SelectItem key={key} value={key}>
                  {PROJECT_STATUS_META[key].label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </Card>

      {projects.isLoading ? <TableSkeleton columns={["Project", "Workspace", "Sources", "Status", "Updated"]} /> : null}

      {projects.isError ? (
        <ErrorState error={projects.error} onRetry={() => void projects.refetch()} />
      ) : null}

      {projects.isSuccess && projects.data.items.length === 0 ? (
        <EmptyState
          icon={<FolderKanban className="h-4 w-4" />}
          title={search || workspaceId !== ALL || status !== ALL ? "No matching projects" : "No projects yet"}
          description={
            search || workspaceId !== ALL || status !== ALL
              ? "Adjust the filters to see other projects."
              : "Create your first project, then connect a repository or upload documents."
          }
          action={
            <Button size="sm" asChild>
              <Link to="/projects/new">
                <Plus className="h-4 w-4" />
                New project
              </Link>
            </Button>
          }
        />
      ) : null}

      {projects.isSuccess && projects.data.items.length > 0 ? (
        <Card className="overflow-hidden p-0">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Project</TableHead>
                <TableHead className="hidden md:table-cell">Workspace</TableHead>
                <TableHead className="text-right">Sources</TableHead>
                <TableHead className="hidden sm:table-cell text-right">Repos</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="hidden lg:table-cell text-right">Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {projects.data.items.map((project) => (
                <TableRow key={project.id}>
                  <TableCell className="max-w-[280px]">
                    <Link to={`/projects/${project.id}`} className="block group">
                      <span className="block truncate text-sm font-medium group-hover:text-primary">
                        {project.name}
                      </span>
                      <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                        {project.description || "No description"}
                      </span>
                    </Link>
                  </TableCell>
                  <TableCell className="hidden max-w-[180px] md:table-cell">
                    <span className="block truncate text-xs text-muted-foreground">
                      {workspaceNames.get(project.workspace_id) ?? "—"}
                    </span>
                  </TableCell>
                  <TableCell className="text-right text-sm tabular-nums">
                    {project.source_count}
                  </TableCell>
                  <TableCell className="hidden text-right text-sm tabular-nums sm:table-cell">
                    {project.repository_count}
                  </TableCell>
                  <TableCell>
                    <ProjectStatusBadge status={project.status} />
                  </TableCell>
                  <TableCell className="hidden text-right text-xs text-muted-foreground lg:table-cell">
                    {formatRelative(project.updated_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      ) : null}

      {projects.isSuccess && projects.data.meta.total > 0 ? (
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>
            {pluralise(projects.data.meta.total, "project")} · page {projects.data.meta.page} of{" "}
            {Math.max(projects.data.meta.total_pages, 1)}
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={!projects.data.meta.has_previous}
              onClick={() => setPage((current) => Math.max(current - 1, 1))}
            >
              <ChevronLeft className="h-3.5 w-3.5" />
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={!projects.data.meta.has_next}
              onClick={() => setPage((current) => current + 1)}
            >
              Next
              <ChevronRight className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      ) : null}

      <WorkspaceCreateDialog open={createWorkspaceOpen} onOpenChange={setCreateWorkspaceOpen} />
    </div>
  );
}
