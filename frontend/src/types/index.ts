/**
 * Typed mirror of the Continuum backend contract (Pydantic schemas).
 * If a field changes on the backend it must change here too — this file is the
 * single place the frontend learns about API shapes.
 */

// ---------------------------------------------------------------------------
// Enumerations (mirrors app/models/enums.py)
// ---------------------------------------------------------------------------
export type WorkspaceRole = "owner" | "admin" | "member" | "viewer";

export type ProjectStatus =
  | "draft"
  | "active"
  | "handover_in_progress"
  | "handed_over"
  | "archived";

export type SourceType =
  | "github_commit"
  | "github_issue"
  | "github_pull_request"
  | "github_readme"
  | "github_file"
  | "uploaded_pdf"
  | "uploaded_markdown"
  | "uploaded_text"
  | "uploaded_zip_entry";

export type ProcessingStatus =
  | "pending"
  | "processing"
  | "completed"
  | "failed"
  | "skipped"
  | "duplicate";

export type AccessLabel = "workspace" | "private" | "public" | "restricted";

export type ClaimStatus = "Supported" | "Uncertain" | "Conflict" | "Verified";

export type VerificationVerdict = "supports" | "partly" | "none";

// ---------------------------------------------------------------------------
// Envelope + pagination
// ---------------------------------------------------------------------------
export interface ApiErrorDetail {
  code: string;
  message: string;
  details: Record<string, unknown>;
}

export interface ApiErrorEnvelope {
  error: ApiErrorDetail;
}

