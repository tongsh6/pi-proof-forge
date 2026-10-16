import { RpcClient } from "@/lib/rpc/client";
import { invoke } from "@tauri-apps/api/core";
import { TauriRpcTransport } from "@/lib/rpc/tauri-transport";
import type {
  ChannelSessionResult,
  EvidenceCreateResult,
  EvidenceDeleteResult,
  EvidenceFilters,
  EvidenceDraftPayload,
  EvidenceGenerateDraftResult,
  EvidenceGetResult,
  EvidenceImportResult,
  EvidenceListResult,
  EvidenceSaveDraftResult,
  EvidenceUpdateResult,
  FeedbackItem,
  FeedbackIterationResult,
  FeedbackListResult,
  GetPendingReviewResult,
  PrepareLiepinDefaultResult,
  HandshakeResult,
  AgentRunGetResult,
  AgentRunStartOptions,
  AgentRunStartResult,
  AgentRunStopResult,
  JobLeadsFilters,
  JobLeadsListResult,
  JobLeadConvertResult,
  LiepinCredentialResult,
  LiepinJobDetailResult,
  LiepinResumeResult,
  LiepinSearchResult,
  LlmConnectionCheckResult,
  MaterialListResult,
  MaterialReadinessResult,
  MaterialUploadResult,
  JobProfileDraftPayload,
  JobProfileGenerateDraftResult,
  JobProfileCreateResult,
  JobProfileDeleteResult,
  JobProfileSaveDraftResult,
  JobProfilesFilters,
  JobProfilesListResult,
  JobProfileUpdateResult,
  OverviewGetResult,
  PingResult,
  ProfileGetResult,
  JobPreferences,
  CareerProfile,
  ProfileUpdateResult,
  MaterialSourceRoot,
  MaterialReferenceScanResult,
  MaterialReferenceStatusResult,
  MaterialReferenceRefreshResult,
  MaterialReferenceRemoveResult,
  MaterialReferenceCreateResult,
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
  SubmissionCheckModeOptions,
  SubmissionCheckModeResult,
  SubmissionDetailResult,
  SubmissionListResult,
  SubmissionRetryResult,
  SubmitReviewResult,
  UploadFilePayload,
  EvidenceReconcileResult,
  ProfileAutoLinkResult,
} from "./types";

const UI_VERSION = "0.1.0";
const PROTOCOL_VERSION = "1.0.0";
const REQUESTED_CAPABILITIES = ["events", "file-preview", "pdf-export"];

const client = new RpcClient(new TauriRpcTransport());

export async function openLiepinAuthorization(): Promise<void> {
  await invoke<void>("open_liepin_authorization");
}

export type NativeLiepinObservation = {
  status: string;
  url?: string;
  authenticated?: boolean;
  attachment_view?: {
    entry_count: number;
    inputs: { accept: string; multiple: boolean; disabled: boolean }[];
    hints: string[];
  };
};

export async function openLiepinNativeSession(): Promise<NativeLiepinObservation> {
  return invoke("open_liepin_native_session");
}

export async function checkLiepinNativeSession(): Promise<NativeLiepinObservation> {
  return invoke("check_liepin_native_session");
}

export type FeedbackSyncResult = {meta: {correlation_id: string}; status: string; page_url: string; matched: Array<{submission_id: string; normalized_status: string; status_label: string; match_basis: string}>; unmatched_rows: number; submissions_total: number; synced_at: string};
export async function syncLiepinFeedback(): Promise<FeedbackSyncResult> {
  return invoke("sync_liepin_feedback");
}
export async function inspectLiepinNativeAttachments(): Promise<NativeLiepinObservation> {
  return invoke("inspect_liepin_native_attachments");
}

export type NativePdfPreparation = {quality?:import('./types').PdfQuality;single_delivery_authorized?: boolean; verification_error?: string; meta: {correlation_id: string}; run_id: string; company: string; position: string; matching_score?: number; can_confirm_send?: boolean; account_effects_accepted?: boolean; recovery_only?: boolean;
  job_lead_id: string; pdf_sha256: string; pdf_path: string; pdf_filename?: string; phase: string; platform_filename?: string; attachment_removal_state?: string;
  platform_attachment_state?: string; platform_attachment_checked_at?: string};
