import * as React from "react";
import { Link, useParams } from "react-router-dom";
import { CheckCircle2, Loader2, MinusCircle, Scale, TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/toast";
import { EmptyState, ErrorState } from "@/components/common/States";
import { PageHeader, PanelSkeleton } from "@/components/common/PageHeader";
import { ClaimStatusBadge, ConflictStatusBadge } from "@/components/common/StatusBadge";
import { useConflicts, useResolveConflict } from "@/hooks/use-memory";
import { useProject } from "@/hooks/use-projects";
import { CONFLICT_KIND_META } from "@/lib/intelligence-meta";
import { formatDateTime } from "@/lib/format";
import { hasAtLeast } from "@/lib/roles";
import { cn } from "@/lib/utils";
import { toErrorMessage } from "@/services/api";
import type { ConflictSummary } from "@/types";

function ConflictPanel({
  projectId,
  conflict,
  canReview,
}: {
  projectId: string;
  conflict: ConflictSummary;
  canReview: boolean;
}) {
  const resolve = useResolveConflict(projectId);
  const { toast } = useToast();
  const [chosen, setChosen] = React.useState<string | null>(null);
  const [note, setNote] = React.useState("");

  const kindMeta = CONFLICT_KIND_META[conflict.kind];
  const open = conflict.status === "open";
  const noteValid = note.trim().length >= 4;

  const submit = async (action: "resolve" | "dismiss") => {
    try {
      await resolve.mutateAsync({
        conflictId: conflict.id,
        input: {
          action,
          note: note.trim(),
          chosen_claim_id: action === "resolve" ? chosen : null,
        },
      });
      toast({
        title: action === "resolve" ? "Conflict resolved" : "Conflict dismissed",
        description: "The decision and audit history were preserved.",
        variant: "success",
      });
      setNote("");
      setChosen(null);
    } catch (caught) {
      toast({ title: "Could not save decision", description: toErrorMessage(caught), variant: "error" });
    }
  };

  return (
    <Card className={cn(open && "border-status-danger/30")}>
      <CardContent className="space-y-4 p-5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="flex items-center gap-1.5 text-xs font-medium">
            {conflict.kind === "value_disagreement" ? (
              <TriangleAlert className="h-3.5 w-3.5 text-status-danger" />
            ) : (
              <Scale className="h-3.5 w-3.5 text-muted-foreground" />
            )}
            {kindMeta?.label ?? conflict.kind}
          </span>
          <ConflictStatusBadge status={conflict.status} />
          {conflict.entity ? (
            <span className="font-mono text-[11px] text-muted-foreground">{conflict.entity}</span>
          ) : null}
          <span className="text-[11px] text-muted-foreground">
            detected {formatDateTime(conflict.created_at)}
          </span>
        </div>

        {conflict.summary ? (
          <p className="text-xs leading-relaxed text-muted-foreground">{conflict.summary}</p>
        ) : kindMeta ? (
          <p className="text-xs leading-relaxed text-muted-foreground">{kindMeta.hint}</p>
        ) : null}

        <div className="grid gap-2 md:grid-cols-2">
          {conflict.claims.map((claim) => {
            const selectable = open && canReview && conflict.kind === "value_disagreement";
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
                aria-label={selectable ? `Choose this claim as correct` : undefined}
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
                  <ClaimStatusBadge status={claim.status} />
                  {claim.critical ? <span className="text-status-danger">critical</span> : null}
                </div>
                <p className="text-xs leading-relaxed text-foreground">{claim.text}</p>
                <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-muted-foreground">
                  <span>{claim.evidence_count} evidence ref(s)</span>
                  {claim.author ? <span>Author · {claim.author}</span> : null}
                  <span>Source date · {formatDateTime(claim.source_date)}</span>
                </div>
                <Link
                  to={`/projects/${projectId}/memory/claims/${claim.id}`}
                  className="mt-2 inline-block text-[10px] text-primary hover:underline"
                  onClick={(event) => event.stopPropagation()}
                >
                  Open claim &amp; evidence →
                </Link>
              </div>
            );
          })}
        </div>

        {open && canReview ? (
          <div className="space-y-2 border-t border-border/70 pt-4">
            {conflict.kind === "value_disagreement" ? (
              <p className="text-[11px] text-muted-foreground">
                Select the claim the reviewer believes is correct, then resolve. The chosen claim
                becomes Supported; the others become Uncertain.
              </p>
            ) : (
              <p className="text-[11px] text-muted-foreground">
                This was classified as a change over time rather than a contradiction. Dismiss it to
                record the finding without treating it as an error.
              </p>
            )}
            <Textarea
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="Explain the decision (recorded in the audit history)…"
              rows={2}
              maxLength={2000}
            />
            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                disabled={
                  !noteValid || resolve.isPending || (conflict.kind === "value_disagreement" && !chosen)
                }
                onClick={() => void submit("resolve")}
              >
                {resolve.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <CheckCircle2 className="h-4 w-4" />
                )}
                Resolve
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={!noteValid || resolve.isPending}
                onClick={() => void submit("dismiss")}
              >
                <MinusCircle className="h-4 w-4" />
                Dismiss
              </Button>
              {!noteValid ? (
                <span className="text-[11px] text-muted-foreground">
                  A note of at least 4 characters is required.
                </span>
              ) : null}
            </div>
          </div>
        ) : open ? (
          <p className="border-t border-border/70 pt-3 text-[11px] text-muted-foreground">
            Resolving a conflict requires the admin role.
          </p>
        ) : (
          <div className="border-t border-border/70 pt-3">
            <p className="text-[11px] text-muted-foreground">
              Decision recorded {formatDateTime(conflict.resolved_at)}.
            </p>
            {conflict.resolution_note ? (
              <p className="mt-1 text-[11px] leading-relaxed text-foreground/90">
                {conflict.resolution_note}
              </p>
            ) : null}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function ConflictCentre() {
  const { projectId } = useParams<{ projectId: string }>();
  const conflicts = useConflicts(projectId, { page_size: 50 });
  const project = useProject(projectId);
  const role = project.data?.workspace?.role ?? null;
  const canReview = hasAtLeast(role, "admin");

  if (!projectId) return null;

  const openCount = conflicts.data?.items.filter((item) => item.status === "open").length ?? 0;

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Conflict Centre"
        title="Contradictions and changes"
        description="Contradictions between claims about the same entity and property. Ownership that changed over time is recorded as a change, not an error."
      />

      {conflicts.isLoading ? (
        <PanelSkeleton rows={3} />
      ) : conflicts.isError ? (
        <ErrorState
          error={conflicts.error}
          title="Conflicts could not be loaded"
          onRetry={() => void conflicts.refetch()}
        />
      ) : !conflicts.data || conflicts.data.items.length === 0 ? (
        <EmptyState
          icon={<Scale className="h-4 w-4" />}
          title="No conflicts detected"
          description="No two claims in this project contradict each other on the same property. This is checked by application code, not the model."
        />
      ) : (
        <>
          <p className="text-[11px] text-muted-foreground">
            {conflicts.data.items.length} finding(s) · {openCount} still open
          </p>
          <div className="space-y-4">
            {conflicts.data.items.map((conflict) => (
              <ConflictPanel
                key={conflict.id}
                projectId={projectId}
                conflict={conflict}
                canReview={canReview}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
