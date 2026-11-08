import * as React from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  FileUp,
  GitBranch,
  Search,
  Trash2,
  Upload,
} from "lucide-react";

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
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { EmptyState, ErrorState } from "@/components/common/States";
import { PageHeader, TableSkeleton } from "@/components/common/PageHeader";
import { ProjectWorkspaceNav } from "@/components/common/ProjectWorkspaceNav";
import { ProcessingStatusBadge, SourceTypeBadge } from "@/components/common/StatusBadge";
import { Tooltip } from "@/components/common/Tooltip";
import { useToast } from "@/components/ui/toast";
import { useProject } from "@/hooks/use-projects";
import { useDeleteSource, useSources } from "@/hooks/use-sources";
import { formatRelative, pluralise } from "@/lib/format";
import {
  PROCESSING_STATUS_META,
  SOURCE_TYPE_META,
  SOURCE_TYPE_ORDER,
} from "@/lib/source-meta";
import { toErrorMessage } from "@/services/api";
import type { ProcessingStatus, SourceType } from "@/types";

const ALL = "__all__";
const PAGE_SIZE = 25;

export default function SourceLibrary() {
  const { projectId } = useParams<{ projectId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const { toast } = useToast();

  const [search, setSearch] = React.useState("");
  const [sourceType, setSourceType] = React.useState<string>(
    searchParams.get("source_type") ?? ALL,
  );
  const [processingStatus, setProcessingStatus] = React.useState<string>(
    searchParams.get("processing_status") ?? ALL,
  );
  const [page, setPage] = React.useState(1);
  const [pendingDelete, setPendingDelete] = React.useState<{ id: string; name: string } | null>(null);

  const project = useProject(projectId);
  const deleteSource = useDeleteSource(projectId ?? "");

  const params = React.useMemo(
    () => ({
      search: search.trim() || undefined,
      source_type: sourceType === ALL ? undefined : (sourceType as SourceType),
      processing_status:
        processingStatus === ALL ? undefined : (processingStatus as ProcessingStatus),
      page,
      page_size: PAGE_SIZE,
    }),
    [search, sourceType, processingStatus, page],
  );

  const sources = useSources(projectId, params);

  React.useEffect(() => {
    setPage(1);
  }, [search, sourceType, processingStatus]);

  // Keep the URL in step with the active filters so links are shareable.
  React.useEffect(() => {
    const next = new URLSearchParams();
    if (sourceType !== ALL) next.set("source_type", sourceType);
    if (processingStatus !== ALL) next.set("processing_status", processingStatus);
    setSearchParams(next, { replace: true });
  }, [sourceType, processingStatus, setSearchParams]);

  const handleDelete = async () => {
    if (!pendingDelete) return;
    try {
      await deleteSource.mutateAsync(pendingDelete.id);
      toast({ title: "Source removed", description: pendingDelete.name, variant: "success" });
    } catch (caught) {
      toast({
        title: "Could not remove source",
        description: toErrorMessage(caught),
        variant: "error",
      });
    } finally {
      setPendingDelete(null);
    }
  };

  const typeCounts = sources.data?.type_counts ?? {};
  const statusCounts = sources.data?.status_counts ?? {};

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={project.data?.name ?? "Project"}
        title="Source library"
        description="Every record below was parsed, normalised, hashed and persisted by the backend. Nothing in this list is synthetic."
        actions={
          <>
            <Button variant="ghost" size="sm" asChild>
              <Link to={`/projects/${projectId}`}>
                <ArrowLeft className="h-4 w-4" />
                Project
              </Link>
            </Button>
            <Button variant="outline" size="sm" asChild>
              <Link to={`/projects/${projectId}/sources/github`}>
                <GitBranch className="h-4 w-4" />
                GitHub
              </Link>
            </Button>
            <Button size="sm" asChild>
              <Link to={`/projects/${projectId}/sources/upload`}>
                <FileUp className="h-4 w-4" />
                Upload
              </Link>
            </Button>
          </>
        }
      />

      {projectId ? <ProjectWorkspaceNav projectId={projectId} /> : null}

      {Object.keys(statusCounts).length > 0 ? (
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setProcessingStatus(ALL)}
            className={
              processingStatus === ALL
                ? "rounded-md border border-primary/50 bg-primary/10 px-2.5 py-1 text-[11px] text-primary"
                : "rounded-md border border-border/70 bg-card/40 px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
            }
          >
            All statuses {sources.data?.meta.total ?? 0}
          </button>
          {(Object.keys(statusCounts) as ProcessingStatus[]).map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => setProcessingStatus(key)}
              className={
                processingStatus === key
                  ? "rounded-md border border-primary/50 bg-primary/10 px-2.5 py-1 text-[11px] text-primary"
                  : "rounded-md border border-border/70 bg-card/40 px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
              }
            >
              {PROCESSING_STATUS_META[key]?.label ?? key} {statusCounts[key]}
            </button>
          ))}
        </div>
      ) : null}

      <Card className="p-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search name, author or external id"
              className="pl-8"
              aria-label="Search sources"
            />
          </div>
          <Select value={sourceType} onValueChange={setSourceType}>
            <SelectTrigger className="sm:w-[220px]" aria-label="Filter by source type">
              <SelectValue placeholder="All source types" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All source types</SelectItem>
              {SOURCE_TYPE_ORDER.map((key) => (
                <SelectItem key={key} value={key}>
                  {SOURCE_TYPE_META[key].label}
                  {typeCounts[key] ? ` (${typeCounts[key]})` : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={processingStatus} onValueChange={setProcessingStatus}>
            <SelectTrigger className="sm:w-[190px]" aria-label="Filter by processing status">
              <SelectValue placeholder="Any status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>Any status</SelectItem>
              {(Object.keys(PROCESSING_STATUS_META) as ProcessingStatus[]).map((key) => (
                <SelectItem key={key} value={key}>
                  {PROCESSING_STATUS_META[key].label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </Card>

      {sources.isLoading ? (
        <TableSkeleton columns={["Source", "Type", "Status", "Author", "Added", ""]} />
      ) : null}

      {sources.isError ? (
        <ErrorState error={sources.error} onRetry={() => void sources.refetch()} />
      ) : null}

      {sources.isSuccess && sources.data.items.length === 0 ? (
        <EmptyState
          icon={<Upload className="h-4 w-4" />}
          title={
            search || sourceType !== ALL || processingStatus !== ALL
              ? "No sources match these filters"
              : "No sources ingested yet"
          }
          description={
            search || sourceType !== ALL || processingStatus !== ALL
              ? "Clear the filters to see everything in this project."
              : "Import a GitHub repository or upload PDF, Markdown, TXT and ZIP files."
          }
          action={
            <div className="flex flex-wrap items-center justify-center gap-2">
              <Button size="sm" asChild>
                <Link to={`/projects/${projectId}/sources/upload`}>
                  <FileUp className="h-4 w-4" />
                  Upload files
                </Link>
              </Button>
              <Button variant="outline" size="sm" asChild>
                <Link to={`/projects/${projectId}/sources/github`}>
                  <GitBranch className="h-4 w-4" />
                  Connect GitHub
                </Link>
              </Button>
            </div>
          }
        />
      ) : null}

      {sources.isSuccess && sources.data.items.length > 0 ? (
        <Card className="overflow-hidden p-0">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Source</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="hidden md:table-cell">Author</TableHead>
                <TableHead className="hidden lg:table-cell text-right">Source date</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sources.data.items.map((source) => (
                <TableRow key={source.id}>
                  <TableCell className="max-w-[320px]">
                    <Link to={`/sources/${source.id}`} className="group block">
                      <span className="block truncate text-sm font-medium group-hover:text-primary">
                        {source.source_name}
                      </span>
                      <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                        {source.content_preview || "No preview available"}
                      </span>
                    </Link>
                  </TableCell>
                  <TableCell>
                    <SourceTypeBadge sourceType={source.source_type} />
                  </TableCell>
                  <TableCell>
                    <div className="space-y-1">
                      <ProcessingStatusBadge status={source.processing_status} />
                      {source.error_message ? (
                        <p className="max-w-[200px] truncate text-[11px] text-status-danger">
                          {source.error_message}
                        </p>
                      ) : null}
                    </div>
                  </TableCell>
                  <TableCell className="hidden max-w-[140px] md:table-cell">
                    <span className="block truncate text-xs text-muted-foreground">
                      {source.author ?? "—"}
                    </span>
                  </TableCell>
                  <TableCell className="hidden text-right text-xs text-muted-foreground lg:table-cell">
                    {formatRelative(source.created_at_source ?? source.created_at)}
                  </TableCell>
                  <TableCell className="text-right">
                    <Tooltip label="Remove source">
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Remove ${source.source_name}`}
                        onClick={() =>
                          setPendingDelete({ id: source.id, name: source.source_name })
                        }
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      ) : null}

      {sources.isSuccess && sources.data.meta.total > 0 ? (
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>
            {pluralise(sources.data.meta.total, "source")} · page {sources.data.meta.page} of{" "}
            {Math.max(sources.data.meta.total_pages, 1)}
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={!sources.data.meta.has_previous}
              onClick={() => setPage((current) => Math.max(current - 1, 1))}
            >
              <ChevronLeft className="h-3.5 w-3.5" />
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={!sources.data.meta.has_next}
              onClick={() => setPage((current) => current + 1)}
            >
              Next
              <ChevronRight className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      ) : null}

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title="Remove this source?"
        description={
          <>
            <strong className="text-foreground">{pendingDelete?.name}</strong> will be deleted from
            this project. Any evidence that references it would lose its origin, so this cannot be
            undone.
          </>
        }
        confirmLabel="Remove source"
        destructive
        busy={deleteSource.isPending}
        onConfirm={() => void handleDelete()}
      />
    </div>
  );
}
