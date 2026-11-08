import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { EmptyState, ErrorState } from "@/components/common/States";
import { ApiClientError } from "@/services/api";

describe("EmptyState", () => {
  it("renders a title, description and action", () => {
    render(
      <EmptyState
        title="No sources ingested yet"
        description="Import a repository or upload documents."
        action={<button type="button">Upload</button>}
      />,
    );

    expect(screen.getByText("No sources ingested yet")).toBeInTheDocument();
    expect(screen.getByText("Import a repository or upload documents.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload" })).toBeInTheDocument();
  });
});

describe("ErrorState", () => {
  it("surfaces the normalised backend message and retries on demand", async () => {
    const onRetry = vi.fn();
    render(
      <ErrorState
        error={new ApiClientError("Database connection failed", { code: "upstream_error" })}
        onRetry={onRetry}
      />,
    );

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Database connection failed")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("renders without a retry control when none is provided", () => {
    render(<ErrorState error="plain string failure" />);
    expect(screen.getByText("Something went wrong.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
  });
});
