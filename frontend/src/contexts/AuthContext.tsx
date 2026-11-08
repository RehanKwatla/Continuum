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
  const [error, setError] = React.useState<string | null>(null);

  const resolve = React.useCallback(async () => {
    if (!getAccessToken()) {
      setUser(null);
      setProvider(null);
      setIsDevSession(false);
      setStatus("unauthenticated");
      return;
    }
    try {
      const session = await fetchCurrentUser();
      setUser(session.user);
      setProvider(session.auth_provider);
      setIsDevSession(session.is_dev_session);
      setError(null);
      setStatus("authenticated");
    } catch (caught) {
      setUser(null);
      setProvider(null);
      setIsDevSession(false);
      if (caught instanceof ApiClientError && caught.status === 503) {
        // recognised token but the backend has no verifier configured
        setError(caught.message);
      } else {
        setError(null);
        clearAccessToken();
      }
      setStatus("unauthenticated");
    }
  }, []);

  // Boot: restore a Supabase session, then resolve the backend identity.
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

  // Any 401 from the API invalidates the local session immediately.
  React.useEffect(() => {
    const handler = () => {
      clearAccessToken();
      setUser(null);
      setProvider(null);
      setIsDevSession(false);
      setStatus("unauthenticated");
    };
    window.addEventListener(UNAUTHORIZED_EVENT, handler);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handler);
  }, []);

  const signOut = React.useCallback(async () => {
    await signOutService();
    setUser(null);
    setProvider(null);
    setIsDevSession(false);
    setError(null);
    setStatus("unauthenticated");
  }, []);

  const value = React.useMemo<AuthContextValue>(
    () => ({ status, user, provider, isDevSession, error, refresh: resolve, signOut }),
    [status, user, provider, isDevSession, error, resolve, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = React.useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>.");
  return context;
}
