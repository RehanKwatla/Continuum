import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  BadgeCheck,
  Ban,
  ListChecks,
  Loader2,
  Plus,
  Sparkles,
  UserCheck,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/toast";
import { PageHeader, PanelSkeleton } from "@/components/common/PageHeader";
import { ProjectWorkspaceNav } from "@/components/common/ProjectWorkspaceNav";
import { EmptyState, ErrorState } from "@/components/common/States";
import { Tooltip } from "@/components/common/Tooltip";
import { useProject } from "@/hooks/use-projects";
import { usePageTitle } from "@/hooks/use-page-title";
import {
  useCreateSuccessorTask,
  useDeriveSuccessorTasks,
  useSuccessorTasks,
  useUpdateSuccessorTask,
} from "@/hooks/use-readiness";
import { formatDateTime } from "@/lib/format";
import { TASK_ORIGIN_META, TASK_PRIORITY_META, TASK_STATUS_META } from "@/lib/phase5-meta";
import { hasAtLeast } from "@/lib/roles";
import { toErrorMessage } from "@/services/api";
import type { SuccessorTask, SuccessorTaskPriority, SuccessorTaskStatus } from "@/types";

const STATUS_OPTIONS: SuccessorTaskStatus[] = ["Not Started", "In Progress", "Blocked", "Completed"];
const PRIORITY_OPTIONS: SuccessorTaskPriority[] = ["High", "Medium", "Low"];

