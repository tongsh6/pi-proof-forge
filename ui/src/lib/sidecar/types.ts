import type { RpcResultBase } from "@/lib/rpc/types";

export type SidecarConnectionState =
  | "starting"
  | "ready"
  | "degraded"
  | "reconnecting"
  | "disconnected"
  | "stopped";

export interface HandshakeResult extends RpcResultBase {
  accepted_protocol_version: string;
  sidecar_version: string;
  capabilities: string[];
  deprecations: string[];
}

export interface PingResult extends RpcResultBase {
  state: SidecarConnectionState;
  timestamp: string;
}

export interface EvidenceListItem {
  candidate_pool_eligible?:boolean;
  evidence_id: string;
  title: string;
  time_range: string;
  role_scope: string;
  score: number;
  status: string;
  updated_at: string;
  time_range_level?: string;
  role_scope_level?: string;
  source_document_count?: number;
}

export interface EvidenceFilters {
  query: string;
  status: string | null;
  role: string | null;
  tags: string[];
  date_range: { start?: string; end?: string } | null;
}

export interface ArtifactSummary {
  resource_id?: string;
  filename?: string;
  mime_type?: string;
  size_bytes?: number;
  created_at?: string;
}

export interface EvidenceDetail {
  field_sources?: EvidenceFieldSource[];
  source_sha256?: string;
  source_error?: string;
  source_documents?:{material_id:string;document_id:string;sha256:string;label:string}[];
  evidence_id: string;
  title: string;
  time_range: string;
  context: string;
  role_scope: string;
  actions: string;
  results: string;
  stack: string[];
  tags: string[];
  artifacts: ArtifactSummary[];
  raw_source?: string;
  source_material_ids?: string[];
  review_decision?: string;
  reviewed_at?: string;
  candidate_pool_eligible?: boolean;
  missing_items?: string[];
  time_range_provenance?: {level?: string; precision?: string; evidence?: unknown[]};
  role_scope_provenance?: {level?: string; confidence?: number; evidence?: unknown[]};
}

export interface EvidenceListResult extends RpcResultBase {
  items: EvidenceListItem[];
  next_cursor: string | null;
}

export interface EvidenceGetResult extends RpcResultBase {
  evidence: EvidenceDetail;
}

export interface EvidenceMutationResult extends RpcResultBase {
  evidence_id: string;
}

export interface EvidenceCreateResult extends EvidenceMutationResult {
  status: string;
  created_at: string;
}

export interface EvidenceUpdateResult extends EvidenceMutationResult {
  updated_at: string;
}

export interface EvidenceDeleteResult extends EvidenceMutationResult {
  deleted: boolean;
}

export interface ProfileAutoLinkResult extends RpcResultBase {
  suggestions: { evidence_id: string; title: string; work_id: string; company: string; basis: string[] }[];
  unresolved: { evidence_id: string; title: string; reason: string; candidates?: string[] }[];
  already_linked: number;
  applied: number;
  revision: string;
}

export interface EvidenceReconcileItem {
  evidence_id: string;
  title: string;
  pool_status: string;
  has_source: boolean;
  traceable_results: number;
  untraceable_results: string[];
  suggested_sources: { material_id: string; document: string; result: string }[];
  verbatim_candidates: { result: string; verbatim: string; similarity: number }[];
  missing_fields: string[];
  date_hints: string[];
  possible_duplicates: string[];
  triage?: EvidenceTriage | null;
}

export type EvidenceTriageDecision = "needs_fill" | "not_for_display" | "duplicate";

export interface EvidenceTriage {
  decision: EvidenceTriageDecision;
  note: string;
  duplicate_of: string;
  stale: boolean;
}

export type EvidenceInferenceCandidate = {
  field: "time_range" | "role_scope";
  value: string;
  level: string;
  confidence?: number;
  precision?: string;
  first_person_hits?: Record<string, number>;
  candidate_hash: string;
  evidence: Array<{material_id:string;document_id:string;sha256?:string;excerpt?:string;key?:string}>;
};

export interface EvidenceInferenceCard {
  card_id: string;
  card_sha256: string;
  cache: "hit" | "miss";
  status: "ok" | "rules_only" | "llm_error";
  error?: string;
  candidates: EvidenceInferenceCandidate[];
  documents: number;
  windows: string[];
}

