import { RpcClient } from "@/lib/rpc/client";
import { TauriRpcTransport } from "@/lib/rpc/tauri-transport";
import type {
  EvidenceCreateResult,
  EvidenceDeleteResult,
  EvidenceFilters,
  EvidenceGetResult,
  EvidenceImportResult,
  EvidenceListResult,
  EvidenceUpdateResult,
  GetPendingReviewResult,
  HandshakeResult,
  AgentRunGetResult,
  AgentRunStartOptions,
  AgentRunStartResult,
  AgentRunStopResult,
  JobLeadsFilters,
  JobLeadsListResult,
  JobLeadConvertResult,
  LlmConnectionCheckResult,
  MaterialListResult,
  MaterialReadinessResult,
  MaterialUploadResult,
  JobProfileCreateResult,
  JobProfileDeleteResult,
  JobProfilesFilters,
  JobProfilesListResult,
  JobProfileUpdateResult,
  OverviewGetResult,
  PingResult,
  ProfileGetResult,
  ProfileUpdateResult,
  QuickRunCancelResult,
  QuickRunStartOptions,
  QuickRunStartResult,
  ResumeExportResult,
  ResumeListResult,
  ResumePreviewResult,
  ResumeUploadResult,
  ReviewDecisionItem,
  SettingsGetResult,
  SettingsUpdateResult,
  SubmissionDetailResult,
  SubmissionListResult,
  SubmissionRetryResult,
  SubmitReviewResult,
} from "./types";

const UI_VERSION = "0.1.0";
const PROTOCOL_VERSION = "1.0.0";
const REQUESTED_CAPABILITIES = ["events", "file-preview", "pdf-export"];

const client = new RpcClient(new TauriRpcTransport());

export async function bootstrapSidecar(): Promise<{
  handshake: HandshakeResult;
  ping: PingResult;
}> {
  const handshake = await client.call<HandshakeResult>("system.handshake", {
    ui_version: UI_VERSION,
    protocol_version: PROTOCOL_VERSION,
    capabilities: REQUESTED_CAPABILITIES,
  });
  const ping = await client.call<PingResult>("system.ping");

  return { handshake, ping };
}

export async function pingSidecar(): Promise<PingResult> {
  return client.call<PingResult>("system.ping");
}

export async function listEvidence(
  filters?: EvidenceFilters,
  options: {
    cursor?: string | null;
    pageSize?: number;
    sortField?: "updated_at" | "score";
    sortOrder?: "asc" | "desc";
  } = {}
): Promise<EvidenceListResult> {
  const effectiveFilters = filters ?? {
    query: "",
    status: null,
    role: null,
    tags: [],
    date_range: null,
  };
  return client.call<EvidenceListResult>("evidence.list", {
    cursor: options.cursor ?? null,
    page_size: options.pageSize ?? 20,
    sort: {
      field: options.sortField ?? "updated_at",
      order: options.sortOrder ?? "desc",
    },
    filters: effectiveFilters,
  });
}

export async function getEvidence(evidenceId: string): Promise<EvidenceGetResult> {
  return client.call<EvidenceGetResult>("evidence.get", {
    evidence_id: evidenceId,
  });
}

export async function createEvidence(payload: {
  title: string;
  time_range: string;
  context: string;
  role_scope: string;
  actions: string;
  results: string;
  stack: string[];
  tags: string[];
}): Promise<EvidenceCreateResult> {
  return client.call<EvidenceCreateResult>("evidence.create", payload);
}

export async function updateEvidence(
  evidenceId: string,
  patch: Partial<{
    title: string;
    time_range: string;
    context: string;
    role_scope: string;
    actions: string;
    results: string;
    artifacts: string[];
    stack: string[];
    tags: string[];
  }>
): Promise<EvidenceUpdateResult> {
  return client.call<EvidenceUpdateResult>("evidence.update", {
    evidence_id: evidenceId,
    patch,
  });
}

export async function deleteEvidence(
  evidenceId: string
): Promise<EvidenceDeleteResult> {
  return client.call<EvidenceDeleteResult>("evidence.delete", {
    evidence_id: evidenceId,
  });
}

