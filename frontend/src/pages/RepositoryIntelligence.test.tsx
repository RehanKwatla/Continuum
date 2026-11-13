import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), useProject: vi.fn() }));
vi.mock("@/services/api", () => ({
  api: { get: mocks.get, post: mocks.post },
  toErrorMessage: (error: unknown) => error instanceof Error ? error.message : "Request failed",
}));
vi.mock("@/hooks/use-projects", () => ({ useProject: mocks.useProject }));

import RepositoryIntelligence from "@/pages/RepositoryIntelligence";

const VALIDATION = {
  data: {
    valid: true,
    repository: {
      name: "fastapi", owner: "fastapi", description: "FastAPI framework", canonical_url: "https://github.com/fastapi/fastapi",
      default_branch: "master", visibility: "public", language: "Python", languages: { Python: 9000 }, stars: 1000,
      forks: 100, open_issues: 20, created_at: null, updated_at: "2026-11-01T00:00:00Z", pushed_at: null, license: "MIT",
    },
    branches: [{ name: "master", commit_sha: "abc123", protected: true, is_default: true }, { name: "feature/demo", commit_sha: "def456", protected: false, is_default: false }],
    selected_branch: "master",
  },
};

function renderPage() {
  return render(<MemoryRouter initialEntries={["/projects/project-1/sources/github"]}><Routes>
    <Route path="/projects/:projectId/sources/github" element={<RepositoryIntelligence />} />
  </Routes></MemoryRouter>);
}