export interface EvidenceInferenceResult extends RpcResultBase {
  status: string;
  enabled: boolean;
  cards: EvidenceInferenceCard[];
  summary: {requested:number;cards_with_candidates?:number;candidates:number;time_candidates?:number;role_candidates?:number;rules_only?:number;cache_hits?:number;errors?:number};
}

export interface EvidenceInferenceConfirmResult extends RpcResultBase {
  status: "accepted" | "rejected";
  evidence_id: string;
  field: "time_range" | "role_scope";
  value?: string;
  card_sha256?: string;
  provenance?: Record<string, unknown>;
  candidate_hash?: string;
}

export interface EvidenceReconcileResult extends RpcResultBase {
  summary: {
    total: number;
    eligible: number;
    incomplete: number;
    legacy: number;
    untraceable_cards: number;
    missing_time_range: number;
    missing_role_scope: number;
    duplicate_cards: number;
    triaged_out?: number;
    needs_fill?: number;
    untriaged?: number;
  };
  items: EvidenceReconcileItem[];
}

export interface EvidenceImportResult extends EvidenceMutationResult {
  imported_resources: string[];
}

export interface EvidenceDraftArtifact {
  type: "markdown_document" | string;
  ref: string;
  label: string;
}

export interface EvidenceDraftPayload {
  field_sources?: EvidenceFieldSource[];
  source_documents?: {material_id:string;document_id:string;sha256:string;label:string}[];
  title: string;
  time_range?: string;
  context: string;
  role_scope?: string;
  actions: string;
  results: string;
  artifacts: EvidenceDraftArtifact[];
  stack: string[];
  tags: string[];
  source_material_ids: string[];
  status?: string;
  missing_items?: string[];
  candidate_pool_eligible?: boolean;
}

export interface EvidenceFieldSource {
  field: 'time_range' | 'role_scope' | 'context' | 'actions' | 'results';
  value: string;
  quote: string;
  material_id: string;
  document_id: string;
}

export interface EvidenceGenerateDraftResult extends RpcResultBase {
  status: "draft_ready_for_review" | "draft_incomplete" | "blocked" | "llm_output_invalid" | string;
  code: "OK" | "BLOCKED_LOCAL_PROVIDER" | "llm_output_invalid" | string;
  message: string;
  draft: EvidenceDraftPayload | null;
  candidate_pool_eligible: boolean;
}

export interface EvidenceSaveDraftResult extends EvidenceMutationResult {
  status: "saved_incomplete" | "saved_eligible" | string;
  missing_items: string[];
  candidate_pool_eligible: boolean;
  updated_at: string;
}

export interface JobProfileListItem {
  job_profile_id: string;
  job_lead_id?: string;
  source_url?: string;
  platform?: string;
  platform_job_id?: string;
  platform_job_type?: string;
  source_jd_sha256?: string;
  /** 人工导入（粘贴 JD）时为 "manual"，界面标明“人工导入 · 平台”。 */
  import_mode?: string;
  company_size?: string;
  financing_stage?: string;
  industry?: string;
  source_recorded_at?: string;
  title: string;
  company: string;
  status: "active" | "draft" | "archived" | string;
  match_score: number;
  evidence_count: number;
  resume_count: number;
  updated_at: string;
  business_domain: string;
  source_jd: string;
  tone: string;
  keywords: string[];
  must_have: string[];
  nice_to_have: string[];
  seniority_signal: string[];
}

export interface JobProfilesFilters {
  status: string | null;
  query: string;
  tags: string[];
}

export interface JobProfilesListResult extends RpcResultBase {
  items: JobProfileListItem[];
  next_cursor: string | null;
}

export interface JobLeadListItem {
  job_lead_id: string;
  job_profile_id?: string;
  company: string;
  position: string;
  salary?: string;
  location?: string;
  source: string;
  status: string;
  favorited: boolean;
  updated_at: string;
  url?: string;
  source_url?: string;
  source_jd?: string;
  source_jd_sha256?: string;
  platform?: string;
  platform_job_id?: string;
  platform_job_type?: string;
  jd_status?: string;
  fetched_at?: string;
  import_mode?: string;
  source_recorded_at?: string;
  company_size?: string;
  financing_stage?: string;
  industry?: string;
  work_years?: string;
  education?: string;
}