export async function importEvidence(payload: {
  source_paths: string[];
  mode: "create" | "append" | "replace";
  target_evidence_id?: string | null;
}): Promise<EvidenceImportResult> {
  return client.call<EvidenceImportResult>("evidence.import", payload);
}

export async function getSettings(): Promise<SettingsGetResult> {
  return client.call<SettingsGetResult>("settings.get");
}

export async function updateExclusionList(
  entries: string[]
): Promise<SettingsUpdateResult> {
  return client.call<SettingsUpdateResult>("settings.update", {
    section: "exclusion_list",
    payload: entries,
  });
}

export async function updateLegalEntityExclusionList(
  entries: string[]
): Promise<SettingsUpdateResult> {
  return client.call<SettingsUpdateResult>("settings.update", {
    section: "excluded_legal_entities",
    payload: entries,
  });
}

export async function updateDeliverySettings(
  delivery_mode: "auto" | "manual",
  batch_review: boolean
): Promise<SettingsUpdateResult> {
  return client.call<SettingsUpdateResult>("settings.update", {
    section: "gate_policy",
    payload: { delivery_mode, batch_review },
  });
}

export async function updateLlmConfig(payload: {
  provider?: string;
  model?: string;
  base_url?: string;
  api_key?: string;
  timeout?: number;
  temperature?: number;
}): Promise<SettingsUpdateResult> {
  return client.call<SettingsUpdateResult>("settings.update", {
    section: "llm_config",
    payload,
  });
}

export async function checkLlmConnection(payload: {
  provider?: string;
  model?: string;
  base_url?: string;
  api_key?: string;
  timeout?: number;
} = {}): Promise<LlmConnectionCheckResult> {
  return client.call<LlmConnectionCheckResult>("settings.checkLlmConnection", {
    payload,
  });
}

export async function getOverview(): Promise<OverviewGetResult> {
  return client.call<OverviewGetResult>("overview.get");
}

export async function listJobProfiles(
  filters: JobProfilesFilters = {
    status: null,
    query: "",
    tags: [],
  },
  options: {
    cursor?: string | null;
    pageSize?: number;
  } = {}
): Promise<JobProfilesListResult> {
  return client.call<JobProfilesListResult>("jobs.listProfiles", {
    cursor: options.cursor ?? null,
    page_size: options.pageSize ?? 20,
    sort: { field: "updated_at", order: "desc" },
    filters,
  });
}

export async function listJobLeads(
  filters: JobLeadsFilters = {
    source: null,
    status: null,
    favorited: null,
    query: "",
  },
  options: { cursor?: string | null; pageSize?: number } = {}
): Promise<JobLeadsListResult> {
  return client.call<JobLeadsListResult>("jobs.listLeads", {
    cursor: options.cursor ?? null,
    page_size: options.pageSize ?? 20,
    sort: { field: "updated_at", order: "desc" },
    filters,
  });
}

export async function createJobProfile(payload: {
  title: string;
  description: string;
  tags: string[];
  status: "active" | "draft";
}): Promise<JobProfileCreateResult> {
  return client.call<JobProfileCreateResult>("jobs.createProfile", payload);
}

export async function updateJobProfile(
  jobProfileId: string,
  patch: Partial<{
    title: string;
    description: string;
    tags: string[];
    status: "active" | "draft" | "archived";
  }>
): Promise<JobProfileUpdateResult> {
  return client.call<JobProfileUpdateResult>("jobs.updateProfile", {
    job_profile_id: jobProfileId,
    patch,
  });
}

export async function deleteJobProfile(
  jobProfileId: string
): Promise<JobProfileDeleteResult> {
  return client.call<JobProfileDeleteResult>("jobs.deleteProfile", {
    job_profile_id: jobProfileId,
  });
}

export async function convertJobLead(
  jobLeadId: string
): Promise<JobLeadConvertResult> {
  return client.call<JobLeadConvertResult>("jobs.convertLead", {
    job_lead_id: jobLeadId,
  });
}

export async function listResumes(): Promise<ResumeListResult> {
  return client.call<ResumeListResult>("resume.list", {
    cursor: null,
    page_size: 20,
    sort: { field: "updated_at", order: "desc" },
    filters: { job_profile: null, status: null, company: null },
  });
}

export async function uploadResume(payload: {
  source_paths: string[];
  language?: string;
  label?: string;
}): Promise<ResumeUploadResult> {
  return client.call<ResumeUploadResult>("resume.upload", payload);
}

