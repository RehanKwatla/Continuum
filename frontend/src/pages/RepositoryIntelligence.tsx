import * as React from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, ExternalLink, Github, Loader2, Search } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/common/PageHeader";
import { ProjectWorkspaceNav } from "@/components/common/ProjectWorkspaceNav";
import { useProject } from "@/hooks/use-projects";
import { usePageTitle } from "@/hooks/use-page-title";
import { api } from "@/services/api";
import { toErrorMessage } from "@/services/api";

type Branch = { name: string; commit_sha: string; protected: boolean; is_default: boolean };
type Repository = {
  name: string; owner: string; description: string | null; canonical_url: string;
  default_branch: string; visibility: string; language: string | null;
  languages: Record<string, number>; stars: number; forks: number; open_issues: number;
  created_at: string | null; updated_at: string | null; pushed_at: string | null; license: string | null;
};
type Snapshot = {
  id: string; repository_id: string; branch: string; commit_sha: string | null; status: string;
  stage: string; tree_complete: boolean; files_discovered: number; files_processed: number;
  files_skipped: number; commits_processed: number; issues_processed: number;
  pull_requests_processed: number; warnings: string[]; error_summary: string | null;
};
type PageData = { items: Record<string, unknown>[]; total: number; page: number; page_size: number };
const ACTIVE = new Set(["queued", "validating", "fetching_metadata", "fetching_branches", "fetching_tree", "fetching_files", "fetching_commits", "fetching_issues", "fetching_pull_requests", "saving_snapshot"]);
const TABS = ["Overview", "Files", "Commits", "Issues", "Pull Requests", "Analysis"] as const;
type Tab = (typeof TABS)[number];

function pretty(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter: string) => letter.toUpperCase());
}

