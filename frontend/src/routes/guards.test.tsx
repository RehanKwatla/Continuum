import * as React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AuthStatus } from "@/contexts/AuthContext";

const authState = {
  status: "loading" as AuthStatus,
};

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    status: authState.status,
    user: null,
    provider: null,
    isDevSession: false,
    isDemoSession: true,
    isDemoReadOnly: true,
    error: null,
    refresh: vi.fn(),
    signOut: vi.fn(),
  }),
}));

vi.mock("@/components/layout/AppShell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="app-shell">{children}</div>
  ),
}));

import { ProtectedRoute, PublicOnlyRoute } from "@/routes/guards";

function renderGuarded() {
  return render(
    <MemoryRouter initialEntries={["/dashboard"]}>
      <Routes>
        <Route element={<ProtectedRoute />}>
          <Route path="/dashboard" element={<div>dashboard view</div>} />
        </Route>
        <Route path="/login" element={<div>login view</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ProtectedRoute", () => {
  beforeEach(() => {
    authState.status = "loading";
  });

  it("holds the route while the session is resolving", () => {
    authState.status = "loading";
    renderGuarded();

    expect(screen.queryByText("dashboard view")).not.toBeInTheDocument();
    expect(screen.queryByText("login view")).not.toBeInTheDocument();
    expect(screen.queryByTestId("app-shell")).not.toBeInTheDocument();
  });

    it("opens the application shell directly for frictionless judge access without login redirects", () => {
      authState.status = "unauthenticated";
      renderGuarded();

      expect(screen.getByTestId("app-shell")).toBeInTheDocument();
      expect(screen.getByText("dashboard view")).toBeInTheDocument();
      expect(screen.queryByText("login view")).not.toBeInTheDocument();
    });

    it("renders the application shell for an authenticated user", () => {
      authState.status = "authenticated";
      renderGuarded();

      expect(screen.getByTestId("app-shell")).toBeInTheDocument();
      expect(screen.getByText("dashboard view")).toBeInTheDocument();
    });
  });

  describe("PublicOnlyRoute", () => {
    it("sends an authenticated user to the dashboard", () => {
      authState.status = "authenticated";
      render(
        <MemoryRouter initialEntries={["/login"]}>
          <Routes>
            <Route
              path="/login"
              element={
                <PublicOnlyRoute>
                  <div>login view</div>
                </PublicOnlyRoute>
              }
            />
            <Route path="/dashboard" element={<div>dashboard view</div>} />
          </Routes>
        </MemoryRouter>,
      );

      expect(screen.getByText("dashboard view")).toBeInTheDocument();
      expect(screen.queryByText("login view")).not.toBeInTheDocument();
    });

      it("redirects unauthenticated visitors to the dashboard without showing a login screen", () => {
        authState.status = "unauthenticated";
        render(
          <MemoryRouter initialEntries={["/login"]}>
            <Routes>
              <Route
                path="/login"
                element={
                  <PublicOnlyRoute>
                    <div>login view</div>
                  </PublicOnlyRoute>
                }
              />
              <Route path="/dashboard" element={<div>dashboard view</div>} />
            </Routes>
          </MemoryRouter>,
        );

        expect(screen.getByText("dashboard view")).toBeInTheDocument();
        expect(screen.queryByText("login view")).not.toBeInTheDocument();
      });
    });