export interface JobLeadsFilters {
  source: string | null;
  status: string | null;
  favorited: boolean | null;
  query: string;
  /** 公司人数上界（含），例如 99 表示 100 人以下；null 不限 */
  company_size_max: number | null;
}

export interface JobLeadsListResult extends RpcResultBase {
  items: JobLeadListItem[];
  next_cursor: string | null;
}

export interface LiepinSearchResult extends RpcResultBase {
  status: "pass" | "blocked";
  code: string;
  message: string;
  items: JobLeadListItem[];
  received_count: number;
  imported_count: number;
  page: number;
  auth: LiepinAuthState;
}

export interface LiepinJobDetailResult extends RpcResultBase {
  status: "pass" | "blocked";
  code: string;
  message: string;
  job_lead_id: string;
  job_profile_id: string;
  jd_text: string;
  source_url: string;
  source_jd_sha256: string;
  jd_status: string;
}

export interface JobProfileMutationResult extends RpcResultBase {
  job_profile_id: string;
}

export interface JobProfileCreateResult extends JobProfileMutationResult {
  status: string;
  created_at: string;
}

export interface JobProfileDraftPayload {
  job_lead_id?: string;
  job_profile_id?: string;
  platform?: string;
  platform_job_id?: string;
  platform_job_type?: string;
  source_jd_sha256?: string;
  target_role: string;
  company?: string;
  source_jd: string;
  jd_summary: string;
  source_url?: string;
  business_domain?: string;
  tone?: string;
  description?: string;
  keywords: string[];
  must_have: string[];
  nice_to_have: string[];
  seniority_signal: string[];
  missing_items?: string[];
  status?: string;
  active_target_eligible?: boolean;
}

export interface JobProfileGenerateDraftResult extends RpcResultBase {
  status: "draft_ready_for_review" | "draft_incomplete" | "parse_blocked_local_provider" | "parse_invalid_json" | string;
  code: "OK" | "BLOCKED_LOCAL_PROVIDER" | "parse_invalid_json" | string;
  message: string;
  draft: JobProfileDraftPayload | null;
  active_target_eligible: boolean;
}

export interface JobProfileSaveDraftResult extends JobProfileMutationResult {
  status: "saved_incomplete" | "saved_complete" | string;
  active_target_eligible: boolean;
  missing_items: string[];
  job_lead_id: string;
  source_url_check: Record<string, unknown>;
  updated_at: string;
}

export interface JobProfileUpdateResult extends JobProfileMutationResult {
  updated_at: string;
}

export interface JobProfileDeleteResult extends JobProfileMutationResult {
  deleted: boolean;
}

export interface JobLeadConvertResult extends RpcResultBase {
  job_profile_id: string;
  job_lead_id?: string;
  source_jd?: string;
  source_url?: string;
  source_jd_sha256?: string;
  jd_status?: string;
}

export interface GatePolicy {
  n_pass_required: number;
  matching_threshold: number;
  evaluation_threshold: number;
  max_rounds: number;
  gate_mode: string;
  delivery_mode: DeliveryMode;
  batch_review: boolean;
}

export interface MaskedSecretStatus {
  configured: boolean;
  masked: boolean;
  updated_at: string;
  source?: "saved" | "environment" | "legacy" | "none" | "storage_error" | string;
}

export interface LlmConfig {
  provider: string;
  model: string;
  base_url: string | null;
  api_key: MaskedSecretStatus;
  configured_providers?: string[];
  thinking_enabled?: boolean;
  thinking_effort?: string;
  timeout: number;
  temperature: number;
}

export type LlmConfigSummary = LlmConfig;

export interface ChannelConfig {
  id: string;
  label: string;
  enabled: boolean;
  priority: number;
  fallback_to: string;
  credential_status: "configured" | "missing" | "unknown" | string;
  last_check_status: "pass" | "fail" | "unknown" | string;
  last_success_at: string;
  last_error: string;
}

export type DeliveryMode = "auto" | "manual";

