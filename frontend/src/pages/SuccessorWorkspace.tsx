import { Link, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  CheckCircle2,
  FileText,
  ListChecks,
  Lock,
  Sparkles,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader, PanelSkeleton } from "@/components/common/PageHeader";
import { ProjectWorkspaceNav } from "@/components/common/ProjectWorkspaceNav";
import { EmptyState, ErrorState } from "@/components/common/States";
import { Tooltip } from "@/components/common/Tooltip";
import { useProject } from "@/hooks/use-projects";
import { usePageTitle } from "@/hooks/use-page-title";
import { useSuccessorWorkspace } from "@/hooks/use-readiness";
import { formatDate, humanise } from "@/lib/format";
import {
  BAND_META,
  CRITICALITY_META,
  GAP_STATUS_META,
  TASK_ORIGIN_META,
  TASK_PRIORITY_META,
  TASK_STATUS_META,
  isWorkspaceClaimItem,
} from "@/lib/phase5-meta";
import { cn } from "@/lib/utils";
import { claimTypeMeta } from "@/lib/intelligence-meta";
import type { ReadinessBand, WorkspaceClaimItem, WorkspaceSection, WorkspaceTaskItem } from "@/types";

function EvidenceRef({ item, projectId }: { item: WorkspaceClaimItem; projectId: string }) {
  if (item.evidence.length === 0) return null;
  return (
    <div className="mt-2 space-y-1.5">
      {item.evidence.slice(0, 4).map((ref, index) => (
        <div
          key={index}
          className={cn(
            "rounded border-l-2 bg-card/30 px-2.5 py-1.5 text-[11px] leading-relaxed",
            ref.restricted ? "border-status-warn/50" : "border-border",
          )}
        >
          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-muted-foreground">
            <span className="font-medium text-foreground/90">{ref.source_name}</span>
            {ref.source_type ? <span>· {humanise(ref.source_type)}</span> : null}
            {ref.location ? <span className="font-mono">· {ref.location}</span> : null}
            {ref.author ? <span>· {ref.author}</span> : null}
            {ref.source_date ? <span>· {formatDate(ref.source_date)}</span> : null}
            {ref.restricted ? (
              <Tooltip label="This source is restricted; its content is not shown.">
                <span className="inline-flex items-center gap-1 text-status-warn">
                  <Lock className="h-3 w-3" />
                  Restricted
                </span>
              </Tooltip>
            ) : null}
          </div>
          {ref.quote ? (
            <p className="mt-1 border-l border-border/70 pl-2 italic text-muted-foreground">
              “{ref.quote}”
            </p>
          ) : null}
        </div>
      ))}
      <Link
        to={`/projects/${projectId}/memory/claims/${item.claim_id}`}
        className="inline-block text-[11px] text-primary hover:underline"
      >
        Open claim ·
      </Link>
    </div>
  );
}

function ClaimItem({ item, projectId }: { item: WorkspaceClaimItem; projectId: string }) {
  const meta = claimTypeMeta(item.claim_type);
  const Icon = meta.Icon;
  return (
    <li className="rounded-md border border-border/70 bg-card/40 p-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
          <Icon className="h-3 w-3" />
          {meta.label}
        </span>
        {item.critical ? <Badge variant="danger">Critical</Badge> : null}
        {item.entity ? <Badge variant="outline">{item.entity}</Badge> : null}
      </div>
      <p className="mt-2 text-sm leading-relaxed text-foreground">{item.text}</p>
      <EvidenceRef item={item} projectId={projectId} />
    </li>
  );
}

function TaskItem({ item }: { item: WorkspaceTaskItem }) {
  const origin = TASK_ORIGIN_META[item.origin];
  return (
    <li className="rounded-md border border-border/70 bg-card/40 p-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant={TASK_PRIORITY_META[item.priority].tone}>{TASK_PRIORITY_META[item.priority].label}</Badge>
        <Badge variant={TASK_STATUS_META[item.status].tone}>{TASK_STATUS_META[item.status].label}</Badge>
        <Tooltip label={origin.hint}>
          <Badge variant={origin.tone}>
            {item.origin === "suggested" ? <Sparkles className="mr-1 h-3 w-3" /> : null}
            {origin.label}
          </Badge>
        </Tooltip>
        {item.owner ? (
          <Badge variant="secondary">owner · {item.owner}</Badge>
        ) : (
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">no owner recorded</span>
        )}
      </div>
      <p className="mt-2 text-sm font-medium text-foreground">{item.title}</p>
      {item.description ? (
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{item.description}</p>
      ) : null}
      {item.completion_criteria ? (
        <p className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">
          <span className="text-foreground/80">Done when:</span> {item.completion_criteria}
        </p>
      ) : null}
      {item.dependency_ids.length > 0 ? (
        <p className="mt-1 text-[11px] text-status-warn">
          Depends on {item.dependency_ids.length} other task(s)
        </p>
      ) : null}
    </li>
  );
}

