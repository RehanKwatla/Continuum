import * as React from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  ChevronsUpDown,
  FolderKanban,
  LayoutDashboard,
  LogOut,
  Plug,
  RotateCcw,
  Settings,
  ShieldCheck,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Topbar } from "@/components/layout/Topbar";
import { ThemeToggle } from "@/components/common/ThemeToggle";
import { Tooltip } from "@/components/common/Tooltip";
import { useToast } from "@/components/ui/toast";
import { WorkspaceCreateDialog } from "@/components/common/WorkspaceCreateDialog";
import { useAuth } from "@/contexts/AuthContext";
import { useWorkspaces } from "@/hooks/use-workspaces";
import { useResetPublicDemo } from "@/hooks/use-demo";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { to: "/dashboard", label: "Overview", Icon: LayoutDashboard },
  { to: "/projects", label: "Projects", Icon: FolderKanban },
  { to: "/sources", label: "Sources", Icon: Plug },
  { to: "/settings", label: "Settings", Icon: Settings },
] as const;

const WORKSPACE_KEY = "continuum.workspaceId";

function Wordmark() {
  return (
    <Link to="/dashboard" className="flex items-center gap-2.5 group">
      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground font-bold text-sm shadow-sm transition-transform group-hover:scale-105">
        C
      </span>
      <span className="font-display text-[15px] font-bold tracking-[0.24em] text-foreground uppercase">
        Continuum
      </span>
    </Link>
  );
}

function WorkspaceSelector() {
  const workspaces = useWorkspaces();
  const navigate = useNavigate();
  const [openCreate, setOpenCreate] = React.useState(false);
  const [selectedId, setSelectedId] = React.useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(WORKSPACE_KEY);
  });

  const items = workspaces.data ?? [];
  const selected = items.find((item) => item.id === selectedId) ?? items[0] ?? null;

  React.useEffect(() => {
    if (selected && selected.id !== selectedId) {
      setSelectedId(selected.id);
      window.localStorage.setItem(WORKSPACE_KEY, selected.id);
    }
  }, [selected, selectedId]);

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className="flex w-full items-center justify-between gap-2 rounded-lg border border-border bg-card/60 px-3 py-2 text-left transition-all hover:border-primary/50 hover:bg-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/70"
          >
            <span className="min-w-0">
              <span className="block text-[11px] font-semibold uppercase tracking-[0.16em] text-primary">
                Workspace
              </span>
              <span className="mt-0.5 block truncate text-sm font-medium text-foreground">
                {workspaces.isLoading ? "Loading…" : selected?.name ?? "No workspace"}
              </span>
            </span>
            <ChevronsUpDown className="h-4 w-4 shrink-0 text-muted-foreground" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-56 border-border bg-card">
          <DropdownMenuLabel className="text-xs text-muted-foreground">Workspaces</DropdownMenuLabel>
          {items.length === 0 ? (
            <DropdownMenuItem disabled>None yet</DropdownMenuItem>
          ) : (
            items.map((workspace) => (
              <DropdownMenuItem
                key={workspace.id}
                onSelect={() => {
                  setSelectedId(workspace.id);
                  window.localStorage.setItem(WORKSPACE_KEY, workspace.id);
                  navigate(`/projects?workspace_id=${workspace.id}`);
                }}
                className="cursor-pointer text-sm hover:bg-secondary"
              >
                <span className="truncate">{workspace.name}</span>
              </DropdownMenuItem>
            ))
          )}
          <DropdownMenuSeparator className="bg-border" />
          <DropdownMenuItem onSelect={() => setOpenCreate(true)} className="cursor-pointer text-sm text-primary hover:bg-secondary">
            New workspace
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <WorkspaceCreateDialog open={openCreate} onOpenChange={setOpenCreate} />
    </>
  );
}