describe("Repository Intelligence", () => {
  beforeEach(() => {
    mocks.get.mockReset().mockResolvedValue({ data: { items: [] } });
    mocks.post.mockReset();
    mocks.useProject.mockReturnValue({ data: { id: "project-1", name: "Billing project" } });
  });

  it("validates a pasted public repository and shows actual metadata and branches", async () => {
    mocks.post.mockResolvedValueOnce(VALIDATION);
    renderPage();
    fireEvent.change(screen.getByLabelText("GitHub repository URL"), { target: { value: "https://github.com/fastapi/fastapi" } });
    fireEvent.click(screen.getByRole("button", { name: "Validate repository" }));

    expect(await screen.findByText("fastapi/fastapi")).toBeInTheDocument();
    expect(screen.getByText("FastAPI framework")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "master (default)" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "feature/demo" })).toBeInTheDocument();
    expect(mocks.post).toHaveBeenCalledWith("/repositories/validate", { repository_url: "https://github.com/fastapi/fastapi" });
  });

  it("submits the selected branch and displays the backend analysis stage", async () => {
    mocks.post.mockResolvedValueOnce(VALIDATION).mockResolvedValueOnce({ data: { repository_id: "repo-id", analysis_run_id: "run-id", status: "fetching_files", stage: "fetching_files" } });
    renderPage();
    fireEvent.change(screen.getByLabelText("GitHub repository URL"), { target: { value: "https://github.com/fastapi/fastapi" } });
    fireEvent.click(screen.getByRole("button", { name: "Validate repository" }));
    await screen.findByText("fastapi/fastapi");
    fireEvent.change(screen.getByLabelText("Analysis branch"), { target: { value: "feature/demo" } });
    fireEvent.click(screen.getByRole("button", { name: "Analyse repository" }));

    await waitFor(() => expect(mocks.post).toHaveBeenLastCalledWith("/repositories/projects/project-1/analyse", {
      repository_url: "https://github.com/fastapi/fastapi", branch: "feature/demo",
    }));
    expect(await screen.findByText("Current backend stage:")).toBeInTheDocument();
    expect(screen.getAllByText("Fetching Files")).toHaveLength(2);
  });

  it("surfaces validation errors without showing repository metadata", async () => {
    mocks.post.mockRejectedValueOnce(new Error("Only public GitHub repositories are supported."));
    renderPage();
    fireEvent.change(screen.getByLabelText("GitHub repository URL"), { target: { value: "https://example.com/private/repo" } });
    fireEvent.click(screen.getByRole("button", { name: "Validate repository" }));

    expect(await screen.findByText("Only public GitHub repositories are supported.")).toBeInTheDocument();
    expect(screen.queryByText("fastapi/fastapi")).not.toBeInTheDocument();
  });

  it("shows code intelligence for an already saved snapshot and explains empty analysis state", async () => {
    mocks.get.mockImplementation((url: string) => {
      if (url === "/repositories/projects/project-1") return Promise.resolve({ data: { items: [{
        id: "repo-id", owner: "fastapi", repository_name: "fastapi", repository_url: "https://github.com/fastapi/fastapi",
        default_branch: "master", selected_branch: "master", branches: [], languages: {}, latest_snapshot: {
          id: "snapshot-id", repository_id: "repo-id", branch: "master", commit_sha: "abc12345", status: "completed", stage: "completed",
          tree_complete: true, files_discovered: 8, files_processed: 8, files_skipped: 0, commits_processed: 0, issues_processed: 0,
          pull_requests_processed: 0, warnings: [], error_summary: null,
        },
      }] } });
      if (url === "/repositories/repo-id/analysis-summary") return Promise.resolve({ data: { status: "not_started" } });
      return Promise.resolve({ data: { items: [] } });
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Code Intelligence" }));
    expect(await screen.findByText("Codebase intelligence")).toBeInTheDocument();
    expect(await screen.findByText(/Run analysis to extract languages/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyse snapshot" })).toBeEnabled();
  });

  it("offers history analysis for the selected completed snapshot", async () => {
    mocks.get.mockImplementation((url: string) => {
      if (url === "/repositories/projects/project-1") return Promise.resolve({ data: { items: [{
        id: "repo-id", owner: "fastapi", repository_name: "fastapi", repository_url: "https://github.com/fastapi/fastapi",
        default_branch: "master", selected_branch: "master", branches: [], languages: {}, latest_snapshot: {
          id: "snapshot-id", repository_id: "repo-id", branch: "master", commit_sha: "abc12345", status: "completed", stage: "completed",
          tree_complete: true, files_discovered: 8, files_processed: 8, files_skipped: 0, commits_processed: 3, issues_processed: 0,
          pull_requests_processed: 1, warnings: [], error_summary: null,
        },
      }] } });
      if (url === "/repositories/repo-id/history-analysis") return Promise.resolve({ data: { status: "not_started" } });
      return Promise.resolve({ data: { items: [] } });
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "History Intelligence" }));
    expect(await screen.findByText("Git history intelligence")).toBeInTheDocument();
    expect(await screen.findByText(/Analyse captured commits/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyse commit history" })).toBeEnabled();
  });

  it("offers evidence-backed knowledge analysis for a saved repository snapshot", async () => {
    mocks.get.mockImplementation((url: string) => {
      if (url === "/repositories/projects/project-1") return Promise.resolve({ data: { items: [{
        id: "repo-id", owner: "fastapi", repository_name: "fastapi", repository_url: "https://github.com/fastapi/fastapi",
        default_branch: "master", selected_branch: "master", branches: [], languages: {}, latest_snapshot: {
          id: "snapshot-id", repository_id: "repo-id", branch: "master", commit_sha: "abc12345", status: "completed", stage: "completed",
          tree_complete: true, files_discovered: 8, files_processed: 8, files_skipped: 0, commits_processed: 3, issues_processed: 0,
          pull_requests_processed: 1, warnings: [], error_summary: null,
        },
      }] } });
      if (url === "/repositories/repo-id/knowledge/overview") return Promise.resolve({ data: { status: "not_started", units: 0, gaps: 0, conflicts: 0, assumptions: 0 } });
      return Promise.resolve({ data: { items: [] } });
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Knowledge" }));
    expect(await screen.findByText("Project knowledge")).toBeInTheDocument();
    expect(await screen.findByText(/Run knowledge analysis to index captured documentation/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyse project knowledge" })).toBeEnabled();
  });
});
