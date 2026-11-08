import * as React from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  BadgeCheck,
  CheckCircle2,
  History,
  Loader2,
  RefreshCw,
  ShieldQuestion,
  TriangleAlert,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { useClaim, useReviewClaim, useVerifyClaim } from "@/hooks/use-memory";
import { useProject } from "@/hooks/use-projects";
import { CONFLICT_KIND_META, claimTypeMeta } from "@/lib/intelligence-meta";
import { formatDateTime } from "@/lib/format";
import { hasAtLeast } from "@/lib/roles";
import { toErrorMessage } from "@/services/api";

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
  const verify = useVerifyClaim(projectId ?? "");
  const review = useReviewClaim(projectId ?? "");
  const { toast } = useToast();
  const [note, setNote] = React.useState("");

  const role = project.data?.workspace?.role ?? null;
  const canVerify = hasAtLeast(role, "member");
  const canReview = hasAtLeast(role, "admin");

  const handleVerify = async () => {
    if (!claimId) return;
    try {
      await verify.mutateAsync(claimId);
      toast({ title: "Verification re-run", description: "A new Verifier verdict was recorded." });
    } catch (caught) {
      toast({ title: "Verification failed", description: toErrorMessage(caught), variant: "error" });
    }
  };

  const handleReview = async (action: "approve" | "reject") => {
    if (!claimId) return;
    try {
      await review.mutateAsync({ claimId, input: { action, note: note.trim() || null } });
      toast({
        title: action === "approve" ? "Claim approved" : "Claim sent back to Uncertain",
        description:
          action === "approve"
            ? "Only a human review can mark a claim Verified."
            : "The claim is no longer approved.",
        variant: "success",
      });
      setNote("");
    } catch (caught) {
      toast({ title: "Review failed", description: toErrorMessage(caught), variant: "error" });
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

  const data = claim.data;
  if (!data) return null;

  const meta = claimTypeMeta(data.claim_type);
  const TypeIcon = meta.Icon;
  const verified = data.status === "Verified";

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
            {data.critical ? <Badge variant="danger">Critical</Badge> : null}
            <span className="text-xs text-muted-foreground">
              extracted {formatDateTime(data.created_at)}
            </span>
          </span>
        }
        actions={
          <>
            {canVerify && !verified ? (
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
          </>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
            <TypeIcon className="h-3.5 w-3.5" />
            Claim
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
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
              Verification verdicts
            </CardTitle>
          </CardHeader>
          <CardContent>
            {data.verifications.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No verdict has been recorded for this claim.
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
              Review history
            </CardTitle>
          </CardHeader>
          <CardContent>
            {data.history.length === 0 ? (
              <p className="text-xs text-muted-foreground">No history recorded.</p>
            ) : (
              <ol className="space-y-3">
                {data.history.map((entry) => (
                  <li key={entry.id} className="border-l-2 border-border pl-3">
                    <div className="flex flex-wrap items-center gap-2 text-[11px]">
                      <span className="font-medium text-foreground">{entry.action}</span>
                      {entry.to_status ? <ClaimStatusBadge status={entry.to_status} /> : null}
                      <span className="text-muted-foreground">
                        {formatDateTime(entry.created_at)}
                      </span>
                    </div>
                    {entry.note ? (
                      <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                        {entry.note}
                      </p>
                    ) : null}
                  </li>
                ))}
              </ol>
            )}
          </CardContent>
        </Card>
      </div>

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
              description="Only a workspace admin can approve or reject a claim. Approving is the only path to a Verified claim."
            />
          ) : verified ? (
            <div className="flex items-start gap-2 rounded-md border border-status-ok/35 bg-status-ok/[0.06] p-3">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-status-ok" />
              <p className="text-xs leading-relaxed text-muted-foreground">
                This claim was approved by a human reviewer
                {data.verified_at ? ` on ${formatDateTime(data.verified_at)}` : ""}. Automatic
                re-verification cannot overwrite a human decision.
              </p>
            </div>
          ) : (
            <>
              <Textarea
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder="Optional note recorded with the decision…"
                rows={3}
                maxLength={2000}
              />
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  size="sm"
                  onClick={() => void handleReview("approve")}
                  disabled={review.isPending || data.evidence_count === 0}
                >
                  {review.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <CheckCircle2 className="h-4 w-4" />
                  )}
                  Approve as Verified
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => void handleReview("reject")}
                  disabled={review.isPending}
                >
                  <XCircle className="h-4 w-4" />
                  Reject
                </Button>
                {data.evidence_count === 0 ? (
                  <span className="text-[11px] text-muted-foreground">
                    A claim without evidence cannot be approved.
                  </span>
                ) : null}
                {data.conflicts.some((conflict) => conflict.status === "open") ? (
                  <span className="text-[11px] text-status-warn">
                    Resolve the open conflict before approving.
                  </span>
                ) : null}
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
