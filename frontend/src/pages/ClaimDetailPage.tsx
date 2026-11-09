import * as React from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  BadgeCheck,
  CheckCircle2,
  FileSearch,
  History,
  Loader2,
  MessageSquareWarning,
  Pencil,
  RefreshCw,
  ShieldQuestion,
  TriangleAlert,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/toast";
import { EmptyState, ErrorState } from "@/components/common/States";
import { PageHeader } from "@/components/common/PageHeader";
import {
  AccessLabelBadge,
  ClaimStatusBadge,
  VerdictBadge,
} from "@/components/common/StatusBadge";
import { EvidenceList } from "@/components/intelligence/EvidenceViewer";
import {
  useClaim,
  useEditClaim,
  useReviewClaim,
  useVerifyClaim,
} from "@/hooks/use-memory";
import { useProject } from "@/hooks/use-projects";
import { usePageTitle } from "@/hooks/use-page-title";
import {
  CLAIM_TYPE_ORDER,
  CONFLICT_KIND_META,
  claimTypeMeta,
} from "@/lib/intelligence-meta";
import { formatDateTime } from "@/lib/format";
import { hasAtLeast } from "@/lib/roles";
import { toErrorMessage } from "@/services/api";
import type { ClaimEditInput, ClaimType, ReviewDecision } from "@/types";

type Tone = "ok" | "warn" | "danger" | "info" | "secondary";

/** How each recorded human decision is presented in the timeline. */
const DECISION_META: Record<ReviewDecision, { label: string; tone: Tone; hint: string }> = {
  approve: {
    label: "Approved",
    tone: "ok",
    hint: "A human reviewer approving this — the only path to an approved claim.",
  },
  reject: { label: "Rejected", tone: "danger", hint: "Rejected by a reviewer." },
  clarification: {
    label: "Clarification requested",
    tone: "warn",
    hint: "The reviewer asked for clarification before deciding.",
  },
  request_evidence: {
    label: "Additional evidence requested",
    tone: "warn",
    hint: "The reviewer asked for more evidence before deciding.",
  },
};

function DefinitionRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-6 border-b border-border/60 py-2 last:border-0">
      <span className="shrink-0 text-[11px] text-muted-foreground">{label}</span>
      <span className="min-w-0 text-right text-[11px]">{children}</span>
    </div>
  );
}