export async function prepareLiepinPdf(quickRunId: string): Promise<NativePdfPreparation> {
  return client.call<NativePdfPreparation>("run.agent.prepareLiepinPdf", {quick_run_id:quickRunId});
}
export async function uploadLiepinNativePdf(runId: string, acceptAccountEffects: boolean): Promise<NativePdfPreparation> {
  return invoke("upload_liepin_native_pdf", {runId,acceptAccountEffects});
}
export async function inspectUploadedLiepinPdf(runId: string): Promise<NativePdfPreparation> {
  return invoke("inspect_uploaded_liepin_pdf", {runId});
}
export async function inspectLiepinPdfTarget(runId: string): Promise<NativePdfPreparation> {
  return invoke("inspect_liepin_pdf_target", {runId});
}
export async function startLiepinPdfCommunication(runId: string): Promise<NativePdfPreparation> {
  return invoke("start_liepin_pdf_communication", {runId});
}
export async function continueLiepinPdfDelivery(runId: string, action: "inspect" | "prepare" | "send"): Promise<NativePdfPreparation> {
  return invoke("continue_liepin_pdf_delivery", {runId,action});
}
export async function recheckLiepinNativePdfRemoval(runId: string): Promise<NativePdfPreparation> {
  return invoke("recheck_liepin_native_pdf_removal", {runId});
}
export async function removeLiepinNativePdfAttachment(runId: string, confirmed: boolean): Promise<NativePdfPreparation> {
  return invoke("remove_liepin_native_pdf_attachment", {runId, confirmed});
}
export async function verifyNativePdfReceipt(runId: string): Promise<NativePdfPreparation> {
  return client.call<NativePdfPreparation>("run.agent.verifyPdfReceipt", {run_id:runId});
}

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

export async function generateEvidenceDraft(
  materialIds: string[], sourceDocumentId?: string
): Promise<EvidenceGenerateDraftResult> {
  return client.call<EvidenceGenerateDraftResult>("evidence.generateDraft", {
    material_ids: materialIds,
    source_document_id: sourceDocumentId,
  });
}

export async function saveEvidenceDraft(payload: {
  evidence_id?:string;
  expected_sha256?:string;
  draft: EvidenceDraftPayload;
  save_mode: "incomplete" | "eligible";
  review: { decision: "approved"; reviewed_at?: string; merge_sources?:boolean };
}): Promise<EvidenceSaveDraftResult> {
  return client.call<EvidenceSaveDraftResult>("evidence.saveDraft", payload);
}

export async function getSettings(): Promise<SettingsGetResult> {
  return client.call<SettingsGetResult>("settings.get");
}

export async function updateLiepinCredential(
  payload: { action: "set"; token: string } | { action: "clear" | "check" }
): Promise<LiepinCredentialResult> {
  return client.call<LiepinCredentialResult>("settings.liepinCredential", payload);
}

export async function getLiepinResume(): Promise<LiepinResumeResult> {
  return client.call<LiepinResumeResult>("settings.liepinResume");
}

export async function searchLiepinJobs(
  keyword: string,
  page = 0
): Promise<LiepinSearchResult> {
  return client.call<LiepinSearchResult>("jobs.searchLiepin", { keyword, page });
}

