import * as React from "react";
import { Link, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Copy,
  ExternalLink,
  Github,
  GitFork,
  Loader2,
  Lock,
  Search,
  ShieldCheck,
  Star,
} from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/common/PageHeader";
import { ProjectWorkspaceNav } from "@/components/common/ProjectWorkspaceNav";
import { EmptyState, ErrorState } from "@/components/common/States";
import { ProcessingStatusBadge } from "@/components/common/StatusBadge";
import { Tooltip } from "@/components/common/Tooltip";
import { useToast } from "@/components/ui/toast";
import { useAuth } from "@/contexts/AuthContext";
import {
  useConnectGitHubToken,
  useGitHubBoundary,
  useGitHubRepositories,
  useGitHubStatus,
  useImportGitHubRepository,
  useStartGitHubConnect,
} from "@/hooks/use-github";
import { useProject } from "@/hooks/use-projects";
import { formatRelative } from "@/lib/format";
import { toErrorMessage } from "@/services/api";
import type { GitHubImportResponse, GitHubRepositorySummary } from "@/types";

interface ImportOptions {
  include_commits: boolean;
  include_issues: boolean;
  include_pull_requests: boolean;
  include_readme: boolean;
  include_files: boolean;
  include_changed_files: boolean;
  max_items: number;
}

const DEFAULT_OPTIONS: ImportOptions = {
  include_commits: true,
  include_issues: true,
  include_pull_requests: true,
  include_readme: true,
  include_files: false,
  include_changed_files: false,
  max_items: 50,
};

function OptionToggle({
  id,
  label,
  description,
  checked,
  onChange,
}: {
  id: string;
  label: string;
  description: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label
      htmlFor={id}
      className="flex cursor-pointer items-start gap-3 rounded-md border border-border/70 bg-card/40 p-2.5"
    >
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="mt-0.5 h-3.5 w-3.5 accent-[hsl(var(--primary))]"
      />
      <span className="min-w-0">
        <span className="block text-xs font-medium">{label}</span>
        <span className="mt-0.5 block text-[11px] leading-relaxed text-muted-foreground">
          {description}
        </span>
      </span>
    </label>
  );
}

