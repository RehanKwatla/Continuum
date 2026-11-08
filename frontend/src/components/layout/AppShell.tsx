import * as React from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { Activity, FolderKanban, LayoutDashboard, Plug, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Topbar } from "@/components/layout/Topbar";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { to: "/dashboard", label: "Dashboard", Icon: LayoutDashboard },
  { to: "/projects", label: "Projects", Icon: FolderKanban },
  { to: "/sources", label: "Sources", Icon: Plug },
] as const;

function BrandMark() {
  return (
    <Link to="/dashboard" className="flex items-center gap-2.5 px-1">
      <span className="flex h-7 w-7 items-center justify-center rounded-md border border-primary/40 bg-primary/10">
        <Activity className="h-3.5 w-3.5 text-primary" />
      </span>
      <span className="flex flex-col leading-none">
        <span className="text-sm font-semibold tracking-tight">Continuum</span>
        <span className="mt-0.5 text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
          Project continuity
        </span>
      </span>
    </Link>
  );
}

function NavItems({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="flex flex-col gap-0.5" aria-label="Primary">
      {NAV_ITEMS.map(({ to, label, Icon }) => (
        <NavLink
          key={to}
          to={to}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors",
              isActive
                ? "bg-secondary text-foreground"
                : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
            )
          }
        >
          <Icon className="h-4 w-4" />
          {label}
        </NavLink>
      ))}
    </nav>
  );
}

/** Responsive application frame: persistent sidebar, sticky top bar. */
export function AppShell({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const location = useLocation();

  React.useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      {/* Desktop sidebar */}
      <aside className="hidden border-r border-border/70 bg-card/30 lg:flex lg:flex-col">
        <div className="flex h-14 items-center border-b border-border/70 px-4">
          <BrandMark />
        </div>
        <div className="flex-1 overflow-y-auto p-3">
          <NavItems />
          <div className="mt-6 rounded-lg border border-border/70 bg-card/50 p-3">
            <p className="label-eyebrow">Pipeline</p>
            <ol className="mt-2 space-y-1.5 text-[11px] text-muted-foreground">
              {["Connect", "Reconstruct", "Verify", "Review", "Handover"].map((stage, index) => (
                <li key={stage} className="flex items-center gap-2">
                  <span
                    className={cn(
                      "flex h-4 w-4 items-center justify-center rounded-full border text-[9px]",
                      index <= 0
                        ? "border-primary/50 text-primary"
                        : "border-border text-muted-foreground/70",
                    )}
                  >
                    {index + 1}
                  </span>
                  <span className={index <= 0 ? "text-foreground" : undefined}>{stage}</span>
                  {index > 0 ? (
                    <span className="ml-auto text-[9px] uppercase tracking-wider text-muted-foreground/60">
                      Phase 3
                    </span>
                  ) : null}
                </li>
              ))}
            </ol>
          </div>
        </div>
      </aside>

      {/* Mobile drawer */}
      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-black/70"
            onClick={() => setMobileOpen(false)}
            aria-hidden="true"
          />
          <div className="relative h-full w-[264px] border-r border-border bg-card p-3">
            <div className="mb-3 flex items-center justify-between px-1">
              <BrandMark />
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setMobileOpen(false)}
                aria-label="Close navigation"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
            <NavItems onNavigate={() => setMobileOpen(false)} />
          </div>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-col">
        <Topbar onOpenNav={() => setMobileOpen(true)} />
        <main className="mx-auto w-full max-w-[1200px] flex-1 px-4 py-6 sm:px-6 lg:px-8">
          {children}
        </main>
        <footer className="border-t border-border/70 px-4 py-4 sm:px-6 lg:px-8">
          <p className="text-[11px] text-muted-foreground">
            Phase 1 foundation + Phase 2 source ingestion. Claim extraction and verification are
            Phase 3.
          </p>
        </footer>
      </div>

    </div>
  );
}
