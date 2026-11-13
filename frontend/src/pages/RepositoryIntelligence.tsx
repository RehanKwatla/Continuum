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
const TABS = ["Overview", "Files", "Commits", "Issues", "Pull Requests", "Analysis", "Code Intelligence", "History Intelligence"] as const;
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
  const [codeAnalysis, setCodeAnalysis] = React.useState<Record<string, any> | null>(null);
  const [codeDetails, setCodeDetails] = React.useState<Record<string, any>>({});
  const [codeBusy, setCodeBusy] = React.useState(false);
  const [selectedModule, setSelectedModule] = React.useState("");
  const [graphZoom, setGraphZoom] = React.useState(1);
  const [historyAnalysis, setHistoryAnalysis] = React.useState<Record<string, any> | null>(null);
  const [historyInsights, setHistoryInsights] = React.useState<Record<string, any>[]>([]);
  const [historyBusy, setHistoryBusy] = React.useState(false);
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

  React.useEffect(() => {
    if (!repoId || tab !== "Code Intelligence") return;
    const load = () => api.get<Record<string, any>>(`/repositories/${repoId}/analysis-summary`)
      .then((response) => setCodeAnalysis(response.data))
      .catch((caught) => setError(toErrorMessage(caught)));
    void load();
    const timer = window.setInterval(() => { void load(); }, 2000);
    return () => window.clearInterval(timer);
  }, [repoId, tab]);

  React.useEffect(() => {
    if (!repoId || !["completed", "partially_completed"].includes(String(codeAnalysis?.status))) return;
    let active = true;
    void Promise.all([
      api.get(`/repositories/${repoId}/structure`), api.get(`/repositories/${repoId}/dependencies/internal`),
      api.get(`/repositories/${repoId}/dependencies/external`), api.get(`/repositories/${repoId}/symbols`),
      api.get(`/repositories/${repoId}/architecture`), api.get(`/repositories/${repoId}/entry-points`),
    ]).then((responses) => { if (active) setCodeDetails({ structure: responses[0].data, internal: responses[1].data, external: responses[2].data, symbols: responses[3].data, architecture: responses[4].data, entryPoints: responses[5].data }); })
      .catch((caught) => { if (active) setError(toErrorMessage(caught)); });
    return () => { active = false; };
  }, [repoId, codeAnalysis?.status, codeAnalysis?.id]);

  React.useEffect(() => {
    if (!repoId || tab !== "History Intelligence" || !snapshot) return;
    void api.get<Record<string, any>>(`/repositories/${repoId}/history-analysis`, { params: { snapshot_id: snapshot.id } })
      .then((response) => setHistoryAnalysis(response.data))
      .catch((caught) => setError(toErrorMessage(caught)));
    void api.get<{ items: Record<string, any>[] }>(`/repositories/${repoId}/commit-insights`, { params: { snapshot_id: snapshot.id, page: 1, page_size: 50 } })
      .then((response) => setHistoryInsights(response.data.items))
      .catch((caught) => setError(toErrorMessage(caught)));
  }, [repoId, tab, snapshot?.id]);

  async function startCodeAnalysis() {
    if (!repoId || !snapshot) return;
    setCodeBusy(true); setError("");
    try {
      const response = await api.post<Record<string, any>>(`/repositories/${repoId}/code-analysis`, null, { params: { snapshot_id: snapshot.id } });
      setCodeAnalysis(response.data);
    } catch (caught) { setError(toErrorMessage(caught)); }
    finally { setCodeBusy(false); }
  }

  async function startHistoryAnalysis() {
    if (!repoId || !snapshot) return;
    setHistoryBusy(true); setError("");
    try {
      const response = await api.post<Record<string, any>>(`/repositories/${repoId}/history-analysis`, null, { params: { snapshot_id: snapshot.id } });
      setHistoryAnalysis(response.data);
      const insights = await api.get<{ items: Record<string, any>[] }>(`/repositories/${repoId}/commit-insights`, { params: { snapshot_id: snapshot.id, page: 1, page_size: 50 } });
      setHistoryInsights(insights.data.items);
    } catch (caught) { setError(toErrorMessage(caught)); }
    finally { setHistoryBusy(false); }
  }

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
      {tab === "Code Intelligence" && <div className="space-y-4">
        <Card><CardHeader className="flex flex-row items-center justify-between gap-3"><div><CardTitle>Codebase intelligence</CardTitle><p className="mt-1 text-sm text-muted-foreground">Static analysis of files already captured in snapshot {snapshot.commit_sha?.slice(0, 8) ?? snapshot.id.slice(0, 8)}.</p></div><Button onClick={() => void startCodeAnalysis()} disabled={codeBusy || ["pending", "running"].includes(String(codeAnalysis?.status)) || !["completed", "partially_completed"].includes(snapshot.status)}>{codeBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}{["pending", "running"].includes(String(codeAnalysis?.status)) ? "Analysis queued" : "Analyse snapshot"}</Button></CardHeader>
          <CardContent className="space-y-4">
            {!codeAnalysis || codeAnalysis.status === "not_started" ? <p className="text-sm text-muted-foreground">Run analysis to extract languages, technologies, symbols, imports, entry points and an evidence-backed structure from stored source files.</p> : <>
              <div className="flex flex-wrap gap-2"><Badge>{pretty(String(codeAnalysis.status ?? "unknown"))}</Badge>{codeAnalysis.parser_version && <Badge variant="secondary">Parser {codeAnalysis.parser_version}</Badge>}</div>
              {codeAnalysis.languages && <section><h3 className="mb-2 text-sm font-semibold">Languages</h3><div className="flex flex-wrap gap-2">{(codeAnalysis.languages.local ?? []).map((item: any) => <Badge key={item.language} variant="secondary">{item.language} · {item.file_count} files · {item.percentage}% (local)</Badge>)}{(codeAnalysis.languages.github ?? []).map((item: any) => <Badge key={`gh-${item.language}`} variant="outline">{item.language} · {item.percentage}% (GitHub)</Badge>)}</div></section>}
              {Array.isArray(codeAnalysis.technologies) && <section><h3 className="mb-2 text-sm font-semibold">Detected technologies</h3><div className="flex flex-wrap gap-2">{codeAnalysis.technologies.length ? codeAnalysis.technologies.map((item: any) => <Badge key={item.technology} variant="secondary">{item.technology} · {item.category} · {item.confidence}</Badge>) : <p className="text-sm text-muted-foreground">No manifest-backed technologies detected.</p>}</div></section>}
              {codeAnalysis.architecture && <><section><h3 className="mb-2 text-sm font-semibold">Project structure</h3><p className="text-sm text-muted-foreground">{codeAnalysis.architecture.directories} directories · {codeAnalysis.architecture.files} files · {codeAnalysis.architecture.analysed_files} analysed · {codeAnalysis.architecture.skipped_files} skipped</p>{codeAnalysis.architecture.truncated && <p className="mt-1 text-xs text-amber-700">Analysis limit reached; this result covers a partial tree.</p>}</section>
                <section><h3 className="mb-2 text-sm font-semibold">Entry points</h3>{(codeDetails.entryPoints?.items ?? codeAnalysis.entry_points ?? []).length ? <div className="space-y-1">{(codeDetails.entryPoints?.items ?? codeAnalysis.entry_points).map((item: any) => <p key={`${item.file_path}-${item.detection_method}`} className="text-sm"><code>{item.file_path}</code> · {item.detection_method} · {item.confidence}</p>)}</div> : <p className="text-sm text-muted-foreground">No conventional entry points found in analysed files.</p>}</section>
                <section><h3 className="mb-2 text-sm font-semibold">Evidence-backed module groups</h3>{(codeAnalysis.architecture.components ?? []).length ? <div className="grid gap-2 sm:grid-cols-2">{codeAnalysis.architecture.components.map((item: any) => <div key={item.component_name} className="rounded-md border p-3"><p className="font-medium">{item.component_name}</p><p className="text-xs text-muted-foreground">{item.confidence} confidence · {item.evidence.join(" · ")}</p></div>)}</div> : <p className="text-sm text-muted-foreground">Not enough parsed source evidence to infer module groups.</p>}</section>
                <section><h3 className="mb-2 text-sm font-semibold">Project tree</h3><details><summary className="cursor-pointer text-sm">Browse {codeDetails.structure?.files ?? codeAnalysis.architecture.files} files and {codeDetails.structure?.directories ?? codeAnalysis.architecture.directories} directories</summary><div className="mt-2 max-h-64 space-y-1 overflow-auto rounded border p-2">{(codeDetails.structure?.tree ?? codeAnalysis.architecture.tree ?? []).slice(0, 200).map((node: any) => <p key={node.node_id} className="truncate text-xs" style={{ paddingLeft: `${Math.min(node.path.split("/").length - 1, 8) * 12}px` }}><span className="text-muted-foreground">{node.node_type === "directory" ? "▸" : "·"}</span> {node.name}{node.language ? ` · ${node.language}` : ""} {node.node_type === "file" && <span className="text-muted-foreground">· {node.analysis_status}</span>}</p>)}</div></details></section>
                <section><h3 className="mb-2 text-sm font-semibold">Module dependency graph</h3>{(() => { const graph = codeDetails.architecture; const resolved = (graph?.edges ?? []).filter((edge: any) => edge.resolution_status === "resolved"); const nodes = (graph?.nodes ?? []).filter((node: any) => resolved.some((edge: any) => edge.source === node.id || edge.target === node.id)).slice(0, 16); const nodeIndex = new Map<string, number>(nodes.map((node: any, index: number): [string, number] => [node.id, index])); return resolved.length && nodes.length ? <div className="overflow-auto rounded border p-2"><svg viewBox="0 0 760 280" className="min-w-[600px] w-full" onWheel={(event) => { event.preventDefault(); setGraphZoom((value) => Math.min(1.8, Math.max(0.65, value + (event.deltaY < 0 ? 0.1 : -0.1)))); }}><g transform={`scale(${graphZoom})`}>{resolved.map((edge: any, index: number) => { const a = nodeIndex.get(edge.source); const b = nodeIndex.get(edge.target); if (a === undefined || b === undefined) return null; return <line key={`${edge.source}-${edge.target}-${index}`} x1="80" y1={24 + a * 15} x2="680" y2={24 + b * 15} stroke={selectedModule && selectedModule !== edge.source && selectedModule !== edge.target ? "#b8b8b3" : "#2F6BFF"} strokeWidth="1.5" />; })}{nodes.map((node: any, index: number) => <g key={node.id} role="button" tabIndex={0} onClick={() => setSelectedModule(node.id)} onKeyDown={(event) => { if (event.key === "Enter") setSelectedModule(node.id); }}><circle cx={index % 2 ? 680 : 80} cy={24 + index * 15} r="5" fill={selectedModule === node.id ? "#2F6BFF" : "#D8CBB3"} /><text x={index % 2 ? 692 : 92} y={28 + index * 15} fontSize="10" fill="currentColor">{node.label.slice(0, 48)}</text></g>)}</g></svg><p className="mt-1 text-xs text-muted-foreground">Click a module to highlight its links · Scroll to zoom · {selectedModule || "No module selected"}</p></div> : <p className="text-sm text-muted-foreground">No resolved internal imports were found among the stored source files.</p>; })()}</section>
                <section><h3 className="mb-2 text-sm font-semibold">Internal imports</h3><div className="max-h-48 space-y-1 overflow-auto">{(codeDetails.internal?.items ?? []).slice(0, 100).map((item: any) => <p key={`${item.source_file}-${item.line_number}-${item.target_module}`} className="text-xs"><code>{item.source_file}:{item.line_number}</code> → <code>{item.target_module}</code> <span className="text-muted-foreground">({item.resolution_status})</span></p>)}</div></section>
                <section><h3 className="mb-2 text-sm font-semibold">External dependencies</h3><div className="max-h-48 space-y-1 overflow-auto">{(codeDetails.external?.items ?? []).slice(0, 100).map((item: any) => <p key={`${item.manifest_path}-${item.package_name}`} className="text-xs"><code>{item.package_name}</code> {item.declared_version ?? "version unspecified"}{item.resolved_version ? ` · resolved ${item.resolved_version}` : ""} · {item.dep_category} · {item.manifest_path}</p>)}{!codeDetails.external?.items?.length && <p className="text-sm text-muted-foreground">No supported external dependencies found.</p>}</div></section>
                <section><h3 className="mb-2 text-sm font-semibold">Parsed symbols</h3><p className="mb-2 text-sm text-muted-foreground">{codeAnalysis.architecture.symbol_count ?? 0} symbols · Parse issues: {(codeAnalysis.architecture.errors ?? []).length}</p><div className="max-h-48 space-y-1 overflow-auto">{(codeDetails.symbols?.items ?? []).slice(0, 100).map((item: any) => <p key={`${item.file_path}-${item.start_line}-${item.symbol_name}`} className="text-xs"><span className="font-medium">{item.symbol_type} {item.symbol_name}</span> · <code>{item.file_path}:{item.start_line}-{item.end_line}</code></p>)}</div>{(codeAnalysis.architecture.errors ?? []).slice(0, 5).map((item: any, index: number) => <p key={`${item.path}-${index}`} className="text-xs text-amber-700">{item.path}:{item.line ?? "?"} {item.message}</p>)}</section>
              </>}</>}
          </CardContent>
        </Card>
      </div>}
      {tab === "History Intelligence" && <Card><CardHeader className="flex flex-row items-center justify-between gap-3"><div><CardTitle>Git history intelligence</CardTitle><p className="mt-1 text-sm text-muted-foreground">Evidence from commits captured for branch {snapshot.branch} in this snapshot.</p></div><Button onClick={() => void startHistoryAnalysis()} disabled={historyBusy || !["completed", "partially_completed"].includes(snapshot.status)}>{historyBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}{historyAnalysis?.status === "completed" ? "Refresh history analysis" : "Analyse commit history"}</Button></CardHeader><CardContent className="space-y-5">
        {!historyAnalysis || historyAnalysis.status === "not_started" ? <p className="text-sm text-muted-foreground">Analyse captured commits to see evidence-backed change categories, contributor activity, frequently changed files, and files that changed together.</p> : <>
          <div className="flex flex-wrap gap-2"><Badge>{pretty(String(historyAnalysis.status))}</Badge><Badge variant="secondary">{historyAnalysis.summary?.classified_commits ?? 0} commits classified</Badge><Badge variant="secondary">{historyAnalysis.summary?.contributors_observed ?? 0} observed contributors</Badge><Badge variant="secondary">{historyAnalysis.summary?.files_changed ?? 0} changed files</Badge></div>
          <section><h3 className="mb-2 text-sm font-semibold">Coverage</h3><p className="text-sm text-muted-foreground">{historyAnalysis.coverage?.commits_retrieved ?? 0} commits captured · {historyAnalysis.coverage?.earliest_available_commit ? new Date(historyAnalysis.coverage.earliest_available_commit).toLocaleDateString() : "earliest date unavailable"} to {historyAnalysis.coverage?.latest_available_commit ? new Date(historyAnalysis.coverage.latest_available_commit).toLocaleDateString() : "latest date unavailable"} · {historyAnalysis.coverage?.changed_files_observed ?? 0} changed paths observed</p><p className="mt-1 text-xs text-amber-700">{historyAnalysis.coverage?.coverage_note}{historyAnalysis.coverage?.coverage_limited_by_configured_limit ? ` The configured commit limit (${historyAnalysis.coverage.configured_commit_limit}) was reached.` : ""}</p><p className="mt-1 text-xs text-muted-foreground">{historyAnalysis.summary?.author_identity_note}</p></section>
          <section><h3 className="mb-2 text-sm font-semibold">Change categories</h3><div className="flex flex-wrap gap-2">{Object.entries(historyAnalysis.summary?.category_counts ?? {}).map(([key, value]) => <Badge key={key} variant="outline">{pretty(key)} · {String(value)}</Badge>)}</div></section>
          <section><h3 className="mb-2 text-sm font-semibold">Pull request outcomes</h3><div className="flex flex-wrap gap-2">{Object.entries(historyAnalysis.summary?.pull_request_outcomes ?? {}).map(([key, value]) => <Badge key={key} variant="secondary">{pretty(key)} · {String(value)}</Badge>)}</div><p className="mt-1 text-xs text-muted-foreground">A requested review is not counted as a completed review; PR review detail is not used to infer understanding.</p></section>
          <section><h3 className="mb-2 text-sm font-semibold">Contributor activity</h3><div className="space-y-2">{(historyAnalysis.contributors ?? []).map((item: any) => <div key={item.identity_key} className="rounded border p-3"><p className="font-medium">{item.author_name || "Git author unavailable"}{item.github_login && <span className="ml-2 text-xs text-muted-foreground">GitHub @{item.github_login} (separate identity)</span>}</p><p className="mt-1 text-xs text-muted-foreground">{item.commits} commits · {item.files_modified} files · {item.line_stats_complete ? `+${item.additions} / −${item.deletions} lines` : "line totals unavailable"} · {item.commit_share_percent}% of observed author-email commits</p>{item.modules_touched?.length > 0 && <p className="mt-1 text-xs">Observed analyzed modules: {item.modules_touched.join(", ")}</p>}</div>)}</div>{!historyAnalysis.contributors?.length && <p className="text-sm text-muted-foreground">No commit authors were available in the captured history.</p>}</section>
          <section><h3 className="mb-2 text-sm font-semibold">Frequently changed files</h3><div className="space-y-1">{(historyAnalysis.hotspots ?? []).slice(0, 20).map((item: any) => <p key={item.file_path} className="text-xs"><code>{item.file_path}</code> · {item.change_count} observed commits{item.known_additions !== null ? ` · +${item.known_additions} / −${item.known_deletions}` : " · line statistics unavailable"}</p>)}</div>{!historyAnalysis.hotspots?.length && <p className="text-sm text-muted-foreground">No changed file paths were returned for these commits.</p>}</section>
          <section><h3 className="mb-2 text-sm font-semibold">Files changed together</h3><div className="space-y-1">{(historyAnalysis.co_changes ?? []).map((item: any) => <p key={item.files.join(":")} className="text-xs"><code>{item.files[0]}</code> ↔ <code>{item.files[1]}</code> · {item.co_change_count} commits</p>)}</div>{!historyAnalysis.co_changes?.length && <p className="text-sm text-muted-foreground">No file pairs co-occurred more than once in the captured commit set.</p>}</section>
          <section><h3 className="mb-2 text-sm font-semibold">Commit summaries</h3><div className="space-y-2">{historyInsights.map((item) => <div key={item.commit_sha} className="rounded border p-3"><div className="flex flex-wrap items-center gap-2"><Badge variant="secondary">{pretty(item.category)}</Badge><Badge variant="outline">{item.confidence} confidence</Badge><code className="text-xs">{item.commit_sha.slice(0, 8)}</code></div><p className="mt-2 text-sm">{item.summary}</p>{item.signals?.length > 0 && <p className="mt-1 text-xs text-muted-foreground">Signals: {item.signals.join(" · ")}</p>}</div>)}</div>{!historyInsights.length && <p className="text-sm text-muted-foreground">No commit insight records are available yet.</p>}</section>
          <p className="border-t pt-3 text-xs text-muted-foreground">History activity is observational evidence. It does not establish expertise, ownership, intent, neglect, or responsibility.</p>
        </>}</CardContent></Card>}
      {["Files", "Commits", "Issues", "Pull Requests"].includes(tab) && <Card><CardHeader><CardTitle>{tab}</CardTitle></CardHeader><CardContent className="space-y-3">
        {!data ? <p className="text-sm text-muted-foreground">Loading repository records…</p> : data.items.length === 0 ? <p className="text-sm text-muted-foreground">No {tab.toLowerCase()} have been saved for this snapshot.</p> : data.items.map((row, index) => <div key={String(row.id ?? index)} className="rounded-md border p-3"><p className="font-medium">{String(row.path ?? row.title ?? row.message ?? row.commit_sha ?? "Repository item")}</p><p className="mt-1 text-xs text-muted-foreground">{String(row.analysis_status ?? row.state ?? row.committed_at ?? row.author_name ?? "")}</p>{row.skip_reason !== undefined && row.skip_reason !== null && <p className="mt-1 text-xs text-amber-700">{String(row.skip_reason)}</p>}</div>)}
        {data && data.total > data.page_size && <div className="flex items-center justify-between"><Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((current) => current - 1)}>Previous</Button><span className="text-xs text-muted-foreground">Page {data.page} · {data.total} records</span><Button variant="outline" size="sm" disabled={page * data.page_size >= data.total} onClick={() => setPage((current) => current + 1)}>Next</Button></div>}
      </CardContent></Card>}
    </>}
  </div>;
}
