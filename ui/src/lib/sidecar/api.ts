import { RpcClient } from "@/lib/rpc/client";
import { TauriRpcTransport } from "@/lib/rpc/tauri-transport";
import type {
  EvidenceGetResult,
  EvidenceListResult,
  HandshakeResult,
  JobProfilesFilters,
  JobProfilesListResult,
  OverviewGetResult,
  PingResult,
  SettingsGetResult,
  SettingsUpdateResult,
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

export async function listEvidence(): Promise<EvidenceListResult> {
  return client.call<EvidenceListResult>("evidence.list", {
    cursor: null,
    page_size: 20,
    sort: { field: "updated_at", order: "desc" },
    filters: {
      query: "",
      status: null,
      role: null,
      tags: [],
      date_range: null,
    },
  });
}

export async function getEvidence(evidenceId: string): Promise<EvidenceGetResult> {
  return client.call<EvidenceGetResult>("evidence.get", {
    evidence_id: evidenceId,
  });
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
    section: "delivery_settings",
    payload: { delivery_mode, batch_review },
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

export function shutdownSidecar(): void {
  client.close();
}
