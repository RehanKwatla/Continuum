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

/**
 * Review lifecycle of a claim (mirrors app/models/enums.py::ClaimStatus).
 * `Verified` is the backend's name for the human-approved state; the API
 * exposes it to people as `review_status: "Approved"`.
 */
export type ClaimStatus =
  | "Extracted"
  | "Supported"
  | "Uncertain"
  | "Conflict"
  | "Pending Review"
  | "Needs Clarification"
  | "Rejected"
  | "Verified";

export type VerificationVerdict = "supports" | "partly" | "none";

/** One recorded human decision (mirrors ReviewDecision). */
export type ReviewDecision = "approve" | "reject" | "clarification" | "request_evidence";

/** The five reviewer outcomes for a contradiction (mirrors ConflictResolution). */
export type ConflictResolution =
  | "claim_a_accepted"
  | "claim_b_accepted"
  | "both_valid_in_different_time_periods"
  | "both_rejected"
  | "more_information_required"
  | "dismissed";

/** Lifecycle of a versioned handover (mirrors HandoverLifecycleStatus). */
export type HandoverLifecycleStatus =
  | "Draft"
  | "In Review"
  | "Approved"
  | "Published"
  | "Archived";

/** Provenance class of a single handover statement (mirrors StatementType). */
export type StatementType =
  | "established_fact"
  | "unresolved_question"
  | "reviewer_note"
  | "suggested_action";

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
  is_demo_session?: boolean;
}