export interface LiepinAuthState {
  configured: boolean;
  state: "unconfigured" | "unverified" | "valid" | "invalid" | "rate_limited" | "error";
  code: string;
  last_checked_at: string;
  last_error: string;
  scope: "read_only";
  storage: "local_file";
  storage_path: string;
  saved: boolean;
}

export interface LiepinCredentialResult extends RpcResultBase {
  auth: LiepinAuthState;
}

export interface LiepinResumeResult extends LiepinCredentialResult {
  status: "pass" | "blocked";
  code: string;
  message: string;
  resume_text: string;
}

export interface SettingsGetResult extends RpcResultBase {
  gate_policy: GatePolicy;
  exclusion_list: string[];
  excluded_legal_entities: string[];
  material_source_roots: MaterialSourceRoot[];
  evidence_inference?: { enabled: boolean };
  channels: ChannelConfig[];
  liepin_api: LiepinAuthState;
  llm_config: LlmConfig;
}

export type SettingsUpdateSection =
  | "gate_policy"
  | "exclusion_list"
  | "excluded_legal_entities"
  | "material_source_roots"
  | "evidence_inference"
  | "llm_config";

export interface SettingsUpdateResult extends RpcResultBase {
  section: SettingsUpdateSection;
  saved: boolean;
}

export interface LlmConnectionCheckResult extends RpcResultBase {
  status: "pass" | "blocked" | string;
  code: "OK" | "BLOCKED_LOCAL_PROVIDER" | string;
  message: string;
  base_url: string | null;
  model_count: number;
  models: string[];
}

/** 受控成功投递按最近一次平台进展归类的计数；unsynced 表示尚未同步过平台状态。 */
export interface OverviewFeedbackFunnel {
  delivered: number;
  viewed: number;
  interested: number;
  interview: number;
  rejected: number;
  closed: number;
  unknown: number;
  unsynced: number;
}

export interface OverviewMetrics {
  evidence_count: number;
  matched_jobs_count: number;
  resume_count: number;
  submission_count: number;
  feedback_funnel?: OverviewFeedbackFunnel;
}

export interface OverviewActivity {
  activity_id: string;
  type:
    | "resume_generated"
    | "submission_sent"
    | "evidence_imported"
    | "agent_run_completed";
  description: string;
  timestamp: string;
}

export interface OverviewTrendPoint {
  date: string;
  score: number;
}

export interface OverviewGap {
  gap_id: string;
  severity: "high" | "medium" | "low";
  description: string;
  suggested_action: string;
}

export interface OverviewGetResult extends RpcResultBase {
  metrics: OverviewMetrics;
  recent_activities: OverviewActivity[];
  match_trend: OverviewTrendPoint[];
  gaps: OverviewGap[];
}

export interface ResumeListItem {
  resume_id: string;
  name: string;
  job_profile_id: string;
  status: string;
  score: number;
  company: string;
  updated_at: string;
}

export interface ResumeListResult extends RpcResultBase {
  items: ResumeListItem[];
  next_cursor: string | null;
}

export interface ResumeUploadResult extends RpcResultBase {
  resume_id: string;
  label: string;
  language: string;
  resource_id: string;
  uploaded_at: string;
}

export interface UploadFilePayload {
  filename: string;
  content_base64: string;
}

export interface ResumePreview {
  name: string;
  contact: { phone: string; email: string; city: string };
  summary: string;
  experience: Array<{ company: string; title: string; period: string; bullets: string[] }>;
  skills: string[];
}

export interface ResumePreviewResult extends RpcResultBase {
  resume_id: string;
  preview: ResumePreview | null;
  preview_status?: string;
  preview_html?: string;
}

export interface ResumeExportResult extends RpcResultBase {
  resource_id: string;
  path: string;
  html_path?: string;
}

export interface MaterialSourceItem {
  material_id: string;
  resource_id: string;
  label: string;
  kind: string;
  filename: string;
  extension: string;
  uploaded_at: string;
  preview: string;
  size_bytes: number;
  source_mode?: string;
  source_root?: string;
  source_relpath?: string;
  manifest_sha256?: string;
  file_count?: string;
}

export interface MaterialSourceRoot {
  id: string;
  label: string;
  path: string;
}

