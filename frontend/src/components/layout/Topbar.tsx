import * as React from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ChevronRight, LogOut, Menu, Server, UserRound } from "lucide-react";

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
import { useAuth } from "@/contexts/AuthContext";
import { useHealth } from "@/hooks/use-dashboard";
import { cn } from "@/lib/utils";

/** Breadcrumb derived from the current URL — no duplicated route metadata. */
export function Topbar({ onOpenNav }: { onOpenNav: () => void }) {
  const { user, provider, isDevSession, signOut } = useAuth();
  const health = useHealth();
  const navigate = useNavigate();
  const location = useLocation();
  const [signingOut, setSigningOut] = React.useState(false);

  const segments = location.pathname.split("/").filter(Boolean);

  const handleSignOut = async () => {
    setSigningOut(true);
    try {
      await signOut();
      navigate("/login", { replace: true });
    } finally {
      setSigningOut(false);
    }
  };

  return (
    <header className="sticky top-0 z-40 flex h-14 items-center gap-3 border-b border-border bg-canvas/90 px-4 backdrop-blur-sm sm:px-6 lg:px-10">
      <Button
        variant="ghost"
        size="icon"
        className="lg:hidden"
        onClick={onOpenNav}
        aria-label="Open navigation"
      >
        <Menu className="h-4 w-4" />
      </Button>

      <nav aria-label="Breadcrumb" className="hidden min-w-0 items-center gap-1.5 sm:flex">
        <Link to="/dashboard" className="text-xs text-muted-foreground hover:text-foreground">
          Continuum
        </Link>
        {segments.map((segment, index) => {
          const href = `/${segments.slice(0, index + 1).join("/")}`;
          const isLast = index === segments.length - 1;
          const label = segment.length > 14 ? `${segment.slice(0, 8)}…` : segment;
          return (
            <React.Fragment key={href}>
              <ChevronRight className="h-3 w-3 text-muted-foreground/50" />
              {isLast ? (
                <span className="truncate text-xs font-medium capitalize text-foreground">
                  {label}
                </span>
              ) : (
                <Link
                  to={href}
                  className="truncate text-xs capitalize text-muted-foreground hover:text-foreground"
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
          <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <Server className="h-3.5 w-3.5" />
            <span
              className={cn(
                "h-1.5 w-1.5 rounded-full",
                health.isSuccess
                  ? "bg-status-ok"
                  : health.isError
                    ? "bg-status-danger"
                    : "bg-status-warn",
              )}
            />
            {health.isSuccess ? "API online" : health.isError ? "API offline" : "Checking…"}
          </span>
        </Tooltip>

        {isDevSession ? (
          <Badge variant="warn" className="hidden sm:inline-flex">
            Development session
          </Badge>
        ) : null}

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="gap-2 px-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-full border border-border bg-secondary text-[10px] font-semibold uppercase">
                {(user?.full_name ?? user?.email ?? "?").slice(0, 1)}
              </span>
              <span className="hidden max-w-[160px] truncate text-xs sm:inline">
                {user?.full_name ?? user?.email ?? "Account"}
              </span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-60">
            <DropdownMenuLabel className="space-y-0.5">
              <span className="block truncate text-xs font-medium text-foreground">
                {user?.full_name ?? "Continuum user"}
              </span>
              <span className="block truncate text-[11px] font-normal text-muted-foreground">
                {user?.email}
              </span>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuLabel className="flex items-center gap-2 font-normal">
              <UserRound className="h-3.5 w-3.5" />
              Provider: {provider ?? "unknown"}
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => void handleSignOut()} disabled={signingOut}>
              <LogOut className="h-4 w-4" />
              {signingOut ? "Signing out…" : "Sign out"}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
