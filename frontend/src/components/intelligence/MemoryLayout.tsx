import { Outlet, useParams, NavLink, useLocation } from "react-router-dom";

import { ProjectWorkspaceNav } from "@/components/common/ProjectWorkspaceNav";
import { ErrorState } from "@/components/common/States";
import { PageHeader } from "@/components/common/PageHeader";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { useProject } from "@/hooks/use-projects";

const SUB_TABS = [
  { label: "Memory", suffix: "" },
  { label: "Claims", suffix: "/claims" },
  { label: "Conflicts", suffix: "/conflicts" },
  { label: "Uncertainty", suffix: "/uncertainty" },
  { label: "Timeline", suffix: "/timeline" },
] as const;

function isActive(suffix: string, base: string, pathname: string): boolean {
  if (suffix === "") return pathname === base;
  return pathname.startsWith(`${base}${suffix}`);
}

/**
 * Shared frame for the intelligence workspace: project header, the project-level
 * tabs and the memory sub-navigation. Each child page owns its own queries so a
 * slow section never blocks the shell.
 */
export function MemoryLayout() {
  const { projectId } = useParams<{ projectId: string }>();
  const project = useProject(projectId);
  const location = useLocation();

  if (!projectId) return null;

  const base = `/projects/${projectId}/memory`;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Project memory"
        title={project.data?.name ?? "Project memory"}
        description={
          project.data
            ? "Claims, evidence and conflicts reconstructed from this project's authorised sources."
            : "Reconstructed project knowledge, every statement traceable to a source."
        }
      />

      {project.isError ? (
        <ErrorState
          error={project.error}
          title="This project could not be loaded"
          onRetry={() => void project.refetch()}
        />
      ) : project.isLoading ? (
        <Skeleton className="h-10 w-full" />
      ) : (
        <ProjectWorkspaceNav projectId={projectId} />
      )}

      <div className="border-b border-border/70">
        <nav aria-label="Memory sections" className="flex gap-1 overflow-x-auto">
          {SUB_TABS.map((tab) => {
            const active = isActive(tab.suffix, base, location.pathname);
            return (
              <NavLink
                key={tab.label}
                to={`${base}${tab.suffix}`}
                className={cn(
                  "shrink-0 rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                  active
                    ? "bg-secondary text-foreground"
                    : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
                )}
                aria-current={active ? "page" : undefined}
              >
                {tab.label}
              </NavLink>
            );
          })}
        </nav>
      </div>

      <Outlet />
    </div>
  );
}
