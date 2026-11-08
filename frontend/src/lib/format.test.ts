import { describe, expect, it } from "vitest";

import {
  formatBytes,
  formatDate,
  formatDateTime,
  formatRelative,
  humanise,
  pluralise,
  titleCase,
} from "@/lib/format";

describe("format helpers", () => {
  it("returns an em dash for missing or invalid values", () => {
    expect(formatDateTime(null)).toBe("—");
    expect(formatDate(undefined)).toBe("—");
    expect(formatRelative("not-a-date")).toBe("—");
    expect(formatBytes(null)).toBe("—");
  });

  it("formats byte sizes across unit boundaries", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
  });

  it("formats relative times", () => {
    const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
    expect(formatRelative(twoHoursAgo)).toBe("2h ago");
    expect(formatRelative(new Date().toISOString())).toBe("just now");
  });

  it("humanises enum-ish identifiers", () => {
    expect(humanise("github_pull_request")).toBe("Github Pull Request");
    expect(titleCase("active")).toBe("Active");
  });

  it("pluralises counts", () => {
    expect(pluralise(0, "source")).toBe("0 sources");
    expect(pluralise(1, "source")).toBe("1 source");
    expect(pluralise(2, "entry", "entries")).toBe("2 entries");
  });
});
