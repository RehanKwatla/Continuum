import * as React from "react";
import { Link, useLocation } from "react-router-dom";
import { ChevronRight, RotateCcw, Server, ShieldCheck, UserRound } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip } from "@/components/common/Tooltip";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { useToast } from "@/components/ui/toast";
import { useAuth } from "@/contexts/AuthContext";
import { useHealth } from "@/hooks/use-dashboard";
import { useResetPublicDemo } from "@/hooks/use-demo";
import { cn } from "@/lib/utils";

/** Breadcrumb derived from the current URL — no duplicated route metadata. */
export function Topbar({ onOpenNav }: { onOpenNav: () => void }) {
  const { user, provider, isDevSession, isDemoSession, signOut } = useAuth();
  const health = useHealth();
  const location = useLocation();
  const { toast } = useToast();
  const resetDemo = useResetPublicDemo();
  const [signingOut, setSigningOut] = React.useState(false);

  const segments = location.pathname.split("/").filter(Boolean);

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
    <header className="sticky top-0 z-40 flex h-16 items-center gap-3 border-b border-border bg-background/85 px-4 backdrop-blur-md sm:px-6 lg:px-10">
      <Button
        variant="ghost"
        size="icon"
        className="lg:hidden text-muted-foreground hover:text-foreground"
        onClick={onOpenNav}
        aria-label="Open navigation"
      >
        <span className="sr-only">Open navigation</span>
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="h-4 w-4"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </Button>

      <nav aria-label="Breadcrumb" className="hidden min-w-0 items-center gap-2 sm:flex">
        <Link to="/dashboard" className="text-xs font-medium text-muted-foreground transition-colors hover:text-foreground">
          Continuum
        </Link>
        {segments.map((segment, index) => {
          const href = `/${segments.slice(0, index + 1).join("/")}`;
          const isLast = index === segments.length - 1;
          const label = segment.length > 14 ? `${segment.slice(0, 8)}…` : segment;
          return (
            <React.Fragment key={href}>
              <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/40" />
              {isLast ? (
                <span className="truncate text-xs font-semibold capitalize text-foreground">
                  {label}
                </span>
              ) : (
                <Link
                  to={href}
                  className="truncate text-xs capitalize text-muted-foreground transition-colors hover:text-foreground"
                >
                  {label}
                </Link>
              )}
            </React.Fragment>
          );
        })}
      </nav>

      <div className="ml-auto flex items-center gap-3">
        <Tooltip
          className="hidden sm:inline-flex"
          label={health.data ? `API v${health.data.version}` : "API unreachable"}
        >
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Server className="h-3.5 w-3.5" />
            <span
              className={cn(
                "h-2 w-2 rounded-full",
                health.isSuccess
                  ? "bg-emerald-400"
                  : health.isError
                    ? "bg-rose-400"
                    : "bg-amber-400",
              )}
            />
            {health.isSuccess ? "API online" : health.isError ? "API offline" : "Checking…"}
          </span>
        </Tooltip>

        {/* Small unobtrusive label demanded by judge access requirements */}
        <Badge
          variant="outline"
          className="border-primary/40 bg-primary/10 text-primary font-mono text-[11px] font-semibold tracking-wider uppercase px-2.5 py-0.5"
        >
          PUBLIC DEMO ENVIRONMENT
        </Badge>

        {isDevSession ? (
          <Badge variant="warn" className="hidden sm:inline-flex text-[11px]">
            Development session
          </Badge>
        ) : null}

        {/* Toggle switch in the UI/UX to change theme between dark and light */}
        <ThemeToggle />

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="gap-2.5 px-2.5 hover:bg-secondary">
              <span className="flex h-7 w-7 items-center justify-center rounded-full border border-border bg-card text-xs font-bold uppercase text-primary shadow-sm">
                {(user?.full_name ?? user?.email ?? "D").slice(0, 1)}
              </span>
              <span className="hidden max-w-[160px] truncate text-xs font-medium text-foreground sm:inline">
                {user?.full_name ?? (isDemoSession ? "Public Demo" : "Account")}
              </span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-64 border-border bg-card shadow-xl">
            <DropdownMenuLabel className="space-y-0.5">
              <span className="block truncate text-xs font-medium text-foreground">
                {user?.full_name ?? (isDemoSession ? "Public Demo" : "Continuum user")}
              </span>
              <span className="block truncate text-[11px] font-normal text-muted-foreground">
                {user?.email ?? "public-demo@example.com"}
              </span>
            </DropdownMenuLabel>
            <DropdownMenuSeparator className="bg-border" />
            <DropdownMenuLabel className="flex items-center gap-2 font-normal text-xs text-muted-foreground">
              <ShieldCheck className="h-3.5 w-3.5 text-primary" />
              Mode: Frictionless Judge Access
            </DropdownMenuLabel>
            <DropdownMenuSeparator className="bg-border" />
            <div className="flex items-center justify-between px-2 py-1.5 text-xs text-muted-foreground">
              <span>Theme appearance</span>
              <ThemeToggle size="sm" />
            </div>
            <DropdownMenuSeparator className="bg-border" />
            {isDemoSession ? (
              <DropdownMenuItem
                onSelect={() => void handleResetDemo()}
                disabled={resetDemo.isPending}
                className="cursor-pointer text-xs hover:bg-secondary"
              >
                <RotateCcw className="h-3.5 w-3.5 mr-2" />
                {resetDemo.isPending ? "Resetting demo…" : "Reset demo workspace to pristine"}
              </DropdownMenuItem>
            ) : (
              <DropdownMenuItem onSelect={() => void handleSignOut()} disabled={signingOut} className="cursor-pointer text-xs hover:bg-secondary">
                <RotateCcw className="h-4 w-4 mr-2" />
                {signingOut ? "Refreshing…" : "Switch to public demo"}
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
