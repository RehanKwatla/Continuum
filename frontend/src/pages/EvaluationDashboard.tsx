import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  BarChart3,
  CheckCircle2,
  FlaskConical,
  Loader2,
  Play,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { PageHeader, PanelSkeleton } from "@/components/common/PageHeader";
import { ProjectWorkspaceNav } from "@/components/common/ProjectWorkspaceNav";
import { EmptyState, ErrorState } from "@/components/common/States";
import { Tooltip } from "@/components/common/Tooltip";
import { useProject } from "@/hooks/use-projects";
import {
  useEvaluationComparison,
  useEvaluationRuns,
  useRunEvaluation,
  useRunSuccessorExercise,
  useSeedSyntheticProject,
  useSuccessorExercise,
} from "@/hooks/use-readiness";
import { formatDateTime, humanise } from "@/lib/format";
import { hasAtLeast } from "@/lib/roles";
import { cn } from "@/lib/utils";
import { toErrorMessage } from "@/services/api";
import type { EvaluationRun, MetricBlock } from "@/types";

const METRIC_LABELS: Record<string, string> = {
  A_claim_extraction: "Claim extraction",
  B_evidence_accuracy: "Evidence citation accuracy",
  C_verification_accuracy: "Verification accuracy",
  D_conflict_detection: "Conflict detection",
  E_stale_detection: "Stale-information detection",
  F_critical_knowledge_coverage: "Critical knowledge coverage",
  G_unsupported_handover_rate: "Unsupported handover rate",
  H_permission_leakage: "Permission leakage",
  I_readiness_agreement: "Readiness agreement",
};

/** Lower is better for these metrics. */
const INVERTED = new Set(["G_unsupported_handover_rate"]);

