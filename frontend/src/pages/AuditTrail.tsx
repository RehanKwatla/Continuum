import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  Activity,
  Archive,
  BadgeCheck,
  CheckCircle2,
  Download,
  FileText,
  Gavel,
  HelpCircle,
  Pencil,
  Send,
  ShieldCheck,
  Sparkles,
  XCircle,
  type LucideIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PageHeader, PanelSkeleton } from "@/components/common/PageHeader";
import { ProjectWorkspaceNav } from "@/components/common/ProjectWorkspaceNav";
import { EmptyState, ErrorState } from "@/components/common/States";
import { useProject } from "@/hooks/use-projects";
import { usePageTitle } from "@/hooks/use-page-title";
import { useAuditTrail } from "@/hooks/use-memory";
import { formatDateTime, humanise } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { AuditLogRead } from "@/types";

type Tone = "ok" | "warn" | "danger" | "info" | "secondary";

/** Presentation metadata for every action the Phase 4 workflow can record. */
const ACTION_META: Record<string, { label: string; tone: Tone; Icon: LucideIcon }> = {
  claim_approved: { label: "Claim approved", tone: "ok", Icon: ShieldCheck },
  claim_rejected: { label: "Claim rejected", tone: "danger", Icon: XCircle },
  claim_edited: { label: "Claim edited", tone: "info", Icon: Pencil },
  claim_clarification_requested: { label: "Clarification requested", tone: "warn", Icon: HelpCircle },
  claim_evidence_requested: { label: "Evidence requested", tone: "warn", Icon: HelpCircle },
  conflict_resolved: { label: "Conflict decided", tone: "info", Icon: Gavel },
  handover_generated: { label: "Handover generated", tone: "info", Icon: Sparkles },
  handover_edited: { label: "Handover edited", tone: "info", Icon: Pencil },
  handover_version_created: { label: "Handover version created", tone: "secondary", Icon: FileText },
  handover_submitted: { label: "Handover submitted", tone: "info", Icon: Send },
  handover_approved: { label: "Handover approved", tone: "ok", Icon: CheckCircle2 },
  handover_published: { label: "Handover published", tone: "ok", Icon: BadgeCheck },
  handover_archived: { label: "Handover archived", tone: "secondary", Icon: Archive },
  handover_exported: { label: "Handover exported", tone: "secondary", Icon: Download },
  handover_accessed: { label: "Handover accessed", tone: "secondary", Icon: FileText },
};

const FILTERS: Array<{ value: string; label: string; actions?: string[] }> = [
  { value: "all", label: "All activity" },
  { value: "approvals", label: "Approvals", actions: ["claim_approved"] },
  { value: "rejections", label: "Rejections", actions: ["claim_rejected"] },
  { value: "edits", label: "Claim edits", actions: ["claim_edited"] },
  {
    value: "clarifications",
    label: "Clarifications",
    actions: ["claim_clarification_requested", "claim_evidence_requested"],
  },
  { value: "conflicts", label: "Conflict decisions", actions: ["conflict_resolved"] },
  {
    value: "handover",
    label: "Handover",
    actions: [
      "handover_generated",
      "handover_edited",
      "handover_version_created",
      "handover_submitted",
      "handover_approved",
      "handover_published",
      "handover_archived",
    ],
  },
  { value: "exports", label: "Exports", actions: ["handover_exported"] },
];

const PAGE_SIZE = 40;

/** Metadata values are shown compactly; the owning project id is redundant here. */
function MetaChips({ entry }: { entry: AuditLogRead }) {
  const entries = Object.entries(entry.metadata ?? {}).filter(
    ([key]) => key !== "project_id" && key !== "workspace_id",
  );
  if (entries.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {entries.map(([key, value]) => (
        <span
          key={key}
          className="rounded-md border border-border/70 bg-card/40 px-2 py-0.5 text-[10px] text-muted-foreground"
        >
          <span className="font-mono">{key}</span>
          {": "}
          {typeof value === "string" || typeof value === "number" ? String(value) : JSON.stringify(value)}
        </span>
      ))}
    </div>
  );
}

