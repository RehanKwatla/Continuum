import * as React from "react";

import { ApiClientError } from "@/services/api";
import {
  fetchCurrentUser,
  restoreSupabaseSession,
  signOut as signOutService,
  subscribeToSupabaseSessions,
} from "@/services/auth";
import { clearAccessToken, getAccessToken, UNAUTHORIZED_EVENT } from "@/lib/session";
import type { UserProfile } from "@/types";

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  status: AuthStatus;
  user: UserProfile | null;
  provider: string | null;
  isDevSession: boolean;
  isDemoSession: boolean;
  isDemoReadOnly: boolean;
  /** Non-fatal problem encountered while resolving the session. */
  error: string | null;
  refresh: () => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = React.createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = React.useState<AuthStatus>("loading");
  const [user, setUser] = React.useState<UserProfile | null>(null);
  const [provider, setProvider] = React.useState<string | null>(null);
  const [isDevSession, setIsDevSession] = React.useState(false);
  const [isDemoSession, setIsDemoSession] = React.useState(false);
  const [isDemoReadOnly, setIsDemoReadOnly] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const applySession = React.useCallback((session: Awaited<ReturnType<typeof fetchCurrentUser>>) => {
    const isDemo = Boolean(session.is_demo_session || session.auth_provider === "demo");
    setUser(session.user);
    setProvider(session.auth_provider);
    setIsDevSession(session.is_dev_session);
    setIsDemoSession(isDemo);
    setIsDemoReadOnly(
      session.is_demo_read_only !== undefined ? session.is_demo_read_only : isDemo,
    );
    setError(null);
    setStatus("authenticated");
  }, []);

  const resolve = React.useCallback(async () => {
    try {
      const session = await fetchCurrentUser();
      applySession(session);
    } catch (caught) {
      // If a real token failed (expired or invalid), clear it and retry anonymously for public demo.
      if (getAccessToken()) {
        clearAccessToken();
        try {
          const session = await fetchCurrentUser();
          applySession(session);
          return;
        } catch {
          // Both token and anonymous attempts failed (e.g. backend unreachable)
        }
      }
      setUser(null);
      setProvider(null);
      setIsDevSession(false);
      setIsDemoSession(false);
      setIsDemoReadOnly(false);
      if (caught instanceof ApiClientError && caught.status === 503) {
        // recognised token but the backend has no verifier configured
        setError(caught.message);
      } else {
        setError(null);
      }
      setStatus("unauthenticated");
    }
  }, [applySession]);

  // Boot: restore a Supabase session if present, then resolve the backend identity.
  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      await restoreSupabaseSession();
      if (!cancelled) await resolve();
    })();
    return () => {
      cancelled = true;
    };
  }, [resolve]);

  // Keep the API token aligned with Supabase refreshes.
  React.useEffect(() => subscribeToSupabaseSessions(), []);

  // Any 401 from the API clears the token and falls back to public demo.
  React.useEffect(() => {
    const handler = () => {
      clearAccessToken();
      void resolve();
    };
    window.addEventListener(UNAUTHORIZED_EVENT, handler);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handler);
}, [resolve]);

const signOut = React.useCallback(async () => {
  await signOutService();
clearAccessToken();
await resolve();
  }, [resolve]);

const value = React.useMemo<AuthContextValue>(
  () => ({
    status,
    user,
    provider,
    isDevSession,
    isDemoSession,
    isDemoReadOnly,
    error,
    refresh: resolve,
    signOut,
  }),
  [status, user, provider, isDevSession, isDemoSession, isDemoReadOnly, error, resolve, signOut],
);

return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

const DEFAULT_AUTH_VALUE: AuthContextValue = {
  status: "authenticated",
  user: {
    id: "public-demo-user",
    email: "public-demo@example.com",
    full_name: "Public Demo",
    created_at: "2026-01-01T00:00:00Z",
  },
  provider: "demo",
  isDevSession: false,
  isDemoSession: false,
  isDemoReadOnly: false,
  error: null,
  refresh: async () => { },
  signOut: async () => { },
};

export function useAuth(): AuthContextValue {
  const context = React.useContext(AuthContext);
  return context ?? DEFAULT_AUTH_VALUE;
}
