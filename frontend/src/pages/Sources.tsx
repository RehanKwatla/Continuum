import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Github,
  Info,
  Plug,
  ShieldCheck,
  Unplug,
} from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { usePageTitle } from "@/hooks/use-page-title";
import { EmptyState, ErrorState } from "@/components/common/States";
import { PageHeader } from "@/components/common/PageHeader";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import {
  useDisconnectGitHub,
  useGitHubBoundary,
  useGitHubStatus,
  useStartGitHubConnect,
} from "@/hooks/use-github";
import { useProjects } from "@/hooks/use-projects";
import { formatRelative } from "@/lib/format";
import { toErrorMessage } from "@/services/api";

/** Outcome banner for the GitHub OAuth redirect (the backend always redirects here). */
function OAuthResultBanner() {
  const [searchParams, setSearchParams] = useSearchParams();
  const outcome = searchParams.get("github");
  const reason = searchParams.get("reason");

  if (!outcome) return null;

  const dismiss = () => {
    const next = new URLSearchParams(searchParams);
    next.delete("github");
    next.delete("reason");
    setSearchParams(next, { replace: true });
  };

  return (
    <Alert
      variant={outcome === "connected" ? "success" : "destructive"}
      title={outcome === "connected" ? "GitHub connected" : "GitHub connection failed"}
      className="flex items-start justify-between gap-4"
    >
      <div className="flex items-start gap-3">
        {outcome === "connected" ? (
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-status-ok" />
        ) : (
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-status-danger" />
        )}
        <span>
          {outcome === "connected"
            ? "The OAuth flow completed. Your access token is stored server-side and never exposed to this page."
            : `GitHub reported: ${reason ?? "unknown_reason"}. Re-run the connection, and confirm the OAuth callback URL matches the backend configuration.`}
        </span>
      </div>
      <Button variant="ghost" size="sm" onClick={dismiss}>
        Dismiss
      </Button>
    </Alert>
  );
}