function StartHere({ section, projectId }: { section: WorkspaceSection; projectId: string }) {
  const readiness = section.readiness ?? null;
  const band = readiness?.band as ReadinessBand | null | undefined;
  return (
    <div className="space-y-4">
      {readiness ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="panel p-4">
            <p className="label-eyebrow">Readiness</p>
            <p className="mt-1 font-display text-2xl tabular-nums text-foreground">
              {readiness.score === null ? "—" : readiness.score}
            </p>
            {band ? <Badge variant={BAND_META[band].tone}>{BAND_META[band].label}</Badge> : null}
          </div>
          <div className="panel p-4">
            <p className="label-eyebrow">Critical blockers</p>
            <p className="mt-1 font-display text-2xl tabular-nums text-status-danger">
              {readiness.blocker_count}
            </p>
          </div>
          <div className="panel p-4">
            <p className="label-eyebrow">Open conflicts / gaps</p>
            <p className="mt-1 font-display text-2xl tabular-nums text-foreground">
              {readiness.open_conflict_count} / {readiness.open_gap_count}
            </p>
          </div>
          <div className="panel p-4">
            <p className="label-eyebrow">Checklist tasks</p>
            <p className="mt-1 font-display text-2xl tabular-nums text-foreground">
              {readiness.task_count}
            </p>
          </div>
        </div>
      ) : null}

      {section.narrative && section.narrative.length > 0 ? (
        <ul className="space-y-1.5">
          {section.narrative.map((line, index) => (
            <li key={index} className="flex items-start gap-2 text-sm leading-relaxed text-muted-foreground">
              <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              {line}
            </li>
          ))}
        </ul>
      ) : null}

      {section.blockers && section.blockers.length > 0 ? (
        <div className="rounded-md border border-status-danger/35 bg-status-danger/[0.05] p-3">
          <p className="flex items-center gap-2 text-xs font-medium text-status-danger">
            <AlertTriangle className="h-3.5 w-3.5" />
            Blockers recorded in the latest readiness evaluation
          </p>
          <ul className="mt-2 space-y-1">
            {section.blockers.map((blocker, index) => (
              <li key={index} className="text-[11px] leading-relaxed text-muted-foreground">
                <span className="font-mono uppercase tracking-wider">{blocker.code ?? "issue"}</span>
                {blocker.message ? ` · ${blocker.message}` : ""}
              </li>
            ))}
          </ul>
          <Button asChild size="sm" variant="outline" className="mt-3">
            <Link to={`/projects/${projectId}/readiness`}>Open readiness dashboard</Link>
          </Button>
        </div>
      ) : null}
    </div>
  );
}

