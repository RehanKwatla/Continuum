import * as React from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Activity, ArrowLeft, KeyRound, Lock, Mail, ShieldAlert, UserRound } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { useAuth } from "@/contexts/AuthContext";
import { useReadiness } from "@/hooks/use-dashboard";
import { supabaseConfigured } from "@/lib/env";
import { signInWithDevToken, signInWithPassword, signUpWithPassword, syncSession } from "@/services/auth";
import { toErrorMessage } from "@/services/api";

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const { refresh } = useAuth();
  const { toast } = useToast();
  const readiness = useReadiness();

  const [tab, setTab] = React.useState<"signin" | "signup">("signin");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [fullName, setFullName] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const fromPath = (location.state as { from?: string } | null)?.from;
  const redirectTo = fromPath && fromPath !== "/login" ? fromPath : "/dashboard";

  const finishSignIn = React.useCallback(async () => {
    // Provision / verify the local profile before entering the app shell.
    await syncSession();
    await refresh();
    navigate(redirectTo, { replace: true });
  }, [navigate, redirectTo, refresh]);

  const handleSupabaseSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (tab === "signin") {
        await signInWithPassword(email, password);
      } else {
        const { needsEmailConfirmation } = await signUpWithPassword(email, password, fullName);
        if (needsEmailConfirmation) {
          toast({
            title: "Confirm your email",
            description: "Supabase sent a confirmation link. Confirm it, then sign in.",
            variant: "success",
          });
          setTab("signin");
          setBusy(false);
          return;
        }
      }
      await finishSignIn();
    } catch (caught) {
      setError(toErrorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  const handleDevSignIn = async () => {
    setBusy(true);
    setError(null);
    try {
      signInWithDevToken();
      await finishSignIn();
    } catch (caught) {
      setError(toErrorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  const devAuthEnabled = readiness.data?.dev_auth_enabled ?? false;

  return (
    <div className="grid min-h-screen lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      {/* Narrative panel */}
      <div className="hidden flex-col justify-between border-r border-border/70 bg-card/30 p-10 lg:flex">
        <Link to="/" className="flex items-center gap-2.5">
          <span className="flex h-7 w-7 items-center justify-center rounded-md border border-primary/40 bg-primary/10">
            <Activity className="h-3.5 w-3.5 text-primary" />
          </span>
          <span className="wordmark">Continuum</span>
        </Link>
        <div className="max-w-md">
          <h1 className="font-display text-4xl font-medium leading-[1.05] tracking-tight text-sand">
            People leave.
            <br />
            Knowledge stays.
          </h1>
          <p className="mt-4 text-xs leading-relaxed text-muted-foreground">
            Sign in to connect authorised sources and reconstruct project knowledge. Access is
            verified server-side on every request — the browser never asserts who you are.
          </p>
          <div className="mt-8 space-y-2.5 text-[11px] text-muted-foreground">
            {[
              "JWT verified by FastAPI, not by this page",
              "Workspace isolation enforced in the database",
              "Secrets redacted before content is stored",
            ].map((line) => (
              <div key={line} className="flex items-center gap-2">
                <Lock className="h-3.5 w-3.5 text-primary" />
                {line}
              </div>
            ))}
          </div>
        </div>
        <p className="text-[11px] text-muted-foreground">
          CodeZen India 2026 · Team Cipher · Phase 1 + Phase 2
        </p>
      </div>

      {/* Auth panel */}
      <div className="flex items-center justify-center p-6 sm:p-10">
        <div className="w-full max-w-sm">
          <Link
            to="/"
            className="mb-6 inline-flex items-center gap-1.5 text-[11px] text-muted-foreground hover:text-foreground lg:hidden"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to overview
          </Link>

          <h2 className="text-lg font-semibold tracking-tight">Sign in to Continuum</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Use your Supabase account, or a development session when the backend allows it.
          </p>

          {error ? (
            <Alert variant="destructive" title="Could not sign in" className="mt-5">
              {error}
            </Alert>
          ) : null}

          {readiness.isLoading ? (
            <div className="mt-6 space-y-2">
              <Skeleton className="h-9 w-full" />
              <Skeleton className="h-9 w-full" />
              <Skeleton className="h-9 w-full" />
            </div>
          ) : null}

          {readiness.isSuccess && supabaseConfigured ? (
            <Tabs
              value={tab}
              onValueChange={(value) => setTab(value as "signin" | "signup")}
              className="mt-6"
            >
              <TabsList className="w-full">
                <TabsTrigger value="signin" className="flex-1">
                  Sign in
                </TabsTrigger>
                <TabsTrigger value="signup" className="flex-1">
                  Create account
                </TabsTrigger>
              </TabsList>

              <TabsContent value="signin">
                <form className="space-y-4" onSubmit={handleSupabaseSubmit}>
                  <div className="space-y-1.5">
                    <Label htmlFor="email">Email</Label>
                    <Input
                      id="email"
                      type="email"
                      autoComplete="email"
                      required
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      placeholder="you@company.com"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="password">Password</Label>
                    <Input
                      id="password"
                      type="password"
                      autoComplete="current-password"
                      required
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                    />
                  </div>
                  <Button type="submit" className="w-full" disabled={busy}>
                    <Mail className="h-4 w-4" />
                    {busy ? "Signing in…" : "Sign in"}
                  </Button>
                </form>
              </TabsContent>

              <TabsContent value="signup">
                <form className="space-y-4" onSubmit={handleSupabaseSubmit}>
                  <div className="space-y-1.5">
                    <Label htmlFor="full-name">Full name</Label>
                    <Input
                      id="full-name"
                      autoComplete="name"
                      value={fullName}
                      onChange={(event) => setFullName(event.target.value)}
                      placeholder="Ada Lovelace"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="signup-email">Email</Label>
                    <Input
                      id="signup-email"
                      type="email"
                      autoComplete="email"
                      required
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      placeholder="you@company.com"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="signup-password">Password</Label>
                    <Input
                      id="signup-password"
                      type="password"
                      autoComplete="new-password"
                      required
                      minLength={8}
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                    />
                  </div>
                  <Button type="submit" className="w-full" disabled={busy}>
                    <UserRound className="h-4 w-4" />
                    {busy ? "Creating account…" : "Create account"}
                  </Button>
                </form>
              </TabsContent>
            </Tabs>
          ) : null}

          {readiness.isSuccess && !supabaseConfigured ? (
            <Alert variant="info" title="Supabase Auth is not configured" className="mt-6">
              Set <code className="mono">VITE_SUPABASE_URL</code> and{" "}
              <code className="mono">VITE_SUPABASE_ANON_KEY</code> in{" "}
              <code className="mono">frontend/.env</code> to enable email sign-in. Supabase Auth is
              the production path; the backend refuses development tokens outside development.
            </Alert>
          ) : null}

          {devAuthEnabled ? (
            <div className="mt-6">
              <div className="relative">
                <Separator />
                <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 bg-background px-2 text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                  or
                </span>
              </div>
              <Button
                type="button"
                variant="outline"
                className="mt-5 w-full"
                onClick={() => void handleDevSignIn()}
                disabled={busy}
              >
                <KeyRound className="h-4 w-4" />
                {busy ? "Starting session…" : "Continue with a development session"}
              </Button>
              <p className="mt-2 flex items-start gap-1.5 text-[11px] leading-relaxed text-muted-foreground">
                <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-status-warn" />
                Development only. The backend reports <code className="mono">dev_auth_enabled</code>{" "}
                and refuses this path when ENVIRONMENT=production.
              </p>
            </div>
          ) : null}

          {readiness.isError ? (
            <Alert variant="warning" title="Backend unreachable" className="mt-6">
              The Continuum API could not be reached at the configured base URL. Start the backend,
              then reload this page.
            </Alert>
          ) : null}
        </div>
      </div>
    </div>
  );
}