export interface MaterialReferenceScanResult extends RpcResultBase {
  root_id: string;
  relpath: string;
  file_count: number;
  total_bytes: number;
  sample_files: string[];
  skipped: Array<{ relpath: string; reason: string }>;
  skipped_count: number;
  existing_materials: string[];
}

export interface MaterialReferenceStatusResult extends RpcResultBase {
  material_id: string;
  status: "ok" | "changed" | string;
  changed: string[];
  missing: string[];
  added: string[];
  manifest_sha256: string;
  checked_at: string;
}

export interface MaterialReferenceRefreshResult extends RpcResultBase {
  manifest_sha256: string;
  file_count: number;
}

export interface MaterialReferenceRemoveResult extends RpcResultBase {
  removed: boolean;
}

export interface MaterialReferenceCreateResult extends RpcResultBase, MaterialSourceItem {}

export interface MaterialUploadResult extends RpcResultBase, MaterialSourceItem {}

export interface MaterialListResult extends RpcResultBase {
  items: MaterialSourceItem[];
}

export interface MaterialReadinessResult extends RpcResultBase {
  status: "ready" | "incomplete" | string;
  missing_items: string[];
}

export interface CareerEntry {
  id:string; [key:string]:string|boolean|string[]|undefined;
  current?:boolean; end?:string; contributions?:string[]; evidence_ids?:string[];
}
export interface CareerProfile {
  schema_version:1; summary:string; work:CareerEntry[]; education_visibility:'show'|'omit'; education:CareerEntry[]; skills:CareerEntry[]; extras:CareerEntry[];
}

export interface ProfilePayload {
  job_preferences?:JobPreferences;
  career?:CareerProfile;
  revision?:string;
  career_status?:{reviewed:boolean;ready:boolean;reviewed_at:string;missing:{field:string;label:string}[]};
  name: string;
  phone: string;
  email: string;
  city: string;
  current_position: string;
  completeness: number;
  missing_fields: string[];
  updated_at: string;
}

export interface JobPreferences {
  schema_version:1;
  revision?:string;
  confirmed_at?:string;
  source:{material_id:string;document_id:string;sha256:string;filename:string;label:string}|null;
  items:Array<{kind:'primary'|'bridge'|'explore'|'avoid';text:string;quote:string}>;
}

export interface CareerDirection {
  status:'aligned'|'needs_review'|'excluded'; reason:string; jd_quote:string;
  preference:{kind:string;text:string;quote:string};
}

export interface ProfileGetResult extends RpcResultBase {
  profile: ProfilePayload;
}

export interface ProfileUpdateResult extends RpcResultBase {
  saved: boolean;
  updated_at: string;
}

export interface SubmissionListItem {
  submission_id: string;
  retry_allowed?: boolean;
  company: string;
  position: string;
  channel: string;
  mode: string;
  status: string;
  error: string;
  job_url: string;
  submitted_at: string;
  last_step: {
    name: string;
    status: string;
    detail: string;
  };
  rate_limit_status: string;
  rate_limit_detail: string;
  platform_feedback?: { status: string; label: string; observed_at: string; time_label: string };
}

export interface SubmissionListResult extends RpcResultBase {
  items: SubmissionListItem[];
  next_cursor: string | null;
}

export interface SubmissionDetailStep {
  name: string;
  status: string;
  detail: string;
  screenshot: string;
  screenshot_path: string;
  screenshot_exists: boolean;
}

export interface SubmissionEvidence {
  status: "verified" | "incomplete";
  reason: string;
  parent_run_id?: string;
  job_lead_id?: string;
  job_profile_id?: string;
  resume_version_id?: string;
  resume_sha256?: string;
  receipt_sha256?: string;
  receipt_source?: string;
  delivery_kind?: string;
}

export interface SubmissionDetail extends SubmissionListItem {
  evidence?: SubmissionEvidence;
  parent_run_id?: string;
  job_lead_id?: string;
  receipt_source?: string;
  started_at: string;
  ended_at: string;
  resume_path: string;
  resume_version_id: string;
  profile_path: string;
  headless: boolean;
  browser_channel: string;
  terminal_status: string;
  adapter_capabilities: Record<string, unknown>;
  original_job_lead: Record<string, unknown>;
  final_verified_target: Record<string, unknown>;
  session_metadata: Record<string, unknown>;
  target_recovery_attempts: Array<Record<string, unknown>>;
  recovered_target_confirmation: Record<string, unknown>;
  resume_target_mismatch_warning: Record<string, unknown>;
  next_action: string;
  final_submit_attempted: boolean;
  external_submission_attempted: boolean;
  steps: SubmissionDetailStep[];
  log_json_path: string;
  log_yaml_path: string;
}