export default function Sources() {
  usePageTitle("Sources");
  const status = useGitHubStatus();
  const boundary = useGitHubBoundary();
  const projects = useProjects({ page: 1, page_size: 5 });
  const startConnect = useStartGitHubConnect();
  const disconnect = useDisconnectGitHub();
  const { toast } = useToast();
  const [confirmDisconnect, setConfirmDisconnect] = React.useState(false);

  const configured = boundary.data?.configured ?? status.data?.configured ?? false;
  const connected = status.data?.connected ?? false;

  const handleConnect = async () => {
    try {
      const { authorize_url } = await startConnect.mutateAsync();
      // Full-page redirect: the backend owns the callback and token exchange.
      window.location.assign(authorize_url);
    } catch (caught) {
      toast({
        title: "Could not start the GitHub connection",
        description: toErrorMessage(caught),
        variant: "error",
      });
    }
  };

  const handleDisconnect = async () => {
    try {
      await disconnect.mutateAsync();
      toast({ title: "GitHub disconnected", variant: "success" });
      setConfirmDisconnect(false);
    } catch (caught) {
      toast({
        title: "Could not disconnect",
        description: toErrorMessage(caught),
        variant: "error",
      });
      setConfirmDisconnect(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Connect"
        title="Sources"
        description="Authorised repositories and uploaded documents are the raw material Continuum reconstructs project knowledge from."
      />

      <OAuthResultBanner />

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
              <Github className="h-3.5 w-3.5" />
              GitHub connection
            </CardTitle>
            {status.isSuccess ? (
              configured ? (
                connected ? (
                  <Badge variant="ok">Connected</Badge>
                ) : (
                  <Badge variant="secondary">Not connected</Badge>
                )
              ) : (
                <Badge variant="warn">Not configured</Badge>
              )
            ) : null}
          </CardHeader>
          <CardContent className="space-y-4">
            {status.isLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-4 w-40" />
                <Skeleton className="h-9 w-36" />
              </div>
            ) : null}

            {status.isError ? (
              <ErrorState error={status.error} onRetry={() => void status.refetch()} />
            ) : null}

            {status.isSuccess && !configured ? (
              <div className="space-y-3">
                <Alert variant="warning" title="GitHub OAuth is not configured on the server">
                  {boundary.data?.reason ??
                    "Server-side OAuth credentials are absent, so repository import is inert."}
                </Alert>
                {boundary.data?.remediation?.length ? (
                  <div className="rounded-lg border border-border/70 bg-card/40 p-3">
                    <p className="label-eyebrow">To enable it</p>
                    <ol className="mt-2 space-y-1.5">
                      {boundary.data.remediation.map((step, index) => (
                        <li key={step} className="flex gap-2 text-[11px] text-muted-foreground">
                          <span className="tabular-nums">{index + 1}.</span>
                          <span className="mono break-all">{step}</span>
                        </li>
                      ))}
                    </ol>
                  </div>
                ) : null}
                <p className="text-[11px] leading-relaxed text-muted-foreground">
                  This is a clearly labelled integration boundary — no repository data is fabricated
                  to fill the gap. File uploads work independently of GitHub.
                </p>
              </div>
            ) : null}

            {status.isSuccess && configured && !connected ? (
              <div className="space-y-3">
                <p className="text-xs leading-relaxed text-muted-foreground">
                  Continuum requests read access only. The access token is exchanged server-side,
                  encrypted at rest and never returned to the browser.
                </p>
                <Button size="sm" onClick={() => void handleConnect()} disabled={startConnect.isPending}>
                  <Github className="h-4 w-4" />
                  {startConnect.isPending ? "Redirecting…" : "Connect GitHub"}
                </Button>
              </div>
            ) : null}

            {status.isSuccess && connected ? (
              <div className="space-y-4">
                <div className="flex items-center gap-3">
                  {status.data?.avatar_url ? (
                    <img
                      src={status.data.avatar_url}
                      alt=""
                      className="h-9 w-9 rounded-full border border-border"
                    />
                  ) : (
                    <span className="flex h-9 w-9 items-center justify-center rounded-full border border-border bg-secondary">
                      <Github className="h-4 w-4" />
                    </span>
                  )}
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">
                      {status.data?.login ?? "GitHub account"}
                    </p>
                    <p className="text-[11px] text-muted-foreground">
                      {status.data?.connected_at
                        ? `Connected ${formatRelative(status.data.connected_at)}`
                        : "Connected"}
                    </p>
                  </div>
                </div>

                {status.data?.scopes?.length ? (
                  <div>
                    <p className="label-eyebrow">Granted scopes</p>
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {status.data.scopes.map((scope) => (
                        <Badge key={scope} variant="outline">
                          {scope}
                        </Badge>
                      ))}
                    </div>
                  </div>
                ) : null}

                <Separator />

                <div className="flex flex-wrap items-center gap-2">
                  {projects.data?.items.length ? (
                    <Button size="sm" asChild>
                      <Link to={`/projects/${projects.data.items[0].id}/sources/github`}>
                        Select a repository
                        <ArrowRight className="h-4 w-4" />
                      </Link>
                    </Button>
                  ) : (
                    <Button size="sm" asChild>
                      <Link to="/projects/new">Create a project first</Link>
                    </Button>
                  )}
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setConfirmDisconnect(true)}
                    disabled={disconnect.isPending}
                  >
                    <Unplug className="h-4 w-4" />
                    Disconnect
                  </Button>
                </div>

                <p className="flex items-start gap-2 text-[11px] leading-relaxed text-muted-foreground">
                  <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  Import always happens into a project. Open a project and choose “Connect GitHub” to
                  import commits, issues, pull requests and documents.
                </p>
              </div>
            ) : null}
          </CardContent>
        </Card>

        <div className="space-y-3">
          <Card>
            <CardHeader>
              <CardTitle className="text-xs font-medium text-muted-foreground">
                Upload documents
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-xs leading-relaxed text-muted-foreground">
                PDF, Markdown, TXT and ZIP archives are parsed, scanned for secrets, normalised and
                hashed before storage. ZIP entries are inspected with path-traversal and
                decompression limits.
              </p>
              {projects.data?.items.length ? (
                <Button variant="outline" size="sm" asChild>
                  <Link to={`/projects/${projects.data.items[0].id}/sources/upload`}>
                    <Plug className="h-4 w-4" />
                    Upload into {projects.data.items[0].name}
                  </Link>
                </Button>
              ) : (
                <Button variant="outline" size="sm" asChild>
                  <Link to="/projects/new">Create a project to upload into</Link>
                </Button>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                <ShieldCheck className="h-3.5 w-3.5" />
                Ingestion safeguards
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2 text-[11px] text-muted-foreground">
                {[
                  "Extension and true file-format validation",
                  "25 MB upload limit, configurable per environment",
                  "Secret patterns redacted before storage",
                  ".env, private keys, node_modules and .git are never ingested",
                  "Uploaded files are never executed",
                ].map((line) => (
                  <li key={line} className="flex gap-2">
                    <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-status-ok" />
                    {line}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-xs font-medium text-muted-foreground">
                Recent projects
              </CardTitle>
            </CardHeader>
            <CardContent>
              {projects.isLoading ? (
                <div className="space-y-2">
                  <Skeleton className="h-8 w-full" />
                  <Skeleton className="h-8 w-full" />
                </div>
              ) : projects.data?.items.length ? (
                <ul className="divide-y divide-border/70">
                  {projects.data.items.map((project) => (
                    <li key={project.id}>
                      <Link
                        to={`/projects/${project.id}/sources`}
                        className="flex items-center justify-between py-2.5 text-xs transition-colors hover:text-primary"
                      >
                        <span className="truncate">{project.name}</span>
                        <span className="shrink-0 tabular-nums text-muted-foreground">
                          {project.source_count}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState
                  icon={<Plug className="h-4 w-4" />}
                  title="No projects yet"
                  description="Sources live inside projects."
                  action={
                    <Button size="sm" asChild>
                      <Link to="/projects/new">New project</Link>
                    </Button>
                  }
                />
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      <ConfirmDialog
        open={confirmDisconnect}
        onOpenChange={setConfirmDisconnect}
        title="Disconnect GitHub?"
        description="The stored access token is deleted immediately. Already imported sources remain in their projects."
        confirmLabel="Disconnect"
        destructive
        busy={disconnect.isPending}
        onConfirm={() => void handleDisconnect()}
      />
    </div>
  );
}