export default function ClaimDetailPage() {
  const { projectId, claimId } = useParams<{ projectId: string; claimId: string }>();
  const claim = useClaim(projectId, claimId);
  const project = useProject(projectId);
  usePageTitle(claim.data ? `Claim — ${claim.data.text.slice(0, 40)}` : "Claim Detail");
  const verify = useVerifyClaim(projectId ?? "");
  const review = useReviewClaim(projectId ?? "");
  const edit = useEditClaim(projectId ?? "");
  const { toast } = useToast();

  const [note, setNote] = React.useState("");
  const [requestEvidence, setRequestEvidence] = React.useState(false);
  const [editing, setEditing] = React.useState(false);
  const [draftText, setDraftText] = React.useState("");
  const [draftType, setDraftType] = React.useState<ClaimType>("decision");
  const [draftEntity, setDraftEntity] = React.useState("");
  const [editNote, setEditNote] = React.useState("");

  const role = project.data?.workspace?.role ?? null;
  const canVerify = hasAtLeast(role, "member");
  const canReview = hasAtLeast(role, "admin");

  const data = claim.data;

  // Reset the edit form whenever a different claim is opened.
  React.useEffect(() => {
    setEditing(false);
    setNote("");
    setRequestEvidence(false);
    if (data) {
      setDraftText(data.text);
      setDraftType(data.claim_type);
      setDraftEntity(data.entity ?? "");
    }
  }, [claimId, data?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleVerify = async () => {
    if (!claimId) return;
    try {
      await verify.mutateAsync(claimId);
      toast({ title: "Verification re-run", description: "A new Verifier verdict was recorded." });
    } catch (caught) {
      toast({ title: "Verification failed", description: toErrorMessage(caught), variant: "error" });
    }
  };

  const handleReview = async (action: "approve" | "reject" | "request_clarification") => {
    if (!claimId) return;
    try {
      await review.mutateAsync({
        claimId,
        input: {
          action,
          explanation: note.trim() || null,
          request_evidence: action === "request_clarification" ? requestEvidence : false,
        },
      });
      toast({
        title:
          action === "approve"
            ? "Claim approved"
            : action === "reject"
              ? "Claim rejected"
              : "Clarification requested",
        description:
          action === "approve"
            ? "Approval is a human decision; the AI verdict never approves a claim."
            : "The decision was recorded in the review history and audit trail.",
        variant: "success",
      });
      setNote("");
      setRequestEvidence(false);
    } catch (caught) {
      toast({ title: "Review failed", description: toErrorMessage(caught), variant: "error" });
    }
  };

  const handleEdit = async () => {
    if (!claimId || !data) return;
    const nextText = draftText.trim();
    const nextEntity = draftEntity.trim();
    const input: ClaimEditInput = { note: editNote.trim() };
    if (nextText && nextText !== data.text) input.text = nextText;
    if (draftType !== data.claim_type) input.claim_type = draftType;
    if (nextEntity !== (data.entity ?? "")) input.entity = nextEntity || null;

    try {
      await edit.mutateAsync({ claimId, input });
      toast({
        title: "Claim edited",
        description:
          "The correction was stored as a new revision. A material change requires re-verification.",
        variant: "success",
      });
      setEditing(false);
      setEditNote("");
    } catch (caught) {
      toast({ title: "Edit failed", description: toErrorMessage(caught), variant: "error" });
    }
  };

  if (!projectId || !claimId) return null;

  if (claim.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-20 w-full rounded-lg" />
        <Skeleton className="h-48 w-full rounded-lg" />
      </div>
    );
  }

  if (claim.isError) {
    return (
      <ErrorState
        error={claim.error}
        title="This claim could not be loaded"
        onRetry={() => void claim.refetch()}
      />
    );
  }

  if (!data) return null;

  const meta = claimTypeMeta(data.claim_type);
  const TypeIcon = meta.Icon;
  const transitions = new Set<string>(data.allowed_transitions ?? []);
  const hasOpenConflict = data.conflicts.some((conflict) => conflict.status === "open");
  const canApprove =
    canReview && transitions.has("Verified") && data.evidence_count > 0 && !hasOpenConflict;
  const canReject = canReview && transitions.has("Rejected");
  const canClarify = canReview && transitions.has("Needs Clarification");

  return (
    <div className="space-y-6">
      <div>
        <Button variant="ghost" size="sm" asChild className="-ml-2">
          <Link to={`/projects/${projectId}/memory/claims`}>
            <ArrowLeft className="h-4 w-4" />
            All claims
          </Link>
        </Button>
      </div>

      <PageHeader
        eyebrow="Claim"
        title={`${meta.label}${data.entity ? ` · ${data.entity}` : ""}`}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <ClaimStatusBadge status={data.status} />
            <AccessLabelBadge label={data.access_label} />
            {data.revision_number > 1 ? (
              <Badge variant="secondary">revision {data.revision_number}</Badge>
            ) : null}
            {data.critical ? <Badge variant="danger">Critical</Badge> : null}
            <span className="text-xs text-muted-foreground">
              extracted {formatDateTime(data.created_at)}
            </span>
          </span>
        }
        actions={
          <>
            {canVerify && data.status !== "Verified" ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => void handleVerify()}
                disabled={verify.isPending}
              >
                {verify.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="h-4 w-4" />
                )}
                Re-run verifier
              </Button>
            ) : null}
            {canReview && !editing ? (
              <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
                <Pencil className="h-4 w-4" />
                Edit statement
              </Button>
            ) : null}
          </>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
            <TypeIcon className="h-3.5 w-3.5" />
            Statement
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {!editing ? (
            <>
              <p className="text-base leading-relaxed text-foreground">{data.text}</p>
              {data.reasoning_summary ? (
                <p className="border-l-2 border-border pl-3 text-xs leading-relaxed text-muted-foreground">
                  {data.reasoning_summary}
                </p>
              ) : null}
              <div className="grid gap-x-8 sm:grid-cols-2">
                <DefinitionRow label="Author">{data.author ?? "—"}</DefinitionRow>
                <DefinitionRow label="Entity">{data.entity ?? "—"}</DefinitionRow>
                <DefinitionRow label="Confidence">
                  {data.confidence !== null ? `${Math.round(data.confidence * 100)}%` : "—"}
                </DefinitionRow>
                <DefinitionRow label="Evidence references">{data.evidence_count}</DefinitionRow>
                <DefinitionRow label="Source date">{formatDateTime(data.source_date)}</DefinitionRow>
                <DefinitionRow label="Reviewed">{formatDateTime(data.reviewed_at)}</DefinitionRow>
              </div>
            </>
          ) : (
            <div className="space-y-4">
              <p className="rounded-md border border-border/70 bg-secondary/40 p-2.5 text-[11px] leading-relaxed text-muted-foreground">
                A correction is stored as a new revision — the previous statement is preserved. A
                material change drops the claim back to Pending review and requires re-verification
                before it can be approved again.
              </p>
              <div className="space-y-1.5">
                <Label htmlFor="claim-statement">Statement</Label>
                <Textarea
                  id="claim-statement"
                  value={draftText}
                  onChange={(event) => setDraftText(event.target.value)}
                  rows={3}
                  maxLength={4000}
                />
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="claim-type">Category</Label>
                  <Select value={draftType} onValueChange={(value) => setDraftType(value as ClaimType)}>
                    <SelectTrigger id="claim-type">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {CLAIM_TYPE_ORDER.map((value) => (
                        <SelectItem key={value} value={value} className="text-xs">
                          {claimTypeMeta(value).label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="claim-entity">Entity</Label>
                  <Input
                    id="claim-entity"
                    value={draftEntity}
                    onChange={(event) => setDraftEntity(event.target.value)}
                    maxLength={300}
                    placeholder="Optional entity this claim is about"
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="claim-edit-note">Why is this being changed?</Label>
                <Textarea
                  id="claim-edit-note"
                  value={editNote}
                  onChange={(event) => setEditNote(event.target.value)}
                  placeholder="Required. Recorded with the new revision."
                  rows={2}
                  maxLength={2000}
                />
                <p className="text-[11px] text-muted-foreground">
                  At least 4 characters, and the statement, category or entity must actually change.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  size="sm"
                  onClick={() => void handleEdit()}
                  disabled={edit.isPending || editNote.trim().length < 4}
                >
                  {edit.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Pencil className="h-4 w-4" />
                  )}
                  Save as new revision
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setEditing(false);
                    setDraftText(data.text);
                    setDraftType(data.claim_type);
                    setDraftEntity(data.entity ?? "");
                    setEditNote("");
                  }}
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <section className="space-y-3">
        <h2 className="label-eyebrow">Evidence</h2>
        <EvidenceList evidence={data.evidence} />
      </section>

      {data.conflicts.length > 0 ? (
        <section className="space-y-3">
          <h2 className="label-eyebrow">Conflicts</h2>
          {data.conflicts.map((conflict) => (
            <Link
              key={conflict.id}
              to={`/projects/${projectId}/memory/conflicts`}
              className="block rounded-lg border border-status-danger/35 bg-status-danger/[0.05] p-4 transition-colors hover:border-status-danger/60"
            >
              <div className="flex items-center gap-2 text-xs">
                <TriangleAlert className="h-3.5 w-3.5 text-status-danger" />
                <span className="font-medium">
                  {CONFLICT_KIND_META[conflict.kind]?.label ?? conflict.kind}
                </span>
                <Badge variant="secondary">{conflict.status}</Badge>
              </div>
              {conflict.summary ? (
                <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                  {conflict.summary}
                </p>
              ) : null}
            </Link>
          ))}
        </section>
      ) : null}

      <div className="grid gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
              <ShieldQuestion className="h-3.5 w-3.5" />
              AI verification verdicts
            </CardTitle>
          </CardHeader>
          <CardContent>
            {data.verifications.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No verdict has been recorded for this claim. A verdict is an evidence assessment —
                it is never an approval.
              </p>
            ) : (
              <ul className="space-y-4">
                {data.verifications.map((verification) => (
                  <li key={verification.id} className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2 text-[11px]">
                      <VerdictBadge verdict={verification.verdict} />
                      {verification.quote_validated ? (
                        <span className="inline-flex items-center gap-1 text-status-ok">
                          <BadgeCheck className="h-3 w-3" />
                          quote validated against source
                        </span>
                      ) : (
                        <span className="text-status-warn">quote not validated</span>
                      )}
                      <span className="text-muted-foreground">
                        {formatDateTime(verification.created_at)}
                      </span>
                    </div>
                    {verification.supporting_quote ? (
                      <blockquote className="rounded-md border border-border/70 bg-secondary/40 p-2.5 text-xs leading-relaxed">
                        {verification.supporting_quote}
                      </blockquote>
                    ) : null}
                    {verification.explanation ? (
                      <p className="text-[11px] leading-relaxed text-muted-foreground">
                        {verification.explanation}
                      </p>
                    ) : null}
                    {verification.model_name ? (
                      <p className="font-mono text-[10px] text-muted-foreground">
                        model {verification.model_name}
                      </p>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
              <History className="h-3.5 w-3.5" />
              Human decisions
            </CardTitle>
          </CardHeader>
          <CardContent>
            {data.decisions.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No reviewer decision has been recorded yet.
              </p>
            ) : (
              <ol className="space-y-3">
                {data.decisions.map((decision) => {
                  const meta = DECISION_META[decision.decision];
                  return (
                    <li key={decision.id} className="border-l-2 border-border pl-3">
                      <div className="flex flex-wrap items-center gap-2 text-[11px]">
                        <Badge variant={meta?.tone ?? "secondary"}>
                          {meta?.label ?? decision.decision}
                        </Badge>
                        {decision.from_status && decision.to_status ? (
                          <span className="text-muted-foreground">
                            {decision.from_status} → {decision.to_status}
                          </span>
                        ) : null}
                        <span className="text-muted-foreground">
                          {formatDateTime(decision.created_at)}
                        </span>
                      </div>
                      {decision.explanation ? (
                        <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                          {decision.explanation}
                        </p>
                      ) : null}
                    </li>
                  );
                })}
              </ol>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
            <FileSearch className="h-3.5 w-3.5" />
            Revisions
          </CardTitle>
        </CardHeader>
        <CardContent>
          {data.revisions.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              This claim still carries its original extracted statement.
            </p>
          ) : (
            <ol className="space-y-3">
              {[...data.revisions].reverse().map((revision) => (
                <li key={revision.id} className="border-l-2 border-border pl-3">
                  <div className="flex flex-wrap items-center gap-2 text-[11px]">
                    <Badge variant="secondary">rev {revision.revision_number}</Badge>
                    {revision.is_material ? <Badge variant="warn">material</Badge> : null}
                    {revision.verification_required ? (
                      <Badge variant="warn">re-verification required</Badge>
                    ) : null}
                    <span className="text-muted-foreground">
                      {formatDateTime(revision.created_at)}
                    </span>
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-foreground">{revision.text}</p>
                  {revision.note ? (
                    <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                      {revision.note}
                    </p>
                  ) : null}
                </li>
              ))}
            </ol>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-xs font-medium text-muted-foreground">
            Human review
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {!canReview ? (
            <EmptyState
              icon={<ShieldQuestion className="h-4 w-4" />}
              title="Review requires the admin role"
              description="Only a workspace admin can approve, reject or request clarification. Approving is the only path to an approved claim — an AI verdict never approves."
            />
          ) : data.status === "Verified" ? (
            <div className="space-y-3">
              <div className="flex items-start gap-2 rounded-md border border-status-ok/35 bg-status-ok/[0.06] p-3">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-status-ok" />
                <p className="text-xs leading-relaxed text-muted-foreground">
                  This claim was approved by a human reviewer
                  {data.verified_at ? ` on ${formatDateTime(data.verified_at)}` : ""}. Automatic
                  re-verification cannot overwrite a human decision.
                </p>
              </div>
              <ReviewControls
                note={note}
                setNote={setNote}
                requestEvidence={requestEvidence}
                setRequestEvidence={setRequestEvidence}
                canApprove={canApprove}
                canReject={canReject}
                canClarify={canClarify}
                pending={review.isPending}
                onDecide={handleReview}
              />
            </div>
          ) : (
            <ReviewControls
              note={note}
              setNote={setNote}
              requestEvidence={requestEvidence}
              setRequestEvidence={setRequestEvidence}
              canApprove={canApprove}
              canReject={canReject}
              canClarify={canClarify}
              pending={review.isPending}
              onDecide={handleReview}
              evidenceCount={data.evidence_count}
              hasOpenConflict={hasOpenConflict}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function ReviewControls({
  note,
  setNote,
  requestEvidence,
  setRequestEvidence,
  canApprove,
  canReject,
  canClarify,
  pending,
  onDecide,
  evidenceCount,
  hasOpenConflict,
}: {
  note: string;
  setNote: (value: string) => void;
  requestEvidence: boolean;
  setRequestEvidence: (value: boolean) => void;
  canApprove: boolean;
  canReject: boolean;
  canClarify: boolean;
  pending: boolean;
  onDecide: (action: "approve" | "reject" | "request_clarification") => void;
  evidenceCount?: number;
  hasOpenConflict?: boolean;
}) {
  return (
    <>
      <Textarea
        value={note}
        onChange={(event) => setNote(event.target.value)}
        placeholder="Explanation recorded with the decision (required for a clarification)…"
        rows={3}
        maxLength={2000}
      />
      <label className="flex items-center gap-2 text-[11px] text-muted-foreground">
        <input
          type="checkbox"
          checked={requestEvidence}
          onChange={(event) => setRequestEvidence(event.target.checked)}
          className="h-3.5 w-3.5 accent-[hsl(var(--primary))]"
        />
        For a clarification, ask for additional <span className="text-foreground">evidence</span>{" "}
        rather than an explanation
      </label>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          onClick={() => onDecide("approve")}
          disabled={pending || !canApprove}
          title={canApprove ? undefined : "This claim cannot be approved in its current state."}
        >
          {pending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <CheckCircle2 className="h-4 w-4" />
          )}
          Approve as Verified
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => onDecide("request_clarification")}
          disabled={pending || !canClarify || note.trim().length < 4}
        >
          <MessageSquareWarning className="h-4 w-4" />
          Request clarification
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => onDecide("reject")}
          disabled={pending || !canReject}
        >
          <XCircle className="h-4 w-4" />
          Reject
        </Button>
      </div>
      <div className="space-y-1 text-[11px] text-muted-foreground">
        {evidenceCount === 0 ? <p>A claim without traceable evidence cannot be approved.</p> : null}
        {hasOpenConflict ? <p>Resolve the open conflict before approving.</p> : null}
        {!canApprove && !hasOpenConflict && (evidenceCount ?? 0) > 0 ? (
          <p>The current status does not allow approval. Re-open it for review first.</p>
        ) : null}
        {!canClarify ? <p>A clarification cannot be requested from this status.</p> : null}
      </div>
    </>
  );
}
