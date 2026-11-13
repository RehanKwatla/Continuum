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
});
