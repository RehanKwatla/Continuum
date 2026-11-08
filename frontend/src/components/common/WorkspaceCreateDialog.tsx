import * as React from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/toast";
import { useCreateWorkspace } from "@/hooks/use-workspaces";
import { toErrorMessage } from "@/services/api";
import type { WorkspaceSummary } from "@/types";

/**
 * Workspaces gate every other resource — the backend refuses project creation
 * outside a workspace the caller is a member of.
 */
export function WorkspaceCreateDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: (workspace: WorkspaceSummary) => void;
}) {
  const [name, setName] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const createWorkspace = useCreateWorkspace();
  const { toast } = useToast();

  React.useEffect(() => {
    if (!open) {
      setName("");
      setError(null);
    }
  }, [open]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      const workspace = await createWorkspace.mutateAsync({ name: name.trim() });
      toast({ title: "Workspace created", description: workspace.name, variant: "success" });
      onCreated?.(workspace);
      onOpenChange(false);
    } catch (caught) {
      setError(toErrorMessage(caught));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Create a workspace</DialogTitle>
          <DialogDescription>
            Projects live inside a workspace. You become its owner, and membership is enforced
            server-side.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="workspace-name">Workspace name</Label>
            <Input
              id="workspace-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Platform Handover"
              required
              maxLength={200}
              autoFocus
            />
          </div>
          {error ? <p className="text-xs text-status-danger">{error}</p> : null}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={createWorkspace.isPending || !name.trim()}>
              {createWorkspace.isPending ? "Creating…" : "Create workspace"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
