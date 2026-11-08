import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";
import { ApiClientError } from "@/services/api";
import type { DashboardStats } from "@/types";

const mocks = vi.hoisted(() => ({
  useDashboard: vi.fn(),
  useWorkspaces: vi.fn(),
}));

vi.mock("@/hooks/use-dashboard", () => ({ useDashboard: mocks.useDashboard }));
vi.mock("@/hooks/use-workspaces", () => ({
  useWorkspaces: mocks.useWorkspaces,
  useCreateWorkspace: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

import Dashboard from "@/pages/Dashboard";

const SAMPLE: DashboardStats = {
  total_projects: 2,
  total_sources: 7,
  total_workspaces: 1,
  total_connected_repositories: 1,
  source_type_counts: { github_commit: 5, uploaded_pdf: 2 },
  processing_status_counts: { completed: 6, failed: 1 },
  recent_projects: [
    {
      id: "11111111-1111-1111-1111-111111111111",
      workspace_id: "22222222-2222-2222-2222-222222222222",
      name: "Payments Handover",
      description: "Reconstruct the payments service before the lead leaves.",
      status: "active",
      departing_role: "Staff Engineer",
      successor_role: "Engineer II",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      source_count: 7,
      repository_count: 1,
    },
  ],
  recent_sources: [
    {
      id: "33333333-3333-3333-3333-333333333333",
      project_id: "11111111-1111-1111-1111-111111111111",
      project_name: "Payments Handover",
      source_type: "uploaded_pdf",
      source_name: "architecture-notes.pdf",
      processing_status: "completed",
      created_at: new Date().toISOString(),
    },
  ],
  upcoming: ["Claim extraction", "Evidence verification", "Handover generation"],
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
      data: [],
      isSuccess: true,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
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

    expect(screen.getByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.queryByText("Connected sources")).not.toBeInTheDocument();
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

  it("renders only the totals reported by the backend", () => {
    mocks.useDashboard.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: SAMPLE,
      error: null,
      refetch: vi.fn(),
    });
    renderDashboard();

    expect(screen.getByText("Connected sources")).toBeInTheDocument();
    expect(screen.getByText("Normalised and stored in PostgreSQL")).toBeInTheDocument();
    // 7 total sources: the tile, the per-type total and the project row all agree.
    expect(screen.getAllByText("7").length).toBeGreaterThanOrEqual(1);
    // Recent project row and recent ingestion row both reference the project.
    expect(screen.getAllByText("Payments Handover").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("architecture-notes.pdf")).toBeInTheDocument();
    // Failed ingests are surfaced rather than hidden.
    expect(screen.getByText(/1 failed — review in the source library/)).toBeInTheDocument();
  });

  it("does not present Phase 3 capabilities as shipped", () => {
    mocks.useDashboard.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: SAMPLE,
      error: null,
      refetch: vi.fn(),
    });
    renderDashboard();

    expect(screen.getByText("Project memory")).toBeInTheDocument();
    expect(screen.getByText("Upcoming")).toBeInTheDocument();
    expect(screen.getByText(/part of Phase 3 and are not implemented/)).toBeInTheDocument();
  });
});