export interface SubmissionDetailResult extends RpcResultBase {
  submission: SubmissionDetail;
}

export interface SubmissionRetryResult extends RpcResultBase {
  submission_id: string;
  status: string;
}

export interface SubmissionCheckModeOptions {
  preflight_confirmed?: boolean;
  confirmed_no_real_submit?: boolean;
  check_mode_no_real_submit?: boolean;
  submit_enabled?: boolean;
  confirmation_items?: string[];
  target_recovery_limit?: number;
  session_identity_accepted?: boolean;
  simulate_rate_limited?: boolean;
  simulate_target_mismatch?: boolean;
  recovered_target_confirmed?: boolean;
  resume_target_mismatch_warning_acknowledged?: boolean;
  abort_to_regenerate_resume?: boolean;
  [key: string]: unknown;
}

export interface SubmissionCheckModeResult extends RpcResultBase {
  submission_id: string;
  status: string;
  terminal_status: string;
  channel: string;
  mode: string;
  resume_version_id: string;
  steps: SubmissionDetailStep[];
  adapter_capabilities: Record<string, unknown>;
  original_job_lead: Record<string, unknown>;
  final_verified_target: Record<string, unknown>;
  session_metadata: Record<string, unknown>;
  target_recovery_attempts: Array<Record<string, unknown>>;
  recovered_target_confirmation: Record<string, unknown>;
  resume_target_mismatch_warning: Record<string, unknown>;
  next_action: string;
  submit_enabled: boolean;
  final_submit_attempted: boolean;
  external_submission_attempted: boolean;
  log_json_path: string;
  log_yaml_path: string;
}

export interface FeedbackItem {
  source_type: string;
  source_run_id: string;
  source_artifact_path_or_id: string;
  summary: string;
  severity_or_priority: string;
  recommended_next_action: string;
}

export interface FeedbackListResult extends RpcResultBase {
  source_binding?: SubmissionEvidence;
  iterations?: FeedbackIterationRecord[];
  source_run_id: string;
  source_artifact_path: string;
  items: FeedbackItem[];
  supported_actions: string[];
}

export interface FeedbackIterationRecord {
  feedback_source?: "user_note" | "manual_recruiter";
  source_binding?: SubmissionEvidence;
  next_quick_run_candidate?: { job_profile_id: string; source_submission_id: string; requires_review: boolean };
  iteration_id: string;
  status: string;
  created_at: string;
  source_run_id: string;
  source_feedback_items: FeedbackItem[];
  selected_actions: string[];
  user_notes: string;
  affected_artifacts: Record<string, unknown>;
  previous_resume_version_id: string;
  new_resume_version_id_or_none: string;
  evidence_card_ids_added_or_updated: string[];
  job_target_id_or_none: string;
  comparison_summary: Record<string, unknown>;
  remaining_gap_tasks: string[];
  next_recommended_step: string;
  next_check_mode_candidate: Record<string, unknown>;
  source_snapshot_path: string;
  record_path: string;
  immutable_source_snapshot: boolean;
  previous_artifacts_preserved: boolean;
  real_submit_disabled: boolean;
}

export interface FeedbackIterationResult extends RpcResultBase {
  iteration: FeedbackIterationRecord;
  iteration_id: string;
  status: string;
  record_path: string;
  next_check_mode_candidate: Record<string, unknown>;
}

export interface SubmissionChannel {
  channel: string;
  label: string;
  login_url: string;
}

export interface ChannelSessionAccountIdentity {
  status: "available" | "account_identity_unknown" | string;
  display_name_or_nickname: string;
  avatar_presence: boolean | null;
  masked_phone_or_email_suffix: string;
}

export interface ChannelSessionPayload {
  channel: string;
  session_id: string;
  session_path: string;
  login_status: string;
  account_identity: ChannelSessionAccountIdentity;
  checked_at: string;
  expires_or_unknown: string;
  clear_available: boolean;
  log_path: string;
  adapter: Record<string, Record<string, unknown>>;
}

