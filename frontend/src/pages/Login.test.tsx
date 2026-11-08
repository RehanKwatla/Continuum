import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";
import { ApiClientError } from "@/services/api";

const mocks = vi.hoisted(() => ({
  useReadiness: vi.fn(),
  refresh: vi.fn(),
  supabaseConfigured: false,
  signInWithPassword: vi.fn(),
  signUpWithPassword: vi.fn(),
  signInWithDevToken: vi.fn(),
  syncSession: vi.fn(),
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ refresh: mocks.refresh }),
}));

vi.mock("@/hooks/use-dashboard", () => ({ useReadiness: mocks.useReadiness }));

vi.mock("@/lib/env", () => ({
  env: {
    apiBaseUrl: "http://localhost:8000/api/v1",
    supabaseUrl: "",
    supabaseAnonKey: "",
    devAuthToken: "dev-local-token",
  },
  get supabaseConfigured() {
    return mocks.supabaseConfigured;
  },
}));

vi.mock("@/services/auth", () => ({
  fetchReadiness: vi.fn(),
  syncSession: mocks.syncSession,
  fetchCurrentUser: vi.fn(),
  signInWithPassword: mocks.signInWithPassword,
  signUpWithPassword: mocks.signUpWithPassword,
  signInWithDevToken: mocks.signInWithDevToken,
  signOut: vi.fn(),
  subscribeToSupabaseSessions: vi.fn(),
  restoreSupabaseSession: vi.fn(),
  getSupabaseClient: () => null,
}));

import Login from "@/pages/Login";

function readiness(overrides: Record<string, unknown>) {
  return {
    isLoading: false,
    isError: false,
    isSuccess: true,
    data: {
      status: "ready",
      version: "0.2.0",
      database: "ok",
      supabase_auth_configured: false,
      github_oauth_configured: false,
      dev_auth_enabled: false,
      ...overrides,
    },
    error: null,
    refetch: vi.fn(),
  };
}

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <ToastProvider>
        <Login />
      </ToastProvider>
    </MemoryRouter>,
  );
}

describe("Login", () => {
  beforeEach(() => {
    mocks.supabaseConfigured = false;
    mocks.useReadiness.mockReset();
    mocks.signInWithDevToken.mockReset();
    mocks.syncSession.mockReset().mockResolvedValue({});
    mocks.refresh.mockReset().mockResolvedValue(undefined);
  });

  it("holds the form while readiness is loading", () => {
    mocks.useReadiness.mockReturnValue({
      isLoading: true,
      isError: false,
      isSuccess: false,
      data: undefined,
      error: null,
      refetch: vi.fn(),
    });
    renderLogin();

    expect(screen.getByText("Sign in to Continuum")).toBeInTheDocument();
    expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /development session/i }),
    ).not.toBeInTheDocument();
  });

  it("explains that Supabase Auth is not configured", () => {
    mocks.useReadiness.mockReturnValue(readiness({}));
    renderLogin();

    expect(screen.getByText("Supabase Auth is not configured")).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Sign in" })).not.toBeInTheDocument();
  });

  it("surfaces an unreachable backend", () => {
    mocks.useReadiness.mockReturnValue({
      isLoading: false,
      isError: true,
      isSuccess: false,
      data: undefined,
      error: new ApiClientError("Network down", { code: "network_error" }),
      refetch: vi.fn(),
    });
    renderLogin();

    expect(screen.getByText("Backend unreachable")).toBeInTheDocument();
  });

  it("only offers the development session when the backend enables it", async () => {
    mocks.useReadiness.mockReturnValue(readiness({ dev_auth_enabled: true }));
    renderLogin();

    const devButton = screen.getByRole("button", { name: /development session/i });
    expect(devButton).toBeInTheDocument();

    await userEvent.click(devButton);

    expect(mocks.signInWithDevToken).toHaveBeenCalledTimes(1);
    expect(mocks.syncSession).toHaveBeenCalledTimes(1);
    expect(mocks.refresh).toHaveBeenCalledTimes(1);
  });

  it("renders Supabase email sign-in when it is configured", () => {
    mocks.supabaseConfigured = true;
    mocks.useReadiness.mockReturnValue(readiness({ supabase_auth_configured: true }));
    renderLogin();

    expect(screen.getByRole("tab", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Create account" })).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
  });

  it("reports a failed Supabase sign-in without leaking a stack trace", async () => {
    mocks.supabaseConfigured = true;
    mocks.useReadiness.mockReturnValue(readiness({ supabase_auth_configured: true }));
    mocks.signInWithPassword.mockRejectedValue(new Error("Invalid login credentials"));
    renderLogin();

    await userEvent.type(screen.getByLabelText("Email"), "ada@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText("Could not sign in")).toBeInTheDocument();
    expect(screen.getByText("Invalid login credentials")).toBeInTheDocument();
    expect(mocks.syncSession).not.toHaveBeenCalled();
  });
});
