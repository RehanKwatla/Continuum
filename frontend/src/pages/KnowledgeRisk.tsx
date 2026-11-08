import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  BadgeCheck,
  CircleHelp,
  Loader2,
  RefreshCw,
  Send,
  ShieldAlert,
  Trash2,
  UserX,
  Wrench,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/toast";
import { PageHeader, PanelSkeleton } from "@/components/common/PageHeader";
import { ProjectWorkspaceNav } from "@/components/common/ProjectWorkspaceNav";
import { EmptyState, ErrorState } from "@/components/common/States";
import { Tooltip } from "@/components/common/Tooltip";
import { useProject } from "@/hooks/use-projects";
import {
  useAnalyseKnowledgeDependencies,
  useDetectKnowledgeGaps,
  useKnowledgeDependencies,
  useKnowledgeGaps,
  useOverrideKnowledgeDependency,
  useUpdateKnowledgeGap,
} from "@/hooks/use-readiness";
import { formatDateTime, humanise } from "@/lib/format";
import { CRITICALITY_META, GAP_STATUS_META, RISK_STATUS_META } from "@/lib/phase5-meta";
import { hasAtLeast } from "@/lib/roles";
import { cn } from "@/lib/utils";
import { toErrorMessage } from "@/services/api";
import type {
  DependencyRiskStatus,
  KnowledgeDependency,
  KnowledgeGap,
  KnowledgeGapStatus,
} from "@/types";

const RISK_OPTIONS: DependencyRiskStatus[] = ["Low", "Moderate", "High", "Unknown"];
const GAP_OPTIONS: KnowledgeGapStatus[] = ["Open", "In Progress", "Resolved", "Accepted Risk"];

