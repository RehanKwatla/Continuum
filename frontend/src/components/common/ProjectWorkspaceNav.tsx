import { NavLink, useLocation } from "react-router-dom";

import { cn } from "@/lib/utils";

const TABS = [
  { id: "overview", label: "Overview", to: (id: string) => `/projects/${id}` },
  { id: "sources", label: "Sources", to: (id: string) => `/projects/${id}/sources` },
  { id: "repository-intelligence", label: "Repository Intelligence", to: (id: string) => `/projects/${id}/sources/github` },
  { id: "memory", label: "Memory", to: (id: string) => `/projects/${id}/memory` },
  { id: "review", label: "Review queue", to: (id: string) => `/projects/${id}/memory/review` },
  { id: "timeline", label: "Timeline", to: (id: string) => `/projects/${id}/memory/timeline` },
  { id: "handover", label: "Handover", to: (id: string) => `/projects/${id}/handover` },
  { id: "readiness", label: "Readiness", to: (id: string) => `/projects/${id}/readiness` },
  { id: "successor-workspace", label: "Successor", to: (id: string) => `/projects/${id}/successor-workspace` },
  { id: "successor-checklist", label: "Checklist", to: (id: string) => `/projects/${id}/successor-checklist` },
  { id: "knowledge-risk", label: "Knowledge risk", to: (id: string) => `/projects/${id}/knowledge-risk` },
  { id: "evaluation", label: "Evaluation", to: (id: string) => `/projects/${id}/evaluation` },
  { id: "system-health", label: "System health", to: (id: string) => `/projects/${id}/system-health` },
  { id: "audit", label: "Audit", to: (id: string) => `/projects/${id}/audit` },
] as const;

function isTabActive(id: string, projectId: string, pathname: string): boolean {
  const base = `/projects/${projectId}`;
  if (id === "overview") return pathname === base;
  if (id === "sources") return pathname.startsWith(`${base}/sources`) && !pathname.startsWith(`${base}/sources/github`);
  if (id === "repository-intelligence") return pathname.startsWith(`${base}/sources/github`);
  if (id === "memory") {
    return pathname.startsWith(`${base}/memory`) && !pathname.startsWith(`${base}/memory/timeline`) && !pathname.startsWith(`${base}/memory/review`);
  }
  if (id === "review") return pathname.startsWith(`${base}/memory/review`);
  if (id === "timeline") return pathname.startsWith(`${base}/memory/timeline`);
  if (id === "handover") return pathname.startsWith(`${base}/handover`);
  if (id === "readiness") return pathname.startsWith(`${base}/readiness`);
  if (id === "successor-workspace") return pathname.startsWith(`${base}/successor-workspace`);
  if (id === "successor-checklist") return pathname.startsWith(`${base}/successor-checklist`);
  if (id === "knowledge-risk") return pathname.startsWith(`${base}/knowledge-risk`);
  if (id === "evaluation") return pathname.startsWith(`${base}/evaluation`);
  if (id === "system-health") return pathname.startsWith(`${base}/system-health`);
  if (id === "audit") return pathname.startsWith(`${base}/audit`);
  return false;
}

export function ProjectWorkspaceNav({ projectId }: { projectId: string }) {
  const location = useLocation();

  return (
    <div className="border-b border-border">
      <nav aria-label="Project" className="-mb-px flex gap-1.5 overflow-x-auto pb-1">
        {TABS.map((tab) => {
          const active = isTabActive(tab.id, projectId, location.pathname);
          return (
            <NavLink
              key={tab.id}
              to={tab.to(projectId)}
              end={tab.id === "overview" || tab.id === "sources"}
              className={cn(
                "inline-flex shrink-0 items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition-all",
                active
                  ? "bg-primary/15 text-foreground border-b-2 border-primary shadow-sm"
                  : "border-b-2 border-transparent text-muted-foreground hover:bg-secondary/70 hover:text-foreground",
              )}
              aria-current={active ? "page" : undefined}
            >
              {tab.label}
            </NavLink>
          );
        })}
      </nav>
    </div>
  );
}
