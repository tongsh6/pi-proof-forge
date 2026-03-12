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
  evidence_id: string;
  title: string;
  time_range: string;
  role_scope: string;
  score: number;
  status: string;
  updated_at: string;
}

export interface ArtifactSummary {
  resource_id?: string;
  filename?: string;
  mime_type?: string;
  size_bytes?: number;
  created_at?: string;
}

export interface EvidenceDetail {
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

export interface JobProfileListItem {
  job_profile_id: string;
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
  company: string;
  position: string;
  source: string;
  status: string;
  favorited: boolean;
  updated_at: string;
}

export interface JobLeadsFilters {
  source: string | null;
  status: string | null;
  favorited: boolean | null;
  query: string;
}

export interface JobLeadsListResult extends RpcResultBase {
  items: JobLeadListItem[];
  next_cursor: string | null;
}

export interface JobProfileMutationResult extends RpcResultBase {
  job_profile_id: string;
}

export interface JobProfileCreateResult extends JobProfileMutationResult {
  status: string;
  created_at: string;
}

export interface JobProfileUpdateResult extends JobProfileMutationResult {
  updated_at: string;
}

export interface JobProfileDeleteResult extends JobProfileMutationResult {
  deleted: boolean;
}

export interface JobLeadConvertResult extends RpcResultBase {
  job_profile_id: string;
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
}

export interface LlmConfig {
  provider: string;
  model: string;
  base_url: string | null;
  api_key: MaskedSecretStatus;
  timeout: number;
  temperature: number;
}

export type DeliveryMode = "auto" | "manual";

export interface SettingsGetResult extends RpcResultBase {
  gate_policy: GatePolicy;
  exclusion_list: string[];
  excluded_legal_entities: string[];
  channels: Array<Record<string, unknown>>;
  llm_config: LlmConfig;
}

export type SettingsUpdateSection =
  | "gate_policy"
  | "exclusion_list"
  | "excluded_legal_entities"

export interface SettingsUpdateResult extends RpcResultBase {
  section: SettingsUpdateSection;
  saved: boolean;
}

export interface OverviewMetrics {
  evidence_count: number;
  matched_jobs_count: number;
  resume_count: number;
  submission_count: number;
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
}

export interface ResumeExportResult extends RpcResultBase {
  resource_id: string;
}

export interface ProfilePayload {
  name: string;
  phone: string;
  email: string;
  city: string;
  current_position: string;
  completeness: number;
  missing_fields: string[];
  updated_at: string;
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
  company: string;
  position: string;
  channel: string;
  status: string;
  submitted_at: string;
}

export interface SubmissionListResult extends RpcResultBase {
  items: SubmissionListItem[];
  next_cursor: string | null;
}

export interface SubmissionRetryResult extends RpcResultBase {
  submission_id: string;
  status: string;
}

/** One candidate in REVIEW state (design: ReviewCandidate). */
export interface ReviewCandidateItem {
  job_lead_id: string;
  company: string;
  position: string;
  matching_score: number;
  evaluation_score: number;
  round_index: number;
  resume_version: string;
  job_url?: string;
}

export interface GetPendingReviewResult extends RpcResultBase {
  candidates: ReviewCandidateItem[];
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
}