function DependencyCard({
  dependency,
  projectId,
  canOverride,
  onOverride,
  busy,
}: {
  dependency: KnowledgeDependency;
  projectId: string;
  canOverride: boolean;
  onOverride: (input: { dependencyId: string; input: { risk_status: DependencyRiskStatus; note: string } }) => void;
  busy: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [risk, setRisk] = useState<DependencyRiskStatus>(
    dependency.effective_risk_status,
  );
  const [note, setNote] = useState("");
  const overridden = Object.keys(dependency.override ?? {}).length > 0;

  return (
    <div className="rounded-lg border border-border/80 bg-card/40 p-3.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant={RISK_STATUS_META[dependency.effective_risk_status].tone}>
          {RISK_STATUS_META[dependency.effective_risk_status].label} risk
        </Badge>
        {overridden ? (
          <Tooltip label={`Computed risk was ${RISK_STATUS_META[dependency.risk_status].label}; a reviewer overrode it.`}>
            <Badge variant="info">Reviewer override</Badge>
          </Tooltip>
        ) : null}
        <Badge variant="outline">level {dependency.dependency_level}</Badge>
        <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          {dependency.dependency_key}
        </span>
      </div>

      <p className="mt-2 text-sm font-medium text-foreground">
        {dependency.entity ?? "Unnamed knowledge entity"}
      </p>

      {dependency.involved_people.length > 0 ? (
        <p className="mt-1 flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <UserX className="h-3 w-3" />
          Concentrated on: {dependency.involved_people.join(", ")}
        </p>
      ) : null}

      {dependency.evidence_summary ? (
        <p className="mt-2 rounded border-l-2 border-border bg-card/30 px-2.5 py-1.5 text-[11px] leading-relaxed text-muted-foreground">
          {dependency.evidence_summary}
        </p>
      ) : null}

      {dependency.missing_backup_information ? (
        <p className="mt-1.5 text-[11px] leading-relaxed text-status-warn">
          Missing backup information: {dependency.missing_backup_information}
        </p>
      ) : null}

      {dependency.claim_ids.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {dependency.claim_ids.slice(0, 8).map((claimId) => (
            <Link
              key={claimId}
              to={`/projects/${projectId}/memory/claims/${claimId}`}
              className="inline-flex items-center gap-1 rounded border border-border/70 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
            >
              <BadgeCheck className="h-3 w-3" />
              {claimId.slice(0, 8)}
            </Link>
          ))}
        </div>
      ) : null}

      <div className="mt-2 flex items-center gap-3 text-[11px] text-muted-foreground">
        {dependency.computed_at ? <span>computed {formatDateTime(dependency.computed_at)}</span> : null}
        {canOverride ? (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="ml-auto h-7"
            onClick={() => setOpen((value) => !value)}
          >
            <Wrench className="h-3.5 w-3.5" />
            {open ? "Cancel" : "Reviewer override"}
          </Button>
        ) : null}
      </div>

      {open && canOverride ? (
        <div className="mt-2 space-y-2 rounded-md border border-primary/30 bg-primary/[0.04] p-3">
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            An override is recorded in the audit trail and never deletes the computed risk — the
            computed value stays visible.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <div className="space-y-1">
              <Label className="text-[11px]">Effective risk</Label>
              <Select value={risk} onValueChange={(value) => setRisk(value as DependencyRiskStatus)}>
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {RISK_OPTIONS.map((option) => (
                    <SelectItem key={option} value={option} className="text-xs">
                      {option}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1 sm:col-span-2">
              <Label className="text-[11px]">Reason (required, audited)</Label>
              <Textarea
                value={note}
                rows={2}
                onChange={(event) => setNote(event.target.value)}
                placeholder="e.g. verified that a second engineer now owns this module"
              />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              disabled={busy || note.trim().length < 3}
              onClick={() => {
                onOverride({ dependencyId: dependency.id, input: { risk_status: risk, note: note.trim() } });
                setOpen(false);
                setNote("");
              }}
            >
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
              Record override
            </Button>
            {overridden ? (
              <Button
                size="sm"
                variant="ghost"
                disabled={busy}
                onClick={() => {
                  onOverride({ dependencyId: dependency.id, input: { risk_status: risk, note: "cleared" } });
                  setOpen(false);
                }}
              >
                <Trash2 className="h-3.5 w-3.5" />
                Clear
              </Button>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function GapCard({
  gap,
  projectId,
  canUpdate,
  onUpdate,
  busy,
}: {
  gap: KnowledgeGap;
  projectId: string;
  canUpdate: boolean;
  onUpdate: (input: { gapId: string; input: { status: KnowledgeGapStatus; note?: string } }) => void;
  busy: boolean;
}) {
  const criticality = CRITICALITY_META[gap.criticality];
  return (
    <div className="rounded-lg border border-border/80 bg-card/40 p-3.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant={GAP_STATUS_META[gap.status].tone}>{GAP_STATUS_META[gap.status].label}</Badge>
        {criticality ? <Badge variant={criticality.tone}>{criticality.label}</Badge> : null}
        <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          {humanise(gap.category)}
        </span>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-foreground">{gap.description}</p>
      {gap.suggested_resolution ? (
        <p className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">
          Suggested resolution: {gap.suggested_resolution}
        </p>
      ) : null}
      {gap.related_claim_ids.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {gap.related_claim_ids.slice(0, 6).map((claimId) => (
            <Link
              key={claimId}
              to={`/projects/${projectId}/memory/claims/${claimId}`}
              className="inline-flex items-center gap-1 rounded border border-border/70 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground hover:border-primary/50 hover:text-foreground"
            >
              <BadgeCheck className="h-3 w-3" />
              {claimId.slice(0, 8)}
            </Link>
          ))}
        </div>
      ) : null}
      {canUpdate ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Select
            value={gap.status}
            disabled={busy}
            onValueChange={(value) => onUpdate({ gapId: gap.id, input: { status: value as KnowledgeGapStatus } })}
          >
            <SelectTrigger className="h-8 w-48 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {GAP_OPTIONS.map((option) => (
                <SelectItem key={option} value={option} className="text-xs">
                  {GAP_STATUS_META[option].label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <span className="text-[11px] text-muted-foreground">
            Moving a gap is audited; a gap is never deleted.
          </span>
        </div>
      ) : null}
    </div>
  );
}

export default function KnowledgeRisk() {
  const { projectId } = useParams<{ projectId: string }>();
  const project = useProject(projectId);
  const dependencies = useKnowledgeDependencies(projectId);
  const gaps = useKnowledgeGaps(projectId);
  const analyse = useAnalyseKnowledgeDependencies(projectId ?? "");
  const detect = useDetectKnowledgeGaps(projectId ?? "");
  const override = useOverrideKnowledgeDependency(projectId ?? "");
  const updateGap = useUpdateKnowledgeGap(projectId ?? "");
  const { toast } = useToast();
  const [gapFilter, setGapFilter] = useState<KnowledgeGapStatus | "all">("all");

  if (!projectId) return null;

  const role = project.data?.workspace?.role ?? null;
  const canAnalyse = hasAtLeast(role, "member");
  const canOverride = hasAtLeast(role, "admin");

  const items = dependencies.data?.items ?? [];
  const highRisk = items.filter((item) => item.effective_risk_status === "High").length;
  const unknown = items.filter((item) => item.effective_risk_status === "Unknown").length;
  const gapItems = (gaps.data?.items ?? []).filter((gap) => gapFilter === "all" || gap.status === gapFilter);

  const runAnalyse = async () => {
    try {
      const result = await analyse.mutateAsync();
      toast({
        title: "Knowledge concentration analysed",
        description: `${result.total} dependency record(s) recomputed from approved evidence.`,
        variant: "success",
      });
    } catch (caught) {
      toast({ title: "Analysis failed", description: toErrorMessage(caught), variant: "error" });
    }
  };

  const runDetect = async () => {
    try {
      const result = await detect.mutateAsync();
      toast({
        title: "Missing knowledge detected",
        description: `${result.total} gap(s) recorded.`,
        variant: "success",
      });
    } catch (caught) {
      toast({ title: "Detection failed", description: toErrorMessage(caught), variant: "error" });
    }
  };

  const doOverride = async (payload: {
    dependencyId: string;
    input: { risk_status: DependencyRiskStatus; note: string };
  }) => {
    try {
      await override.mutateAsync(payload);
      toast({ title: "Override recorded", description: "The computed risk is preserved.", variant: "success" });
    } catch (caught) {
      toast({ title: "Could not record the override", description: toErrorMessage(caught), variant: "error" });
    }
  };

  const doUpdateGap = async (payload: { gapId: string; input: { status: KnowledgeGapStatus; note?: string } }) => {
    try {
      await updateGap.mutateAsync(payload);
      toast({ title: "Gap updated", description: "The change is recorded in the audit trail.", variant: "success" });
    } catch (caught) {
      toast({ title: "Could not update the gap", description: toErrorMessage(caught), variant: "error" });
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Knowledge risk"
        title={project.data?.name ? `Knowledge risk · ${project.data.name}` : "Knowledge risk"}
        description="Where project knowledge concentrates on a single person, and where documented knowledge is missing. Nothing is inferred from a name alone — a dependency needs evidence of actual responsibility."
        actions={
          <>
            <Button variant="ghost" size="sm" asChild>
              <Link to={`/projects/${projectId}`}>
                <ArrowLeft className="h-4 w-4" />
                Project
              </Link>
            </Button>
            <Button size="sm" variant="outline" onClick={() => void runDetect()} disabled={!canAnalyse || detect.isPending}>
              {detect.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <CircleHelp className="h-4 w-4" />}
              Detect gaps
            </Button>
            <Button size="sm" onClick={() => void runAnalyse()} disabled={!canAnalyse || analyse.isPending}>
              {analyse.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              Analyse dependencies
            </Button>
          </>
        }
      />

      <ProjectWorkspaceNav projectId={projectId} />

      <Tabs defaultValue="dependencies">
        <TabsList>
          <TabsTrigger value="dependencies">
            Dependencies{dependencies.data ? ` (${items.length})` : ""}
          </TabsTrigger>
          <TabsTrigger value="gaps">Missing knowledge{gaps.data ? ` (${gaps.data.items.length})` : ""}</TabsTrigger>
        </TabsList>

        <TabsContent value="dependencies">
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="panel p-4">
                <p className="label-eyebrow">Dependencies tracked</p>
                <p className="mt-1 font-display text-2xl tabular-nums text-foreground">{items.length}</p>
              </div>
              <div className="panel p-4">
                <p className="label-eyebrow">High risk</p>
                <p className="mt-1 font-display text-2xl tabular-nums text-status-danger">{highRisk}</p>
              </div>
              <div className="panel p-4">
                <p className="label-eyebrow">Uncertain evidence</p>
                <p className="mt-1 font-display text-2xl tabular-nums text-muted-foreground">{unknown}</p>
              </div>
            </div>

            {dependencies.isError ? (
              <ErrorState
                error={dependencies.error}
                title="Knowledge dependencies could not be loaded"
                onRetry={() => void dependencies.refetch()}
              />
            ) : dependencies.isLoading ? (
              <PanelSkeleton rows={3} />
            ) : items.length === 0 ? (
              <EmptyState
                icon={<ShieldAlert className="h-4 w-4" />}
                title="No knowledge dependency has been analysed yet"
                description="Run the analysis to find knowledge that appears to depend on a single person. A dependency is only recorded when approved evidence shows real responsibility."
                action={
                  canAnalyse ? (
                    <Button size="sm" onClick={() => void runAnalyse()} disabled={analyse.isPending}>
                      <RefreshCw className="h-4 w-4" />
                      Analyse dependencies
                    </Button>
                  ) : null
                }
              />
            ) : (
              <div
                className={cn(
                  "grid gap-3",
                  items.length > 1 ? "lg:grid-cols-2" : "",
                )}
              >
                {items.map((dependency) => (
                  <DependencyCard
                    key={dependency.id}
                    dependency={dependency}
                    projectId={projectId}
                    canOverride={canOverride}
                    onOverride={(payload) => void doOverride(payload)}
                    busy={override.isPending}
                  />
                ))}
              </div>
            )}

            {!canOverride && items.length > 0 ? (
              <p className="text-[11px] text-muted-foreground">
                Reviewer overrides require the admin role. The computed risk is always shown.
              </p>
            ) : null}
          </div>
        </TabsContent>

        <TabsContent value="gaps">
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <Label className="text-[11px]">Filter</Label>
              <Select value={gapFilter} onValueChange={(value) => setGapFilter(value as KnowledgeGapStatus | "all")}>
                <SelectTrigger className="h-8 w-44 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all" className="text-xs">
                    All statuses
                  </SelectItem>
                  {GAP_OPTIONS.map((option) => (
                    <SelectItem key={option} value={option} className="text-xs">
                      {GAP_STATUS_META[option].label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {gaps.isError ? (
              <ErrorState
                error={gaps.error}
                title="Knowledge gaps could not be loaded"
                onRetry={() => void gaps.refetch()}
              />
            ) : gaps.isLoading ? (
              <PanelSkeleton rows={3} />
            ) : gapItems.length === 0 ? (
              <EmptyState
                icon={<CircleHelp className="h-4 w-4" />}
                title="No missing knowledge recorded"
                description="Gaps are detected by comparing readiness requirements against approved knowledge. Run a readiness evaluation first, then detect gaps."
                action={
                  canAnalyse ? (
                    <Button size="sm" variant="outline" onClick={() => void runDetect()} disabled={detect.isPending}>
                      <CircleHelp className="h-4 w-4" />
                      Detect gaps
                    </Button>
                  ) : null
                }
              />
            ) : (
              <div className="grid gap-3 lg:grid-cols-2">
                {gapItems.map((gap) => (
                  <GapCard
                    key={gap.id}
                    gap={gap}
                    projectId={projectId}
                    canUpdate={canAnalyse}
                    onUpdate={(payload) => void doUpdateGap(payload)}
                    busy={updateGap.isPending}
                  />
                ))}
              </div>
            )}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
