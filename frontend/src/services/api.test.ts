import { describe, expect, it } from "vitest";

import { ApiClientError, toErrorMessage } from "@/services/api";

describe("ApiClientError", () => {
  it("defaults to a generic code when the envelope is missing", () => {
    const error = new ApiClientError("Something failed");
    expect(error.code).toBe("unknown_error");
    expect(error.status).toBeNull();
    expect(error.details).toEqual({});
    expect(error.isAuthError).toBe(false);
    expect(error.isNotFound).toBe(false);
  });

  it("recognises 401 responses as authentication failures", () => {
    const error = new ApiClientError("Not authenticated", {
      code: "unauthorized",
      status: 401,
    });
    expect(error.isAuthError).toBe(true);
    expect(error.isNotFound).toBe(false);
  });

  it("recognises 404 responses as missing resources", () => {
    const error = new ApiClientError("Source not found", { code: "not_found", status: 404 });
    expect(error.isNotFound).toBe(true);
    expect(error.isAuthError).toBe(false);
  });

  it("preserves backend error details", () => {
    const error = new ApiClientError("Upload rejected", {
      code: "validation_error",
      status: 422,
      details: { issues: [{ loc: ["body", "files"], msg: "unsupported extension" }] },
    });
    expect(error.details).toHaveProperty("issues");
  });
});

describe("toErrorMessage", () => {
  it("prefers the backend message", () => {
    expect(toErrorMessage(new ApiClientError("Backend is unavailable"))).toBe(
      "Backend is unavailable",
    );
  });

  it("falls back to the Error message", () => {
    expect(toErrorMessage(new Error("boom"))).toBe("boom");
  });

  it("never leaks non-Error values", () => {
    expect(toErrorMessage({ weird: true })).toBe("Something went wrong.");
    expect(toErrorMessage(undefined)).toBe("Something went wrong.");
  });
});