function TaskRow({
  task,
  projectId,
  blockedByIds,
  canUpdate,
  onStatusChange,
  busy,
}: {
  task: SuccessorTask;
  projectId: string;
  blockedByIds: Set<string>;
  canUpdate: boolean;
  onStatusChange: (input: { taskId: string; input: { status: SuccessorTaskStatus } }) => void;
  busy: boolean;
}) {
  const origin = TASK_ORIGIN_META[task.origin];
  const isBlocked = task.status !== "Completed" && blockedByIds.size > 0;
  return (
    <div className="rounded-lg border border-border/80 bg-card/40 p-3.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant={TASK_PRIORITY_META[task.priority].tone}>{TASK_PRIORITY_META[task.priority].label}</Badge>
        <Badge variant={TASK_STATUS_META[task.status].tone}>{TASK_STATUS_META[task.status].label}</Badge>
        <Tooltip label={origin.hint}>
          <Badge variant={origin.tone}>
            {task.origin === "suggested" ? <Sparkles className="mr-1 h-3 w-3" /> : null}
            {origin.label}
          </Badge>
        </Tooltip>
        {isBlocked ? (
          <Tooltip label="One or more prerequisite tasks are not complete.">
            <Badge variant="danger" className="gap-1">
              <Ban className="h-3 w-3" />
              Blocked by prerequisites
            </Badge>
          </Tooltip>
        ) : null}
      </div>

      <p className="mt-2 text-sm font-medium text-foreground">{task.title}</p>
      {task.description ? (
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{task.description}</p>
      ) : null}

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
        {task.owner ? (
          <span className="inline-flex items-center gap-1">
            <UserCheck className="h-3 w-3" />
            Owner: {task.owner}
          </span>
        ) : (
          <span className="inline-flex items-center gap-1">
            <UserCheck className="h-3 w-3" />
            No owner recorded
          </span>
        )}
        <span>created {formatDateTime(task.created_at)}</span>
      </div>

      {task.completion_criteria ? (
        <p className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">
          <span className="text-foreground/80">Done when:</span> {task.completion_criteria}
        </p>
      ) : null}

      {task.supporting_claim_ids.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {task.supporting_claim_ids.slice(0, 6).map((claimId) => (
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
      ) : (
        <p className="mt-2 text-[11px] text-muted-foreground">No approved claim backs this task.</p>
      )}

      {canUpdate ? (
        <div className="mt-3">
          <Select
            value={task.status}
            disabled={busy}
            onValueChange={(value) =>
              onStatusChange({ taskId: task.id, input: { status: value as SuccessorTaskStatus } })
            }
          >
            <SelectTrigger className="h-8 w-44 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {STATUS_OPTIONS.map((option) => (
                <SelectItem key={option} value={option} className="text-xs">
                  {TASK_STATUS_META[option].label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      ) : null}
    </div>
  );
}

export default function SuccessorChecklist() {
  const { projectId } = useParams<{ projectId: string }>();
  const project = useProject(projectId);
  usePageTitle(project.data ? `Checklist — ${project.data.name}` : "Successor Checklist");
  const tasks = useSuccessorTasks(projectId);
  const derive = useDeriveSuccessorTasks(projectId ?? "");
  const update = useUpdateSuccessorTask(projectId ?? "");
  const create = useCreateSuccessorTask(projectId ?? "");
  const { toast } = useToast();

  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState<SuccessorTaskPriority>("Medium");
  const [criteria, setCriteria] = useState("");

  const items = tasks.data?.items ?? [];
  const byId = useMemo(() => new Map(items.map((task) => [task.id, task])), [items]);

  /** For each task, the ids of its incomplete prerequisites. */
  const blockedMap = useMemo(() => {
    const map = new Map<string, Set<string>>();
    for (const task of items) {
      const incomplete = new Set<string>();
      for (const dependencyId of task.dependency_ids) {
        const dependency = byId.get(dependencyId);
        if (dependency && dependency.status !== "Completed") incomplete.add(dependencyId);
      }
      map.set(task.id, incomplete);
    }
    return map;
  }, [items, byId]);

  if (!projectId) return null;

  const role = project.data?.workspace?.role ?? null;
  const canUpdate = hasAtLeast(role, "member");

  const counts = STATUS_OPTIONS.reduce<Record<string, number>>((acc, status) => {
    acc[status] = items.filter((task) => task.status === status).length;
    return acc;
  }, {});

  const runDerive = async () => {
    try {
      const result = await derive.mutateAsync();
      toast({
        title: "Checklist derived",
        description: `${result.created} new task(s) from approved knowledge; ${result.total} total. ${result.gaps_considered} gap(s) considered.`,
        variant: "success",
      });
    } catch (caught) {
      toast({ title: "Could not derive the checklist", description: toErrorMessage(caught), variant: "error" });
    }
  };

  const doStatus = async (payload: { taskId: string; input: { status: SuccessorTaskStatus } }) => {
    try {
      await update.mutateAsync(payload);
      toast({ title: "Task updated", description: "The progress change is recorded in the audit trail.", variant: "success" });
    } catch (caught) {
      toast({ title: "Could not update the task", description: toErrorMessage(caught), variant: "error" });
    }
  };

  const addTask = async () => {
    try {
      await create.mutateAsync({
        title: title.trim(),
        description: description.trim() || null,
        priority,
        completion_criteria: criteria.trim() || null,
      });
      setTitle("");
      setDescription("");
      setCriteria("");
      setPriority("Medium");
      setShowCreate(false);
      toast({ title: "Task added", description: "No owner or deadline was inferred.", variant: "success" });
    } catch (caught) {
      toast({ title: "Could not add the task", description: toErrorMessage(caught), variant: "error" });
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Successor checklist"
        title={project.data?.name ? `Checklist · ${project.data.name}` : "Successor checklist"}
        description="Actionable tasks derived from approved knowledge. Owners are only shown when an approved ownership statement establishes one, and no deadline is ever invented."
        actions={
          <>
            <Button variant="ghost" size="sm" asChild>
              <Link to={`/projects/${projectId}`}>
                <ArrowLeft className="h-4 w-4" />
                Project
              </Link>
            </Button>
            <Button size="sm" variant="outline" onClick={() => setShowCreate((value) => !value)} disabled={!canUpdate}>
              <Plus className="h-4 w-4" />
              Add task
            </Button>
            <Button size="sm" onClick={() => void runDerive()} disabled={!canUpdate || derive.isPending}>
              {derive.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              Derive from knowledge
            </Button>
          </>
        }
      />

      <ProjectWorkspaceNav projectId={projectId} />

      <div className="grid gap-3 sm:grid-cols-4">
        {STATUS_OPTIONS.map((status) => (
          <div key={status} className="panel p-4">
            <p className="label-eyebrow">{TASK_STATUS_META[status].label}</p>
            <p className="mt-1 font-display text-2xl tabular-nums text-foreground">{counts[status] ?? 0}</p>
          </div>
        ))}
      </div>

      {showCreate && canUpdate ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-xs font-medium text-muted-foreground">
              Add a successor-authored task
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="space-y-1.5 sm:col-span-2">
                <Label htmlFor="task-title">Title</Label>
                <Input
                  id="task-title"
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  placeholder="e.g. Confirm the deployment owner"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="task-priority">Priority</Label>
                <Select value={priority} onValueChange={(value) => setPriority(value as SuccessorTaskPriority)}>
                  <SelectTrigger id="task-priority" className="h-9">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PRIORITY_OPTIONS.map((option) => (
                      <SelectItem key={option} value={option}>
                        {option}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="task-desc">Description</Label>
              <Textarea
                id="task-desc"
                value={description}
                rows={2}
                onChange={(event) => setDescription(event.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="task-criteria">Completion criteria</Label>
              <Input
                id="task-criteria"
                value={criteria}
                onChange={(event) => setCriteria(event.target.value)}
                placeholder="How will you know this is done?"
              />
            </div>
            <div className="flex items-center gap-2">
              <Button size="sm" onClick={() => void addTask()} disabled={create.isPending || title.trim().length < 1}>
                {create.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                Add task
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setShowCreate(false)}>
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {tasks.isError ? (
        <ErrorState
          error={tasks.error}
          title="The checklist could not be loaded"
          onRetry={() => void tasks.refetch()}
        />
      ) : tasks.isLoading ? (
        <PanelSkeleton rows={4} />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<ListChecks className="h-4 w-4" />}
          title="No successor tasks yet"
          description="Derive tasks from the approved knowledge, or add one yourself. Deriving is idempotent — running it again will not duplicate a task."
          action={
            canUpdate ? (
              <Button size="sm" onClick={() => void runDerive()} disabled={derive.isPending}>
                <Sparkles className="h-4 w-4" />
                Derive from knowledge
              </Button>
            ) : null
          }
        />
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {items.map((task) => (
            <TaskRow
              key={task.id}
              task={task}
              projectId={projectId}
              blockedByIds={blockedMap.get(task.id) ?? new Set()}
              canUpdate={canUpdate}
              onStatusChange={(payload) => void doStatus(payload)}
              busy={update.isPending}
            />
          ))}
        </div>
      )}

      {!canUpdate && items.length > 0 ? (
        <p className="text-[11px] text-muted-foreground">
          Updating task progress requires the member role.
        </p>
      ) : null}
    </div>
  );
}
