/**
 * Authentication service.
 *
 * Two modes, chosen at runtime:
 *   1. Supabase Auth — used when VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY
 *      are present. The SDK owns the session; this module simply mirrors the
 *      access token into the API client's session store.
 *   2. Development token — used only when Supabase is absent AND the backend
 *      reports `dev_auth_enabled`. Clearly labelled in the UI; the backend
 *      refuses this path entirely when ENVIRONMENT=production.
 *
 * The frontend never asserts an identity to the backend: it only forwards the
 * bearer token, and the backend re-derives the user on every request.
 */

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

import { env, supabaseConfigured } from "@/lib/env";
import { clearAccessToken, setAccessToken } from "@/lib/session";
import { apiGet, apiPost } from "@/services/api";
import type { AuthSessionResponse, ReadinessResponse } from "@/types";

let supabaseClient: SupabaseClient | null = null;

export function getSupabaseClient(): SupabaseClient | null {
  if (!supabaseConfigured) return null;
  if (!supabaseClient) {
    supabaseClient = createClient(env.supabaseUrl, env.supabaseAnonKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    });
  }
  return supabaseClient;
}

/** Readiness probe — also tells the UI whether the dev token path is allowed. */
export function fetchReadiness(): Promise<ReadinessResponse> {
  return apiGet<ReadinessResponse>("/health/ready");
}

/** Verify the current token with the backend and provision the local profile. */
export function syncSession(): Promise<AuthSessionResponse> {
  return apiPost<AuthSessionResponse>("/auth/session");
}

export function fetchCurrentUser(): Promise<AuthSessionResponse> {
  return apiGet<AuthSessionResponse>("/auth/me");
}

export async function signInWithPassword(email: string, password: string): Promise<void> {
  const client = getSupabaseClient();
  if (!client) {
    throw new Error(
      "Supabase Auth is not configured. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY.",
    );
  }
  const { data, error } = await client.auth.signInWithPassword({ email, password });
  if (error) throw new Error(error.message);
  setAccessToken(data.session?.access_token ?? null);
}

export async function signUpWithPassword(
  email: string,
  password: string,
  fullName?: string,
): Promise<{ needsEmailConfirmation: boolean }> {
  const client = getSupabaseClient();
  if (!client) {
    throw new Error(
      "Supabase Auth is not configured. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY.",
    );
  }
  const { data, error } = await client.auth.signUp({
    email,
    password,
    options: { data: fullName ? { full_name: fullName } : undefined },
  });
  if (error) throw new Error(error.message);

  if (data.session?.access_token) {
    setAccessToken(data.session.access_token);
    return { needsEmailConfirmation: false };
  }
  return { needsEmailConfirmation: true };
}

/** Development-only sign-in. Refused by the backend outside development. */
export function signInWithDevToken(token: string = env.devAuthToken): void {
  setAccessToken(token);
}

export async function signOut(): Promise<void> {
  const client = getSupabaseClient();
  if (client) {
    try {
      await client.auth.signOut();
    } catch {
      /* ignore — the local token is cleared regardless */
    }
  }
  clearAccessToken();
}

/**
 * Keep the API session token in sync with Supabase token refreshes.
 * Returns an unsubscribe function.
 */
export function subscribeToSupabaseSessions(): () => void {
  const client = getSupabaseClient();
  if (!client) return () => undefined;

  const { data } = client.auth.onAuthStateChange((_event, session) => {
    setAccessToken(session?.access_token ?? null);
  });
  return () => data.subscription.unsubscribe();
}

/** Restore a persisted Supabase session into the API client (called on boot). */
export async function restoreSupabaseSession(): Promise<void> {
  const client = getSupabaseClient();
  if (!client) return;
  const { data } = await client.auth.getSession();
  if (data.session?.access_token) {
    setAccessToken(data.session.access_token);
  }
}