function AuditRow({ entry, projectId }: { entry: AuditLogRead; projectId: string }) {
  const meta = ACTION_META[entry.action] ?? {
    label: humanise(entry.action),
    tone: "secondary" as Tone,
    Icon: Activity,
  };
  const Icon = meta.Icon;
  const claimHref =
    entry.resource_type === "claim" && entry.resource_id
      ? `/projects/${projectId}/memory/claims/${entry.resource_id}`
      : null;

  return (
    <li className="relative pl-10">
      <span
        className={cn(
          "absolute left-0 top-0.5 flex h-7 w-7 items-center justify-center rounded-full border border-border bg-card",
          meta.tone === "ok" && "text-status-ok",
          meta.tone === "danger" && "text-status-danger",
          meta.tone === "warn" && "text-status-warn",
          meta.tone === "info" && "text-status-info",
          meta.tone === "secondary" && "text-muted-foreground",
        )}
      >
        <Icon className="h-3.5 w-3.5" />
      </span>
      <div className="space-y-1.5 pb-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={meta.tone}>{meta.label}</Badge>
          <span className="text-[11px] text-muted-foreground">
            {formatDateTime(entry.created_at)}
          </span>
          {entry.resource_type ? (
            <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              {entry.resource_type}
              {entry.resource_id ? ` · ${entry.resource_id.slice(0, 8)}` : ""}
            </span>
          ) : null}
          {claimHref ? (
            <Link
              to={claimHref}
              className="text-[11px] text-primary underline-offset-2 hover:underline"
            >
              open claim
            </Link>
          ) : null}
        </div>
        {entry.user_id ? (
          <p className="text-[10px] text-muted-foreground">
            actor <span className="font-mono">{entry.user_id.slice(0, 8)}</span>
          </p>
        ) : null}
        <MetaChips entry={entry} />
      </div>
    </li>
  );
}

export default function AuditTrail() {
  const { projectId } = useParams<{ projectId: string }>();
  const project = useProject(projectId);
  usePageTitle(project.data ? `Audit Trail — ${project.data.name}` : "Audit Trail");
  const [params, setParams] = useSearchParams();

  const filter = params.get("filter") ?? "all";
  const page = Math.max(1, Number.parseInt(params.get("page") ?? "1", 10) || 1);
  const activeFilter = FILTERS.find((entry) => entry.value === filter) ?? FILTERS[0];

  const audit = useAuditTrail(projectId, {
    action: activeFilter.actions?.join(","),
    page,
    page_size: PAGE_SIZE,
  });

  if (!projectId) return null;

  const update = (next: Record<string, string | null>) => {
    const merged = new URLSearchParams(params);
    for (const [key, value] of Object.entries(next)) {
      if (value === null || value === "") merged.delete(key);
      else merged.set(key, value);
    }
    setParams(merged, { replace: true });
  };

  const items = audit.data?.items ?? [];
  const meta = audit.data?.meta;

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Audit"
        title="Audit trail"
        description="An append-only record of every human decision, edit, approval, publication and download. Entries are never modified or deleted."
      />
      <ProjectWorkspaceNav projectId={projectId} />

      <div className="flex flex-wrap items-center gap-1.5 border-b border-border/70 pb-3">
        {FILTERS.map((entry) => (
          <button
            key={entry.value}
            type="button"
            onClick={() => update({ filter: entry.value, page: null })}
            aria-pressed={filter === entry.value}
            className={cn(
              "rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors",
              filter === entry.value
                ? "bg-secondary text-foreground"
                : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
            )}
          >
            {entry.label}
          </button>
        ))}
        {meta ? (
          <span className="ml-auto tabular-nums text-[11px] text-muted-foreground">
            {meta.total} entr{meta.total === 1 ? "y" : "ies"}
          </span>
        ) : null}
      </div>

      {audit.isLoading ? (
        <PanelSkeleton rows={6} />
      ) : audit.isError ? (
        <ErrorState
          error={audit.error}
          title="The audit trail could not be loaded"
          onRetry={() => void audit.refetch()}
        />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<Activity className="h-4 w-4" />}
          title="Nothing recorded yet"
          description="Review decisions, approvals and handover activity will appear here as they happen."
        />
      ) : (
        <Card>
          <CardContent className="pt-5">
            <ol className="border-l border-border/70 pl-0">
              {items.map((entry) => (
                <AuditRow key={entry.id} entry={entry} projectId={projectId} />
              ))}
            </ol>
          </CardContent>
        </Card>
      )}

      {meta && meta.total_pages > 1 ? (
        <div className="flex items-center justify-between border-t border-border/70 pt-3">
          <span className="text-[11px] text-muted-foreground">
            Page {meta.page} of {meta.total_pages}
          </span>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={!meta.has_previous}
              onClick={() => update({ page: String(meta.page - 1) })}
            >
              Previous
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={!meta.has_next}
              onClick={() => update({ page: String(meta.page + 1) })}
            >
              Next
            </Button>
          </div>
        </div>
      ) : null}

      <span className="sr-only">{project.data?.name}</span>
    </div>
  );
}
