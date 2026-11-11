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
    <Link to="/dashboard" className="wordmark">
      Continuum
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
            className="flex w-full items-center justify-between gap-2 rounded-md border border-border bg-background/40 px-2.5 py-2 text-left transition-colors hover:border-primary/50"
          >
            <span className="min-w-0">
              <span className="block text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                Workspace
              </span>
              <span className="mt-0.5 block truncate text-sm text-foreground">
                {workspaces.isLoading ? "Loading…" : selected?.name ?? "No workspace"}
              </span>
            </span>
            <ChevronsUpDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-56">
          <DropdownMenuLabel>Workspaces</DropdownMenuLabel>
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
              >
                <span className="truncate">{workspace.name}</span>
              </DropdownMenuItem>
            ))
          )}
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => setOpenCreate(true)}>New workspace</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <WorkspaceCreateDialog open={openCreate} onOpenChange={setOpenCreate} />
    </>
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
              "flex items-center gap-2.5 rounded-md border-l-2 px-2.5 py-2 text-sm transition-colors",
              isActive
                ? "border-primary bg-primary/10 text-foreground"
                : "border-transparent text-muted-foreground hover:bg-secondary/70 hover:text-foreground",
            )
          }
        >
          <Icon className="h-4 w-4" />
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
    <div className="border-t border-border p-3">
      <div className="flex items-center gap-2.5">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border bg-secondary text-xs font-medium uppercase text-sand">
          {label.slice(0, 1)}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm text-foreground">
            {isDemoSession ? "Public Demo" : (user?.full_name ?? "Continuum user")}
          </p>
          <p className="truncate font-mono text-[10px] text-muted-foreground">
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

/** Responsive application frame: charcoal sidebar, lifted main canvas. */
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
    <div className="min-h-screen bg-canvas lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <aside className="hidden border-r border-border bg-sidebar lg:flex lg:flex-col">
        <SidebarBody />
      </aside>

      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation menu">
          <div
            className="absolute inset-0 bg-black/70"
            onClick={() => setMobileOpen(false)}
            aria-hidden="true"
          />
          <div className="relative flex h-full w-[280px] flex-col border-r border-border bg-sidebar">
            <Button
              variant="ghost"
              size="icon"
              className="absolute right-2 top-3"
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
        <main className="mx-auto w-full max-w-[1180px] flex-1 px-4 py-8 sm:px-6 lg:px-10">
          <div key={location.pathname} className="animate-fade-in">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
