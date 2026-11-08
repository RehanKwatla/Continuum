import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  BadgeCheck,
  CircleAlert,
  Gauge,
  History,
  Loader2,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  TriangleAlert,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import { MetricTile, PageHeader, PanelSkeleton } from "@/components/common/PageHeader";
import { ProjectWorkspaceNav } from "@/components/common/ProjectWorkspaceNav";
import { EmptyState, ErrorState } from "@/components/common/States";
import { Tooltip } from "@/components/common/Tooltip";
import { useProject } from "@/hooks/use-projects";
import {
  useEvaluateReadiness,
  useReadinessHistory,
  useReadinessOverview,
  useScorecard,
} from "@/hooks/use-readiness";
import { formatDateTime, humanise, pluralise } from "@/lib/format";
import { BAND_META, COMPLETION_META, CRITICALITY_META, scoreTone } from "@/lib/phase5-meta";
import { hasAtLeast } from "@/lib/roles";
import { cn } from "@/lib/utils";
import { toErrorMessage } from "@/services/api";
import type { ContinuityScorecard, ReadinessEvaluation, ReadinessIssue } from "@/types";

function ScoreBar({ score }: { score: number | null }) {
  const value = score ?? 0;
  const tone = scoreTone(score);
  const toneClass =
    tone === "ok"
      ? "bg-status-ok"
      : tone === "info"
        ? "bg-status-info"
        : tone === "warn"
          ? "bg-status-warn"
          : "bg-status-danger";
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
      <div className={cn("h-full rounded-full transition-all", toneClass)} style={{ width: `${value}%` }} />
    </div>
  );
}

function IssueList({ issues, tone }: { issues: ReadinessIssue[]; tone: "danger" | "warn" }) {
  if (issues.length === 0) {
    return (
      <p className="text-xs leading-relaxed text-muted-foreground">
        {tone === "danger" ? "No critical blockers were recorded in this evaluation." : "No warnings."}
      </p>
    );
  }
  const Icon = tone === "danger" ? ShieldAlert : TriangleAlert;
  return (
    <ul className="space-y-2">
      {issues.map((issue, index) => (
        <li
          key={`${issue.code}-${issue.requirement_id ?? index}`}
          className={cn(
            "flex items-start gap-2.5 rounded-md border p-2.5 text-xs leading-relaxed",
            tone === "danger"
              ? "border-status-danger/35 bg-status-danger/[0.05]"
              : "border-status-warn/35 bg-status-warn/[0.05]",
          )}
        >
          <Icon
            className={cn(
              "mt-0.5 h-3.5 w-3.5 shrink-0",
              tone === "danger" ? "text-status-danger" : "text-status-warn",
            )}
          />
          <div className="space-y-0.5">
            <p className="text-foreground">{issue.message}</p>
            <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              {issue.code}
              {issue.dimension ? ` · ${humanise(issue.dimension)}` : ""}
              {issue.requirement_id ? ` · ${issue.requirement_id}` : ""}
            </p>
          </div>
        </li>
      ))}
    </ul>
  );
}

function DimensionGrid({
  evaluation,
  labels,
}: {
  evaluation: ReadinessEvaluation;
  labels: Record<string, string>;
}) {
  const dimensions = Object.entries(evaluation.dimension_scores);
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {dimensions.map(([key, dimension]) => (
        <div key={key} className="rounded-lg border border-border/80 bg-card/40 p-3.5">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="text-sm font-medium text-foreground">
                {dimension.label || labels[key] || humanise(key)}
              </p>
              <p className="text-[11px] text-muted-foreground">
                weight {dimension.weight}% · {dimension.complete_count}/{dimension.requirement_count}{" "}
                requirements
              </p>
            </div>
            <span
              className={cn(
                "shrink-0 font-mono text-sm tabular-nums",
                dimension.score >= 75
                  ? "text-status-ok"
                  : dimension.score >= 50
                    ? "text-status-warn"
                    : "text-status-danger",
              )}
            >
              {dimension.score}%
            </span>
          </div>
          <div className="mt-2.5">
            <ScoreBar score={dimension.score} />
          </div>
        </div>
      ))}
    </div>
  );
}

