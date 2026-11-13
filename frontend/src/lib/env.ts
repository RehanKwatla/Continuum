/** Environment access with sane local defaults. Never put secrets here. */

export const env = {
  apiBaseUrl:
    import.meta.env.VITE_API_BASE_URL ||
    (import.meta.env.PROD
      ? "https://continuum-api-np4r.onrender.com/api/v1"
      : "http://localhost:8000/api/v1"),
  supabaseUrl: import.meta.env.VITE_SUPABASE_URL ?? "",
  supabaseAnonKey: import.meta.env.VITE_SUPABASE_ANON_KEY ?? "",
  devAuthToken: import.meta.env.VITE_DEV_AUTH_TOKEN ?? "dev-local-token",
} as const;

/** Supabase Auth is only usable when both the URL and the anon key are set. */
export const supabaseConfigured = Boolean(env.supabaseUrl && env.supabaseAnonKey);