export default function SuccessorWorkspace() {
  const { projectId } = useParams<{ projectId: string }>();
  const project = useProject(projectId);
  usePageTitle(project.data ? `Successor — ${project.data.name}` : "Successor Workspace");
  const workspace = useSuccessorWorkspace(projectId);

  if (!projectId) return null;

  const data = workspace.data;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Successor workspace"
        title={project.data?.name ? `Start here · ${project.data.name}` : "Successor workspace"}
        description="A guided, section-by-section onboarding. Every statement is approved by a human reviewer and links back to its source evidence; restricted material is never shown."
        actions={
          <Button variant="ghost" size="sm" asChild>
            <Link to={`/projects/${projectId}`}>
              <ArrowLeft className="h-4 w-4" />
              Project
            </Link>
          </Button>
        }
      />

      <ProjectWorkspaceNav projectId={projectId} />

      {workspace.isError ? (
        <ErrorState
          error={workspace.error}
          title="The successor workspace could not be loaded"
          onRetry={() => void workspace.refetch()}
        />
      ) : workspace.isLoading ? (
        <PanelSkeleton rows={6} />
      ) : !data ? (
        <EmptyState icon={<BookOpen className="h-4 w-4" />} title="Nothing to show" />
      ) : (
        <div className="space-y-5">
          <div className="panel flex flex-wrap items-center gap-x-5 gap-y-2 border border-border p-4 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1.5">
              <FileText className="h-3.5 w-3.5" />
              {data.counts.approved_claims ?? 0} approved claims
            </span>
            <span>{data.counts.pending_review ?? 0} awaiting review</span>
            <span>{data.counts.open_conflicts ?? 0} open conflicts</span>
            <span>{data.counts.open_gaps ?? 0} open gaps</span>
            <span className="inline-flex items-center gap-1.5">
              <ListChecks className="h-3.5 w-3.5" />
              {data.counts.tasks_open ?? 0} of {data.counts.tasks ?? 0} tasks remaining
            </span>
            <span className="ml-auto">
              {data.handover.published_version_number ? (
                <span className="inline-flex items-center gap-1.5 text-status-ok">
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  Handover v{data.handover.published_version_number} published{" "}
                  {formatDate(data.handover.published_at)}
                </span>
              ) : (
                <span>No handover published yet</span>
              )}
            </span>
          </div>

          {/* Section navigation */}
          <nav aria-label="Workspace sections" className="flex flex-wrap gap-1.5">
            {data.sections.map((section, index) => (
              <a
                key={section.key}
                href={`#ws-${section.key}`}
                className="inline-flex items-center gap-1.5 rounded-md border border-border/70 px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
              >
                <span className="font-mono text-[10px] text-muted-foreground">
                  {String.fromCharCode(65 + index)}
                </span>
                {section.title}
              </a>
            ))}
          </nav>

          {data.sections.map((section, index) => (
            <Card key={section.key} id={`ws-${section.key}`} className="scroll-mt-6">
              <CardHeader className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="flex h-5 w-5 items-center justify-center rounded border border-border/80 font-mono text-[10px] text-muted-foreground">
                    {String.fromCharCode(65 + index)}
                  </span>
                  <CardTitle className="font-display text-base font-medium text-foreground">
                    {section.title}
                  </CardTitle>
                </div>
                <p className="text-[11px] leading-relaxed text-muted-foreground">{section.intro}</p>
              </CardHeader>
              <CardContent>
                {section.key === "start_here" ? (
                  <StartHere section={section} projectId={projectId} />
                ) : section.items.length === 0 ? (
                  <p className="text-xs leading-relaxed text-muted-foreground">
                    {section.empty_reason ?? "No approved knowledge for this section."}
                  </p>
                ) : (
                  <ul className="space-y-2.5">
                    {section.items.map((item, itemIndex) =>
                      isWorkspaceClaimItem(item) ? (
                        <ClaimItem key={item.claim_id} item={item} projectId={projectId} />
                      ) : (
                        <TaskItem key={item.task_id} item={item} />
                      ),
                    )}
                  </ul>
                )}
              </CardContent>
            </Card>
          ))}

          {data.open_gaps.length > 0 ? (
            <Card className="border-status-warn/30">
              <CardHeader className="flex-row items-center justify-between space-y-0">
                <CardTitle className="text-xs font-medium text-muted-foreground">
                  Known missing knowledge
                </CardTitle>
                <Button asChild size="sm" variant="ghost">
                  <Link to={`/projects/${projectId}/knowledge-risk`}>Open knowledge risk</Link>
                </Button>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2">
                  {data.open_gaps.map((gap) => (
                    <li key={gap.gap_id} className="rounded-md border border-border/70 bg-card/40 p-2.5">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Badge variant={GAP_STATUS_META[gap.status].tone}>
                          {GAP_STATUS_META[gap.status].label}
                        </Badge>
                        <Badge
                          variant={
                            CRITICALITY_META[gap.criticality]?.tone ?? "secondary"
                          }
                        >
                          {CRITICALITY_META[gap.criticality]?.label ?? gap.criticality}
                        </Badge>
                        <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                          {humanise(gap.category)}
                        </span>
                      </div>
                      <p className="mt-1.5 text-xs leading-relaxed text-foreground">{gap.description}</p>
                      {gap.suggested_resolution ? (
                        <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                          Suggested resolution: {gap.suggested_resolution}
                        </p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ) : null}

          <p className="text-[11px] leading-relaxed text-muted-foreground">{data.disclaimer}</p>
        </div>
      )}
    </div>
  );
}
