import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  BadgeCheck,
  CircleDashed,
  FileCheck2,
  HelpCircle,
  Loader2,
  RefreshCw,
  ScrollText,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { EmptyState, ErrorState } from "@/components/common/States";
import { PageHeader } from "@/components/common/PageHeader";
import { ProjectWorkspaceNav } from "@/components/common/ProjectWorkspaceNav";
import { useProject } from "@/hooks/use-projects";
import { useClaims, useGenerateHandover, useHandover, useQuestions } from "@/hooks/use-memory";
import { claimTypeMeta } from "@/lib/intelligence-meta";
import { formatDateTime } from "@/lib/format";
import { hasAtLeast } from "@/lib/roles";
import { ApiClientError, toErrorMessage } from "@/services/api";
import type { ClaimSummary, HandoverRead, HandoverSectionRead } from "@/types";

function LinkedClaimChip({
  projectId,
  claimId,
  claim,
}: {
  projectId: string;
  claimId: string;
  claim: ClaimSummary | undefined;
}) {
  const meta = claim ? claimTypeMeta(claim.claim_type) : null;
  const Icon = meta?.Icon ?? BadgeCheck;
  return (
    <Link
      to={`/projects/${projectId}/memory/claims/${claimId}`}
      className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-border/70 bg-card/50 px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
      title={claim ? claim.text : "Open the approved claim"}
    >
      <Icon className="h-3 w-3 shrink-0" />
      <span className="truncate">{claim ? claim.text : "Approved claim"}</span>
    </Link>
  );
}

