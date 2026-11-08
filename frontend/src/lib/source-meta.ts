import {
  FileArchive,
  FileCode2,
  FileText,
  FileType2,
  GitCommitHorizontal,
  GitPullRequest,
  MessagesSquare,
  Package,
  type LucideIcon,
} from "lucide-react";

import type { AccessLabel, ProcessingStatus, ProjectStatus, SourceType } from "@/types";

export interface SourceTypeMeta {
  label: string;
  Icon: LucideIcon;
  group: "github" | "upload";
}

/** Presentation metadata for every source type the backend can emit. */
export const SOURCE_TYPE_META: Record<SourceType, SourceTypeMeta> = {
  github_commit: { label: "Commit", Icon: GitCommitHorizontal, group: "github" },
  github_issue: { label: "Issue", Icon: MessagesSquare, group: "github" },
  github_pull_request: { label: "Pull request", Icon: GitPullRequest, group: "github" },
  github_readme: { label: "README", Icon: FileText, group: "github" },
  github_file: { label: "Repository file", Icon: FileCode2, group: "github" },
  uploaded_pdf: { label: "PDF", Icon: FileType2, group: "upload" },
  uploaded_markdown: { label: "Markdown", Icon: FileText, group: "upload" },
  uploaded_text: { label: "Text", Icon: FileText, group: "upload" },
  uploaded_zip_entry: { label: "ZIP entry", Icon: Package, group: "upload" },
};

export const SOURCE_TYPE_ORDER: SourceType[] = [
  "github_commit",
  "github_issue",
  "github_pull_request",
  "github_readme",
  "github_file",
  "uploaded_pdf",
  "uploaded_markdown",
  "uploaded_text",
  "uploaded_zip_entry",
];

export const PROCESSING_STATUS_META: Record<
  ProcessingStatus,
  { label: string; tone: "ok" | "warn" | "danger" | "info" | "secondary" }
> = {
  pending: { label: "Pending", tone: "info" },
  processing: { label: "Processing", tone: "info" },
  completed: { label: "Completed", tone: "ok" },
  failed: { label: "Failed", tone: "danger" },
  skipped: { label: "Skipped", tone: "warn" },
  duplicate: { label: "Duplicate", tone: "secondary" },
};

export const PROJECT_STATUS_META: Record<
  ProjectStatus,
  { label: string; tone: "ok" | "warn" | "danger" | "info" | "secondary" }
> = {
  draft: { label: "Draft", tone: "secondary" },
  active: { label: "Active", tone: "ok" },
  handover_in_progress: { label: "Handover in progress", tone: "warn" },
  handed_over: { label: "Handed over", tone: "info" },
  archived: { label: "Archived", tone: "secondary" },
};

export const ACCESS_LABEL_META: Record<AccessLabel, string> = {
  workspace: "Workspace",
  private: "Private",
  public: "Public",
  restricted: "Restricted",
};

export const ALLOWED_UPLOAD_EXTENSIONS = [".pdf", ".md", ".markdown", ".txt", ".zip"] as const;

export const UPLOAD_ACCEPT_ATTRIBUTE = ALLOWED_UPLOAD_EXTENSIONS.join(",");

/** Mirrors the backend allow-list so obvious mistakes are caught client-side. */
export function isAllowedUpload(file: File): boolean {
  const name = file.name.toLowerCase();
  return ALLOWED_UPLOAD_EXTENSIONS.some((extension) => name.endsWith(extension));
}

export { FileArchive };
