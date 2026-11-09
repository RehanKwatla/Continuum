import * as React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Copy,
  Download,
  ExternalLink,
  FileText,
  Sparkles,
  Trash2,
} from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { ErrorState } from "@/components/common/States";
import { PageHeader, PanelSkeleton } from "@/components/common/PageHeader";
import { Tooltip } from "@/components/common/Tooltip";
import {
  AccessLabelBadge,
  ProcessingStatusBadge,
  SourceTypeBadge,
} from "@/components/common/StatusBadge";
import { useToast } from "@/components/ui/toast";
import { useDeleteSource, useSource } from "@/hooks/use-sources";
import { usePageTitle } from "@/hooks/use-page-title";
import { formatBytes, formatDateTime, formatRelative, humanise } from "@/lib/format";
import { SOURCE_TYPE_META } from "@/lib/source-meta";
import { toErrorMessage } from "@/services/api";

/** Renders a flat key/value list from the source's free-form metadata JSON. */
function MetadataTable({ metadata }: { metadata: Record<string, unknown> }) {
  const entries = Object.entries(metadata ?? {}).filter(([, value]) => value !== null);
  if (entries.length === 0) {
    return <p className="text-xs text-muted-foreground">No structured metadata recorded.</p>;
  }
  return (
    <dl className="divide-y divide-border/60">
      {entries.map(([key, value]) => (
        <div key={key} className="flex flex-col gap-0.5 py-2 sm:flex-row sm:gap-4">
          <dt className="w-full shrink-0 text-[11px] uppercase tracking-wider text-muted-foreground sm:w-52">
            {humanise(key)}
          </dt>
          <dd className="min-w-0 break-words font-mono text-xs text-foreground">
            {typeof value === "string" ? value : JSON.stringify(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function DefinitionRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1 py-2 sm:flex-row sm:items-center sm:gap-4">
      <dt className="w-full shrink-0 text-[11px] uppercase tracking-wider text-muted-foreground sm:w-44">
        {label}
      </dt>
      <dd className="min-w-0 break-words text-xs text-foreground">{children}</dd>
    </div>
  );
}

export default function SourceDetails() {
  const { sourceId } = useParams<{ sourceId: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const source = useSource(sourceId);
  usePageTitle(source.data ? source.data.source_name : "Source Details");
  const deleteSource = useDeleteSource(source.data?.project_id ?? "");
  const [confirmOpen, setConfirmOpen] = React.useState(false);

  const content = source.data?.content ?? "";

  const handleCopyHash = async () => {
    if (!source.data?.content_hash) return;
    try {
      await navigator.clipboard.writeText(source.data.content_hash);
      toast({ title: "Content hash copied", variant: "success" });
    } catch {
      toast({ title: "Clipboard unavailable", variant: "error" });
    }
  };

  const handleDelete = async () => {
    if (!source.data) return;
    try {
      await deleteSource.mutateAsync(source.data.id);
      toast({ title: "Source removed", description: source.data.source_name, variant: "success" });
      navigate(`/projects/${source.data.project_id}/sources`, { replace: true });
    } catch (caught) {
      toast({
        title: "Could not remove source",
        description: toErrorMessage(caught),
        variant: "error",
      });
    } finally {
      setConfirmOpen(false);
    }
  };

  if (source.isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader title="Source" eyebrow="Loading" />
        <PanelSkeleton rows={6} />
      </div>
    );
  }

  if (source.isError) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Source unavailable"
          actions={
            <Button variant="ghost" size="sm" asChild>
              <Link to="/sources">
                <ArrowLeft className="h-4 w-4" />
                Back
              </Link>
            </Button>
          }
        />
        <ErrorState
          error={source.error}
          title="This source could not be loaded"
          onRetry={() => void source.refetch()}
        />
      </div>
    );
  }

  const data = source.data;
  if (!data) return null;

  const meta = SOURCE_TYPE_META[data.source_type];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={meta.label}
        title={data.source_name}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <ProcessingStatusBadge status={data.processing_status} />
            <AccessLabelBadge label={data.access_label} />
            <span className="text-xs text-muted-foreground">
              Ingested {formatRelative(data.created_at)}
            </span>
          </span>
        }
        actions={
          <>
            <Button variant="ghost" size="sm" asChild>
              <Link to={`/projects/${data.project_id}/sources`}>
                <ArrowLeft className="h-4 w-4" />
                Source library
              </Link>
            </Button>
            {data.source_url ? (
              <Button variant="outline" size="sm" asChild>
                <a href={data.source_url} target="_blank" rel="noreferrer noopener">
                  <ExternalLink className="h-4 w-4" />
                  Open origin
                </a>
              </Button>
            ) : null}
            <Button variant="destructive" size="sm" onClick={() => setConfirmOpen(true)}>
              <Trash2 className="h-4 w-4" />
              Remove
            </Button>
          </>
        }
      />

      {data.processing_status === "failed" && data.error_message ? (
        <Alert variant="destructive" title="Ingestion failed">
          {data.error_message}
        </Alert>
      ) : null}

      {data.warnings.length > 0 ? (
        <Alert
          variant="warning"
          title={
            data.warnings.length === 1
              ? "1 processing warning"
              : `${data.warnings.length} processing warnings`
          }
        >
          <ul className="list-disc space-y-1 pl-4">
            {data.warnings.map((warning, index) => (
              <li key={index}>{warning}</li>
            ))}
          </ul>
        </Alert>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Card className="min-w-0">
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-muted-foreground" />
              Parsed content
            </CardTitle>
            <span className="font-mono text-[11px] text-muted-foreground">
              {content ? `${content.length.toLocaleString()} characters` : "empty"}
            </span>
          </CardHeader>
          <CardContent className="p-0">
            {content ? (
              <ol className="max-h-[560px] overflow-auto border-t border-border/60 bg-secondary/20 py-3 font-mono text-xs leading-relaxed text-foreground">
                {content.split("\n").map((line, index) => (
                  <li key={index} className="grid grid-cols-[3rem_minmax(0,1fr)] gap-3 px-3">
                    <span className="select-none text-right text-muted-foreground">{index + 1}</span>
                    <span className="whitespace-pre-wrap break-words">{line || " "}</span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="border-t border-border/60 p-5 text-xs text-muted-foreground">
                No text was extracted from this source. It may have been a binary, a skipped archive
                entry, or a duplicate that was recorded without stored content.
              </p>
            )}
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Record</CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              <dl className="divide-y divide-border/60">
                <DefinitionRow label="Type">
                  <SourceTypeBadge sourceType={data.source_type} />
                </DefinitionRow>
                <DefinitionRow label="Status">
                  <ProcessingStatusBadge status={data.processing_status} />
                </DefinitionRow>
                <DefinitionRow label="Author">{data.author ?? "—"}</DefinitionRow>
                <DefinitionRow label="External id">
                  <span className="font-mono">{data.external_id ?? "—"}</span>
                </DefinitionRow>
                <DefinitionRow label="Source date">
                  {formatDateTime(data.created_at_source)}
                </DefinitionRow>
                <DefinitionRow label="Ingested">{formatDateTime(data.created_at)}</DefinitionRow>
                <DefinitionRow label="MIME type">
                  <span className="font-mono">{data.mime_type ?? "—"}</span>
                </DefinitionRow>
                <DefinitionRow label="Size">{formatBytes(data.size_bytes)}</DefinitionRow>
                <DefinitionRow label="Access label">
                  <AccessLabelBadge label={data.access_label} />
                </DefinitionRow>
              </dl>
              {data.content_hash ? (
                <>
                  <Separator className="my-3" />
                  <div className="space-y-1.5">
                    <p className="label-eyebrow">Content hash (SHA-256)</p>
                    <div className="flex items-start gap-2">
                      <code className="min-w-0 flex-1 break-all rounded-md border border-border/70 bg-secondary/40 p-2 font-mono text-[11px]">
                        {data.content_hash}
                      </code>
                      <Tooltip label="Copy content hash">
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label="Copy content hash"
                          onClick={() => void handleCopyHash()}
                        >
                          <Copy className="h-3.5 w-3.5" />
                        </Button>
                      </Tooltip>
                    </div>
                  </div>
                </>
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Source metadata</CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              <MetadataTable metadata={data.metadata} />
            </CardContent>
          </Card>

          <Card className="border-dashed">
            <CardHeader className="flex flex-row items-center gap-2 space-y-0">
              <Sparkles className="h-4 w-4 text-primary" />
              <CardTitle>Project memory</CardTitle>
            </CardHeader>
            <CardContent className="pt-0 text-xs leading-relaxed text-muted-foreground">
              This source is stored, hashed and ready to be handed to the Phase 3 extractor, which
              will propose claims backed by evidence spans. No claims are generated yet.
              <Button variant="outline" size="sm" className="mt-3 w-full" asChild>
                <Link to={`/projects/${data.project_id}`}>
                  <Download className="h-3.5 w-3.5" />
                  View project
                </Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Remove this source?"
        description={
          <>
            <strong className="text-foreground">{data.source_name}</strong> will be deleted
            permanently. Evidence that references it would lose its origin.
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