function SectionBlock({
  projectId,
  section,
  claimMap,
}: {
  projectId: string;
  section: HandoverSectionRead;
  claimMap: Map<string, ClaimSummary>;
}) {
  const advisory = section.key === "next_actions";
  const hasContent = section.statements.length > 0;

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="text-xs font-medium text-muted-foreground">
          {section.title}
        </CardTitle>
        {advisory ? (
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
            Advisory
          </span>
        ) : null}
      </CardHeader>
      <CardContent>
        {hasContent ? (
          <ul className="space-y-3">
            {section.statements.map((statement, index) => (
              <li key={index} className="space-y-1.5">
                <p className="text-sm leading-relaxed text-foreground">{statement.text}</p>
                <div className="flex flex-wrap gap-1.5">
                  {statement.claim_ids.map((claimId) => (
                    <LinkedClaimChip
                      key={claimId}
                      projectId={projectId}
                      claimId={claimId}
                      claim={claimMap.get(claimId)}
                    />
                  ))}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs leading-relaxed text-muted-foreground">
            No approved claim covers this section, so nothing was written for it.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function HandoverDocument({ projectId, document }: { projectId: string; document: HandoverRead }) {
  const claims = useClaims(projectId, { status: "Verified", page_size: 100 });
  const questions = useQuestions(projectId, { status: "open", page_size: 100 });

  const claimMap = new Map<string, ClaimSummary>(
    (claims.data?.items ?? []).map((claim) => [claim.id, claim]),
  );
  const rejected = document.validation_errors ?? [];

  return (
    <div className="space-y-4">
      <div className="panel flex flex-col gap-2 border border-border p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <ShieldCheck className="h-3.5 w-3.5" />
          Written from {document.claim_ids.length} approved claim
          {document.claim_ids.length === 1 ? "" : "s"} only. Unlinked sentences are deleted by the
          output validator.
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
          <span>Generated {formatDateTime(document.created_at)}</span>
          {document.model_name ? <span className="font-mono">model {document.model_name}</span> : null}
        </div>
      </div>

      {document.status === "failed" ? (
        <div className="panel border border-status-danger/35 bg-status-danger/[0.06] p-4">
          <p className="flex items-center gap-2 text-xs text-muted-foreground">
            <TriangleAlert className="h-3.5 w-3.5 text-status-danger" />
            The Handover Writer could not complete. The sections below may be empty.
          </p>
        </div>
      ) : null}

      {document.claim_ids.length === 0 ? (
        <div className="panel border border-border p-4">
          <p className="text-xs leading-relaxed text-muted-foreground">
            No claims have been approved for this project yet, so the handover contains no
            statements. A claim is only included here after a human reviewer marks it{" "}
            <span className="text-foreground">Verified</span>.
          </p>
        </div>
      ) : null}

      {document.summary ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-xs font-medium text-muted-foreground">Summary</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm leading-relaxed text-foreground">{document.summary}</p>
          </CardContent>
        </Card>
      ) : null}

      <div className="space-y-3">
        {document.sections.map((section) => (
          <SectionBlock
            key={section.key}
            projectId={projectId}
            section={section}
            claimMap={claimMap}
          />
        ))}
      </div>

      {rejected.length > 0 ? (
        <Card className="border-dashed">
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle className="text-xs font-medium text-muted-foreground">
              Statements rejected by the output validator
            </CardTitle>
            <span className="text-[11px] tabular-nums text-muted-foreground">{rejected.length}</span>
          </CardHeader>
          <CardContent className="space-y-2">
            {rejected.map((error, index) => (
              <div
                key={index}
                className="rounded-md border border-border/70 bg-card/40 p-2.5 text-[11px] leading-relaxed text-muted-foreground"
              >
                <span className="font-mono uppercase tracking-wider">
                  {String(error.code ?? "rejected")}
                </span>
                {error.section ? <span> · {String(error.section)}</span> : null}
                {error.text ? <p className="mt-1 text-foreground/90">{String(error.text)}</p> : null}
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}

      <Card className="border-dashed">
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle className="text-xs font-medium text-muted-foreground">
            Open questions — kept separate from the handover
          </CardTitle>
          <HelpCircle className="h-3.5 w-3.5 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          {questions.isLoading ? (
            <Skeleton className="h-12 w-full" />
          ) : questions.data && questions.data.items.length > 0 ? (
            <ul className="space-y-2">
              {questions.data.items.map((question) => (
                <li
                  key={question.id}
                  className="rounded-md border border-border/70 bg-card/40 p-2.5"
                >
                  <p className="text-xs leading-relaxed text-foreground">{question.question}</p>
                  {question.context ? (
                    <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                      {question.context}
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs leading-relaxed text-muted-foreground">
              No open questions were raised for this project.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function HandoverPreview() {
  const { projectId } = useParams<{ projectId: string }>();
  const project = useProject(projectId);
  const handover = useHandover(projectId);
  const generate = useGenerateHandover(projectId ?? "");
  const { toast } = useToast();

  const role = project.data?.workspace?.role ?? null;
  const canGenerate = hasAtLeast(role, "member");

  const handleGenerate = async () => {
    try {
      const document = await generate.mutateAsync();
      toast({
        title: "Handover generated",
        description: `${document.claim_ids.length} approved claim(s) referenced.`,
        variant: document.status === "failed" ? "error" : "success",
      });
    } catch (caught) {
      const notConfigured =
        caught instanceof ApiClientError && caught.code === "ai_not_configured";
      toast({
        title: notConfigured ? "Intelligence layer not configured" : "Could not generate handover",
        description: toErrorMessage(caught),
        variant: "error",
      });
    }
  };

  if (!projectId) return null;

  const generateButton = (
    <Button
      size="sm"
      onClick={() => void handleGenerate()}
      disabled={!canGenerate || generate.isPending}
    >
      {generate.isPending ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : handover.data ? (
        <RefreshCw className="h-4 w-4" />
      ) : (
        <Sparkles className="h-4 w-4" />
      )}
      {handover.data ? "Regenerate handover" : "Generate handover"}
    </Button>
  );

  const missing = handover.error instanceof ApiClientError && handover.error.isNotFound;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Handover"
        title={project.data?.name ?? "Handover"}
        description="A structured handover assembled from approved claims only. Every statement links back to the claim it came from."
        actions={
          <>
            <Button variant="ghost" size="sm" asChild>
              <Link to={`/projects/${projectId}`}>
                <ArrowLeft className="h-4 w-4" />
                Project
              </Link>
            </Button>
            {generateButton}
          </>
        }
      />

      <ProjectWorkspaceNav projectId={projectId} />

      {!canGenerate ? (
        <p className="text-[11px] text-muted-foreground">
          The member role is required to generate a handover.
        </p>
      ) : null}

      {handover.isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-16 w-full rounded-lg" />
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-32 w-full rounded-lg" />
          ))}
        </div>
      ) : missing ? (
        <EmptyState
          icon={<ScrollText className="h-4 w-4" />}
          title="No handover generated yet"
          description="A handover is written from the claims a human has approved. Approve claims in the memory workspace, then generate the handover here."
          action={
            <Button size="sm" variant="outline" asChild>
              <Link to={`/projects/${projectId}/memory/claims?status=Verified`}>
                <FileCheck2 className="h-4 w-4" />
                Review approved claims
              </Link>
            </Button>
          }
        />
      ) : handover.isError ? (
        <ErrorState
          error={handover.error}
          title="The handover could not be loaded"
          onRetry={() => void handover.refetch()}
        />
      ) : handover.data ? (
        <HandoverDocument projectId={projectId} document={handover.data} />
      ) : (
        <EmptyState
          icon={<CircleDashed className="h-4 w-4" />}
          title="Nothing to show"
          description="No handover is available for this project."
        />
      )}
    </div>
  );
}