function NavItems({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="flex flex-col gap-1" aria-label="Primary">
      {NAV_ITEMS.map(({ to, label, Icon }) => (
        <NavLink
          key={to}
          to={to}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              "group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all",
              isActive
                ? "border-l-2 border-primary bg-primary/15 text-foreground shadow-sm"
                : "border-l-2 border-transparent text-muted-foreground hover:bg-secondary/70 hover:text-foreground",
            )
          }
        >
          <Icon className="h-4 w-4 shrink-0 transition-colors group-hover:text-primary" />
          <span className="truncate">{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}

function ProfileFooter() {
  const { user, isDemoSession, isDemoReadOnly, signOut } = useAuth();
  const resetDemo = useResetPublicDemo();
  const { toast } = useToast();
  const [signingOut, setSigningOut] = React.useState(false);
  const label = isDemoSession ? "Public Demo" : (user?.full_name ?? user?.email ?? "Account");

  const handleResetDemo = async () => {
    try {
      await resetDemo.mutateAsync();
      toast({
        title: "Demo workspace reset",
        description: "The synthetic demonstration workspace has been restored to pristine seed data.",
        variant: "success",
      });
    } catch {
      toast({
        title: "Reset failed",
        description: "Could not reset the demo workspace. Please try again shortly.",
        variant: "error",
      });
    }
  };

  const handleSignOut = async () => {
    setSigningOut(true);
    try {
      await signOut();
      toast({
        title: "Session refreshed",
        description: "Demo workspace reloaded in public judge mode.",
        variant: "default",
      });
    } finally {
      setSigningOut(false);
    }
  };

  return (
    <div className="border-t border-border p-3.5 space-y-2.5">
      <div className="flex items-center justify-between rounded-lg border border-border/70 bg-card/40 px-3 py-1.5">
        <span className="text-xs font-medium text-muted-foreground">Theme</span>
        <ThemeToggle size="sm" />
      </div>

      <div className="flex items-center gap-3">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border bg-card text-xs font-bold uppercase text-primary shadow-sm">
          {label.slice(0, 1)}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-foreground">
            {isDemoSession ? "Public Demo" : (user?.full_name ?? "Continuum user")}
          </p>
          <p className="truncate font-mono text-[11px] text-muted-foreground">
            {isDemoSession
              ? isDemoReadOnly
                ? "Judge access · Read-only"
                : "Public workspace · Interactive"
              : user?.email}
          </p>
        </div>
        {isDemoSession ? (
          <Tooltip label="Reset demo data to pristine seed">
            <Button
              variant="ghost"
              size="icon"
              aria-label="Reset demo workspace"
              disabled={resetDemo.isPending}
              onClick={() => void handleResetDemo()}
              className="hover:bg-secondary text-muted-foreground hover:text-foreground"
            >
              <RotateCcw className={cn("h-4 w-4", resetDemo.isPending && "animate-spin")} />
            </Button>
          </Tooltip>
        ) : (
          <Tooltip label="Sign out">
            <Button
              variant="ghost"
              size="icon"
              aria-label="Sign out"
              disabled={signingOut}
              onClick={() => void handleSignOut()}
              className="hover:bg-secondary text-muted-foreground hover:text-foreground"
            >
              <LogOut className="h-4 w-4" />
            </Button>
          </Tooltip>
        )}
      </div>
    </div>
  );
}

function SidebarBody({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <>
      <div className="flex h-16 items-center px-5">
        <Wordmark />
      </div>
      <div className="flex-1 space-y-4 overflow-y-auto px-3 pb-4">
        <WorkspaceSelector />
        <NavItems onNavigate={onNavigate} />
      </div>
      <ProfileFooter />
    </>
  );
}

/** Responsive application frame: Midnight Amethyst sidebar, lifted main canvas. */
export function AppShell({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const location = useLocation();

  // Close on navigation
  React.useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  // Keyboard: Escape closes the mobile drawer
  React.useEffect(() => {
    if (!mobileOpen) return;
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileOpen(false);
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [mobileOpen]);

  // Body scroll lock while the mobile drawer is open
  React.useEffect(() => {
    if (mobileOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [mobileOpen]);

  return (
    <div className="min-h-screen bg-transparent lg:grid lg:grid-cols-[264px_minmax(0,1fr)]">
      <aside className="hidden border-r border-border bg-sidebar/95 backdrop-blur-md lg:flex lg:flex-col">
        <SidebarBody />
      </aside>

      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation menu">
          <div
            className="absolute inset-0 bg-black/80 backdrop-blur-sm"
            onClick={() => setMobileOpen(false)}
            aria-hidden="true"
          />
          <div className="relative flex h-full w-[270px] flex-col border-r border-border bg-sidebar shadow-2xl">
            <Button
              variant="ghost"
              size="icon"
              className="absolute right-2 top-3 text-muted-foreground hover:text-foreground"
              onClick={() => setMobileOpen(false)}
              aria-label="Close navigation"
            >
              <X className="h-4 w-4" />
            </Button>
            <SidebarBody onNavigate={() => setMobileOpen(false)} />
          </div>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-col">
        <Topbar onOpenNav={() => setMobileOpen(true)} />
        <main className="mx-auto w-full max-w-[1240px] flex-1 px-4 py-8 sm:px-6 lg:px-10">
          <div key={location.pathname} className="animate-fade-in">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
