import { Navigate, Outlet, useLocation } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/contexts/AuthContext";

function SessionLoading() {
  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <div className="w-full max-w-sm space-y-3">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-4 w-48" />
      </div>
    </div>
  );
}

/**
 * Application route shell: provides frictionless judge access without login gates
 * or protected-route redirects.
 */
export function ProtectedRoute() {
  const { status } = useAuth();

  if (status === "loading") return <SessionLoading />;

  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}

  /** Redirects visitors away from login/signup directly into the dashboard. */
  export function PublicOnlyRoute({ children }: { children?: React.ReactNode }) {
    const { status } = useAuth();
    if (status === "loading") return <SessionLoading />;
    // Never show a login or signup screen in public demo mode
    return <Navigate to="/dashboard" replace />;
  }
