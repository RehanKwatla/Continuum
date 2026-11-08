import * as React from "react";
import { Link, useParams } from "react-router-dom";
import { CheckCircle2, Loader2, MinusCircle, Scale, TriangleAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/toast";
import { EmptyState, ErrorState } from "@/components/common/States";
import { PageHeader, PanelSkeleton } from "@/components/common/PageHeader";
import { ProjectWorkspaceNav } from "@/components/common/ProjectWorkspaceNav";
import { ClaimStatusBadge, ConflictStatusBadge } from "@/components/common/StatusBadge";
import { EvidenceList } from "@/components/intelligence/EvidenceViewer";
import { useConflict, useConflicts, useResolveConflict } from "@/hooks/use-memory";
import { useProject } from "@/hooks/use-projects";
import {
  CONFLICT_KIND_META,
  CONFLICT_RESOLUTION_OPTIONS,
} from "@/lib/intelligence-meta";
import { formatDateTime } from "@/lib/format";
import { hasAtLeast } from "@/lib/roles";
import { cn } from "@/lib/utils";
import { toErrorMessage } from "@/services/api";
import type {
  ConflictDetail,
  ConflictResolution,
  ConflictStatus,
  ConflictSummary,
} from "@/types";

const FILTERS: Array<{ value: ConflictStatus | "all"; label: string; hint: string }> = [
  { value: "open", label: "Open", hint: "Undecided — these claims cannot be approved yet." },
  { value: "resolved", label: "Resolved", hint: "A reviewer decided the contradiction." },
  { value: "dismissed", label: "Dismissed", hint: "Recorded, but not treated as a contradiction." },
  { value: "all", label: "All findings", hint: "Every conflict and change finding." },
];

function ConflictRow({
  conflict,
  selected,
  onSelect,
}: {
  conflict: ConflictSummary;
  selected: boolean;
  onSelect: () => void;
}) {
  const meta = CONFLICT_KIND_META[conflict.kind];
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={cn(
        "w-full rounded-lg border p-3 text-left transition-colors",
        selected ? "border-primary bg-primary/[0.06]" : "border-border bg-card/40 hover:border-primary/40",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        {conflict.kind === "value_disagreement" ? (
          <TriangleAlert className="h-3.5 w-3.5 text-status-danger" />
        ) : (
          <Scale className="h-3.5 w-3.5 text-muted-foreground" />
        )}
        <span className="text-xs font-medium">{meta?.label ?? conflict.kind}</span>
        <ConflictStatusBadge status={conflict.status} />
      </div>
      <p className="mt-1.5 line-clamp-2 text-[11px] leading-relaxed text-muted-foreground">
        {conflict.summary ?? meta?.hint ?? "No summary was recorded for this finding."}
      </p>
      <div className="mt-1.5 flex flex-wrap gap-x-3 text-[10px] text-muted-foreground">
        {conflict.entity ? <span className="font-mono">{conflict.entity}</span> : null}
        <span>{conflict.claims.length} claim(s)</span>
        <span>{formatDateTime(conflict.created_at)}</span>
      </div>
    </button>
  );
}

function ConflictDetailPanel({
  projectId,
  conflict,
  canReview,
}: {
  projectId: string;
  conflict: ConflictDetail;
  canReview: boolean;
}) {
  const resolve = useResolveConflict(projectId);
  const { toast } = useToast();
  const [resolution, setResolution] = React.useState<ConflictResolution>("claim_a_accepted");
  const [chosen, setChosen] = React.useState<string | null>(null);
  const [note, setNote] = React.useState("");

  // Reset the decision form whenever a different conflict is opened.
  React.useEffect(() => {
    setResolution(conflict.kind === "changed_over_time" ? "dismissed" : "claim_a_accepted");
    setChosen(null);
    setNote("");
  }, [conflict.id, conflict.kind]);

  const kindMeta = CONFLICT_KIND_META[conflict.kind];
  const open = conflict.status === "open";
  const chosenOption = CONFLICT_RESOLUTION_OPTIONS.find((item) => item.value === resolution);
  const needsChoice =
    resolution === "claim_a_accepted" || resolution === "claim_b_accepted";
  const noteValid = note.trim().length >= 4;

  const submit = async (value: ConflictResolution = resolution) => {
    const requiresChoice = value === "claim_a_accepted" || value === "claim_b_accepted";
    try {
      await resolve.mutateAsync({
        conflictId: conflict.id,
        input: {
          resolution: value,
          note: note.trim(),
          chosen_claim_id: requiresChoice ? chosen : null,
        },
      });
      toast({
        title: value === "dismissed" ? "Finding dismissed" : "Decision recorded",
        description: "Both claims and their evidence are preserved.",
        variant: "success",
      });
      setNote("");
      setChosen(null);
    } catch (caught) {
      toast({
        title: "Could not save decision",
        description: toErrorMessage(caught),
        variant: "error",
      });
    }
  };

  return (
    <Card className={cn(open && "border-status-danger/30")}>
      <CardContent className="space-y-5 p-5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="flex items-center gap-1.5 text-sm font-medium">
            {conflict.kind === "value_disagreement" ? (
              <TriangleAlert className="h-4 w-4 text-status-danger" />
            ) : (
              <Scale className="h-4 w-4 text-muted-foreground" />
            )}
            {kindMeta?.label ?? conflict.kind}
          </span>
          <ConflictStatusBadge status={conflict.status} />
          {conflict.entity ? (
            <span className="font-mono text-[11px] text-muted-foreground">{conflict.entity}</span>
          ) : null}
          {conflict.property_key ? (
            <span className="font-mono text-[11px] text-muted-foreground">
              {conflict.property_key}
            </span>
          ) : null}
        </div>

        {conflict.summary ? (
          <p className="text-xs leading-relaxed text-muted-foreground">{conflict.summary}</p>
        ) : kindMeta ? (
          <p className="text-xs leading-relaxed text-muted-foreground">{kindMeta.hint}</p>
        ) : null}

        {conflict.could_be_temporal_change ? (
          <p className="rounded-md border border-border/70 bg-secondary/40 p-2.5 text-[11px] leading-relaxed text-muted-foreground">
            These statements could both be true of different time periods. That is a valid
            resolution, not an error.
          </p>
        ) : null}

        <div className="space-y-3">
          {conflict.claims.map((claim, index) => {
            const selectable = open && canReview && needsChoice;
            const selected = chosen === claim.id;
            return (
              <div
                key={claim.id}
                className={cn(
                  "rounded-lg border p-3 transition-colors",
                  selected ? "border-primary bg-primary/[0.06]" : "border-border bg-card/40",
                  selectable && "cursor-pointer hover:border-primary/50",
                )}
                onClick={selectable ? () => setChosen(claim.id) : undefined}
                role={selectable ? "radio" : undefined}
                aria-checked={selectable ? selected : undefined}
                aria-label={selectable ? "Choose this claim as the accepted one" : undefined}
                tabIndex={selectable ? 0 : undefined}
                onKeyDown={
                  selectable
                    ? (event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          setChosen(claim.id);
                        }
                      }
                    : undefined
                }
              >
                <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px]">
                  <Badge variant="outline">Claim {index === 0 ? "A" : "B"}</Badge>
                  <ClaimStatusBadge status={claim.status} />
                  {selected ? <Badge variant="default">Accepted</Badge> : null}
                  <span className="text-muted-foreground">confidence {claim.confidence ?? "—"}</span>
                </div>
                <p className="text-xs leading-relaxed text-foreground">{claim.text}</p>
                <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-muted-foreground">
                  {claim.author ? <span>Author · {claim.author}</span> : null}
                  <span>Source date · {formatDateTime(claim.source_date)}</span>
                  <Link
                    to={`/projects/${projectId}/memory/claims/${claim.id}`}
                    className="text-primary hover:underline"
                    onClick={(event) => event.stopPropagation()}
                  >
                    Open claim →
                  </Link>
                </div>
                <div className="mt-3 border-t border-border/60 pt-3">
                  <p className="mb-2 text-[10px] uppercase tracking-wider text-muted-foreground">
                    Evidence
                  </p>
                  <EvidenceList evidence={claim.evidence} />
                </div>
              </div>
            );
          })}
        </div>

        {open && canReview ? (
          <div className="space-y-3 border-t border-border/70 pt-4">
            <h3 className="label-eyebrow">Reviewer decision</h3>
            <div className="space-y-1.5">
              {CONFLICT_RESOLUTION_OPTIONS.map((option) => (
                <label
                  key={option.value}
                  className={cn(
                    "flex cursor-pointer items-start gap-2 rounded-md border p-2.5 transition-colors",
                    resolution === option.value
                      ? "border-primary bg-primary/[0.06]"
                      : "border-border/70 hover:border-primary/40",
                  )}
                >
                  <input
                    type="radio"
                    name={`resolution-${conflict.id}`}
                    value={option.value}
                    checked={resolution === option.value}
                    onChange={() => setResolution(option.value)}
                    className="mt-0.5 h-3.5 w-3.5 accent-[hsl(var(--primary))]"
                  />
                  <span className="space-y-0.5">
                    <span className="block text-xs font-medium text-foreground">{option.label}</span>
                    <span className="block text-[11px] leading-relaxed text-muted-foreground">
                      {option.hint}
                    </span>
                  </span>
                </label>
              ))}
            </div>

            {needsChoice && !chosen ? (
              <p className="text-[11px] text-status-warn">
                Select the claim you are accepting above (Claim A or Claim B).
              </p>
            ) : null}

            <Textarea
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="Explain the decision (required, recorded in the audit trail)…"
              rows={2}
              maxLength={2000}
            />

            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                disabled={!noteValid || resolve.isPending || (needsChoice && !chosen)}
                onClick={() => void submit()}
              >
                {resolve.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <CheckCircle2 className="h-4 w-4" />
                )}
                Record decision
              </Button>
              {chosenOption && resolution !== "dismissed" ? (
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={!noteValid || resolve.isPending}
                  onClick={() => void submit("dismissed")}
                >
                  <MinusCircle className="h-4 w-4" />
                  Dismiss as not a contradiction
                </Button>
              ) : null}
              {!noteValid ? (
                <span className="text-[11px] text-muted-foreground">
                  A note of at least 4 characters is required.
                </span>
              ) : null}
            </div>
          </div>
        ) : open ? (
          <p className="border-t border-border/70 pt-3 text-[11px] text-muted-foreground">
            Deciding a conflict requires the admin role.
          </p>
        ) : (
          <div className="border-t border-border/70 pt-3">
            <p className="text-xs font-medium text-foreground">
              {conflict.resolution_label ?? conflict.resolution ?? "Decision recorded"}
            </p>
            {conflict.resolution_note ? (
              <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                {conflict.resolution_note}
              </p>
            ) : null}
            <p className="mt-1 text-[10px] text-muted-foreground">
              {formatDateTime(conflict.resolved_at)}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function ConflictCentre() {
  const { projectId } = useParams<{ projectId: string }>();
  const project = useProject(projectId);
  const [filter, setFilter] = React.useState<ConflictStatus | "all">("open");
  const [selectedId, setSelectedId] = React.useState<string | null>(null);

  const conflicts = useConflicts(projectId, {
    status: filter === "all" ? undefined : filter,
    page_size: 50,
  });
  const detail = useConflict(projectId, selectedId ?? undefined);

  const role = project.data?.workspace?.role ?? null;
  const canReview = hasAtLeast(role, "admin");

  const items = conflicts.data?.items ?? [];
  const current = detail.data;

  // Keep a selection that still belongs to the current filter.
  React.useEffect(() => {
    if (items.length === 0) {
      setSelectedId(null);
      return;
    }
    if (!selectedId || !items.some((item) => item.id === selectedId)) {
      setSelectedId(items[0].id);
    }
  }, [items, selectedId]);

  if (!projectId) return null;

  const openCount = items.filter((item) => item.status === "open").length;

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Conflict Resolution Centre"
        title="Contradictions and changes"
        description="Application code detects contradictions between claims about the same entity and property. A reviewer decides; nothing is deleted and no side is picked automatically."
      />
      <ProjectWorkspaceNav projectId={projectId} />

      <div className="flex flex-wrap items-center gap-1.5 border-b border-border/70 pb-3">
        {FILTERS.map((entry) => (
          <button
            key={entry.value}
            type="button"
            onClick={() => setFilter(entry.value)}
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
        <span className="ml-auto text-[11px] tabular-nums text-muted-foreground">
          {items.length} finding(s) · {openCount} open
        </span>
      </div>

      {conflicts.isLoading ? (
        <PanelSkeleton rows={3} />
      ) : conflicts.isError ? (
        <ErrorState
          error={conflicts.error}
          title="Conflicts could not be loaded"
          onRetry={() => void conflicts.refetch()}
        />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<Scale className="h-4 w-4" />}
          title="No conflicts in this view"
          description="No claim contradicts another on the same property in this filter. Detection is performed in application code, not by the model."
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <div className="space-y-2">
            {items.map((conflict) => (
              <ConflictRow
                key={conflict.id}
                conflict={conflict}
                selected={conflict.id === selectedId}
                onSelect={() => setSelectedId(conflict.id)}
              />
            ))}
          </div>
          <div>
            {detail.isLoading ? (
              <PanelSkeleton rows={2} />
            ) : detail.isError ? (
              <ErrorState
                error={detail.error}
                title="This conflict could not be loaded"
                onRetry={() => void detail.refetch()}
              />
            ) : current ? (
              <ConflictDetailPanel
                projectId={projectId}
                conflict={current}
                canReview={canReview}
              />
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
