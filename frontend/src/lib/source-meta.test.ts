import { describe, expect, it } from "vitest";

import {
  ACCESS_LABEL_META,
  ALLOWED_UPLOAD_EXTENSIONS,
  isAllowedUpload,
  PROCESSING_STATUS_META,
  SOURCE_TYPE_META,
  SOURCE_TYPE_ORDER,
  UPLOAD_ACCEPT_ATTRIBUTE,
} from "@/lib/source-meta";

function file(name: string, size = 16): File {
  return new File([new Uint8Array(size)], name, { type: "application/octet-stream" });
}

describe("upload allow-list", () => {
  it("mirrors the backend extension allow-list", () => {
    expect(ALLOWED_UPLOAD_EXTENSIONS).toEqual([".pdf", ".md", ".markdown", ".txt", ".zip"]);
    expect(UPLOAD_ACCEPT_ATTRIBUTE).toBe(".pdf,.md,.markdown,.txt,.zip");
  });

  it("accepts permitted extensions case-insensitively", () => {
    expect(isAllowedUpload(file("handover.pdf"))).toBe(true);
    expect(isAllowedUpload(file("NOTES.MD"))).toBe(true);
    expect(isAllowedUpload(file("readme.markdown"))).toBe(true);
    expect(isAllowedUpload(file("log.txt"))).toBe(true);
    expect(isAllowedUpload(file("archive.zip"))).toBe(true);
  });

  it("rejects credentials, binaries and unsupported types", () => {
    expect(isAllowedUpload(file(".env"))).toBe(false);
    expect(isAllowedUpload(file("id_rsa"))).toBe(false);
    expect(isAllowedUpload(file("report.docx"))).toBe(false);
    expect(isAllowedUpload(file("installer.exe"))).toBe(false);
    expect(isAllowedUpload(file("notes.pdf.exe"))).toBe(false);
  });
});

describe("source presentation metadata", () => {
  it("covers every source type the backend can emit", () => {
    expect(Object.keys(SOURCE_TYPE_META).sort()).toEqual([...SOURCE_TYPE_ORDER].sort());
  });

  it("covers every processing status and access label", () => {
    expect(Object.keys(PROCESSING_STATUS_META)).toEqual([
      "pending",
      "processing",
      "completed",
      "failed",
      "skipped",
      "duplicate",
    ]);
    expect(Object.keys(ACCESS_LABEL_META)).toEqual(["workspace", "private", "public", "restricted"]);
  });
});