export async function getResumePreview(
  resumeId: string
): Promise<ResumePreviewResult> {
  return client.call<ResumePreviewResult>("resume.getPreview", {
    resume_id: resumeId,
  });
}

export async function exportResumePdf(payload: {
  resume_id: string;
  destination: string;
}): Promise<ResumeExportResult> {
  return client.call<ResumeExportResult>("resume.exportPdf", payload);
}

export async function uploadMaterial(payload: {
  source_paths: string[];
  label?: string;
}): Promise<MaterialUploadResult> {
  return client.call<MaterialUploadResult>("material.upload", payload);
}

export async function listMaterials(): Promise<MaterialListResult> {
  return client.call<MaterialListResult>("material.list");
}

export async function getMaterialReadiness(): Promise<MaterialReadinessResult> {
  return client.call<MaterialReadinessResult>("material.readiness");
}

export async function listEvidenceMaterialSources(): Promise<MaterialListResult> {
  return client.call<MaterialListResult>("evidence.listMaterialSources");
}

export async function getProfile(): Promise<ProfileGetResult> {
  return client.call<ProfileGetResult>("profile.get");
}

export async function updateProfile(
  patch: Partial<{
    name: string;
    phone: string;
    email: string;
    city: string;
    current_position: string;
  }>
): Promise<ProfileUpdateResult> {
  return client.call<ProfileUpdateResult>("profile.update", { patch });
}

export async function listSubmissions(): Promise<SubmissionListResult> {
  return client.call<SubmissionListResult>("submission.list", {
    cursor: null,
    page_size: 20,
    sort: { field: "submitted_at", order: "desc" },
    filters: { company: null, channel: null, status: null, date_range: null },
  });
}

export async function getSubmissionDetail(
  submissionId: string
): Promise<SubmissionDetailResult> {
  return client.call<SubmissionDetailResult>("submission.detail", {
    submission_id: submissionId,
  });
}

export async function retrySubmission(
  submissionId: string,
  strategy: "same_channel" | "fallback_email" = "same_channel"
): Promise<SubmissionRetryResult> {
  return client.call<SubmissionRetryResult>("submission.retry", {
    submission_id: submissionId,
    strategy,
  });
}

export async function getPendingReview(
  runId?: string
): Promise<GetPendingReviewResult> {
  return client.call<GetPendingReviewResult>("run.agent.getPendingReview", {
    ...(runId ? { run_id: runId } : {}),
  });
}

export async function submitReview(
  decisions: ReviewDecisionItem[],
  runId?: string
): Promise<SubmitReviewResult> {
  return client.call<SubmitReviewResult>("run.agent.submitReview", {
    ...(runId ? { run_id: runId } : {}),
    decisions,
  });
}

export async function startQuickRun(payload: {
  job_profile_id: string;
  evidence_id?: string;
  options?: QuickRunStartOptions;
}): Promise<QuickRunStartResult> {
  return client.call<QuickRunStartResult>("run.quick.start", {
    job_profile_id: payload.job_profile_id,
    evidence_id: payload.evidence_id,
    options: payload.options ?? {},
  });
}

export async function cancelQuickRun(
  runId: string
): Promise<QuickRunCancelResult> {
  return client.call<QuickRunCancelResult>("run.quick.cancel", {
    run_id: runId,
  });
}

export async function startAgentRun(payload: {
  job_profile_id: string;
  options?: AgentRunStartOptions;
}): Promise<AgentRunStartResult> {
  return client.call<AgentRunStartResult>("run.agent.start", {
    job_profile_id: payload.job_profile_id,
    options: payload.options ?? {},
  });
}

export async function getAgentRun(
  runId: string,
  eventCursor: string | null = null,
  eventLimit = 50
): Promise<AgentRunGetResult> {
  return client.call<AgentRunGetResult>("run.agent.get", {
    run_id: runId,
    event_cursor: eventCursor,
    event_limit: eventLimit,
  });
}

export async function stopAgentRun(runId: string): Promise<AgentRunStopResult> {
  return client.call<AgentRunStopResult>("run.agent.stop", {
    run_id: runId,
  });
}

export function shutdownSidecar(): void {
  client.close();
}
