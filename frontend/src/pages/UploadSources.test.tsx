import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";

const mocks = vi.hoisted(() => ({
  useProject: vi.fn(),
  useUploadSources: vi.fn(),
}));

vi.mock("@/hooks/use-projects", () => ({ useProject: mocks.useProject }));
vi.mock("@/hooks/use-sources", () => ({ useUploadSources: mocks.useUploadSources }));

import UploadSources from "@/pages/UploadSources";

function pdf(name: string, bytes: number): File {
  return new File([new Uint8Array(bytes)], name, { type: "application/pdf" });
}

/**
 * `userEvent.upload` silently drops files that fail the input's `accept`
 * filter, which would hide the client-side validation under test. Fire a plain
 * change event with an explicit FileList instead.
 */
function selectFiles(input: HTMLElement, files: File[]) {
  Object.defineProperty(input, "files", { configurable: true, value: files });
  fireEvent.change(input);
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/projects/project-1/sources/upload"]}>
      <ToastProvider>
        <Routes>
          <Route path="/projects/:projectId/sources/upload" element={<UploadSources />} />
        </Routes>
      </ToastProvider>
    </MemoryRouter>,
  );
}

describe("UploadSources", () => {
  beforeEach(() => {
    mocks.useProject.mockReturnValue({
      data: { id: "project-1", name: "Payments Handover" },
      isLoading: false,
      isError: false,
      error: null,
    });
    mocks.useUploadSources.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  });

  it("queues permitted files and enables the upload action", async () => {
    renderPage();

    selectFiles(screen.getByLabelText("Choose files"), [pdf("architecture-notes.pdf", 2048)]);

    expect(screen.getByText("Queued")).toBeInTheDocument();
    expect(screen.getByText("architecture-notes.pdf")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /upload 1/i })).toBeEnabled();
  });

  it("rejects unsupported extensions before any request is made", async () => {
    renderPage();

    selectFiles(screen.getByLabelText("Choose files"), [new File(["skills"], "notes.docx")]);

    expect(screen.getByText("Some files were rejected before upload")).toBeInTheDocument();
    expect(screen.getByText(/notes.docx/)).toBeInTheDocument();
    expect(screen.getByText(/Unsupported type/)).toBeInTheDocument();
    expect(screen.queryByText("Queued")).not.toBeInTheDocument();
  });

  it("rejects files that exceed the upload size limit", async () => {
    renderPage();

    selectFiles(screen.getByLabelText("Choose files"), [pdf("huge.pdf", 26 * 1024 * 1024)]);

    expect(screen.getByText(/Exceeds the 25 MB upload limit/)).toBeInTheDocument();
  });

  it("rejects empty files", async () => {
    renderPage();

    selectFiles(screen.getByLabelText("Choose files"), [new File([], "empty.md")]);

    expect(screen.getByText(/File is empty\./)).toBeInTheDocument();
  });

  it("lets a rejected file be replaced by a valid selection", async () => {
    renderPage();

    const input = screen.getByLabelText("Choose files");
    selectFiles(input, [new File(["x"], ".env")]);
    expect(screen.getByText(/Unsupported type/)).toBeInTheDocument();

    selectFiles(input, [new File(["# Handover"], "handover.md")]);
    expect(screen.getByText("handover.md")).toBeInTheDocument();
    expect(screen.queryByText("Some files were rejected before upload")).not.toBeInTheDocument();
  });
});