function pct(value: number | boolean | string | undefined): string {
  if (typeof value !== "number") return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function metricLabel(key: string): string {
  return METRIC_LABELS[key] ?? humanise(key);
}

function MetricTile({ metricKey, run }: { metricKey: string; run: EvaluationRun }) {
  const block = run.report[metricKey] as MetricBlock | undefined;
  const value = run.metrics[metricKey];
  const undefinedMetric = block?.undefined === true;
  const inverted = INVERTED.has(metricKey);
  const numeric = typeof value === "number" ? value : null;
  const good = numeric === null ? null : inverted ? numeric <= 0.05 : numeric >= 0.75;
  return (
    <div className="panel p-4">
      <p className="label-eyebrow">{metricLabel(metricKey)}</p>
      <p
        className={cn(
          "mt-1 font-display text-2xl tabular-nums",
          undefinedMetric ? "text-muted-foreground" : good ? "text-status-ok" : "text-status-warn",
        )}
      >
        {undefinedMetric ? "n/a" : pct(value)}
      </p>
      {undefinedMetric ? (
        <p className="mt-0.5 text-[10px] leading-tight text-muted-foreground">
          No data to evaluate (denominator was zero).
        </p>
      ) : inverted && numeric !== null ? (
        <p className="mt-0.5 text-[10px] leading-tight text-muted-foreground">lower is better</p>
      ) : null}
    </div>
  );
}

function MetricDetail({ metricKey, run }: { metricKey: string; run: EvaluationRun }) {
  const block = run.report[metricKey] as MetricBlock | undefined;
  if (!block) return null;
  const entries = Object.entries(block).filter(
    ([key, value]) => key !== "value" && key !== "undefined" && typeof value !== "object",
  );
  return (
    <div className="rounded-md border border-border/70 bg-card/40 p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium text-foreground">{metricLabel(metricKey)}</p>
        <span className="font-mono text-xs text-muted-foreground">
          {block.undefined ? "n/a" : pct(block.value)}
        </span>
      </div>
      {entries.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
          {entries.map(([key, value]) => (
            <span key={key} className="text-[11px] text-muted-foreground">
              {humanise(key)}: <span className="tabular-nums text-foreground/90">{String(value)}</span>
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ExerciseReport({ run }: { run: EvaluationRun }) {
  const questions = run.report.questions ?? [];
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {[
          ["Attempted", run.metrics.tasks_attempted],
          ["Completed", run.metrics.tasks_completed],
          ["Blocked", run.metrics.tasks_blocked],
          ["Missing information", run.metrics.tasks_missing_information],
          ["Exercise score", run.metrics.exercise_score],
        ].map(([label, value]) => (
          <div key={String(label)} className="panel p-4">
            <p className="label-eyebrow">{String(label)}</p>
            <p className="mt-1 font-display text-2xl tabular-nums text-foreground">
              {label === "Exercise score" && typeof value === "number" ? `${value}%` : String(value ?? "—")}
            </p>
          </div>
        ))}
      </div>
      <div className="space-y-2">
        {questions.map((question) => (
          <div key={question.question_id} className="rounded-md border border-border/70 bg-card/40 p-3">
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge
                variant={
                  question.outcome === "completed"
                    ? "ok"
                    : question.outcome === "blocked"
                      ? "danger"
                      : "warn"
                }
              >
                {humanise(question.outcome)}
              </Badge>
              <span className="text-xs text-foreground">{question.prompt}</span>
            </div>
            {question.answer ? (
              <p className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">
                {question.answer}
              </p>
            ) : null}
            <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
              {question.explanation}
            </p>
            {question.supporting_claim_ids.length > 0 ? (
              <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                {question.supporting_claim_ids.length} supporting claim(s)
              </p>
            ) : null}
          </div>
        ))}
      </div>
      {typeof run.report.disclaimer === "string" ? (
        <p className="text-[11px] leading-relaxed text-muted-foreground">{run.report.disclaimer}</p>
      ) : null}
    </div>
  );
}

function ComparisonView({
  base,
  candidate,
  comparison,
  loading,
  error,
}: {
  base: string;
  candidate: string;
  comparison: ReturnType<typeof useEvaluationComparison>["data"];
  loading: boolean;
  error: unknown;
}) {
  if (!base || !candidate) {
    return (
      <p className="text-xs text-muted-foreground">
        Select a baseline and a candidate run to compare them and detect regressions.
      </p>
    );
  }
  if (loading) return <PanelSkeleton rows={3} />;
  if (error) return <ErrorState error={error} title="The comparison could not be computed" />;
  if (!comparison) return null;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3 text-xs">
        <Badge variant={comparison.regression_count > 0 ? "danger" : "ok"}>
          {comparison.regression_count} regression(s)
        </Badge>
        <Badge variant="info">{comparison.improvement_count} improvement(s)</Badge>
        <span className="text-muted-foreground">dataset {comparison.dataset_version}</span>
      </div>
      <ul className="space-y-1.5">
        {comparison.deltas.map((delta) => {
          const isRegression = comparison.regressions.some((item) => item.metric === delta.metric);
          const isImprovement = comparison.improvements.some((item) => item.metric === delta.metric);
          return (
            <li
              key={delta.metric}
              className={cn(
                "flex items-center gap-3 rounded-md border px-3 py-2 text-xs",
                isRegression
                  ? "border-status-danger/35 bg-status-danger/[0.05]"
                  : isImprovement
                    ? "border-status-ok/35 bg-status-ok/[0.05]"
                    : "border-border/70 bg-card/40",
              )}
            >
              <span className="text-foreground">{metricLabel(delta.metric)}</span>
              <span className="ml-auto tabular-nums text-muted-foreground">
                {String(delta.before)} → {String(delta.after)}
              </span>
              {typeof delta.delta === "number" ? (
                <span
                  className={cn(
                    "w-16 text-right tabular-nums",
                    delta.delta > 0 ? "text-status-ok" : delta.delta < 0 ? "text-status-danger" : "text-muted-foreground",
                  )}
                >
                  {delta.delta > 0 ? "+" : ""}
                  {delta.delta}
                </span>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default function EvaluationDashboard() {
  const { projectId } = useParams<{ projectId: string }>();
  const project = useProject(projectId);
  const runs = useEvaluationRuns(projectId, { page_size: 50 });
  const exercise = useSuccessorExercise(projectId);
  const runMetrics = useRunEvaluation(projectId ?? "");
  const runExercise = useRunSuccessorExercise(projectId ?? "");
  const workspaceId = project.data?.workspace?.id;
  const seed = useSeedSyntheticProject(workspaceId);
  const { toast } = useToast();

  const [base, setBase] = useState<string>("");
  const [candidate, setCandidate] = useState<string>("");
  const comparison = useEvaluationComparison(projectId, base || undefined, candidate || undefined);

  const metricRuns = useMemo(
    () => (runs.data?.items ?? []).filter((run) => run.kind === "metrics"),
    [runs.data],
  );
  const latest = metricRuns[0] ?? null;

  if (!projectId) return null;

  const role = project.data?.workspace?.role ?? null;
  const isAdmin = hasAtLeast(role, "admin");
  const canRunExercise = hasAtLeast(role, "member");

  const metricKeys = latest
    ? Object.keys(latest.metrics).filter((key) => key !== "permission_leakage_passed")
    : [];

  const doRunMetrics = async () => {
    try {
      const run = await runMetrics.mutateAsync(undefined);
      toast({
        title: "Evaluation complete",
        description: `${run.failures.length} metric(s) undefined or flagged. ${run.dataset_version}.`,
        variant: "success",
      });
    } catch (caught) {
      toast({ title: "Evaluation failed", description: toErrorMessage(caught), variant: "error" });
    }
  };

  const doRunExercise = async () => {
    try {
      const run = await runExercise.mutateAsync();
      toast({
        title: "Successor exercise complete",
        description: `${run.metrics.tasks_completed}/${run.metrics.tasks_attempted} tasks answerable from approved knowledge.`,
        variant: "success",
      });
    } catch (caught) {
      toast({ title: "Exercise failed", description: toErrorMessage(caught), variant: "error" });
    }
  };

  const doSeed = async () => {
    try {
      const result = await seed.mutateAsync();
      toast({
        title: "Ground-truth corpus seeded",
        description: `Project “${result.name}” created with ${result.sources} source(s).`,
        variant: "success",
      });
    } catch (caught) {
      toast({ title: "Could not seed the corpus", description: toErrorMessage(caught), variant: "error" });
    }
  };

  const leakagePassed = latest?.metrics.permission_leakage_passed;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Evaluation"
        title={project.data?.name ? `Evaluation · ${project.data.name}` : "Evaluation"}
        description="Reproducible evaluation of the extraction, verification, conflict and readiness layers against a synthetic ground-truth dataset, plus a limited evidence-based successor exercise."
        actions={
          <>
            <Button variant="ghost" size="sm" asChild>
              <Link to={`/projects/${projectId}`}>
                <ArrowLeft className="h-4 w-4" />
                Project
              </Link>
            </Button>
            <Button size="sm" variant="outline" onClick={() => void doRunExercise()} disabled={!canRunExercise || runExercise.isPending}>
              {runExercise.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <FlaskConical className="h-4 w-4" />}
              Run successor exercise
            </Button>
            <Button size="sm" onClick={() => void doRunMetrics()} disabled={!isAdmin || runMetrics.isPending}>
              {runMetrics.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              Run evaluation
            </Button>
          </>
        }
      />

      <ProjectWorkspaceNav projectId={projectId} />

      {!isAdmin ? (
        <p className="text-[11px] text-muted-foreground">
          Running the ground-truth evaluation requires the admin role; running the successor exercise
          requires the member role.
        </p>
      ) : null}

      <Tabs defaultValue="metrics">
        <TabsList>
          <TabsTrigger value="metrics">Extraction metrics</TabsTrigger>
          <TabsTrigger value="exercise">Successor exercise</TabsTrigger>
          <TabsTrigger value="runs">Runs and regressions</TabsTrigger>
        </TabsList>

        <TabsContent value="metrics">
          {runs.isError ? (
            <ErrorState error={runs.error} title="Evaluation runs could not be loaded" onRetry={() => void runs.refetch()} />
          ) : runs.isLoading ? (
            <PanelSkeleton rows={4} />
          ) : !latest ? (
            <EmptyState
              icon={<BarChart3 className="h-4 w-4" />}
              title="No evaluation run yet"
              description="Run the reproducible evaluation to score the extraction and verification layers against the synthetic ground-truth dataset. Metrics with no data are reported as undefined rather than as a fake score."
              action={
                isAdmin ? (
                  <div className="flex items-center gap-2">
                    <Button size="sm" onClick={() => void doRunMetrics()} disabled={runMetrics.isPending}>
                      <Play className="h-4 w-4" />
                      Run evaluation
                    </Button>
                    <Tooltip label="Creates the synthetic ground-truth project in this workspace.">
                      <Button size="sm" variant="outline" onClick={() => void doSeed()} disabled={!isAdmin || seed.isPending}>
                        {seed.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <FlaskConical className="h-4 w-4" />}
                        Seed ground-truth corpus
                      </Button>
                    </Tooltip>
                  </div>
                ) : null
              }
            />
          ) : (
            <div className="space-y-5">
              <div className="panel flex flex-wrap items-center gap-x-5 gap-y-2 p-4 text-xs text-muted-foreground">
                <span>Run {latest.id.slice(0, 8)}</span>
                <span>dataset {latest.dataset_version}</span>
                {latest.model_version ? <span className="font-mono">model {latest.model_version}</span> : null}
                <span>{formatDateTime(latest.created_at)}</span>
                {leakagePassed === false ? (
                  <Badge variant="danger" className="gap-1">
                    <TriangleAlert className="h-3 w-3" />
                    Permission leakage check failed
                  </Badge>
                ) : leakagePassed === true ? (
                  <Badge variant="ok" className="gap-1">
                    <ShieldCheck className="h-3 w-3" />
                    Permission leakage check passed
                  </Badge>
                ) : null}
              </div>

              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {metricKeys.map((key) => (
                  <MetricTile key={key} metricKey={key} run={latest} />
                ))}
              </div>

              <Card>
                <CardHeader>
                  <CardTitle className="text-xs font-medium text-muted-foreground">
                    Metric detail and counts
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {metricKeys.map((key) => (
                    <MetricDetail key={key} metricKey={key} run={latest} />
                  ))}
                </CardContent>
              </Card>

              {latest.failures.length > 0 ? (
                <Card className="border-status-warn/30">
                  <CardHeader>
                    <CardTitle className="text-xs font-medium text-muted-foreground">
                      Failures and undefined metrics
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ul className="space-y-1.5">
                      {latest.failures.map((failure, index) => (
                        <li key={index} className="text-[11px] leading-relaxed text-muted-foreground">
                          <span className="font-mono uppercase tracking-wider text-foreground/80">
                            {String(failure.metric ?? "issue")}
                          </span>{" "}
                          · {String(failure.reason ?? "")}
                        </li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              ) : null}
            </div>
          )}
        </TabsContent>

        <TabsContent value="exercise">
          {exercise.isError && !exercise.data ? (
            <EmptyState
              icon={<FlaskConical className="h-4 w-4" />}
              title="No successor exercise has been run"
              description="The exercise asks a fixed set of project-specific questions and reports which ones the approved knowledge can answer. It is a limited quality check, not a simulation of human competence."
              action={
                canRunExercise ? (
                  <Button size="sm" onClick={() => void doRunExercise()} disabled={runExercise.isPending}>
                    <FlaskConical className="h-4 w-4" />
                    Run successor exercise
                  </Button>
                ) : null
              }
            />
          ) : exercise.isLoading ? (
            <PanelSkeleton rows={4} />
          ) : exercise.data ? (
            <ExerciseReport run={exercise.data} />
          ) : null}
        </TabsContent>

        <TabsContent value="runs">
          <div className="space-y-5">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="base-run" className="text-[11px]">
                  Baseline run
                </Label>
                <Select value={base} onValueChange={setBase}>
                  <SelectTrigger id="base-run" className="h-9 text-xs">
                    <SelectValue placeholder="Select a baseline" />
                  </SelectTrigger>
                  <SelectContent>
                    {metricRuns.map((run) => (
                      <SelectItem key={run.id} value={run.id} className="text-xs">
                        {run.id.slice(0, 8)} · {formatDateTime(run.created_at)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="candidate-run" className="text-[11px]">
                  Candidate run
                </Label>
                <Select value={candidate} onValueChange={setCandidate}>
                  <SelectTrigger id="candidate-run" className="h-9 text-xs">
                    <SelectValue placeholder="Select a candidate" />
                  </SelectTrigger>
                  <SelectContent>
                    {metricRuns.map((run) => (
                      <SelectItem key={run.id} value={run.id} className="text-xs">
                        {run.id.slice(0, 8)} · {formatDateTime(run.created_at)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <ComparisonView
              base={base}
              candidate={candidate}
              comparison={comparison.data}
              loading={comparison.isLoading}
              error={comparison.isError ? comparison.error : null}
            />

            <Card>
              <CardHeader className="flex-row items-center justify-between space-y-0">
                <CardTitle className="text-xs font-medium text-muted-foreground">
                  All runs ({runs.data?.total ?? 0})
                </CardTitle>
                <Button size="sm" variant="outline" asChild>
                  <Link to={`/projects/${projectId}/system-health`}>
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    System health
                  </Link>
                </Button>
              </CardHeader>
              <CardContent>
                {runs.isLoading ? (
                  <PanelSkeleton rows={2} />
                ) : (runs.data?.items.length ?? 0) === 0 ? (
                  <p className="text-xs text-muted-foreground">No runs recorded.</p>
                ) : (
                  <ul className="divide-y divide-border/70">
                    {runs.data?.items.map((run) => (
                      <li key={run.id} className="flex flex-wrap items-center gap-3 py-2.5 text-xs">
                        <Badge variant={run.kind === "metrics" ? "info" : "secondary"}>
                          {run.kind === "metrics" ? "Metrics" : "Exercise"}
                        </Badge>
                        <span className="font-mono text-muted-foreground">{run.id.slice(0, 8)}</span>
                        <span className="text-muted-foreground">{run.dataset_version}</span>
                        <span className="ml-auto text-[11px] text-muted-foreground">
                          {formatDateTime(run.created_at)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>

      <p className="text-[11px] leading-relaxed text-muted-foreground">
        Metrics are computed by pure functions over real database rows and a stored ground-truth
        dataset. Repeated runs on unchanged data produce identical results; a comparison highlights any
        movement between two runs.
      </p>
    </div>
  );
}