function RequirementTable({ evaluation }: { evaluation: ReadinessEvaluation }) {
  const grouped = useMemo(() => {
    const map = new Map<string, typeof evaluation.requirements>();
    for (const requirement of evaluation.requirements) {
      const list = map.get(requirement.dimension) ?? [];
      list.push(requirement);
      map.set(requirement.dimension, list);
    }
    return [...map.entries()];
  }, [evaluation.requirements]);

  return (
    <div className="space-y-4">
      <p className="text-[11px] leading-relaxed text-muted-foreground">
        Every requirement the engine evaluated, with the evidence that satisfied it. A requirement is
        only credited when an <span className="text-foreground">approved</span> claim supports it.
      </p>
      {grouped.map(([dimension, requirements]) => (
        <div key={dimension} className="space-y-2">
          <p className="label-eyebrow">{humanise(dimension)}</p>
          <ul className="space-y-2">
            {requirements.map((requirement) => {
              const completion = COMPLETION_META[requirement.completion];
              const criticality =
                CRITICALITY_META[requirement.criticality as keyof typeof CRITICALITY_META];
              return (
                <li
                  key={requirement.requirement_id}
                  className="rounded-md border border-border/70 bg-card/40 p-3"
                >
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge variant={completion.tone}>{completion.label}</Badge>
                    {criticality ? <Badge variant={criticality.tone}>{criticality.label}</Badge> : null}
                    <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                      {requirement.requirement_id}
                    </span>
                  </div>
                  <p className="mt-2 text-xs leading-relaxed text-foreground">
                    {requirement.description}
                  </p>
                  {requirement.evaluation_reason ? (
                    <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                      {requirement.evaluation_reason}
                    </p>
                  ) : null}
                  {requirement.missing_information ? (
                    <p className="mt-1 text-[11px] leading-relaxed text-status-warn">
                      Missing: {requirement.missing_information}
                    </p>
                  ) : null}
                  {requirement.supporting_claim_ids.length > 0 ? (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {requirement.supporting_claim_ids.slice(0, 8).map((claimId) => (
                        <Link
                          key={claimId}
                          to={`/projects/${evaluation.project_id}/memory/claims/${claimId}`}
                          className="inline-flex items-center gap-1 rounded border border-border/70 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
                        >
                          <BadgeCheck className="h-3 w-3" />
                          {claimId.slice(0, 8)}
                        </Link>
                      ))}
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}

function ScorecardPanel({ projectId, scorecard }: { projectId: string; scorecard: ContinuityScorecard }) {
  const counts: Array<{ label: string; value: number; to?: string }> = [
    { label: "Pending review items", value: scorecard.pending_review_items },
    {
      label: "Unresolved conflicts",
      value: scorecard.conflicts.open,
      to: `/projects/${projectId}/memory/conflicts`,
    },
    {
      label: "Open knowledge gaps",
      value: scorecard.missing_knowledge.open,
      to: `/projects/${projectId}/knowledge-risk`,
    },
    {
      label: "High-risk dependencies",
      value: scorecard.knowledge_dependencies.high_risk,
      to: `/projects/${projectId}/knowledge-risk`,
    },
    {
      label: "Successor tasks remaining",
      value:
        (scorecard.successor_tasks["Not Started"] ?? 0) +
        (scorecard.successor_tasks["In Progress"] ?? 0) +
        (scorecard.successor_tasks.Blocked ?? 0),
      to: `/projects/${projectId}/successor-checklist`,
    },
  ];
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="text-xs font-medium text-muted-foreground">
          Project continuity scorecard
        </CardTitle>
        <span className="text-[11px] text-muted-foreground">
          generated {formatDateTime(scorecard.generated_at)}
        </span>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-3 lg:grid-cols-5">
          {counts.map((item) => (
            <div key={item.label} className="bg-card px-4 py-3">
              <p className="text-2xl font-display tabular-nums text-foreground">{item.value}</p>
              <p className="mt-0.5 text-[11px] leading-tight text-muted-foreground">{item.label}</p>
              {item.to ? (
                <Link to={item.to} className="mt-1 inline-block text-[11px] text-primary hover:underline">
                  Open
                </Link>
              ) : null}
            </div>
          ))}
        </div>
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          Every figure above is read from the database. Pending review counts include claims awaiting a
          human decision and unresolved conflicts. Source coverage:{" "}
          {scorecard.source_coverage.total_sources} total · {scorecard.source_coverage.processed_sources}{" "}
          processed · {scorecard.source_coverage.evidence_coverage_percent}% of approved claims carry
          evidence.
        </p>
      </CardContent>
    </Card>
  );
}

export default function HandoverReadiness() {
  const { projectId } = useParams<{ projectId: string }>();
  const project = useProject(projectId);
  const overview = useReadinessOverview(projectId);
  const history = useReadinessHistory(projectId, { limit: 8 });
  const scorecard = useScorecard(projectId);
  const evaluate = useEvaluateReadiness(projectId ?? "");
  const { toast } = useToast();

  if (!projectId) return null;

  const role = project.data?.workspace?.role ?? null;
  const canEvaluate = hasAtLeast(role, "member");
  const evaluation = overview.data?.evaluation ?? null;

  const handleEvaluate = async () => {
    try {
      const result = await evaluate.mutateAsync({});
      toast({
        title: "Readiness evaluated",
        description: `Overall score ${result.overall_score} · ${BAND_META[result.band].label}.`,
        variant: "success",
      });
    } catch (caught) {
      toast({
        title: "Could not run the readiness evaluation",
        description: toErrorMessage(caught),
        variant: "error",
      });
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Handover readiness"
        title={project.data?.name ?? "Handover readiness"}
        description="A deterministic assessment of how complete and trustworthy the approved knowledge is. The score never appears without its blockers, and it is never computed by an LLM."
        actions={
          <>
            <Button variant="ghost" size="sm" asChild>
              <Link to={`/projects/${projectId}`}>
                <ArrowLeft className="h-4 w-4" />
                Project
              </Link>
            </Button>
            <Button size="sm" onClick={() => void handleEvaluate()} disabled={!canEvaluate || evaluate.isPending}>
              {evaluate.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : evaluation ? (
                <RefreshCw className="h-4 w-4" />
              ) : (
                <Sparkles className="h-4 w-4" />
              )}
              {evaluation ? "Re-evaluate" : "Run evaluation"}
            </Button>
          </>
        }
      />

      <ProjectWorkspaceNav projectId={projectId} />

      {!canEvaluate ? (
        <p className="text-[11px] text-muted-foreground">
          Running an evaluation requires the member role. The result is visible to every member of the
          workspace.
        </p>
      ) : null}

      {overview.isError ? (
        <ErrorState
          error={overview.error}
          title="The readiness assessment could not be loaded"
          onRetry={() => void overview.refetch()}
        />
      ) : overview.isLoading ? (
        <PanelSkeleton rows={4} />
      ) : !evaluation ? (
        <EmptyState
          icon={<Gauge className="h-4 w-4" />}
          title="No readiness evaluation has been run yet"
          description="Approving claims in the memory workspace is what makes a project ready. Run the deterministic engine to measure the current state."
          action={
            canEvaluate ? (
              <Button size="sm" onClick={() => void handleEvaluate()} disabled={evaluate.isPending}>
                <Sparkles className="h-4 w-4" />
                Run evaluation
              </Button>
            ) : null
          }
        />
      ) : (
        <div className="space-y-5">
          <div className="panel p-5">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
              <div className="flex items-end gap-4">
                <div>
                  <p className="label-eyebrow">Overall readiness</p>
                  <p className="font-display text-5xl tabular-nums text-foreground">
                    {evaluation.overall_score}
                    <span className="ml-1 text-lg text-muted-foreground">/100</span>
                  </p>
                </div>
                <div className="pb-1">
                  <Tooltip label={BAND_META[evaluation.band].hint}>
                    <Badge variant={BAND_META[evaluation.band].tone}>{BAND_META[evaluation.band].label}</Badge>
                  </Tooltip>
                </div>
              </div>
              <p className="text-[11px] leading-relaxed text-muted-foreground sm:max-w-sm sm:text-right">
                Evaluated {formatDateTime(evaluation.created_at)}
                {evaluation.handover_id ? " against the current handover" : ""}.{" "}
                {pluralise(evaluation.blockers.length, "blocker")},{" "}
                {pluralise(evaluation.warnings.length, "warning")}.
              </p>
            </div>
            <p className="mt-4 text-[11px] leading-relaxed text-muted-foreground">
              {overview.data?.disclaimer}
            </p>
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card className="border-status-danger/30">
              <CardHeader className="flex-row items-center justify-between space-y-0">
                <CardTitle className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                  <ShieldAlert className="h-3.5 w-3.5 text-status-danger" />
                  Critical blockers
                </CardTitle>
                <span className="text-[11px] tabular-nums text-muted-foreground">
                  {evaluation.blockers.length}
                </span>
              </CardHeader>
              <CardContent>
                <IssueList issues={evaluation.blockers} tone="danger" />
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex-row items-center justify-between space-y-0">
                <CardTitle className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                  <TriangleAlert className="h-3.5 w-3.5 text-status-warn" />
                  Warnings and missing information
                </CardTitle>
                <span className="text-[11px] tabular-nums text-muted-foreground">
                  {evaluation.warnings.length}
                </span>
              </CardHeader>
              <CardContent>
                <IssueList issues={evaluation.warnings} tone="warn" />
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-xs font-medium text-muted-foreground">
                Dimension scores
              </CardTitle>
            </CardHeader>
            <CardContent>
              <DimensionGrid
                evaluation={evaluation}
                labels={overview.data?.dimension_labels ?? {}}
              />
              <p className="mt-4 text-[11px] leading-relaxed text-muted-foreground">
                Weighted by the configuration used at evaluation time:{" "}
                {Object.entries(evaluation.weights)
                  .map(([key, weight]) => `${humanise(key)} ${weight}%`)
                  .join(" · ")}
                .
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-xs font-medium text-muted-foreground">
                Requirements and evidence
              </CardTitle>
            </CardHeader>
            <CardContent>
              <RequirementTable evaluation={evaluation} />
            </CardContent>
          </Card>
        </div>
      )}

      {scorecard.data ? (
        <ScorecardPanel projectId={projectId} scorecard={scorecard.data} />
      ) : scorecard.isError ? (
        <ErrorState
          error={scorecard.error}
          title="The continuity scorecard could not be loaded"
          onRetry={() => void scorecard.refetch()}
        />
      ) : null}

      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
            <History className="h-3.5 w-3.5" />
            Evaluation history
          </CardTitle>
        </CardHeader>
        <CardContent>
          {history.isLoading ? (
            <PanelSkeleton rows={2} />
          ) : (history.data?.items.length ?? 0) === 0 ? (
            <p className="flex items-center gap-2 text-xs text-muted-foreground">
              <CircleAlert className="h-3.5 w-3.5" />
              No stored evaluations yet.
            </p>
          ) : (
            <ul className="divide-y divide-border/70">
              {history.data?.items.map((item) => (
                <li key={item.id} className="flex items-center gap-3 py-2.5 text-xs">
                  <Badge variant={BAND_META[item.band].tone}>{item.overall_score}</Badge>
                  <span className="text-muted-foreground">{BAND_META[item.band].label}</span>
                  <span className="ml-auto tabular-nums text-muted-foreground">
                    {item.blockers.length} blockers · {item.warnings.length} warnings
                  </span>
                  <span className="text-[11px] text-muted-foreground">
                    {formatDateTime(item.created_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <p className="text-[11px] leading-relaxed text-muted-foreground">
        The formula is fixed and documented: {overview.data?.formula ?? "weighted requirement completion"}.
        A readiness score is a measure of the approved knowledge, not proof that a successor will
        succeed.
      </p>
    </div>
  );
}
