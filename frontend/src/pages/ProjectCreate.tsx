import * as React from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft, FolderPlus, Layers } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/toast";
import { useAuth } from "@/contexts/AuthContext";
import { PageHeader } from "@/components/common/PageHeader";
import { WorkspaceCreateDialog } from "@/components/common/WorkspaceCreateDialog";
import { useCreateProject } from "@/hooks/use-projects";
import { usePageTitle } from "@/hooks/use-page-title";
import { useWorkspaces } from "@/hooks/use-workspaces";
import { toErrorMessage } from "@/services/api";
import { PROJECT_STATUS_META } from "@/lib/source-meta";
import type { ProjectStatus } from "@/types";

const DEFAULT_STATUS: ProjectStatus = "active";

export default function ProjectCreate() {
  usePageTitle("New Project");
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const workspaces = useWorkspaces();
  const createProject = useCreateProject();
  const { toast } = useToast();
  const { isDemoSession } = useAuth();

  const [workspaceId, setWorkspaceId] = React.useState("");
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [departingRole, setDepartingRole] = React.useState("");
  const [successorRole, setSuccessorRole] = React.useState("");
  const [status, setStatus] = React.useState<ProjectStatus>(DEFAULT_STATUS);
  const [error, setError] = React.useState<string | null>(null);
  const [createWorkspaceOpen, setCreateWorkspaceOpen] = React.useState(false);

  // Preselect from ?workspace_id=... or the only available workspace.
  React.useEffect(() => {
    const requested = searchParams.get("workspace_id");
    if (requested && (workspaces.data ?? []).some((item) => item.id === requested)) {
      setWorkspaceId(requested);
      return;
    }
    if (!workspaceId && workspaces.data?.length === 1) {
      setWorkspaceId(workspaces.data[0].id);
    }
  }, [searchParams, workspaces.data, workspaceId]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    if (!workspaceId) {
      setError("Select a workspace. Projects are always created inside a workspace.");
      return;
    }
    try {
      const project = await createProject.mutateAsync({
        workspace_id: workspaceId,
        name: name.trim(),
        description: description.trim() || null,
        departing_role: departingRole.trim() || null,
        successor_role: successorRole.trim() || null,
        status,
      });
      toast({ title: "Project created", description: project.name, variant: "success" });
      navigate(`/projects/${project.id}`, { replace: true });
    } catch (caught) {
      setError(toErrorMessage(caught));
    }
  };

  const noWorkspaces = workspaces.isSuccess && (workspaces.data?.length ?? 0) === 0;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Projects"
        title="Create a project"
        description="Projects scope the sources, claims and evidence for one continuity effort."
        actions={
          <Button variant="ghost" size="sm" asChild>
            <Link to="/projects">
              <ArrowLeft className="h-4 w-4" />
              Back
            </Link>
          </Button>
        }
      />

      {isDemoSession ? (
        <Alert variant="default" className="border-primary/40 bg-primary/10">
          <div>
            <p className="text-xs font-semibold text-foreground">
              Public Demo Environment: Read-Only Project Management
            </p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Creating new projects is disabled in public demo mode to maintain workspace isolation.
              You can explore the pre-seeded{" "}
              <Link to="/projects" className="text-primary underline">
                Payment Gateway System
              </Link>{" "}
              project and all its reconstructed memory.
            </p>
          </div>
        </Alert>
      ) : null}

      {workspaces.isLoading ? (
        <Skeleton className="h-[420px] rounded-lg" />
      ) : noWorkspaces ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">A workspace is required first</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-xs leading-relaxed text-muted-foreground">
              You are not a member of any workspace yet. Projects are created inside a workspace,
              and the backend enforces membership on every request.
            </p>
            <Button size="sm" onClick={() => setCreateWorkspaceOpen(true)}>
              <Layers className="h-4 w-4" />
              Create workspace
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Project details</CardTitle>
          </CardHeader>
          <CardContent>
            <form className="space-y-5" onSubmit={handleSubmit}>
              {error ? <Alert variant="destructive" title="Could not create project">{error}</Alert> : null}

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5 sm:col-span-2">
                  <Label htmlFor="workspace">Workspace</Label>
                  <Select value={workspaceId} onValueChange={setWorkspaceId}>
                    <SelectTrigger id="workspace">
                      <SelectValue placeholder="Select a workspace" />
                    </SelectTrigger>
                    <SelectContent>
                      {(workspaces.data ?? []).map((workspace) => (
                        <SelectItem key={workspace.id} value={workspace.id}>
                          {workspace.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1.5 sm:col-span-2">
                  <Label htmlFor="name">Project name</Label>
                  <Input
                    id="name"
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    placeholder="Billing service handover"
                    required
                    maxLength={200}
                  />
                </div>

                <div className="space-y-1.5 sm:col-span-2">
                  <Label htmlFor="description">Description</Label>
                  <Textarea
                    id="description"
                    value={description}
                    onChange={(event) => setDescription(event.target.value)}
                    placeholder="What this project covers and why the handover matters."
                    maxLength={5000}
                    rows={3}
                  />
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="departing-role">Departing role</Label>
                  <Input
                    id="departing-role"
                    value={departingRole}
                    onChange={(event) => setDepartingRole(event.target.value)}
                    placeholder="Staff engineer"
                    maxLength={120}
                  />
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="successor-role">Successor role</Label>
                  <Input
                    id="successor-role"
                    value={successorRole}
                    onChange={(event) => setSuccessorRole(event.target.value)}
                    placeholder="Backend engineer"
                    maxLength={120}
                  />
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="status">Status</Label>
                  <Select
                    value={status}
                    onValueChange={(value) => setStatus(value as ProjectStatus)}
                  >
                    <SelectTrigger id="status">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {(Object.keys(PROJECT_STATUS_META) as ProjectStatus[]).map((key) => (
                        <SelectItem key={key} value={key}>
                          {PROJECT_STATUS_META[key].label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="flex items-center gap-2 border-t border-border/70 pt-4">
                  <Button type="submit" disabled={createProject.isPending || !name.trim() || isDemoSession}>
                    <FolderPlus className="h-4 w-4" />
                    {isDemoSession
                      ? "Creation disabled in demo mode"
                      : createProject.isPending
                        ? "Creating…"
                        : "Create project"}
                  </Button>
                  <Button type="button" variant="ghost" asChild>
                    <Link to="/projects">Cancel</Link>
                  </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      <WorkspaceCreateDialog
        open={createWorkspaceOpen}
        onOpenChange={setCreateWorkspaceOpen}
        onCreated={(workspace) => setWorkspaceId(workspace.id)}
      />
    </div>
  );
}