export async function fetchLiepinJobDetail(
  jobLeadId: string
): Promise<LiepinJobDetailResult> {
  return client.call<LiepinJobDetailResult>("jobs.fetchLiepinDetail", {
    job_lead_id: jobLeadId,
  });
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
    company_size_max: null,
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

export async function generateJobProfileDraft(payload: {
  jd_text: string;
  source_url?: string;
  job_lead_id?: string;
}): Promise<JobProfileGenerateDraftResult> {
  return client.call<JobProfileGenerateDraftResult>(
    "jobs.generateProfileDraft",
    payload
  );
}

export async function saveJobProfileDraft(payload: {
  draft: JobProfileDraftPayload;
  job_lead_id?: string;
  job_profile_id?: string;
  save_mode: "incomplete" | "complete";
  review: { decision: "approved"; reviewed_at?: string };
}): Promise<JobProfileSaveDraftResult> {
  return client.call<JobProfileSaveDraftResult>("jobs.saveProfileDraft", payload);
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
  source_paths?: string[];
  file?: UploadFilePayload;
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
  source_paths?: string[];
  file?: UploadFilePayload;
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

export async function reconcileEvidence(evidenceIds?: string[]): Promise<EvidenceReconcileResult> {
  return client.call<EvidenceReconcileResult>("evidence.reconcile", evidenceIds ? { evidence_ids: evidenceIds } : {});
}

export async function getProfile(): Promise<ProfileGetResult> {
  return client.call<ProfileGetResult>("profile.get");
}

export async function generateJobPreferences(materialId:string,documentId:string):Promise<{draft:JobPreferences}> {
  return client.call<{meta:{correlation_id:string};draft:JobPreferences}>('profile.generateJobPreferences',{material_id:materialId,document_id:documentId});
}
export async function saveJobPreferences(draft:JobPreferences,revision:string):Promise<{preferences:JobPreferences}> {
  return client.call<{meta:{correlation_id:string};preferences:JobPreferences}>('profile.saveJobPreferences',{draft,expected_revision:revision,confirmed:true});
}

export async function updateProfile(
  patch: Partial<{
    career: CareerProfile;
    name: string;
    phone: string;
    email: string;
    city: string;
    current_position: string;
  }>, expectedRevision?:string
): Promise<ProfileUpdateResult> {
  return client.call<ProfileUpdateResult>("profile.update", { patch, expected_revision:expectedRevision });
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

/** 手动投递记录：用户在 App 外投递后回填；后端写入与自动投递同位置的记录，不可重试。 */
export async function recordManualSubmission(payload: {
  job_profile_id: string;
  delivered_at?: string;
  quick_run_id?: string;
  note?: string;
}): Promise<{ meta: { correlation_id: string }; submission_id: string; status: string; platform: string; delivered_at: string }> {
  return client.call("submission.recordManual", payload);
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

export async function getChannelSession(
  channel: string
): Promise<ChannelSessionResult> {
  return client.call<ChannelSessionResult>("submission.channelSession.get", {
    channel,
  });
}

export async function startChannelSession(
  channel: string
): Promise<ChannelSessionResult> {
  return client.call<ChannelSessionResult>("submission.channelSession.start", {
    channel,
  });
}

export async function checkChannelSession(
  channel: string
): Promise<ChannelSessionResult> {
  return client.call<ChannelSessionResult>("submission.channelSession.check", {
    channel,
  });
}

export async function clearChannelSession(
  channel: string
): Promise<ChannelSessionResult> {
  return client.call<ChannelSessionResult>("submission.channelSession.clear", {
    channel,
  });
}

export async function startSubmissionCheckMode(payload: {
  channel: string;
  job_lead_id: string;
  resume_version_id: string;
  resume_pdf_path: string;
  options?: SubmissionCheckModeOptions;
}): Promise<SubmissionCheckModeResult> {
  return client.call<SubmissionCheckModeResult>("submission.checkMode.start", {
    channel: payload.channel,
    job_lead_id: payload.job_lead_id,
    resume_version_id: payload.resume_version_id,
    resume_pdf_path: payload.resume_pdf_path,
    preflight_confirmed: payload.options?.preflight_confirmed ?? true,
    confirmed_no_real_submit:
      payload.options?.confirmed_no_real_submit ?? true,
    options: payload.options ?? {},
  });
}

export async function listSubmissionFeedback(
  sourceRunId: string
): Promise<FeedbackListResult> {
  return client.call<FeedbackListResult>("submission.feedback.list", {
    source_run_id: sourceRunId,
  });
}

export async function createFeedbackIteration(payload: {
  feedback_source?: "user_note" | "manual_recruiter";
  source_run_id: string;
  source_feedback_items?: FeedbackItem[];
  selected_actions: string[];
  user_notes?: string;
  evidence_card_ids_added_or_updated?: string[];
  new_or_updated_claims?: string[];
  remaining_gap_tasks?: string[];
  job_target_id_or_none?: string;
}): Promise<FeedbackIterationResult> {
  return client.call<FeedbackIterationResult>(
    "submission.feedback.createIteration",
    payload,
  );
}

export async function prepareLiepinDefault(jobLeadId: string): Promise<PrepareLiepinDefaultResult> {
  return client.call<PrepareLiepinDefaultResult>("run.agent.prepareLiepinDefault", { job_lead_id: jobLeadId });
}

export async function recheckReceipt(runId: string, jobLeadId: string): Promise<Pick<GetPendingReviewResult, "meta" | "delivery_results"> & { status: string; code: string }> {
  return client.call("run.agent.recheckReceipt", { run_id: runId, job_lead_id: jobLeadId });
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

export type DailyCandidate = {run_id:string;company:string;position:string;pdf_sha256:string;pdf_path:string;pdf_filename?:string;matching_score?:number;job_url:string};
export type DailyAuthorization = {id:string;state:string;scope:DailyCandidate[];maximum:number;time:string;expires_at:string};
export type DailyProgressItem = {run_id:string;company:string;position:string;phase:string;quick_run_id:string|null;recovery_required:boolean};
export type DailyBatchHistory = {id:string;day:string;state:string;reason:string;maximum?:number;confirmed?:number;unresolved?:number;started_at?:string;finished_at?:string|null;items?:DailyProgressItem[]};
export type DailyStatus = {meta:{correlation_id:string};authorization:DailyAuthorization|null;today:{day:string;confirmed:number;occupied:number;remaining:number;unresolved:number};history:DailyBatchHistory[];candidates:DailyCandidate[];recovery_required?:boolean;recovery_items?:DailyProgressItem[]};
export async function getDailyStatus():Promise<DailyStatus> {return client.call<DailyStatus>("daily.status",{});}
export async function saveDailyDraft(params:{run_ids:string[];maximum:number;time:string;expires_at:string}):Promise<DailyStatus> {return client.call<DailyStatus>("daily.save",params);}
export async function changeDailyAuthorization(id:string,state:string,confirmed=false):Promise<DailyStatus> {return invoke("change_daily_authorization",{id,state,confirmed});}
export async function runDailyDelivery(force=false):Promise<DailyStatus|{claimed:false;reason:string}> {return invoke("run_daily_delivery",{force});}
export async function closeInterruptedDaily(id:string):Promise<DailyStatus> {return invoke("close_interrupted_daily",{id});}

export async function previewDailyPdf(runId:string):Promise<{meta:{correlation_id:string};pdf_base64:string;pdf_sha256:string}> {return client.call("daily.preview",{run_id:runId});}

export type MaterialDocumentRef = {material_id:string;document_id:string;sha256:string;label:string};
export type MaterialDocument = Omit<MaterialDocumentRef,'material_id'> & {char_count:number;text?:string};
export async function listMaterialDocuments(materialId:string,query=''):Promise<{meta:{correlation_id:string};items:MaterialDocument[];total:number;matched:number}> {return client.call('evidence.listMaterialDocuments',{material_id:materialId,query});}
export async function readMaterialDocument(materialId:string,documentId:string):Promise<MaterialDocument & {meta:{correlation_id:string};text:string}> {return client.call('evidence.readMaterialDocument',{material_id:materialId,document_id:documentId});}

export async function reviewCareerProfile(revision:string):Promise<ProfileGetResult>{return client.call("profile.review",{expected_revision:revision,confirmed:true});}
export async function autoLinkEvidence(expectedRevision: string, apply = true): Promise<ProfileAutoLinkResult> {
  return client.call<ProfileAutoLinkResult>("profile.autoLinkEvidence", { expected_revision: expectedRevision, apply });
}

export async function authorizeSingleLiepinPdf(runId: string): Promise<NativePdfPreparation> {
  return client.call<NativePdfPreparation>("run.agent.authorizeSinglePdfDelivery", {run_id:runId,confirmed:true});
}

export async function scanMaterialReference(rootId: string, relpath: string): Promise<MaterialReferenceScanResult> {
  return client.call<MaterialReferenceScanResult>("material.reference.scan", {root_id: rootId, relpath});
}
export async function createMaterialReference(rootId: string, relpath: string, label: string): Promise<MaterialReferenceCreateResult> {
  return client.call<MaterialReferenceCreateResult>("material.reference.create", {root_id: rootId, relpath, label});
}
export async function checkMaterialReference(materialId: string): Promise<MaterialReferenceStatusResult> {
  return client.call<MaterialReferenceStatusResult>("material.reference.status", {material_id: materialId});
}
export async function refreshMaterialReference(materialId: string): Promise<MaterialReferenceRefreshResult> {
  return client.call<MaterialReferenceRefreshResult>("material.reference.refresh", {material_id: materialId, confirmed: true});
}
export async function removeMaterialReference(materialId: string): Promise<MaterialReferenceRemoveResult> {
  return client.call<MaterialReferenceRemoveResult>("material.reference.remove", {material_id: materialId, confirmed: true});
}
export async function updateMaterialSourceRoots(roots: MaterialSourceRoot[]): Promise<SettingsUpdateResult> {
  return client.call<SettingsUpdateResult>("settings.update", {section: "material_source_roots", payload: roots});
}
