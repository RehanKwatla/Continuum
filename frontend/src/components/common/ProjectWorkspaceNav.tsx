import { NavLink, useLocation } from "react-router-dom";

import { cn } from "@/lib/utils";

const TABS = [
  { id: "overview", label: "Overview", suffix: "" },
  { id: "sources", label: "Sources", suffix: "/sources" },
  { id: "memory", label: "Memory", suffix: "?view=memory", soon: true },
  { id: "timeline", label: "Timeline", suffix: "?view=timeline", soon: true },
  { id: "handover", label: "Handover", suffix: "?view=handover", soon: true },
] as const;

export function ProjectWorkspaceNav({ projectId }: { projectId: string }) {
  const location = useLocation();
  const view = new URLSearchParams(location.search).get("view");
  const onProjectRoot = location.pathname === `/projects/${projectId}`;

  return (
    <div className="border-b border-border">
      <nav aria-label="Project" className="-mb-px flex gap-1 overflow-x-auto">
        {TABS.map((tab) => {
          const to = `/projects/${projectId}${tab.suffix}`;
          const active = tab.id === "sources"
            ? location.pathname.startsWith(`/projects/${projectId}/sources`)
            : tab.id === "overview"
              ? onProjectRoot && !view
              : onProjectRoot && view === tab.id;

          return (
            <NavLink
              key={tab.id}
              to={to}
              className={cn(
                "inline-flex shrink-0 items-center gap-2 border-b-2 px-3 py-2.5 text-sm transition-colors",
                active
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
              aria-current={active ? "page" : undefined}
            >
              {tab.label}
              {"soon" in tab && tab.soon ? (
                <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  Soon
                </span>
              ) : null}
            </NavLink>
          );
        })}
      </nav>
    </div>
  );
}