export interface ChannelSessionStep {
  name: string;
  status: string;
  detail: string;
}

export interface ChannelSessionResult extends RpcResultBase {
  supported_channels: SubmissionChannel[];
  session: ChannelSessionPayload;
  steps: ChannelSessionStep[];
  manual_login_required: boolean;
  browser_automation: {
    opened_login_page: boolean;
    entered_credentials: boolean;
    entered_captcha_or_sms: boolean;
    captcha_sms_bypass_attempted: boolean;
  };
  artifact_paths: {
    channel_session: string;
    session_check_log: string;
  };
}

/** One candidate in REVIEW state (design: ReviewCandidate). */
export interface ReviewCandidateItem {
  job_lead_id: string;
  company: string;
  position: string;
  matching_score: number | null;
  evaluation_score: number | null;
  round_index: number;
  resume_version: string;
  snapshot_status?: "ready" | "invalid";
  delivery_kind?: "platform_default" | "generated_pdf";
  status?: string;
  resume_preview?: string;
  job_url?: string;
}

export type QualityFailure = {rule:string;target?:string;reason?:string};
export type QualityTier = {
  passed:boolean;failures:QualityFailure[];metrics?:Record<string,unknown>;
  matrix?:Array<Record<string,unknown>>;highlights?:Array<Record<string,unknown>>;blocked_by?:string;
};
export type QualityReport = {
  schema_version?:number;resume_version?:string;job_profile_id?:string;thresholds_version?:number;
  auto_pass?:boolean;llm_pending?:string[];gap_tasks?:string[];
  legacy_scores?:{rule_total?:number|null;llm_expression?:number|null};
  tiers?:{eligible?:QualityTier;fit?:QualityTier;strong?:QualityTier;distinct?:QualityTier};
};

export type PdfQuality = {
  matching_mode?:'semantic'|'rule';
  status:'bound'|'current'|'unrecorded';
  matching_score?:number|null;resume_score?:number|null;expression_score?:number|null;
  content_ready?:boolean;quality_passed?:boolean;gap_tasks?:string[];evaluation_version?:string;
  auto_pass?:boolean;quality_report?:QualityReport|null;quality_failures?:string[];
  legacy_scores?:{rule_total?:number|null;llm_expression?:number|null};
};

export interface GetPendingReviewResult extends RpcResultBase {
  native_pdf_quick_run_id?: string | null;
  candidates: ReviewCandidateItem[];
  run_id: string;
  delivery_results?: ReviewDeliveryResult[];
}

export interface ReviewDeliveryResult {
  job_lead_id: string;
  success: boolean;
  status: string;
  code: string;
  submission_id?: string;
  receipt_source?: string;
  app_verified?: boolean;
}

export interface PrepareLiepinDefaultResult extends RpcResultBase {
  status: "ready" | "blocked";
  code: string;
  run_id?: string;
  job_profile_id?: string;
  reused?: boolean;
}

export interface ReviewDecisionItem {
  job_lead_id: string;
  action: "approve" | "reject" | "skip" | "skip_all";
  decided_by: string;
  decided_at: string;
  note?: string;
}

export interface SubmitReviewResult extends RpcResultBase {
  accepted: number;
  delivery_results?: ReviewDeliveryResult[];
}

export interface QuickRunStartOptions {
  generate_resume?: boolean;
  raw_path?: string;
  material_id?: string;
  evidence_ids?: string[];
  resume_positioning?: string;
  custom_positioning?: string;
  job_profile_path?: string;
  timeout_seconds?: number;
  use_llm?: boolean;
  require_llm?: boolean;
  [key: string]: unknown;
}

