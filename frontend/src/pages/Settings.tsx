import * as React from "react";
import { useNavigate } from "react-router-dom";
import { LogOut } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/common/PageHeader";
import { useAuth } from "@/contexts/AuthContext";
import { useHealth, useReadiness } from "@/hooks/use-dashboard";

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-6 border-b border-border py-3 last:border-0">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-right text-sm">{value}</span>
    </div>
  );
}

export default function Settings() {
  const { user, provider, isDevSession, signOut } = useAuth();
  const health = useHealth();
  const readiness = useReadiness();
  const navigate = useNavigate();
  const [busy, setBusy] = React.useState(false);

  const handleSignOut = async () => {
    setBusy(true);
    try {
      await signOut();
      navigate("/login", { replace: true });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Account"
        title="Settings"
        description="The session, provider and API this browser is talking to."
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-xs font-medium text-muted-foreground">Profile</CardTitle>
          </CardHeader>
          <CardContent>
            <Row label="Name" value={user?.full_name ?? "—"} />
            <Row label="Email" value={user?.email ?? "—"} />
            <Row label="Provider" value={provider ?? "unknown"} />
            <Row label="Session" value={isDevSession ? "Development" : "Authenticated"} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-xs font-medium text-muted-foreground">Platform</CardTitle>
          </CardHeader>
          <CardContent>
            <Row
              label="API"
              value={
                health.isSuccess
                  ? `Online · v${health.data?.version ?? "—"}`
                  : health.isError
                    ? "Offline"
                    : "Checking"
              }
            />
            <Row label="Environment" value={health.data?.environment ?? "—"} />
            <Row
              label="Database"
              value={readiness.data?.database ?? (readiness.isLoading ? "Checking" : "—")}
            />
            <Row
              label="GitHub OAuth"
              value={
                readiness.data
                  ? readiness.data.github_oauth_configured
                    ? "Configured"
                    : "Not configured"
                  : "—"
              }
            />
          </CardContent>
        </Card>
      </div>

      <div className="flex items-center justify-between border-t border-border pt-4">
        <div>
          <p className="text-sm font-medium">Sign out</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Ends this browser session. Workspace data stays on the server.
          </p>
        </div>
        <Button variant="outline" size="sm" disabled={busy} onClick={() => void handleSignOut()}>
          <LogOut className="h-4 w-4" />
          {busy ? "Signing out…" : "Sign out"}
        </Button>
      </div>
    </div>
  );
}
