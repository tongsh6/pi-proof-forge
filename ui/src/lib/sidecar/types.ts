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

export interface GatePolicy {
  n_pass_required: number;
  matching_threshold: number;
  evaluation_threshold: number;
  max_rounds: number;
  gate_mode: string;
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
  /** auto: GATE 通过后直接 DELIVER；manual: 进入 REVIEW 等待审批 */
  delivery_mode: DeliveryMode;
  /** 仅 delivery_mode=manual 时有效；true=批量审批，false=逐轮审批 */
  batch_review: boolean;
  exclusion_list: string[];
  excluded_legal_entities: string[];
  channels: Array<Record<string, unknown>>;
  llm_config: LlmConfig;
}

export type SettingsUpdateSection =
  | "gate_policy"
  | "delivery_settings"
  | "exclusion_list"
  | "excluded_legal_entities"
  | "channels"
  | "llm_config";

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