export default function RepositoryIntelligence() {
  const { projectId } = useParams<{ projectId: string }>();
  const project = useProject(projectId);
  usePageTitle("Repository Intelligence");
  const [url, setUrl] = React.useState("");
  const [metadata, setMetadata] = React.useState<Repository | null>(null);
  const [branches, setBranches] = React.useState<Branch[]>([]);
  const [branch, setBranch] = React.useState("");
  const [repoId, setRepoId] = React.useState("");
  const [snapshot, setSnapshot] = React.useState<Snapshot | null>(null);
  const [tab, setTab] = React.useState<Tab>("Overview");
  const [page, setPage] = React.useState(1);
  const [data, setData] = React.useState<PageData | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const languageSummary = metadata
    ? Object.entries(metadata.languages).sort((left, right) => right[1] - left[1]).slice(0, 5).map(([name]) => name).join(", ")
    : "";

  React.useEffect(() => {
    if (!projectId) return;
    void api.get<{ items: Array<Record<string, unknown>> }>(`/repositories/projects/${projectId}`)
      .then((response) => {
        const saved = response.data.items[0];
        if (!saved) return;
        const savedBranches = Array.isArray(saved.branches) ? (saved.branches as Branch[]) : [];
        setMetadata({
          name: String(saved.repository_name), owner: String(saved.owner),
          description: (saved.description as string | null) ?? null,
          canonical_url: String(saved.repository_url), default_branch: String(saved.default_branch ?? ""),
          visibility: "public", language: (saved.language as string | null) ?? null,
          languages: (saved.languages as Record<string, number>) ?? {},
          stars: Number(saved.stars ?? 0), forks: Number(saved.forks ?? 0), open_issues: Number(saved.open_issues ?? 0),
          created_at: (saved.repository_created_at as string | null) ?? null,
          updated_at: (saved.repository_updated_at as string | null) ?? null,
          pushed_at: (saved.repository_pushed_at as string | null) ?? null,
          license: (saved.license_name as string | null) ?? null,
        });
        setUrl(String(saved.repository_url));
        setBranches(savedBranches);
        setBranch(String(saved.selected_branch ?? saved.default_branch ?? ""));
        setRepoId(String(saved.id));
        if (saved.latest_snapshot && typeof saved.latest_snapshot === "object") {
          setSnapshot(saved.latest_snapshot as Snapshot);
        }
      })
      .catch((caught) => setError(toErrorMessage(caught)));
  }, [projectId]);

  React.useEffect(() => {
    if (!repoId || !snapshot?.id || !ACTIVE.has(snapshot.status)) return;
    const timer = window.setInterval(() => {
      void api.get<Snapshot>(`/repositories/${repoId}/analysis/${snapshot.id}`)
        .then((response) => setSnapshot(response.data))
        .catch((caught) => setError(toErrorMessage(caught)));
    }, 2000);
    return () => window.clearInterval(timer);
  }, [repoId, snapshot?.id, snapshot?.status]);

  React.useEffect(() => {
    if (!repoId || !["Files", "Commits", "Issues", "Pull Requests"].includes(tab)) {
      setData(null);
      return;
    }
    const endpoint: Record<string, string> = { Files: "files", Commits: "commits", Issues: "issues", "Pull Requests": "pull-requests" };
    void api.get<PageData>(`/repositories/${repoId}/${endpoint[tab]}`, { params: { page, page_size: 20, ...(tab === "Files" && snapshot?.id ? { snapshot_id: snapshot.id } : {}) } })
      .then((response) => setData(response.data))
      .catch((caught) => setError(toErrorMessage(caught)));
  }, [repoId, tab, page, snapshot?.id]);

  async function validate() {
    setBusy(true); setError(""); setMetadata(null); setSnapshot(null); setRepoId("");
    try {
      const response = await api.post<{ repository: Repository; branches: Branch[]; selected_branch: string }>("/repositories/validate", { repository_url: url });
      setMetadata(response.data.repository); setBranches(response.data.branches); setBranch(response.data.selected_branch);
    } catch (caught) { setError(toErrorMessage(caught)); }
    finally { setBusy(false); }
  }

  async function analyse() {
    if (!projectId || !metadata) return;
    setBusy(true); setError("");
    try {
      const response = await api.post<{ repository_id: string; analysis_run_id: string; status: string; stage: string }>(`/repositories/projects/${projectId}/analyse`, { repository_url: metadata.canonical_url, branch });
      setRepoId(response.data.repository_id);
      setSnapshot({ id: response.data.analysis_run_id, repository_id: response.data.repository_id, branch, commit_sha: null, status: response.data.status, stage: response.data.stage, tree_complete: false, files_discovered: 0, files_processed: 0, files_skipped: 0, commits_processed: 0, issues_processed: 0, pull_requests_processed: 0, warnings: [], error_summary: null });
      setTab("Overview");
    } catch (caught) { setError(toErrorMessage(caught)); }
    finally { setBusy(false); }
  }

  return <div className="space-y-6">
    <PageHeader eyebrow={project.data?.name ?? "Project"} title="Repository Intelligence" description="Inspect a real public GitHub repository. No GitHub login is needed." actions={<Button variant="ghost" size="sm" asChild><Link to={`/projects/${projectId}`}><ArrowLeft className="mr-2 h-4 w-4" />Project</Link></Button>} />
    <ProjectWorkspaceNav projectId={projectId ?? ""} />
    <Card><CardHeader><CardTitle className="flex items-center gap-2"><Github className="h-5 w-5" />Connect a public repository</CardTitle><p className="text-sm text-muted-foreground">Paste a repository URL to retrieve its metadata and available branches from GitHub.</p></CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
          <div className="space-y-2"><Label htmlFor="repo-url">GitHub repository URL</Label><Input id="repo-url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://github.com/owner/repository" onKeyDown={(event) => { if (event.key === "Enter") void validate(); }} /></div>
          <Button className="self-end" disabled={busy || !url.trim()} onClick={() => void validate()}>{busy && !metadata ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Search className="mr-2 h-4 w-4" />}Validate repository</Button>
        </div>
        <p className="text-xs text-muted-foreground">Public repositories only · Example: https://github.com/fastapi/fastapi</p>
        {error && <Alert variant="destructive">{error}</Alert>}
        {metadata && <div className="rounded-lg border p-4">
          <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="font-semibold">{metadata.owner}/{metadata.name}</h3><p className="mt-1 text-sm text-muted-foreground">{metadata.description || "No description provided by GitHub."}</p></div><a href={metadata.canonical_url} target="_blank" rel="noreferrer" className="text-sm text-primary">Open on GitHub <ExternalLink className="inline h-3.5 w-3.5" /></a></div>
          <div className="mt-3 flex flex-wrap gap-2 text-xs"><Badge variant="secondary">Public</Badge><Badge variant="secondary">Default: {metadata.default_branch}</Badge>{metadata.language && <Badge variant="secondary">{metadata.language}</Badge>}{languageSummary && <Badge variant="secondary">Languages: {languageSummary}</Badge>}<Badge variant="secondary">★ {metadata.stars}</Badge><Badge variant="secondary">⑂ {metadata.forks}</Badge><Badge variant="secondary">{metadata.open_issues} open issues</Badge>{metadata.license && <Badge variant="secondary">{metadata.license}</Badge>}{metadata.created_at && <Badge variant="secondary">Created {new Date(metadata.created_at).toLocaleDateString()}</Badge>}{metadata.updated_at && <Badge variant="secondary">Updated {new Date(metadata.updated_at).toLocaleDateString()}</Badge>}{metadata.pushed_at && <Badge variant="secondary">Pushed {new Date(metadata.pushed_at).toLocaleDateString()}</Badge>}</div>
          <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end"><div className="space-y-2"><Label htmlFor="branch">Analysis branch</Label><select id="branch" className="h-10 w-full rounded-md border bg-background px-3 text-sm" value={branch} onChange={(event) => setBranch(event.target.value)}>{branches.map((item) => <option key={item.name} value={item.name}>{item.name}{item.is_default ? " (default)" : ""}</option>)}</select></div><Button disabled={busy || !branch} onClick={() => void analyse()}>{busy && metadata ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}Analyse repository</Button></div>
        </div>}
      </CardContent>
    </Card>

    {repoId && snapshot && <>
      <div className="flex flex-wrap gap-2">{TABS.map((item) => <Button key={item} variant={tab === item ? "default" : "outline"} size="sm" onClick={() => { setTab(item); setPage(1); }}>{item}</Button>)}</div>
      {tab === "Overview" && <Card><CardHeader><CardTitle>{metadata?.owner}/{metadata?.name}</CardTitle></CardHeader><CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2"><Badge>{pretty(snapshot.status)}</Badge><Badge variant="secondary">Branch: {snapshot.branch}</Badge>{snapshot.commit_sha && <Badge variant="secondary">{snapshot.commit_sha.slice(0, 8)}</Badge>}</div>
        <p className="text-sm">Current backend stage: <strong>{pretty(snapshot.stage)}</strong></p>
        <div className="grid gap-3 sm:grid-cols-4">{[["Files", snapshot.files_processed, snapshot.files_discovered], ["Commits", snapshot.commits_processed], ["Issues", snapshot.issues_processed], ["Pull requests", snapshot.pull_requests_processed]].map(([label, count, total]) => <div key={String(label)} className="rounded-md border p-3"><p className="text-xs text-muted-foreground">{String(label)}</p><p className="mt-1 font-semibold">{String(count)}{total !== undefined ? ` / ${String(total)}` : ""}</p></div>)}</div>
        {snapshot.error_summary && <Alert variant="destructive">{snapshot.error_summary}</Alert>}{snapshot.warnings.map((warning) => <Alert key={warning}>{warning}</Alert>)}
      </CardContent></Card>}
      {tab === "Analysis" && <Card><CardHeader><CardTitle>Analysis run</CardTitle></CardHeader><CardContent><dl className="grid gap-3 sm:grid-cols-2">{Object.entries({ Status: snapshot.status, Stage: snapshot.stage, Branch: snapshot.branch, "Tree complete": String(snapshot.tree_complete), "Files processed": snapshot.files_processed, "Files skipped": snapshot.files_skipped }).map(([key, value]) => <div key={key}><dt className="text-xs text-muted-foreground">{key}</dt><dd className="text-sm">{String(value)}</dd></div>)}</dl></CardContent></Card>}
      {["Files", "Commits", "Issues", "Pull Requests"].includes(tab) && <Card><CardHeader><CardTitle>{tab}</CardTitle></CardHeader><CardContent className="space-y-3">
        {!data ? <p className="text-sm text-muted-foreground">Loading repository records…</p> : data.items.length === 0 ? <p className="text-sm text-muted-foreground">No {tab.toLowerCase()} have been saved for this snapshot.</p> : data.items.map((row, index) => <div key={String(row.id ?? index)} className="rounded-md border p-3"><p className="font-medium">{String(row.path ?? row.title ?? row.message ?? row.commit_sha ?? "Repository item")}</p><p className="mt-1 text-xs text-muted-foreground">{String(row.analysis_status ?? row.state ?? row.committed_at ?? row.author_name ?? "")}</p>{row.skip_reason !== undefined && row.skip_reason !== null && <p className="mt-1 text-xs text-amber-700">{String(row.skip_reason)}</p>}</div>)}
        {data && data.total > data.page_size && <div className="flex items-center justify-between"><Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((current) => current - 1)}>Previous</Button><span className="text-xs text-muted-foreground">Page {data.page} · {data.total} records</span><Button variant="outline" size="sm" disabled={page * data.page_size >= data.total} onClick={() => setPage((current) => current + 1)}>Next</Button></div>}
      </CardContent></Card>}
    </>}
  </div>;
}