export interface QuickRunStartResult extends RpcResultBase {
  career_direction?:CareerDirection|null;
  run_id: string;
  status: string;
  exit_code?: number | null;
  run_record?: string;
  summary?: string;
  stdout?: string;
  stderr?: string;
  artifacts?: Record<string, string>;
  failed_step?: string;
  reason?: string;
  score_total?: number | null;
  score_breakdown?: Record<string, { score: number; reason?: string }>;
  semantic_review?: {
    assessment_scope?:{qualification_count:number;responsibility_count:number;check_count:number};
    mode: "semantic";
    fit_score: number;
    resume_score: number;
    expression_score?: number;
    reviewed_card_count?: number;
    all_requirements_supported: boolean;
    requirements: Array<{
      requirement_id: string; text: string; status: string; resume_status: string; reason: string;
      kind?:string;
      checks?:Array<{requirement_id:string;criterion:string;status:string;resume_status:string;reason:string;cautions?:string[]}>;
      citations: Array<{ fact_id: string; quote: string; source_id: string; field: string; in_resume: boolean }>;
    }>;
  } | null;
  quality_report?: QualityReport | null;
  llm_config_summary?: LlmConfigSummary;
  material_source?: MaterialSourceItem | null;
  job_profile?: {
    job_profile_id: string;
    status: string;
    active_target_eligible: boolean;
    title?: string;
    company?: string;
  };
  selected_evidence_card_ids?: string[];
  gaps?: string[];
  gap_tasks?: string[];
  resume_positioning?: Record<string, string>;
  resume_pdf?: string;
  resume_readiness?: {
    status: "NEEDS_EVIDENCE" | "NEEDS_REVIEW" | "NOT_GENERATED";
    deliverable: boolean;
    quality_passed: boolean;
    auto_pass?: boolean;
    quality_report?: QualityReport | null;
    quality_failures?: string[];
    evaluation_score: number | null;
    reasons: string[];
    gap_tasks: string[];
    content_ready?: boolean;
    missing_profile_fields?: string[];
    missing_target_fields?: string[];
    missing_evidence_fields?: string[];
    missing_career_fields?: string[];
  };
  pdf_export_error?: string;
  traceability?: {
    evidence_card_ids: string[];
    selected_evidence_card_ids?: string[];
    evidence: {
      evidence_id?: string;
      raw_source?: string;
      artifacts?: string[];
      results_count?: number;
    };
    evidence_cards?: Array<{
      evidence_id?: string;
      raw_source?: string;
      artifacts?: string[];
      results_count?: number;
    }>;
    resume_a: string;
    resume_pdf?: string;
    resume_traceable: boolean;
    scorecard: string;
    matching_uses_selected_evidence?: boolean;
    fact_preserving_traceability?: boolean;
  };
}

export interface QuickRunCancelResult extends RpcResultBase {
  accepted: boolean;
}

export interface AgentRunStartOptions {
  max_rounds?: number;
  execute_dry_run?: boolean;
  execute_guided_batch?: boolean;
  preflight_confirmed?: boolean;
  confirmed_no_real_submit?: boolean;
  submit_enabled?: boolean;
  max_candidates?: number;
  max_passed_candidates?: number;
  max_generated_resumes?: number;
  candidate_ids?: string[];
  evidence_ids?: string[];
  [key: string]: unknown;
}

export interface AgentRunStartResult extends RpcResultBase {
  run_id: string;
  status: "queued" | string;
  llm_config_summary?: LlmConfigSummary;
  guided_batch?: boolean;
  review_queue?: Record<string, unknown>;
  delivery_plan?: Record<string, unknown>;
}

export interface AgentRunSummary {
  run_id: string;
  status: string;
  round: number;
  started_at: string;
  job_profile_id: string;
  options: AgentRunStartOptions;
  llm_config_summary?: LlmConfigSummary;
  guided_batch?: boolean;
  selected_candidate_ids?: string[];
  policy_limits?: Record<string, unknown>;
  preflight_confirmation?: Record<string, unknown>;
  delivery_plan?: Record<string, unknown>;
  review_queue?: Record<string, unknown>;
  run_log?: string;
  stopped_at?: string;
  deliveries_completed?: number;
  app_verified_deliveries?: number;
  externally_confirmed_deliveries?: number;
}

export interface AgentRunGetResult extends RpcResultBase {
  delivery_batch?: { batch_id: string; authorized_max: number; consumed: number; remaining: number; confirmed: number; unresolved: number } | null;
  run: AgentRunSummary;
  gate_checks: Array<Record<string, unknown>>;
  events: Array<Record<string, unknown>>;
  next_event_cursor: string | null;
}

export interface AgentRunStopResult extends RpcResultBase {
  accepted: boolean;
}
