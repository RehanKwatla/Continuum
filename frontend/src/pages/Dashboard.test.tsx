import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";
import { ApiClientError } from "@/services/api";
import type { DashboardStats } from "@/types";

const mocks = vi.hoisted(() => ({
  useDashboard: vi.fn(),
  useWorkspaces: vi.fn(),
  usePublicDemo: vi.fn(),
  useResetPublicDemo: vi.fn(),
}));

vi.mock("@/hooks/use-dashboard", () => ({ useDashboard: mocks.useDashboard }));
vi.mock("@/hooks/use-workspaces", () => ({
  useWorkspaces: mocks.useWorkspaces,
  useCreateWorkspace: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock("@/hooks/use-demo", () => ({
  usePublicDemo: mocks.usePublicDemo,
  useResetPublicDemo: mocks.useResetPublicDemo,
}));

import Dashboard from "@/pages/Dashboard";

const SAMPLE: DashboardStats = {
  total_projects: 1,
  total_sources: 8,
  total_workspaces: 1,
  total_connected_repositories: 1,
  source_type_counts: { github_pull_request: 2, github_commit: 3, uploaded_pdf: 2, uploaded_markdown: 1 },
  processing_status_counts: { completed: 8, failed: 0 },
  recent_projects: [
    {
      id: "11111111-1111-1111-1111-111111111111",
      workspace_id: "22222222-2222-2222-2222-222222222222",
      name: "Payment Gateway System",
      description: "Reconstruct the payments service before the lead leaves.",
      status: "active",
      departing_role: "Staff Engineer",
      successor_role: "Engineer II",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      source_count: 8,
      repository_count: 1,
    },
  ],
  recent_sources: [
    {
      id: "33333333-3333-3333-3333-333333333333",
      project_id: "11111111-1111-1111-1111-111111111111",
      project_name: "Payment Gateway System",
      source_type: "uploaded_pdf",
      source_name: "architecture-notes.pdf",
      processing_status: "completed",
      created_at: new Date().toISOString(),
    },
  ],
  upcoming: [],
};

function renderDashboard() {
  return render(
    <MemoryRouter>
      <ToastProvider>
        <Dashboard />
      </ToastProvider>
    </MemoryRouter>,
  );
}

describe("Dashboard", () => {
  beforeEach(() => {
    mocks.useWorkspaces.mockReturnValue({
      data: [{ id: "22222222-2222-2222-2222-222222222222", name: "Continuum Demo Workspace" }],
      isSuccess: true,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    mocks.usePublicDemo.mockReturnValue({
      data: {
        enabled: true,
        read_only: true,
        seeded: true,
        banner_label: "PUBLIC DEMO ENVIRONMENT",
        disclaimer: "Synthetic demonstration data",
        workspace_id: "22222222-2222-2222-2222-222222222222",
        workspace_name: "Continuum Demo Workspace",
        project_id: "11111111-1111-1111-1111-111111111111",
        project_name: "Payment Gateway System",
        counts: { sources: 8, claims: 28, conflicts: 1 },
      },
      isLoading: false,
      isSuccess: true,
    });
    mocks.useResetPublicDemo.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
    });
  });

  it("shows a loading skeleton before data arrives", () => {
    mocks.useDashboard.mockReturnValue({
      isLoading: true,
      isError: false,
      isSuccess: false,
      data: undefined,
      error: null,
      refetch: vi.fn(),
    });
    renderDashboard();

    expect(screen.getByRole("heading", { name: /welcome to continuum\./i })).toBeInTheDocument();
    expect(screen.queryByText("Connected Sources")).not.toBeInTheDocument();
  });

  it("renders a normalised error state when the API fails", () => {
    mocks.useDashboard.mockReturnValue({
      isLoading: false,
      isError: true,
      isSuccess: false,
      data: undefined,
      error: new ApiClientError("Unable to reach the Continuum API.", { status: null }),
      refetch: vi.fn(),
    });
    renderDashboard();

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Unable to reach the Continuum API.")).toBeInTheDocument();
  });

    it("renders the public demo workspace and sample project totals", () => {
      mocks.useDashboard.mockReturnValue({
        isLoading: false,
        isError: false,
        isSuccess: true,
        data: SAMPLE,
        error: null,
        refetch: vi.fn(),
      });
      renderDashboard();

      expect(screen.getByRole("heading", { name: "Welcome to Continuum." })).toBeInTheDocument();
      expect(
        screen.getByText("Project knowledge, reconstructed and ready for its next owner."),
      ).toBeInTheDocument();
      expect(screen.getByText("PUBLIC DEMO ENVIRONMENT")).toBeInTheDocument();
      expect(screen.getByText("Connected Sources")).toBeInTheDocument();
      expect(screen.getAllByText("Payment Gateway System").length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText("architecture-notes.pdf")).toBeInTheDocument();
      expect(screen.getByText("Reconstructed Claims")).toBeInTheDocument();
      expect(screen.getByText("Readiness Assessment")).toBeInTheDocument();
    });

      it("presents reconstructed memory, conflicts, and approved handover", () => {
        mocks.useDashboard.mockReturnValue({
          isLoading: false,
          isError: false,
          isSuccess: true,
          data: SAMPLE,
          error: null,
          refetch: vi.fn(),
        });
        renderDashboard();

        expect(screen.getByText("Project Memory")).toBeInTheDocument();
        expect(screen.getByText("Conflict Centre")).toBeInTheDocument();
        expect(screen.getByText("Approved Handover")).toBeInTheDocument();
        expect(screen.getByText("PostgreSQL Version Disagreement")).toBeInTheDocument();
      });
    });
