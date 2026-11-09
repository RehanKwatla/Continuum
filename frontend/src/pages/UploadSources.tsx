import * as React from "react";
import { Link, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Copy,
  FileUp,
  Loader2,
  UploadCloud,
  X,
  XCircle,
} from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/common/PageHeader";
import { ProjectWorkspaceNav } from "@/components/common/ProjectWorkspaceNav";
import { ProcessingStatusBadge } from "@/components/common/StatusBadge";
import { Tooltip } from "@/components/common/Tooltip";
import { useToast } from "@/components/ui/toast";
import { useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/hooks/use-projects";
import { usePageTitle } from "@/hooks/use-page-title";
import { useUploadSources } from "@/hooks/use-sources";
import { formatBytes } from "@/lib/format";
import { ALLOWED_UPLOAD_EXTENSIONS, UPLOAD_ACCEPT_ATTRIBUTE, isAllowedUpload } from "@/lib/source-meta";
import { toErrorMessage } from "@/services/api";
import type { IngestionResult } from "@/types";

const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;

interface RejectedFile {
  name: string;
  reason: string;
}

export default function UploadSources() {
  const { projectId } = useParams<{ projectId: string }>();
  const project = useProject(projectId);
  usePageTitle(project.data ? `Upload — ${project.data.name}` : "Upload Sources");
  const upload = useUploadSources(projectId ?? "");
  const { toast } = useToast();
  const { isDemoSession } = useAuth();

  const inputRef = React.useRef<HTMLInputElement>(null);
  const [files, setFiles] = React.useState<File[]>([]);
  const [rejected, setRejected] = React.useState<RejectedFile[]>([]);
  const [dragging, setDragging] = React.useState(false);
  const [progress, setProgress] = React.useState(0);
  const [results, setResults] = React.useState<IngestionResult[] | null>(null);

  const addFiles = React.useCallback(
    (incoming: File[]) => {
      const accepted: File[] = [];
      const nextRejected: RejectedFile[] = [];

      for (const file of incoming) {
        if (!isAllowedUpload(file)) {
          nextRejected.push({
            name: file.name,
            reason: `Unsupported type. Allowed: ${ALLOWED_UPLOAD_EXTENSIONS.join(", ")}.`,
          });
          continue;
        }
        if (file.size > MAX_UPLOAD_BYTES) {
          nextRejected.push({
            name: file.name,
            reason: `Exceeds the ${formatBytes(MAX_UPLOAD_BYTES)} upload limit.`,
          });
          continue;
        }
        if (file.size === 0) {
          nextRejected.push({ name: file.name, reason: "File is empty." });
          continue;
        }
        accepted.push(file);
      }

      setFiles((current) => {
        const names = new Set(current.map((file) => `${file.name}:${file.size}`));
        return [
          ...current,
          ...accepted.filter((file) => !names.has(`${file.name}:${file.size}`)),
        ];
      });
      setRejected(nextRejected);
    },
    [],
  );

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    addFiles(Array.from(event.dataTransfer.files));
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!files.length || !projectId) return;
    setProgress(0);
    setResults(null);
    try {
      const response = await upload.mutateAsync({
        files,
        onProgress: (percent) => setProgress(percent),
      });
      setResults(response.results);
      setFiles([]);
      if (inputRef.current) inputRef.current.value = "";
      toast({
        title: `${response.accepted} source${response.accepted === 1 ? "" : "s"} stored`,
        description:
          response.duplicates || response.failed
            ? `${response.duplicates} duplicate(s), ${response.failed} failed.`
            : "All files were parsed and normalised.",
        variant: response.failed ? "warning" : "success",
      });
    } catch (caught) {
      toast({ title: "Upload failed", description: toErrorMessage(caught), variant: "error" });
    } finally {
      setProgress(0);
    }
  };

  const busy = upload.isPending;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={project.data?.name ?? "Project"}
        title="Upload sources"
        description="PDF, Markdown, TXT and ZIP. Each file is validated, scanned for secrets, parsed, normalised and hashed by the backend before it is stored."
        actions={
          <>
            <Button variant="ghost" size="sm" asChild>
              <Link to={`/projects/${projectId}`}>
                <ArrowLeft className="h-4 w-4" />
                Project
              </Link>
            </Button>
            <Button variant="outline" size="sm" asChild>
              <Link to={`/projects/${projectId}/sources`}>Source library</Link>
            </Button>
          </>
        }
      />

      {projectId ? <ProjectWorkspaceNav projectId={projectId} /> : null}

      {isDemoSession ? (
        <Alert variant="default" className="border-primary/40 bg-primary/10">
          <AlertTriangle className="h-4 w-4 text-primary" />
          <div>
            <p className="text-xs font-semibold text-foreground">
              Public Demo Environment: Read-Only Ingestion
            </p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              New uploads are disabled in public demo mode to ensure workspace isolation and security.
              Inspect the pre-loaded synthetic documents in the{" "}
              <Link to={`/projects/${projectId}/sources`} className="text-primary underline">
                Source Library
              </Link>
              .
            </p>
          </div>
        </Alert>
      ) : null}

      {project.isError ? (
        <Alert variant="destructive" title="Project unavailable">
          {toErrorMessage(project.error)}
        </Alert>
      ) : null}

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader>
            <CardTitle className="text-xs font-medium text-muted-foreground">Select files</CardTitle>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={handleSubmit}>
              <div
                onDragOver={(event) => {
                  event.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={handleDrop}
                className={
                  dragging
                    ? "flex flex-col items-center justify-center rounded-lg border border-dashed border-primary/60 bg-primary/[0.06] px-6 py-12 text-center transition-colors"
                    : "flex flex-col items-center justify-center rounded-lg border border-dashed border-border bg-card/40 px-6 py-12 text-center transition-colors hover:border-primary/50 hover:bg-primary/[0.04]"
                }
              >
                <UploadCloud className="h-5 w-5 text-muted-foreground" />
                <p className="mt-3 text-sm font-medium">Drop files here</p>
                <p className="mt-1 max-w-sm text-xs text-muted-foreground">
                  or choose them from disk. Allowed extensions:{" "}
                  <span className="mono">{ALLOWED_UPLOAD_EXTENSIONS.join(" ")}</span> · up to{" "}
                  {formatBytes(MAX_UPLOAD_BYTES)} each.
                </p>
                <div className="mt-4">
                  <Label htmlFor="file-input" className="sr-only">
                    Choose files
                  </Label>
                  <input
                    ref={inputRef}
                    id="file-input"
                    type="file"
                    multiple
                    accept={UPLOAD_ACCEPT_ATTRIBUTE}
                    className="sr-only"
                    onChange={(event) => addFiles(Array.from(event.target.files ?? []))}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => inputRef.current?.click()}
                  >
                    <FileUp className="h-4 w-4" />
                    Choose files
                  </Button>
                </div>
              </div>

              {rejected.length > 0 ? (
                <Alert variant="warning" title="Some files were rejected before upload">
                  <ul className="space-y-1">
                    {rejected.map((item) => (
                      <li key={`${item.name}-${item.reason}`} className="flex gap-2">
                        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-status-warn" />
                        <span>
                          <span className="text-foreground">{item.name}</span> — {item.reason}
                        </span>
                      </li>
                    ))}
                  </ul>
                </Alert>
              ) : null}

              {files.length > 0 ? (
                <div className="rounded-lg border border-border/70 bg-card/40 p-3">
                  <p className="label-eyebrow">Queued</p>
                  <ul className="mt-2 divide-y divide-border/60">
                    {files.map((file) => (
                      <li
                        key={`${file.name}-${file.size}`}
                        className="flex items-center justify-between gap-3 py-2"
                      >
                        <div className="min-w-0">
                          <p className="truncate text-xs">{file.name}</p>
                          <p className="text-[11px] text-muted-foreground">
                            {formatBytes(file.size)}
                          </p>
                        </div>
                        <Tooltip label="Remove file">
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            aria-label={`Remove ${file.name}`}
                            disabled={busy}
                            onClick={() =>
                              setFiles((current) =>
                                current.filter(
                                  (item) => !(item.name === file.name && item.size === file.size),
                                ),
                              )
                            }
                          >
                            <X className="h-3.5 w-3.5" />
                          </Button>
                        </Tooltip>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {busy ? (
                <div>
                  <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                    <span className="flex items-center gap-2">
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      Uploading and processing
                    </span>
                    <span className="tabular-nums">{progress}%</span>
                  </div>
                  <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-primary transition-all"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                </div>
              ) : null}

              <div className="flex items-center gap-2 border-t border-border/70 pt-4">
                <Button type="submit" disabled={!files.length || busy}>
                  <FileUp className="h-4 w-4" />
                  {busy ? "Processing…" : `Upload ${files.length || ""}`.trim()}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => {
                    setFiles([]);
                    setRejected([]);
                    setResults(null);
                  }}
                  disabled={busy}
                >
                  Clear
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-xs font-medium text-muted-foreground">
              What happens on upload
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="space-y-2.5">
              {[
                "Extension and true file format validated",
                "Size limits enforced (uploads and ZIP expansion)",
                "Secrets and credentials scanned and redacted",
                "Content parsed with PyMuPDF, Markdown and text parsers",
                "Metadata and source locations extracted",
                "Normalised to the common source format",
                "SHA-256 content hash computed and de-duplicated",
                "Source persisted and processing status returned",
              ].map((step, index) => (
                <li key={step} className="flex gap-2.5 text-[11px] text-muted-foreground">
                  <span className="tabular-nums text-muted-foreground/70">{index + 1}.</span>
                  {step}
                </li>
              ))}
            </ol>
            <p className="mt-4 border-t border-border/70 pt-3 text-[11px] leading-relaxed text-muted-foreground">
              .env files, private keys, node_modules and .git internals are never ingested, and
              uploaded files are never executed.
            </p>
          </CardContent>
        </Card>
      </div>

      {busy && !results ? (
        <Skeleton className="h-40 w-full rounded-lg" />
      ) : null}

      {results ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-xs font-medium text-muted-foreground">Ingestion results</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="divide-y divide-border/70">
              {results.map((result) => {
                const Icon =
                  result.status === "completed"
                    ? CheckCircle2
                    : result.status === "duplicate"
                      ? Copy
                      : result.status === "failed"
                        ? XCircle
                        : AlertTriangle;
                const tone =
                  result.status === "completed"
                    ? "text-status-ok"
                    : result.status === "duplicate"
                      ? "text-muted-foreground"
                      : result.status === "failed"
                        ? "text-status-danger"
                        : "text-status-warn";
                return (
                  <li key={`${result.filename}-${result.source_id ?? result.status}`} className="flex items-start gap-3 py-3">
                    <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${tone}`} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="truncate text-sm">{result.filename}</span>
                        <ProcessingStatusBadge status={result.status} />
                        {result.source_type ? (
                          <Badge variant="outline">{result.source_type}</Badge>
                        ) : null}
                      </div>
                      {result.message ? (
                        <p className="mt-1 text-[11px] text-muted-foreground">{result.message}</p>
                      ) : null}
                      {result.warnings.length ? (
                        <ul className="mt-1 space-y-0.5">
                          {result.warnings.map((warning) => (
                            <li key={warning} className="text-[11px] text-status-warn">
                              {warning}
                            </li>
                          ))}
                        </ul>
                      ) : null}
                      <div className="mt-1.5 flex flex-wrap items-center gap-3">
                        {result.source_id ? (
                          <Link
                            to={`/sources/${result.source_id}`}
                            className="text-[11px] text-primary hover:underline"
                          >
                            View source
                          </Link>
                        ) : null}
                        {result.duplicate_of ? (
                          <Link
                            to={`/sources/${result.duplicate_of}`}
                            className="text-[11px] text-muted-foreground hover:underline"
                          >
                            Duplicate of existing source
                          </Link>
                        ) : null}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
            <div className="mt-3 border-t border-border/70 pt-3">
              <Button variant="outline" size="sm" asChild>
                <Link to={`/projects/${projectId}/sources`}>Open source library</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
