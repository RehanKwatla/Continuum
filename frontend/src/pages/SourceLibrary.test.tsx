import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";
import { ApiClientError } from "@/services/api";
import type { SourceSummary } from "@/types";

const mocks = vi.hoisted(() => ({
  useProject: vi.fn(),
  useSources: vi.fn(),
  useDeleteSource: vi.fn(),
}));

vi.mock("@/hooks/use-projects", () => ({ useProject: mocks.useProject }));
vi.mock("@/hooks/use-sources", () => ({
  useSources: mocks.useSources,
  useDeleteSource: mocks.useDeleteSource,
}));

import SourceLibrary from "@/pages/SourceLibrary";

const ITEM: SourceSummary = {
  id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  project_id: "project-1",
  source_type: "uploaded_pdf",
  source_name: "architecture-notes.pdf",
  external_id: null,
  author: "Rehan K.",
  created_at_source: new Date().toISOString(),
  access_label: "workspace",
  processing_status: "completed",
  content_hash: "a".repeat(64),
  mime_type: "application/pdf",
  size_bytes: 2048,
  source_url: null,
  error_message: null,
  warnings: [],
  created_at: new Date().toISOString(),
  metadata: { page_count: 12 },
  content_preview: "The payments service owns refunds…",
};

const FAILED_ITEM: SourceSummary = {
  ...ITEM,
  id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
  source_type: "uploaded_text",
  source_name: "broken.txt",
  processing_status: "failed",
  error_message: "Unable to decode file contents.",
  content_preview: null,
};

function response(items: SourceSummary[]) {
  return {
    items,
    meta: {
      page: 1,
      page_size: 25,
      total: items.length,
      total_pages: 1,
      has_next: false,
      has_previous: false,
    },
    type_counts: items.reduce<Record<string, number>>((acc, item) => {
      acc[item.source_type] = (acc[item.source_type] ?? 0) + 1;
      return acc;
    }, {}),
    status_counts: items.reduce<Record<string, number>>((acc, item) => {
      acc[item.processing_status] = (acc[item.processing_status] ?? 0) + 1;
      return acc;
    }, {}),
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/projects/project-1/sources"]}>
      <ToastProvider>
        <Routes>
          <Route path="/projects/:projectId/sources" element={<SourceLibrary />} />
        </Routes>
      </ToastProvider>
    </MemoryRouter>,
  );
}

describe("SourceLibrary", () => {
  beforeEach(() => {
    mocks.useProject.mockReturnValue({
      data: { id: "project-1", name: "Payments Handover" },
      isLoading: false,
      isError: false,
      error: null,
    });
    mocks.useDeleteSource.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  });

  it("shows a table skeleton while loading", () => {
    mocks.useSources.mockReturnValue({
      isLoading: true,
      isError: false,
      isSuccess: false,
      data: undefined,
      error: null,
      refetch: vi.fn(),
    });
    renderPage();

    expect(screen.getByRole("heading", { name: "Source library" })).toBeInTheDocument();
    expect(screen.queryByText("architecture-notes.pdf")).not.toBeInTheDocument();
  });

  it("surfaces a normalised error state", () => {
    mocks.useSources.mockReturnValue({
      isLoading: false,
      isError: true,
      isSuccess: false,
      data: undefined,
      error: new ApiClientError("Workspace access denied", { code: "forbidden", status: 403 }),
      refetch: vi.fn(),
    });
    renderPage();

    expect(screen.getByText("Workspace access denied")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("lists real backend records with counts and failure messages", () => {
    mocks.useSources.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: response([ITEM, FAILED_ITEM]),
      error: null,
      refetch: vi.fn(),
    });
    renderPage();

    expect(screen.getByText("architecture-notes.pdf")).toBeInTheDocument();
    expect(screen.getByText("broken.txt")).toBeInTheDocument();
    expect(screen.getAllByText("Rehan K.")).toHaveLength(2);
    expect(screen.getByText("Unable to decode file contents.")).toBeInTheDocument();
    expect(screen.getByText("The payments service owns refunds…")).toBeInTheDocument();
    expect(screen.getByText("All statuses 2")).toBeInTheDocument();
    expect(screen.getByText("2 sources · page 1 of 1")).toBeInTheDocument();
  });

  it("shows an invitation to connect or upload when nothing is ingested", () => {
    mocks.useSources.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: response([]),
      error: null,
      refetch: vi.fn(),
    });
    renderPage();

    expect(screen.getByText("No sources ingested yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /upload files/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /connect github/i })).toBeInTheDocument();
  });
});
