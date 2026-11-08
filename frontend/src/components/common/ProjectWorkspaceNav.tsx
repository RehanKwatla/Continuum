import { NavLink, useLocation } from "react-router-dom";

import { cn } from "@/lib/utils";

const TABS = [
  { id: "overview", label: "Overview", to: (id: string) => `/projects/${id}` },
  { id: "sources", label: "Sources", to: (id: string) => `/projects/${id}/sources` },
  { id: "memory", label: "Memory", to: (id: string) => `/projects/${id}/memory` },
  { id: "review", label: "Review queue", to: (id: string) => `/projects/${id}/memory/review` },
  { id: "timeline", label: "Timeline", to: (id: string) => `/projects/${id}/memory/timeline` },
  { id: "handover", label: "Handover", to: (id: string) => `/projects/${id}/handover` },
  { id: "audit", label: "Audit", to: (id: string) => `/projects/${id}/audit` },
] as const;

function isTabActive(id: string, projectId: string, pathname: string): boolean {
  const base = `/projects/${projectId}`;
  if (id === "overview") return pathname === base;
  if (id === "sources") return pathname.startsWith(`${base}/sources`);
  if (id === "memory") {
    return pathname.startsWith(`${base}/memory`) && !pathname.startsWith(`${base}/memory/timeline`) && !pathname.startsWith(`${base}/memory/review`);
  }
  if (id === "review") return pathname.startsWith(`${base}/memory/review`);
  if (id === "timeline") return pathname.startsWith(`${base}/memory/timeline`);
  if (id === "handover") return pathname.startsWith(`${base}/handover`);
  if (id === "audit") return pathname.startsWith(`${base}/audit`);
  return false;
}

export function ProjectWorkspaceNav({ projectId }: { projectId: string }) {
  const location = useLocation();

  return (
    <div className="border-b border-border">
      <nav aria-label="Project" className="-mb-px flex gap-1 overflow-x-auto">
        {TABS.map((tab) => {
          const active = isTabActive(tab.id, projectId, location.pathname);
          return (
            <NavLink
              key={tab.id}
              to={tab.to(projectId)}
              className={cn(
                "inline-flex shrink-0 items-center gap-2 border-b-2 px-3 py-2.5 text-sm transition-colors",
                active
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
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