export interface PageMeta {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface Page<T> {
  items: T[];
  meta: PageMeta;
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------
export interface UserProfile {
  id: string;
  email: string;
  full_name: string | null;
  created_at: string;
}

export interface AuthSessionResponse {
  user: UserProfile;
  auth_provider: string;
  is_dev_session: boolean;
}

// ---------------------------------------------------------------------------
// Workspaces
// ---------------------------------------------------------------------------
export interface WorkspaceMember {
  id: string;
  user_id: string;
  role: WorkspaceRole;
  created_at: string;
  email: string | null;
  full_name: string | null;
}

export interface WorkspaceSummary {
  id: string;
  name: string;
  owner_id: string;
  created_at: string;
  role: WorkspaceRole | null;
  project_count: number;
  member_count: number;
}

export interface Workspace extends WorkspaceSummary {
  members: WorkspaceMember[];
}

export interface WorkspaceCreateInput {
  name: string;
}

// ---------------------------------------------------------------------------
// Projects
// ---------------------------------------------------------------------------
export interface ProjectSummary {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  status: ProjectStatus;
  departing_role: string | null;
  successor_role: string | null;
  created_at: string;
  updated_at: string;
  source_count: number;
  repository_count: number;
}

export interface Repository {
  id: string;
  provider: string;
  full_name: string;
  external_id: string | null;
  description: string | null;
  default_branch: string | null;
  is_private: boolean;
  html_url: string | null;
  connected_at: string;
  metadata: Record<string, unknown>;
}

export interface Project extends ProjectSummary {
  workspace: WorkspaceSummary | null;
  repositories: Repository[];
  source_type_counts: Record<string, number>;
  processing_status_counts: Record<string, number>;
}

export interface ProjectCreateInput {
  workspace_id: string;
  name: string;
  description?: string | null;
  departing_role?: string | null;
  successor_role?: string | null;
  status?: ProjectStatus;
}

export interface ProjectUpdateInput {
  name?: string;
  description?: string | null;
  departing_role?: string | null;
  successor_role?: string | null;
  status?: ProjectStatus;
}

export interface ProjectListParams {
  workspace_id?: string;
  search?: string;
  status?: ProjectStatus;
  page?: number;
  page_size?: number;
}

// ---------------------------------------------------------------------------
// Sources
// ---------------------------------------------------------------------------
export interface SourceSummary {
  id: string;
  project_id: string;
  source_type: SourceType;
  source_name: string;
  external_id: string | null;
  author: string | null;
  created_at_source: string | null;
  access_label: AccessLabel;
  processing_status: ProcessingStatus;
  content_hash: string | null;
  mime_type: string | null;
  size_bytes: number | null;
  source_url: string | null;
  error_message: string | null;
  warnings: string[];
  created_at: string;
  metadata: Record<string, unknown>;
  content_preview: string | null;
}

export interface Source extends SourceSummary {
  content: string | null;
}

export interface SourceListResponse {
  items: SourceSummary[];
  meta: PageMeta;
  type_counts: Record<string, number>;
  status_counts: Record<string, number>;
}

export interface SourceListParams {
  source_type?: SourceType;
  processing_status?: ProcessingStatus;
  search?: string;
  page?: number;
  page_size?: number;
}

export interface IngestionResult {
  filename: string;
  source_id: string | null;
  source_type: SourceType | null;
  status: ProcessingStatus;
  message: string | null;
  warnings: string[];
  duplicate_of: string | null;
}

export interface UploadResponse {
  results: IngestionResult[];
  accepted: number;
  duplicates: number;
  failed: number;
}

export interface SourceDeleteResponse {
  id: string;
  deleted: boolean;
}

// ---------------------------------------------------------------------------
// GitHub
// ---------------------------------------------------------------------------
export interface GitHubStatus {
  configured: boolean;
  connected: boolean;
  login: string | null;
  avatar_url: string | null;
  github_user_id: string | null;
  scopes: string[];
  connected_at: string | null;
  message: string | null;
}

export interface GitHubConnectResponse {
  authorize_url: string;
  state: string;
}

export interface GitHubRepositorySummary {
  id: string;
  full_name: string;
  name: string;
  owner: string;
  private: boolean;
  description: string | null;
  default_branch: string | null;
  html_url: string | null;
  language: string | null;
  stars: number;
  updated_at: string | null;
}

export interface GitHubRepositoryListResponse {
  items: GitHubRepositorySummary[];
  total: number;
  truncated: boolean;
}

export interface GitHubRepositoryDetail {
  repository: GitHubRepositorySummary;
  readme_present: boolean;
  default_branch_sha: string | null;
  open_issues: number | null;
}

export interface GitHubImportInput {
  repository: string;
  include_commits?: boolean;
  include_issues?: boolean;
  include_pull_requests?: boolean;
  include_readme?: boolean;
  include_files?: boolean;
  include_changed_files?: boolean;
  max_items?: number;
}

export interface GitHubImportResponse {
  repository: Repository;
  imported: number;
  duplicates: number;
  skipped: number;
  failed: number;
  results: IngestionResult[];
}

export interface GitHubBoundary {
  configured: boolean;
  reason: string;
  remediation: string[];
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------
export interface RecentSourceItem {
  id: string;
  project_id: string;
  project_name: string;
  source_type: SourceType;
  source_name: string;
  processing_status: ProcessingStatus;
  created_at: string;
}

export interface DashboardStats {
  total_projects: number;
  total_sources: number;
  total_workspaces: number;
  total_connected_repositories: number;
  source_type_counts: Record<string, number>;
  processing_status_counts: Record<string, number>;
  recent_projects: ProjectSummary[];
  recent_sources: RecentSourceItem[];
  upcoming: string[];
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------
export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  environment: string;
}

export interface ReadinessResponse {
  status: string;
  version: string;
  database: string;
  supabase_auth_configured: boolean;
  github_oauth_configured: boolean;
  dev_auth_enabled: boolean;
}

// ---------------------------------------------------------------------------
// Phase 3 AI contracts (typed, but not yet wired to any agent)
// ---------------------------------------------------------------------------
export interface ClaimContract {
  id: string;
  text: string;
  claim_type: string;
  entity: string | null;
  source_span_ids: string[];
  access_label: AccessLabel;
  critical: boolean;
  status: ClaimStatus;
}

export interface VerificationContract {
  claim_id: string;
  verdict: VerificationVerdict;
  supporting_quote: string | null;
  contradicted_by: string[];
}