export interface PublicDemoStatus {
  enabled: boolean;
  read_only: boolean;
  seeded: boolean;
  banner_label: string;
  disclaimer: string;
  workspace_id?: string;
  workspace_name?: string;
  project_id?: string;
  project_name?: string;
  counts: Record<string, number>;
  links: Record<string, string>;
  projects?: Array<{ id: string; name: string; description: string; focus: string }>;
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
// Phase 3 intelligence layer (mirrors app/schemas/memory.py)
// ---------------------------------------------------------------------------
export type ClaimType =
  | "decision"
  | "responsibility"
  | "ownership"
  | "task"
  | "unfinished_work"
  | "risk"
  | "dependency"
  | "technical_constraint"
  | "operational_procedure"
  | "open_question"
  | "architecture"
  | "process"
  | "constraint"
  | "contact"
  | "status"
  | "other";

export type ProcessingRunStatus = "pending" | "running" | "completed" | "partial" | "failed";

export type ConflictStatus = "open" | "resolved" | "dismissed";

export type ConflictKind = "value_disagreement" | "changed_over_time";

export type FreshnessStatus =
  | "current"
  | "potentially_stale"
  | "contradicted_by_newer_evidence";

export type OpenQuestionStatus = "open" | "resolved";

export interface ProcessingRun {
  id: string;
  project_id: string;
  status: ProcessingRunStatus;
  source_count: number;
  claim_count: number;
  verified_count: number;
  uncertain_count: number;
  conflict_count: number;
  open_question_count: number;
  model_name: string | null;
  error_message: string | null;
  errors: Array<Record<string, unknown>>;
  stats: Record<string, unknown>;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface ProcessingRunListResponse {
  items: ProcessingRun[];
  meta: PageMeta;
}

export interface EvidenceRef {
  id: string;
  source_id: string;
  span_id: string | null;
  source_name: string | null;
  source_type: SourceType | null;
  source_location: string | null;
  start_offset: number | null;
  end_offset: number | null;
  supporting_quote: string | null;
  access_label: AccessLabel | null;
  source_date: string | null;
  author: string | null;
  metadata: Record<string, unknown>;
}

export interface VerificationRead {
  id: string;
  verdict: VerificationVerdict;
  supporting_quote: string | null;
  quote_validated: boolean;
  contradicted_by: string[];
  explanation: string | null;
  confidence: number | null;
  model_name: string | null;
  created_at: string;
}

export interface ClaimHistoryRead {
  id: string;
  action: string;
  from_status: ClaimStatus | null;
  to_status: ClaimStatus | null;
  note: string | null;
  actor_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface ClaimSummary {
  id: string;
  project_id: string;
  text: string;
  claim_type: ClaimType;
  entity: string | null;
  status: ClaimStatus;
  critical: boolean;
  author: string | null;
  confidence: number | null;
  reasoning_summary: string | null;
  access_label: AccessLabel;
  reviewed_at: string | null;
  review_note: string | null;
  verified_at: string | null;
  verified_by_id: string | null;
  created_at: string;
  updated_at: string;
  evidence_count: number;
  source_date: string | null;
}

export interface ClaimDetail extends ClaimSummary {
  evidence: EvidenceRef[];
  verifications: VerificationRead[];
  history: ClaimHistoryRead[];
  conflicts: ConflictSummary[];
  // --- Phase 4 human review -------------------------------------------------
  /** Human-facing review status; "Approved" is the product word for Verified. */
  review_status: string | null;
  /** Which revision of the statement this claim currently carries. */
  revision_number: number;
  /** Legal next states — the UI hides actions, the backend enforces them. */
  allowed_transitions: string[];
  /** Every preserved revision of the statement (oldest first). */
  revisions: ClaimRevisionRead[];
  /** Every human decision recorded against a revision (newest first). */
  decisions: ClaimDecisionRead[];
}

export interface ClaimRevisionRead {
  id: string;
  revision_number: number;
  text: string;
  claim_type: ClaimType;
  entity: string | null;
  note: string | null;
  created_by_id: string | null;
  is_material: boolean;
  verification_required: boolean;
  created_at: string;
}

export interface ClaimDecisionRead {
  id: string;
  claim_id: string;
  claim_revision_id: string | null;
  reviewer_id: string | null;
  decision: ReviewDecision;
  explanation: string | null;
  from_status: string | null;
  to_status: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface ClaimListResponse {
  items: ClaimSummary[];
  meta: PageMeta;
  status_counts: Record<string, number>;
  type_counts: Record<string, number>;
}

export interface ClaimListParams {
  category?: ClaimType;
  status?: ClaimStatus;
  critical?: boolean;
  entity?: string;
  search?: string;
  order?: "recent" | "oldest" | "timeline";
  page?: number;
  page_size?: number;
}

/**
 * A human review decision on a claim (Phase 4 §4, §7).
 * `action` is the endpoint the reviewer chose; the approval engine owns the
 * state machine, so the UI never decides whether a transition is legal.
 */
export interface ClaimDecisionInput {
  action: "approve" | "reject" | "request_clarification";
  explanation?: string | null;
  request_evidence?: boolean;
}

/** Correction of a claim's statement; always stored as a new revision. */
export interface ClaimEditInput {
  text?: string | null;
  claim_type?: ClaimType | null;
  entity?: string | null;
  /** Why the reviewer changed the statement (required, ≥ 4 characters). */
  note: string;
}

// ---------------------------------------------------------------------------
// Phase 4 §3 Human review queue
// ---------------------------------------------------------------------------
export interface ReviewQueueItem {
  id: string;
  text: string;
  category: ClaimType;
  critical: boolean;
  /** The AI verifier's evidence assessment — never an approval. */
  ai_verdict: string | null;
  evidence_count: number;
  source_references: string[];
  conflict_status: string;
  stale_warning: boolean;
  created_at: string;
  /** Human-facing review status ("Approved" for Verified, "Pending review", …). */
  review_status: string;
  status: ClaimStatus;
  revision_number: number;
}

export interface ReviewQueueResponse {
  items: ReviewQueueItem[];
  meta: PageMeta;
}

export type ReviewQueueFilter =
  | "all"
  | "pending"
  | "supported"
  | "uncertain"
  | "conflict"
  | "critical"
  | "resolved"
  | "approved"
  | "rejected"
  | "clarification";

export type ReviewQueueOrder = "critical" | "recent" | "oldest" | "verification";

export interface ReviewQueueParams {
  status?: ReviewQueueFilter;
  critical?: boolean;
  order?: ReviewQueueOrder;
  page?: number;
  page_size?: number;
}

export interface ConflictSummary {
  id: string;
  project_id: string;
  entity: string | null;
  claim_type: ClaimType | null;
  property_key: string | null;
  kind: string;
  status: ConflictStatus;
  summary: string | null;
  resolution_note: string | null;
  resolved_by_id: string | null;
  resolved_at: string | null;
  created_at: string;
  claims: ClaimSummary[];
}

export interface ConflictListResponse {
  items: ConflictSummary[];
  meta: PageMeta;
}

export interface ConflictListParams {
  status?: ConflictStatus;
  kind?: string;
  page?: number;
  page_size?: number;
}

/**
 * Decide a contradiction (Phase 4 §6). An explanation is always required and
 * accepting one side must name which side. Both claims and their evidence are
 * preserved either way.
 */
export interface ConflictResolutionInput {
  resolution: ConflictResolution;
  note: string;
  /** Required when the resolution accepts claim A or claim B. */
  chosen_claim_id?: string | null;
}

/** One side of a contradiction, with the evidence that supports it. */
export interface ConflictClaimRead {
  id: string;
  text: string;
  claim_type: ClaimType;
  entity: string | null;
  status: ClaimStatus;
  author: string | null;
  confidence: number | null;
  created_at: string;
  source_date: string | null;
  evidence: EvidenceRef[];
}

export interface ConflictDetail {
  id: string;
  project_id: string;
  entity: string | null;
  claim_type: ClaimType | null;
  property_key: string | null;
  kind: string;
  status: ConflictStatus;
  summary: string | null;
  resolution: string | null;
  resolution_label: string | null;
  resolution_note: string | null;
  resolution_metadata: Record<string, unknown>;
  resolved_by_id: string | null;
  resolved_at: string | null;
  created_at: string;
  /** True when the two statements could both be true of different periods. */
  could_be_temporal_change: boolean;
  claims: ConflictClaimRead[];
}

export interface OpenQuestionRead {
  id: string;
  project_id: string;
  claim_id: string | null;
  question: string;
  context: string | null;
  entity: string | null;
  status: OpenQuestionStatus;
  access_label: AccessLabel;
  resolution_note: string | null;
  resolved_at: string | null;
  created_at: string;
}

export interface OpenQuestionListResponse {
  items: OpenQuestionRead[];
  meta: PageMeta;
}

export interface StaleSourceRead {
  id: string;
  source_name: string;
  source_type: SourceType;
  author: string | null;
  created_at_source: string | null;
  freshness: FreshnessStatus;
  freshness_checked_at: string | null;
  warnings: Array<Record<string, unknown>>;
}

export interface UncertaintyResponse {
  unsupported_claims: ClaimSummary[];
  open_questions: OpenQuestionRead[];
  stale_sources: StaleSourceRead[];
}

export interface ProjectMemory {
  project_id: string;
  reconstructed: boolean;
  version: number | null;
  summary: string | null;
  stats: Record<string, unknown>;
  generated_at: string | null;
  last_run_id: string | null;
  last_run: ProcessingRun | null;
}

export interface ReconstructInput {
  source_ids?: string[] | null;
}

// ---------------------------------------------------------------------------
// Phase 4 §8–§13 Versioned handover
// ---------------------------------------------------------------------------
/**
 * One statement of a handover version, carrying its provenance. The
 * application — never the model — creates and validates these references.
 */
export interface HandoverStatement {
  statement_id: string;
  text: string;
  statement_type: StatementType;
  claim_ids: string[];
  claim_revisions: Record<string, number>;
  /** Kept when a reviewer edits generated text, so the original is never lost. */
  original_text: string | null;
  reviewer_edited: boolean;
  /** Set when the deterministic validator could not substantiate the statement. */
  unsupported: boolean;
}

export interface HandoverSection {
  key: string;
  title: string;
  statements: HandoverStatement[];
  not_established: boolean;
  placeholder: string | null;
  removed: boolean;
}

export interface ReviewerNote {
  id: string;
  text: string;
  author_id: string | null;
  created_at: string | null;
}

export interface HandoverVersion {
  id: string;
  handover_id: string;
  version_number: number;
  status: HandoverLifecycleStatus;
  summary: string | null;
  model_name: string | null;
  generated_by_id: string | null;
  approved_by_id: string | null;
  approved_at: string | null;
  included_claim_ids: string[];
  claim_revisions: Record<string, number>;
  validation_errors: Array<Record<string, unknown>>;
  reviewer_notes: ReviewerNote[];
  sections: HandoverSection[];
  created_at: string;
}

export interface Handover {
  id: string;
  project_id: string;
  title: string;
  status: HandoverLifecycleStatus;
  current_version: number;
  created_by_id: string | null;
  created_at: string;
  updated_at: string;
  current: HandoverVersion | null;
}

export interface HandoverListResponse {
  items: Handover[];
  meta: PageMeta;
}

/** A reviewer's edit of the current draft; always saved as a new version. */
export interface HandoverUpdateInput {
  title?: string | null;
  summary?: string | null;
  sections: Array<{
    key: string;
    title?: string | null;
    statements: Array<{
      statement_id?: string | null;
      text: string;
      claim_ids?: string[];
      original_text?: string | null;
    }>;
    removed?: boolean;
  }>;
  reviewer_notes?: string[];
  note?: string | null;
}

// ---------------------------------------------------------------------------
// Phase 4 §15 Audit trail
// ---------------------------------------------------------------------------
export interface AuditLogRead {
  id: string;
  user_id: string | null;
  workspace_id: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface AuditTrailResponse {
  items: AuditLogRead[];
  meta: PageMeta;
}

// ---------------------------------------------------------------------------
// Phase 5 §2–§3 Handover readiness (mirrors app/schemas/phase5.py)
// ---------------------------------------------------------------------------
export type ReadinessDimension =
  | "project_context"
  | "important_decisions"
  | "technical_dependencies"
  | "ownership_clarity"
  | "unfinished_work"
  | "risks_and_operations";

export type RequirementCriticality = "critical" | "important" | "optional";

export type RequirementCompletion =
  | "Complete"
  | "Partial"
  | "Missing"
  | "Uncertain"
  | "Blocked";

export type ReadinessBand = "strong" | "mostly_ready" | "needs_review" | "not_ready";

/** One evaluated readiness requirement and the evidence behind its status. */
export interface RequirementResult {
  requirement_id: string;
  dimension: string;
  description: string;
  criticality: string;
  completion: RequirementCompletion;
  supporting_claim_ids: string[];
  supporting_source_ids: string[];
  missing_information: string;
  evaluation_reason: string;
  suggested_resolution: string;
  gap_category: string;
}

export interface DimensionScore {
  key: string;
  label: string;
  score: number;
  weight: number;
  requirement_count: number;
  complete_count: number;
  criticality_weight: number;
}

export interface ReadinessIssue {
  code: string;
  message: string;
  requirement_id?: string | null;
  dimension?: string | null;
  criticality?: string | null;
  conflict_id?: string | null;
  property_key?: string | null;
}

/**
 * An immutable, deterministic readiness snapshot. The score is always returned
 * together with its blockers, warnings and the exact claim revisions used.
 */
export interface ReadinessEvaluation {
  id: string;
  project_id: string;
  handover_id: string | null;
  overall_score: number;
  band: ReadinessBand;
  weights: Record<string, number>;
  dimension_scores: Record<string, DimensionScore>;
  requirements: RequirementResult[];
  blockers: ReadinessIssue[];
  warnings: ReadinessIssue[];
  claim_revisions: Record<string, number>;
  formula: string | null;
  config: Record<string, unknown>;
  created_at: string;
}

export interface ReadinessBandSpec {
  threshold: number;
  band: ReadinessBand;
  label: string;
}

/** The readiness dashboard payload, including its not-yet-evaluated state. */
export interface ReadinessOverview {
  project_id: string;
  evaluation: ReadinessEvaluation | null;
  bands: ReadinessBandSpec[];
  default_weights: Record<string, number>;
  dimension_labels: Record<string, string>;
  formula: string;
  disclaimer: string;
}

export interface ReadinessHistoryResponse {
  items: ReadinessEvaluation[];
  total: number;
}

export interface ReadinessEvaluateInput {
  weights?: Record<string, number> | null;
}

// ---------------------------------------------------------------------------
// Phase 5 §5 Successor task checklist
// ---------------------------------------------------------------------------
export type SuccessorTaskPriority = "High" | "Medium" | "Low";
export type SuccessorTaskStatus = "Not Started" | "In Progress" | "Blocked" | "Completed";
/** "derived" = established obligation, "suggested" = AI/system recommendation, "manual" = successor-authored. */
export type SuccessorTaskOrigin = "derived" | "suggested" | "manual";

export interface SuccessorTask {
  id: string;
  project_id: string;
  title: string;
  description: string | null;
  priority: SuccessorTaskPriority;
  status: SuccessorTaskStatus;
  owner: string | null;
  completion_criteria: string | null;
  supporting_claim_ids: string[];
  dependency_ids: string[];
  origin: SuccessorTaskOrigin;
  origin_claim_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface SuccessorTaskListResponse {
  items: SuccessorTask[];
  total: number;
}

export interface SuccessorTaskCreateInput {
  title: string;
  description?: string | null;
  priority?: SuccessorTaskPriority;
  completion_criteria?: string | null;
}

export interface SuccessorTaskStatusUpdateInput {
  status: SuccessorTaskStatus;
  note?: string | null;
}

export interface SuccessorDeriveResponse {
  created: number;
  total: number;
  task_ids: string[];
  gaps_considered: number;
}

// ---------------------------------------------------------------------------
// Phase 5 §6 Knowledge dependency analysis
// ---------------------------------------------------------------------------
export type DependencyRiskStatus = "Low" | "Moderate" | "High" | "Unknown";

export interface KnowledgeDependency {
  id: string;
  project_id: string;
  dependency_key: string;
  entity: string | null;
  claim_ids: string[];
  related_source_ids: string[];
  involved_people: string[];
  dependency_level: number;
  risk_status: DependencyRiskStatus;
  /** The reviewer's override when one exists, otherwise `risk_status`. */
  effective_risk_status: DependencyRiskStatus;
  evidence_summary: string | null;
  missing_backup_information: string | null;
  override: Record<string, unknown>;
  computed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeDependencyListResponse {
  items: KnowledgeDependency[];
  total: number;
}

export interface KnowledgeDependencyOverrideInput {
  risk_status: DependencyRiskStatus | null;
  note: string;
}

// ---------------------------------------------------------------------------
// Phase 5 §7 Missing knowledge detection
// ---------------------------------------------------------------------------
export type KnowledgeGapStatus = "Open" | "In Progress" | "Resolved" | "Accepted Risk";

export interface KnowledgeGap {
  id: string;
  project_id: string;
  gap_key: string;
  category: string;
  description: string;
  criticality: RequirementCriticality;
  related_claim_ids: string[];
  related_source_ids: string[];
  suggested_resolution: string | null;
  status: KnowledgeGapStatus;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeGapListResponse {
  items: KnowledgeGap[];
  total: number;
}

export interface KnowledgeGapStatusUpdateInput {
  status: KnowledgeGapStatus;
  note?: string | null;
}

// ---------------------------------------------------------------------------
// Phase 5 §8 Continuity scorecard
// ---------------------------------------------------------------------------
export interface HandoverReadinessSummary {
  evaluation_id: string | null;
  overall_score: number | null;
  band: string | null;
  dimension_scores: Record<string, DimensionScore>;
  weights: Record<string, number>;
  evaluated_at: string | null;
  blocker_count: number;
  warning_count: number;
}

export interface ContinuitySourceCoverage {
  total_sources: number;
  processed_sources: number;
  github_sources: number;
  sources_by_type: Record<string, number>;
  approved_claims: number;
  approved_claims_with_evidence: number;
  evidence_coverage_percent: number;
}

export interface ContinuityScorecard {
  project_id: string;
  handover_readiness: HandoverReadinessSummary;
  critical_blockers: ReadinessIssue[];
  warnings: ReadinessIssue[];
  pending_review_items: number;
  conflicts: { open: number; total: number };
  missing_knowledge: { open: number; accepted_risk: number };
  knowledge_dependencies: { high_risk: number; unknown: number };
  successor_tasks: Record<string, number> & { total: number };
  source_coverage: ContinuitySourceCoverage;
  last_evaluation_at: string | null;
  generated_at: string;
}

// ---------------------------------------------------------------------------
// Phase 5 §4 Successor readiness workspace
// ---------------------------------------------------------------------------
export interface WorkspaceEvidenceRef {
  source_name: string;
  source_type: string | null;
  location: string | null;
  quote: string | null;
  author: string | null;
  source_date: string | null;
  restricted: boolean;
}

/** A claim-backed workspace item (sections B–I). */
export interface WorkspaceClaimItem {
  claim_id: string;
  text: string;
  claim_type: ClaimType;
  entity: string | null;
  critical: boolean;
  revision_number: number;
  evidence: WorkspaceEvidenceRef[];
}

export interface WorkspaceReadiness {
  score: number | null;
  band: string | null;
  blocker_count: number;
  open_conflict_count: number;
  open_gap_count: number;
  task_count: number;
}

/** A task-backed workspace item (section J). Its key is `task_id`, not `id`. */
export interface WorkspaceTaskItem {
  task_id: string;
  title: string;
  description: string | null;
  priority: SuccessorTaskPriority;
  status: SuccessorTaskStatus;
  owner: string | null;
  completion_criteria: string | null;
  origin: SuccessorTaskOrigin;
  supporting_claim_ids: string[];
  dependency_ids: string[];
}

export interface WorkspaceSection {
  key: string;
  title: string;
  intro: string;
  /** Claim-backed (A–I) or task-backed (J); the shapes differ by section. */
  items: Array<WorkspaceClaimItem | WorkspaceTaskItem>;
  empty_reason: string | null;
  readiness?: WorkspaceReadiness | null;
  blockers?: Array<{ code: string | null; message: string | null }> | null;
  narrative?: string[] | null;
}

export interface WorkspaceHandoverRef {
  published_version_id: string | null;
  published_version_number: number | null;
  published_at: string | null;
}

export interface SuccessorWorkspace {
  project_id: string;
  sections: WorkspaceSection[];
  handover: WorkspaceHandoverRef;
  counts: Record<string, number>;
  open_gaps: Array<{
    gap_id: string;
    gap_key: string;
    category: string;
    description: string;
    criticality: RequirementCriticality;
    suggested_resolution: string | null;
    status: KnowledgeGapStatus;
  }>;
  disclaimer: string;
}

// ---------------------------------------------------------------------------
// Phase 5 §9–§10 Evaluation framework + successor exercise
// ---------------------------------------------------------------------------
export type EvaluationKind = "metrics" | "successor_exercise";
export type ExerciseOutcome = "completed" | "blocked" | "missing_information";

export interface ExerciseQuestionResult {
  question_id: string;
  prompt: string;
  outcome: ExerciseOutcome;
  answer: string | null;
  supporting_claim_ids: string[];
  explanation: string;
}

/** One metric block: its headline `value`, the counts behind it, and `undefined`. */
export interface MetricBlock {
  value: number;
  undefined?: boolean;
  [detail: string]: unknown;
}

export interface EvaluationReport {
  dataset_version?: string;
  disclaimer?: string;
  questions?: ExerciseQuestionResult[];
  A_claim_extraction?: MetricBlock;
  B_evidence_accuracy?: MetricBlock;
  C_verification_accuracy?: MetricBlock;
  D_conflict_detection?: MetricBlock;
  E_stale_detection?: MetricBlock;
  F_critical_knowledge_coverage?: MetricBlock;
  G_unsupported_handover_rate?: MetricBlock;
  H_permission_leakage?: MetricBlock;
  I_readiness_agreement?: MetricBlock;
  [metric: string]: unknown;
}

export interface EvaluationRun {
  id: string;
  project_id: string | null;
  kind: EvaluationKind;
  dataset_version: string;
  model_version: string | null;
  configuration: Record<string, unknown>;
  metrics: Record<string, number | boolean | string>;
  failures: Array<Record<string, unknown>>;
  report: EvaluationReport;
  created_at: string;
}

export interface EvaluationRunListResponse {
  items: EvaluationRun[];
  total: number;
}

export interface EvaluationRunInput {
  model_version?: string | null;
}

export interface EvaluationComparison {
  project_id: string;
  base_run_id: string;
  candidate_run_id: string;
  dataset_version: string;
  deltas: Array<{ metric: string; before: unknown; after: unknown; delta?: number }>;
  regressions: Array<{ metric: string; before: unknown; after: unknown; delta?: number }>;
  improvements: Array<{ metric: string; before: unknown; after: unknown; delta?: number }>;
  regression_count: number;
  improvement_count: number;
}

export interface SyntheticSeedResponse {
  project_id: string;
  name: string;
  sources: number;
  dataset_version: string;
}

// ---------------------------------------------------------------------------
// Phase 5 §12 System health
// ---------------------------------------------------------------------------
export interface ProcessingRunSummary {
  run_id: string;
  status: ProcessingRunStatus;
  source_count: number;
  claim_count: number;
  verified_count: number;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface SystemHealth {
  project_id: string;
  database: "ok" | "unavailable";
  status: "ok" | "degraded";
  sources_by_status: Record<string, number>;
  processing_runs_by_status: Record<string, number>;
  claims_by_status: Record<string, number>;
  recent_failures: Array<{
    run_id: string;
    status: string;
    error: string | null;
    errors: Array<Record<string, unknown>>;
    created_at: string;
  }>;
  recent_runs: ProcessingRunSummary[];
}