export default function GitHubRepositories() {
  const { projectId } = useParams<{ projectId: string }>();
  const { isDemoSession } = useAuth();
  const project = useProject(projectId);
  const status = useGitHubStatus();
  const boundary = useGitHubBoundary();
  const startConnect = useStartGitHubConnect();
  const connectToken = useConnectGitHubToken();
  const importRepo = useImportGitHubRepository(projectId ?? "");
  const { toast } = useToast();

  const configured = boundary.data?.configured ?? status.data?.configured ?? false;
  const connected = status.data?.connected ?? false;

  const repositories = useGitHubRepositories(connected);
  const [filter, setFilter] = React.useState("");
  const [selected, setSelected] = React.useState<GitHubRepositorySummary | null>(null);
  const [options, setOptions] = React.useState<ImportOptions>(DEFAULT_OPTIONS);
  const [outcome, setOutcome] = React.useState<GitHubImportResponse | null>(null);
  const [patToken, setPatToken] = React.useState("");

  const visibleRepositories = React.useMemo(() => {
    const items = repositories.data?.items ?? [];
    const needle = filter.trim().toLowerCase();
    if (!needle) return items;
    return items.filter(
      (repository) =>
        repository.full_name.toLowerCase().includes(needle) ||
        (repository.language ?? "").toLowerCase().includes(needle),
    );
  }, [repositories.data, filter]);

  const handleConnectToken = async () => {
    if (!patToken.trim()) return;
    try {
      await connectToken.mutateAsync(patToken.trim());
      setPatToken("");
      toast({
        title: "GitHub connected",
        description: "Personal access token authenticated successfully.",
        variant: "success",
      });
    } catch (caught) {
      toast({
        title: "Token authentication failed",
        description: toErrorMessage(caught),
        variant: "error",
      });
    }
  };

  const handleConnect = async () => {
    try {
      const { authorize_url } = await startConnect.mutateAsync();
      window.location.assign(authorize_url);
    } catch (caught) {
      toast({
        title: "Could not start the GitHub connection",
        description: toErrorMessage(caught),
        variant: "error",
      });
    }
  };

  const handleImport = async () => {
    if (!selected) return;
    setOutcome(null);
    try {
      const response = await importRepo.mutateAsync({
        repository: selected.full_name,
        ...options,
      });
      setOutcome(response);
      toast({
        title: `Imported ${response.imported} source${response.imported === 1 ? "" : "s"}`,
        description: `${response.duplicates} duplicate(s), ${response.skipped} skipped, ${response.failed} failed.`,
        variant: response.failed ? "warning" : "success",
      });
    } catch (caught) {
      toast({ title: "Import failed", description: toErrorMessage(caught), variant: "error" });
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={project.data?.name ?? "Project"}
        title="Connect a repository"
        description="Commits, issues, pull requests, README and permitted text files are normalised into sources. Access is limited to repositories you authorise."
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

      {status.isLoading ? <Skeleton className="h-24 w-full rounded-lg" /> : null}

      {status.isSuccess && !configured ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
              <Github className="h-3.5 w-3.5" />
              GitHub integration boundary
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Alert variant="warning" title="Server-side GitHub OAuth credentials are missing">
              {boundary.data?.reason ??
                "Repository import is inert until the backend is configured. No repository data is fabricated."}
            </Alert>
            {boundary.data?.remediation?.length ? (
              <div className="rounded-lg border border-border/70 bg-card/40 p-3">
                <p className="label-eyebrow">Configure on the backend</p>
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
            <Button variant="outline" size="sm" asChild>
              <Link to={`/projects/${projectId}/sources/upload`}>
                Upload documents instead
              </Link>
            </Button>
          </CardContent>
        </Card>
      ) : null}

      {status.isSuccess && connected ? (
        <Card className="border-border/70 bg-card/40">
          <CardContent className="flex flex-wrap items-center justify-between gap-3 py-3">
            <div className="flex items-center gap-3">
              {status.data?.avatar_url ? (
                <img
                  src={status.data.avatar_url}
                  alt={status.data.login ?? "GitHub user"}
                  className="h-8 w-8 rounded-full border border-border"
                />
              ) : (
                <Github className="h-6 w-6 text-muted-foreground" />
              )}
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold">{status.data?.login}</span>
                  <Badge variant="outline" className="text-[10px] bg-primary/10 text-primary border-primary/30">
                    Connected
                  </Badge>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  Scopes: {status.data?.scopes?.join(", ") || "repo, read:user"}
                </p>
              </div>
            </div>
            {isDemoSession ? (
              <Badge variant="secondary" className="text-[11px]">
                Repository browsing enabled in Demo Mode
              </Badge>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {isDemoSession && !connected ? (
        <Card className="border-primary/40 bg-primary/10">
          <CardHeader>
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-primary" />
              <CardTitle className="text-sm">Public Demo Environment: Pre-loaded Synthetic Activity</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="max-w-2xl text-xs leading-relaxed text-muted-foreground">
              External GitHub account connection is disabled in public demo mode to maintain isolation and security.
              This demo workspace has already ingested realistic synthetic GitHub activity (pull requests, issues,
              commits, and repository README) into the Payment Gateway System.
            </p>
            <Button size="sm" asChild variant="outline">
              <Link to={`/projects/${projectId}/sources`}>
                Browse Ingested GitHub Sources
                <ArrowRight className="h-3.5 w-3.5 ml-1" />
              </Link>
            </Button>
          </CardContent>
        </Card>
      ) : status.isSuccess && !connected ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-xs font-medium text-muted-foreground">
              Connect GitHub
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {configured ? (
              <div className="space-y-2">
                <p className="text-xs leading-relaxed text-muted-foreground">
                  Authorise via GitHub OAuth (redirects to GitHub):
                </p>
                <Button size="sm" onClick={() => void handleConnect()} disabled={startConnect.isPending}>
                  <Github className="h-4 w-4" />
                  {startConnect.isPending ? "Redirecting…" : "Connect with GitHub OAuth"}
                </Button>
              </div>
            ) : null}
            <div className="space-y-2 pt-2">
              <p className="text-xs leading-relaxed text-muted-foreground">
                Or connect with a Personal Access Token (PAT):
              </p>
              <div className="flex max-w-md gap-2">
                <Input
                  type="password"
                  placeholder="ghp_..."
                  value={patToken}
                  onChange={(e) => setPatToken(e.target.value)}
                  className="font-mono text-xs"
                />
                <Button
                  size="sm"
                  onClick={() => void handleConnectToken()}
                  disabled={connectToken.isPending || !patToken.trim()}
                >
                  {connectToken.isPending ? "Connecting…" : "Connect Token"}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      ) : null}

{
  connected ? (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <Card className="overflow-hidden">
        <CardHeader className="space-y-3">
          <CardTitle className="flex items-center justify-between text-xs font-medium text-muted-foreground">
            <span className="flex items-center gap-2">
              <Github className="h-3.5 w-3.5" />
              Authorised repositories
            </span>
            {repositories.data ? (
              <span className="tabular-nums">{repositories.data.total}</span>
            ) : null}
          </CardTitle>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              placeholder="Filter repositories"
              className="pl-8"
              aria-label="Filter repositories"
            />
          </div>
        </CardHeader>
        <CardContent className="max-h-[520px] overflow-y-auto p-0">
          {repositories.isLoading ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 6 }).map((_, index) => (
                <Skeleton key={index} className="h-14 w-full rounded-md" />
              ))}
            </div>
          ) : null}

          {repositories.isError ? (
            <div className="p-4">
              <ErrorState error={repositories.error} onRetry={() => void repositories.refetch()} />
            </div>
          ) : null}

          {repositories.isSuccess && visibleRepositories.length === 0 ? (
            <div className="p-4">
              <EmptyState
                icon={<GitFork className="h-4 w-4" />}
                title={filter ? "No repositories match" : "No repositories available"}
                description={
                  filter
                    ? "Adjust the filter."
                    : "The connected account has no repositories this token can read."
                }
              />
            </div>
          ) : null}

          {repositories.isSuccess && visibleRepositories.length > 0 ? (
            <ul className="divide-y divide-border/70">
              {visibleRepositories.map((repository) => {
                const isSelected = selected?.full_name === repository.full_name;
                return (
                  <li key={repository.id}>
                    <button
                      type="button"
                      onClick={() => setSelected(repository)}
                      className={
                        isSelected
                          ? "w-full bg-primary/[0.07] px-4 py-3 text-left transition-colors"
                          : "w-full px-4 py-3 text-left transition-colors hover:bg-accent/40"
                      }
                    >
                      <div className="flex items-center gap-2">
                        <span className="truncate text-sm font-medium">
                          {repository.full_name}
                        </span>
                        {repository.private ? (
                          <Badge variant="outline" className="gap-1">
                            <Lock className="h-2.5 w-2.5" />
                            Private
                          </Badge>
                        ) : null}
                      </div>
                      <p className="mt-0.5 line-clamp-1 text-[11px] text-muted-foreground">
                        {repository.description || "No description"}
                      </p>
                      <div className="mt-1 flex items-center gap-3 text-[11px] text-muted-foreground">
                        {repository.language ? <span>{repository.language}</span> : null}
                        <span className="flex items-center gap-1">
                          <Star className="h-3 w-3" />
                          {repository.stars}
                        </span>
                        {repository.updated_at ? (
                          <span>updated {formatRelative(repository.updated_at)}</span>
                        ) : null}
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-xs font-medium text-muted-foreground">
            Import configuration
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {!selected ? (
            <EmptyState
              icon={<GitFork className="h-4 w-4" />}
              title="Select a repository"
              description="Choose a repository from the list to configure what gets imported."
            />
          ) : (
            <>
              <div className="rounded-lg border border-border/70 bg-card/40 p-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{selected.full_name}</p>
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      {selected.private ? "Private" : "Public"}
                      {selected.default_branch ? ` · ${selected.default_branch}` : ""}
                    </p>
                  </div>
                  {selected.html_url ? (
                    <Tooltip label="Open on GitHub">
                      <Button variant="ghost" size="icon" asChild>
                        <a
                          href={selected.html_url}
                          target="_blank"
                          rel="noreferrer noopener"
                          aria-label="Open on GitHub"
                        >
                          <ExternalLink className="h-4 w-4" />
                        </a>
                      </Button>
                    </Tooltip>
                  ) : null}
                </div>
              </div>

              <div className="grid gap-2">
                <OptionToggle
                  id="opt-commits"
                  label="Commits"
                  description="SHA, author, message, timestamp and repository information."
                  checked={options.include_commits}
                  onChange={(value) => setOptions((current) => ({ ...current, include_commits: value }))}
                />
                <OptionToggle
                  id="opt-issues"
                  label="Issues"
                  description="Number, title, body, author, labels, state and timestamps."
                  checked={options.include_issues}
                  onChange={(value) => setOptions((current) => ({ ...current, include_issues: value }))}
                />
                <OptionToggle
                  id="opt-prs"
                  label="Pull requests"
                  description="Number, title, description, author, state, merged status and timestamps."
                  checked={options.include_pull_requests}
                  onChange={(value) =>
                    setOptions((current) => ({ ...current, include_pull_requests: value }))
                  }
                />
                <OptionToggle
                  id="opt-readme"
                  label="README"
                  description="The repository README, when present."
                  checked={options.include_readme}
                  onChange={(value) => setOptions((current) => ({ ...current, include_readme: value }))}
                />
                <OptionToggle
                  id="opt-files"
                  label="Permitted text files"
                  description="Documentation files from the repository root and docs folder."
                  checked={options.include_files}
                  onChange={(value) => setOptions((current) => ({ ...current, include_files: value }))}
                />
                <OptionToggle
                  id="opt-changed"
                  label="Changed-file lists"
                  description="Fetch changed files per commit and pull request. Costs one extra API request each."
                  checked={options.include_changed_files}
                  onChange={(value) =>
                    setOptions((current) => ({ ...current, include_changed_files: value }))
                  }
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="max-items">Maximum items per category</Label>
                <Input
                  id="max-items"
                  type="number"
                  min={1}
                  max={200}
                  value={options.max_items}
                  onChange={(event) =>
                    setOptions((current) => ({
                      ...current,
                      max_items: Math.min(200, Math.max(1, Number(event.target.value) || 1)),
                    }))
                  }
                />
                <p className="text-[11px] text-muted-foreground">
                  Pagination and rate limits are handled server-side. Lower this value to stay
                  well within your GitHub API quota.
                </p>
              </div>

              <Button
                className="w-full"
                onClick={() => void handleImport()}
                disabled={importRepo.isPending}
              >
                {importRepo.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Importing…
                  </>
                ) : (
                  <>
                    <Github className="h-4 w-4" />
                    Import into this project
                  </>
                )}
              </Button>

              {importRepo.isError ? (
                <ErrorState error={importRepo.error} title="Import could not be completed" />
              ) : null}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  ) : null
}

{
  outcome ? (
    <Card>
      <CardHeader>
        <CardTitle className="text-xs font-medium text-muted-foreground">Import outcome</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {[
            { label: "Imported", value: outcome.imported, tone: "text-status-ok" },
            { label: "Duplicates", value: outcome.duplicates, tone: "text-muted-foreground" },
            { label: "Skipped", value: outcome.skipped, tone: "text-status-warn" },
            { label: "Failed", value: outcome.failed, tone: "text-status-danger" },
          ].map((item) => (
            <div key={item.label} className="rounded-md border border-border/70 bg-card/40 p-2.5">
              <p className="label-eyebrow">{item.label}</p>
              <p className={`mt-1 text-lg font-semibold tabular-nums ${item.tone}`}>
                {item.value}
              </p>
            </div>
          ))}
        </div>

        <Separator />

        {outcome.results.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            No individual records were returned. The repository may be empty or all selected
            categories were disabled.
          </p>
        ) : (
          <ul className="max-h-[420px] divide-y divide-border/70 overflow-y-auto">
            {outcome.results.map((result, index) => {
              const Icon =
                result.status === "completed"
                  ? CheckCircle2
                  : result.status === "duplicate"
                    ? Copy
                    : AlertTriangle;
              return (
                <li
                  key={`${result.filename}-${result.source_id ?? index}`}
                  className="flex items-start gap-3 py-2.5"
                >
                  <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="truncate text-xs">{result.filename}</span>
                      <ProcessingStatusBadge status={result.status} />
                    </div>
                    {result.message ? (
                      <p className="mt-0.5 text-[11px] text-muted-foreground">{result.message}</p>
                    ) : null}
                    {result.source_id ? (
                      <Link
                        to={`/sources/${result.source_id}`}
                        className="mt-1 inline-block text-[11px] text-primary hover:underline"
                      >
                        View source
                      </Link>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        <Button variant="outline" size="sm" asChild>
          <Link to={`/projects/${projectId}/sources`}>Open source library</Link>
        </Button>
      </CardContent>
    </Card>
  ) : null
}
    </div >
  );
}
