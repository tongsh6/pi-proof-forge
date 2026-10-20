import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  FolderOpen,
  KeyRound,
  Link2,
  RefreshCw,
  Save,
  Server,
  Settings2,
  Sparkles,
  ShieldCheck,
  Wifi,
  XCircle,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import { getErrorMessage } from "@/lib/errors";
import { confirmAction, notify } from "@/lib/ui";
import {
  checkLlmConnection,
  checkMaterialReference,
  clearLlmApiKey,
  createMaterialReference,
  getLiepinResume,
  getSettings,
  listEvidenceMaterialSources,
  openLiepinAuthorization,
  refreshMaterialReference,
  removeMaterialReference,
  scanMaterialReference,
  updateLiepinCredential,
  updateEvidenceInferenceSetting,
  updateLlmConfig,
  updateMaterialSourceRoots,
} from "@/lib/sidecar/api";
import type {
  ChannelConfig,
  LiepinAuthState,
  MaterialReferenceScanResult,
  MaterialSourceItem,
  LlmConfig,
  LlmConnectionCheckResult,
  SettingsGetResult,
} from "@/lib/sidecar/types";

type LoadState = "loading" | "ready" | "error";
type SectionId = "channels" | "materialSources" | "evidenceInference" | "llm";
type LlmSaveState = "idle" | "saving" | "saved";
type LlmCheckState = "idle" | "checking" | "checked";

type LlmForm = {
  provider: string;
  model: string;
  base_url: string;
  api_key: string;
  timeout: string;
  temperature: string;
  thinking_enabled: boolean;
  thinking_effort: string;
};

type StatusTone = "success" | "warning" | "muted" | "error";
const LLM_PROVIDER_DEFAULTS: Record<
  string,
  Pick<LlmForm, "model" | "base_url" | "api_key">
> = {
  lm_studio: {
    model: "local-model",
    base_url: "http://127.0.0.1:1234/v1",
    api_key: "lm-studio",
  },
  openai: {
    model: "gpt-4",
    base_url: "https://api.openai.com/v1",
    api_key: "",
  },
  openai_compatible: {
    model: "",
    base_url: "",
    api_key: "",
  },
  deepseek: {
    model: "deepseek-flash",
    base_url: "https://api.deepseek.com",
    api_key: "",
  },
};

const LLM_PROVIDER_OPTIONS = [
  { id: "lm_studio", label: "LM Studio", hintKey: "providerLmStudioHint" },
  { id: "openai", label: "OpenAI", hintKey: "providerOpenAiHint" },
  { id: "deepseek", label: "DeepSeek", hintKey: "providerDeepSeekHint" },
  {
    id: "openai_compatible",
    label: "OpenAI Compatible",
    hintKey: "providerCompatibleHint",
  },
] as const;

const LLM_THINKING_EFFORTS = [
  { value: "low", labelKey: "effortLow" },
  { value: "high", labelKey: "effortHigh" },
  { value: "max", labelKey: "effortMax" },
] as const;

const LLM_FIELD_INPUT_CLASS =
  "w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none transition-colors focus:border-accent";

const LLM_FIELD_LABEL_CLASS = "text-xs font-medium text-text-secondary";

function formatNullable(value: string | null | undefined): string {
  return value && value.trim() ? value : "--";
}

function formatShortTimestamp(value: string | null | undefined): string {
  if (!value || !value.trim()) return "";
  return value.replace("T", " ").replace("Z", "").slice(0, 16);
}

function toLlmForm(config: LlmConfig | null): LlmForm {
  const provider = config?.provider ?? "lm_studio";
  const defaults = LLM_PROVIDER_DEFAULTS[provider] ?? LLM_PROVIDER_DEFAULTS.lm_studio;
  return {
    provider,
    model: config?.model ?? defaults.model,
    base_url: config?.base_url ?? defaults.base_url,
    api_key: "",
    timeout: String(config?.timeout ?? 60),
    temperature: String(config?.temperature ?? 0.2),
    thinking_enabled: config?.thinking_enabled ?? false,
    thinking_effort: config?.thinking_effort ?? "high",
  };
}

function applyProviderDefaults(
  current: LlmForm,
  nextProvider: string
): LlmForm {
  const nextDefaults =
    LLM_PROVIDER_DEFAULTS[nextProvider] ?? LLM_PROVIDER_DEFAULTS.openai_compatible;

  return {
    ...current,
    provider: nextProvider,
    model: nextDefaults.model,
    base_url: nextDefaults.base_url,
    api_key: nextProvider === current.provider ? current.api_key : "",
    thinking_enabled: current.thinking_enabled,
    thinking_effort: current.thinking_effort,
  };
}

function llmPayloadFromForm(form: LlmForm): {
  provider: string;
  model?: string;
  base_url?: string;
  api_key?: string;
  timeout: number;
  temperature: number;
  thinking_enabled?: boolean;
  thinking_effort?: string;
} {
  const payload: {
    provider: string;
    model?: string;
    base_url?: string;
    api_key?: string;
    timeout: number;
    temperature: number;
    thinking_enabled?: boolean;
    thinking_effort?: string;
  } = {
    provider: form.provider.trim(),
    timeout: Number(form.timeout),
    temperature: Number(form.temperature),
  };
  if (form.provider === "deepseek") {
    payload.thinking_enabled = form.thinking_enabled;
    payload.thinking_effort = form.thinking_effort;
  }
  const model = form.model.trim();
  if (model) {
    payload.model = model;
  }
  const baseUrl = form.base_url.trim();
  if (baseUrl) {
    payload.base_url = baseUrl;
  }
  const apiKey = form.api_key.trim();
  if (apiKey) {
    payload.api_key = apiKey;
  }
  return payload;
}

function statusTone(value: string): StatusTone {
  const normalized = value.toLowerCase();
  if (
    normalized === "configured" ||
    normalized === "enabled" ||
    normalized === "ready" ||
    normalized === "pass" ||
    normalized === "ok" ||
    value === "已配置（掩码）"
  ) {
    return "success";
  }
  if (
    normalized === "missing" ||
    normalized === "unknown" ||
    normalized === "not configured" ||
    normalized === "blocked" ||
    normalized.includes("missing") ||
    value === "未配置"
  ) {
    return "warning";
  }
  if (
    normalized === "disabled" ||
    normalized === "fail" ||
    normalized === "failed" ||
    normalized === "error"
  ) {
    return "error";
  }
  return "muted";
}

function statusLabel(value: string, t: (key: string) => string): string {
  const normalized = value.toLowerCase();
  if (value === "已配置（掩码）") {
    return t("pages.systemSettings.secretConfigured");
  }
  if (value === "未配置") return t("pages.systemSettings.secretMissing");
  if (normalized === "enabled") return t("pages.systemSettings.status.enabled");
  if (normalized === "disabled") return t("pages.systemSettings.status.disabled");
  if (normalized === "configured") return t("pages.systemSettings.status.configured");
  if (normalized === "missing") return t("pages.systemSettings.status.missing");
  if (normalized === "unknown") return t("pages.systemSettings.status.unknown");
  if (normalized === "ready") return t("pages.systemSettings.status.ready");
  if (normalized === "blocked") return t("pages.systemSettings.status.blocked");
  if (normalized === "fail" || normalized === "failed") {
    return t("pages.systemSettings.status.failed");
  }
  if (normalized === "error") return t("pages.systemSettings.status.error");
  if (normalized === "not configured") {
    return t("pages.systemSettings.status.notConfigured");
  }
  return value;
}

function statusClassName(tone: StatusTone): string {
  if (tone === "success") {
    return "border-success/40 bg-success/10 text-success";
  }
  if (tone === "warning") {
    return "border-warning/40 bg-warning/10 text-warning";
  }
  if (tone === "error") {
    return "border-error/40 bg-error/10 text-error";
  }
  return "border-border bg-bg-primary text-text-secondary";
}

function StatusChip({ value }: { value: string }) {
  const { t } = useTranslation();
  const tone = statusTone(value);
  const Icon =
    tone === "success" ? CheckCircle2 : tone === "error" ? XCircle : AlertTriangle;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-chip border px-2.5 py-1 text-xs font-medium ${statusClassName(tone)}`}
    >
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      {statusLabel(value, t)}
    </span>
  );
}

function FieldCard({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string | number;
  mono?: boolean;
}) {
  return (
    <div className="min-h-[58px] rounded-card border border-border bg-bg-primary/70 p-3">
      <p className="text-xs uppercase tracking-[0.16em] text-text-muted">{label}</p>
      <p
        className={`mt-2 break-all text-sm text-text-primary ${
          mono ? "font-mono" : "font-medium"
        }`}
      >
        {value}
      </p>
    </div>
  );
}

function ChannelCard({
  channel,
  fallbackLabel,
  labels,
}: {
  channel: ChannelConfig;
  fallbackLabel: string;
  labels: {
    priority: string;
    fallback: string;
    credential: string;
    lastCheck: string;
    lastSuccess: string;
    lastError: string;
  };
}) {
  const fallback = channel.fallback_to ? channel.fallback_to : fallbackLabel;
  return (
    <article className="rounded-card border border-border bg-bg-primary/70 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Server className="h-4 w-4 text-accent" aria-hidden="true" />
            <h3 className="text-sm font-semibold text-text-primary">{channel.label}</h3>
          </div>
          <p className="mt-1 font-mono text-xs text-text-muted">{channel.id}</p>
        </div>
        <StatusChip value={channel.enabled ? "enabled" : "disabled"} />
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <FieldCard label={labels.priority} value={channel.priority} />
        <FieldCard label={labels.fallback} value={fallback} mono />
        <div className="min-h-[58px] rounded-card border border-border bg-bg-panel/60 p-3">
          <p className="text-xs uppercase tracking-[0.16em] text-text-muted">
            {labels.credential}
          </p>
          <div className="mt-2">
            <StatusChip value={channel.credential_status} />
          </div>
        </div>
        <div className="min-h-[58px] rounded-card border border-border bg-bg-panel/60 p-3">
          <p className="text-xs uppercase tracking-[0.16em] text-text-muted">
            {labels.lastCheck}
          </p>
          <div className="mt-2">
            <StatusChip value={channel.last_check_status} />
          </div>
        </div>
      </div>

      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <FieldCard
          label={labels.lastSuccess}
          value={formatNullable(channel.last_success_at)}
          mono
        />
        <FieldCard
          label={labels.lastError}
          value={formatNullable(channel.last_error)}
          mono
        />
      </div>
    </article>
  );
}

export function SystemSettingsPage() {
  const { t } = useTranslation();
  const [settings, setSettings] = useState<SettingsGetResult | null>(null);
  const [newRootPath, setNewRootPath] = useState("");
  const [newRootLabel, setNewRootLabel] = useState("");
  const [rootsBusy, setRootsBusy] = useState(false);
  const [inferenceToggleBusy, setInferenceToggleBusy] = useState(false);
  const [rootsError, setRootsError] = useState("");
  const [referencedItems, setReferencedItems] = useState<MaterialSourceItem[]>([]);
  const [referencesLoading, setReferencesLoading] = useState(false);
  const [referenceRootId, setReferenceRootId] = useState("");
  const [referenceRelpath, setReferenceRelpath] = useState("");
  const [referenceLabel, setReferenceLabel] = useState("");
  const [referenceScan, setReferenceScan] = useState<MaterialReferenceScanResult | null>(null);
  const [referenceBusy, setReferenceBusy] = useState(false);
  const [referenceError, setReferenceError] = useState("");
  const [referenceStatus, setReferenceStatus] = useState<Record<string, string>>({});
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [searchParams] = useSearchParams();
  // 总览“配置模型”等入口可用 ?section=llm 直接打开模型分组。
  const [activeSection, setActiveSection] = useState<SectionId>(
    searchParams.get("section") === "llm"
      ? "llm"
      : searchParams.get("section") === "materialSources"
        ? "materialSources"
        : searchParams.get("section") === "evidenceInference"
          ? "evidenceInference"
          : "channels");
  const [llmForm, setLlmForm] = useState<LlmForm>(() => toLlmForm(null));
  const [llmSaveState, setLlmSaveState] = useState<LlmSaveState>("idle");
  const [llmCheckState, setLlmCheckState] = useState<LlmCheckState>("idle");
  const [llmConnection, setLlmConnection] =
    useState<LlmConnectionCheckResult | null>(null);
  const [llmError, setLlmError] = useState<string | null>(null);
  const [liepinToken, setLiepinToken] = useState("");
  const [liepinAction, setLiepinAction] = useState<"set" | "check" | "clear" | "resume" | null>(null);
  const [liepinError, setLiepinError] = useState<string | null>(null);
  const [liepinResume, setLiepinResume] = useState<string | null>(null);

  const loadSettings = useCallback(async () => {
    setLoadState("loading");
    setError(null);
    setLiepinToken("");
    setLiepinResume(null);
    setLiepinError(null);

    try {
      const result = await getSettings();
      setSettings(result);
      setLlmForm(toLlmForm(result.llm_config));
      setLoadState("ready");
    } catch (nextError) {
      setSettings(null);
      setLoadState("error");
      setError(getErrorMessage(nextError));
    }
  }, []);

  const handleInferenceToggle = useCallback(async (enabled: boolean) => {
    setInferenceToggleBusy(true);
    try {
      await updateEvidenceInferenceSetting(enabled);
      await loadSettings();
      notify("success", t("toasts.settings.evidenceInferenceSaved"));
    } catch (reason) {
      notify("error", getErrorMessage(reason));
    } finally {
      setInferenceToggleBusy(false);
    }
  }, [loadSettings, t]);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  const loadReferencedItems = useCallback(async () => {
    setReferencesLoading(true);
    try {
      const result = await listEvidenceMaterialSources();
      setReferencedItems(result.items.filter((item) => item.source_mode === "referenced"));
    } catch (reason) {
      setReferenceError(getErrorMessage(reason));
    } finally {
      setReferencesLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeSection !== "materialSources") return;
    void loadReferencedItems();
  }, [activeSection, loadReferencedItems]);

  useEffect(() => {
    const roots = settings?.material_source_roots ?? [];
    if (!referenceRootId && roots.length > 0) setReferenceRootId(roots[0].id);
  }, [referenceRootId, settings]);

  const handleReferenceScan = useCallback(async () => {
    setReferenceBusy(true);
    setReferenceError("");
    setReferenceScan(null);
    try {
      setReferenceScan(await scanMaterialReference(referenceRootId, referenceRelpath.trim()));
    } catch (reason) {
      setReferenceError(getErrorMessage(reason));
    } finally {
      setReferenceBusy(false);
    }
  }, [referenceRelpath, referenceRootId]);

  const handleReferenceCreate = useCallback(async () => {
    if (!referenceScan || !referenceLabel.trim()) return;
    setReferenceBusy(true);
    setReferenceError("");
    try {
      await createMaterialReference(referenceRootId, referenceRelpath.trim(), referenceLabel.trim());
      setReferenceScan(null);
      setReferenceRelpath("");
      setReferenceLabel("");
      await loadReferencedItems();
      notify("success", t("toasts.evidence.materialReferenced"));
    } catch (reason) {
      setReferenceError(getErrorMessage(reason));
    } finally {
      setReferenceBusy(false);
    }
  }, [loadReferencedItems, referenceLabel, referenceRelpath, referenceRootId, referenceScan, t]);

  const handleReferenceCheck = useCallback(async (materialId: string) => {
    try {
      const result = await checkMaterialReference(materialId);
      setReferenceStatus((current) => ({
        ...current,
        [materialId]: result.status === "ok"
          ? t("pages.evidence.materialSources.referenceStatusOk")
          : t("pages.evidence.materialSources.referenceStatusChanged", {
              changed: result.changed.length, missing: result.missing.length, added: result.added.length,
            }),
      }));
    } catch (reason) {
      notify("error", getErrorMessage(reason));
    }
  }, [t]);

  const handleReferenceRefresh = useCallback(async (materialId: string) => {
    const approved = await confirmAction({
      title: t("pages.evidence.materialSources.referenceRefresh"),
      description: t("pages.evidence.materialSources.referenceRefreshConfirm"),
      confirmLabel: t("common.confirm"),
    });
    if (!approved) return;
    try {
      await refreshMaterialReference(materialId);
      await loadReferencedItems();
      setReferenceStatus((current) => {
        const next = { ...current };
        delete next[materialId];
        return next;
      });
      notify("success", t("toasts.evidence.materialRefreshed"));
    } catch (reason) {
      notify("error", getErrorMessage(reason));
    }
  }, [loadReferencedItems, t]);

  const handleReferenceRemove = useCallback(async (materialId: string) => {
    const approved = await confirmAction({
      title: t("pages.evidence.materialSources.referenceRemove"),
      description: t("pages.evidence.materialSources.referenceRemoveConfirm"),
      confirmLabel: t("common.confirm"),
      tone: "danger",
    });
    if (!approved) return;
    try {
      await removeMaterialReference(materialId);
      await loadReferencedItems();
      notify("success", t("toasts.evidence.materialReferenceRemoved"));
    } catch (reason) {
      notify("error", getErrorMessage(reason));
    }
  }, [loadReferencedItems, t]);

  const handleAddRoot = useCallback(async () => {
    if (!settings || !newRootPath.trim()) return;
    setRootsBusy(true);
    setRootsError("");
    try {
      await updateMaterialSourceRoots([
        ...(settings.material_source_roots ?? []),
        { id: "", label: newRootLabel.trim(), path: newRootPath.trim() },
      ]);
      setNewRootPath("");
      setNewRootLabel("");
      await loadSettings();
      notify("success", t("toasts.settings.materialRootSaved"));
    } catch (reason) {
      setRootsError(getErrorMessage(reason));
    } finally {
      setRootsBusy(false);
    }
  }, [settings, newRootPath, newRootLabel, loadSettings, t]);

  const handleRemoveRoot = useCallback(async (rootId: string) => {
    if (!settings) return;
    const approved = await confirmAction({
      title: t("pages.systemSettings.materialSources.remove"),
      description: t("pages.systemSettings.materialSources.removeConfirm"),
      confirmLabel: t("common.confirm"),
      tone: "danger",
    });
    if (!approved) return;
    setRootsBusy(true);
    setRootsError("");
    try {
      await updateMaterialSourceRoots((settings.material_source_roots ?? []).filter((root) => root.id !== rootId));
      await loadSettings();
      notify("success", t("toasts.settings.materialRootRemoved"));
    } catch (reason) {
      setRootsError(getErrorMessage(reason));
    } finally {
      setRootsBusy(false);
    }
  }, [settings, loadSettings, t]);

  const fallbackOrder = useMemo(() => {
    if (!settings || settings.channels.length === 0) {
      return "--";
    }
    return [...settings.channels]
      .sort((left, right) => left.priority - right.priority)
      .map((channel) => channel.id)
      .join(" / ");
  }, [settings]);

  const connectionSummary = useMemo(() => {
    if (!settings || settings.channels.length === 0) {
      return "unknown";
    }
    const failing = settings.channels.find(
      (channel) => channel.last_check_status.toLowerCase() === "fail"
    );
    if (failing) {
      return `${failing.id}: ${failing.last_error || t("pages.systemSettings.status.failed")}`;
    }
    const missing = settings.channels.find(
      (channel) => channel.credential_status.toLowerCase() === "missing"
    );
    return missing
      ? `${missing.id}: ${t("pages.systemSettings.status.missingCredential")}`
      : "ready";
  }, [settings, t]);

  const detectedModels = useMemo(() => {
    return llmConnection?.models ?? [];
  }, [llmConnection]);

  const configuredProviders = settings?.llm_config.configured_providers ?? [];
  const providerKeyConfigured = (provider: string): boolean => {
    if (provider === "lm_studio") {
      return true;
    }
    if (configuredProviders.includes(provider)) {
      return true;
    }
    return (
      settings?.llm_config.provider === provider &&
      Boolean(settings.llm_config.api_key.configured)
    );
  };
  const providerKeySource = (provider: string): string => {
    if (settings?.llm_config.provider === provider) {
      return (
        settings.llm_config.api_key.source ??
        (settings.llm_config.api_key.configured ? "saved" : "none")
      );
    }
    if (configuredProviders.includes(provider)) {
      return "saved";
    }
    return provider === "lm_studio" ? "legacy" : "none";
  };
  const canClearProviderKey = configuredProviders.includes(llmForm.provider);
  const keyStatusLabel = (provider: string): string => {
    const source = providerKeySource(provider);
    if (source === "saved") {
      return t("pages.systemSettings.llm.keySaved");
    }
    if (source === "environment") {
      return t("pages.systemSettings.llm.keyEnvironment");
    }
    if (source === "legacy") {
      return t("pages.systemSettings.llm.keyLocalPlaceholder");
    }
    if (source === "storage_error") {
      return t("pages.systemSettings.llm.keyStorageError");
    }
    return t("pages.systemSettings.llm.keyMissing");
  };
  const providerStatusDot = (provider: string): string => {
    if (!providerKeyConfigured(provider)) {
      return "bg-text-muted/40";
    }
    return providerKeySource(provider) === "environment" ? "bg-warning" : "bg-success";
  };
  const keyStatusDot = (): string => {
    if (!providerKeyConfigured(llmForm.provider)) {
      return "bg-text-muted/40";
    }
    return providerKeySource(llmForm.provider) === "environment"
      ? "bg-warning"
      : "bg-success";
  };
  const llmConnectionSummary =
    llmCheckState === "checking"
      ? t("pages.systemSettings.llm.checking")
      : llmConnection
        ? `${llmConnection.message} · ${t("pages.systemSettings.llm.modelCount", {
            count: llmConnection.model_count,
          })}`
        : t("pages.systemSettings.llm.notChecked");

  const llmDirty = settings
    ? JSON.stringify(llmForm) !== JSON.stringify(toLlmForm(settings.llm_config))
    : false;

  // 有未保存的模型配置修改时，重新加载前先确认。
  const handleReload = useCallback(async () => {
    if (llmDirty) {
      const confirmed = await confirmAction({
        title: t("common.discardTitle"),
        description: t("common.discardDescription"),
        confirmLabel: t("common.discard"),
        tone: "danger",
      });
      if (!confirmed) return;
    }
    await loadSettings();
  }, [llmDirty, loadSettings, t]);

  const handleSaveLlmConfig = useCallback(async () => {
    setLlmSaveState("saving");
    setLlmError(null);
    try {
      await updateLlmConfig(llmPayloadFromForm(llmForm));
      const nextSettings = await getSettings();
      setSettings(nextSettings);
      setLlmForm(toLlmForm(nextSettings.llm_config));
      setLlmConnection(null);
      setLlmCheckState("idle");
      setLlmSaveState("saved");
      notify("success", t("toasts.systemSettings.saved"));
    } catch (nextError) {
      setLlmSaveState("idle");
      setLlmError(getErrorMessage(nextError));
    }
  }, [llmForm]);

  const handleProviderChange = useCallback(
    (nextProvider: string) => {
      if (nextProvider === llmForm.provider) return;
      setLlmConnection(null);
      setLlmCheckState("idle");
      setLlmForm((current) => applyProviderDefaults(current, nextProvider));
    },
    [llmForm.provider]
  );

  const handleClearLlmApiKey = useCallback(async () => {
    const confirmed = await confirmAction({
      title: t("confirmations.systemSettings.clearLlmKey.title"),
      description: t("confirmations.systemSettings.clearLlmKey.description", {
        provider: llmForm.provider,
      }),
      confirmLabel: t("confirmations.systemSettings.clearLlmKey.confirm"),
      tone: "danger",
    });
    if (!confirmed) return;
    setLlmError(null);
    try {
      await clearLlmApiKey(llmForm.provider);
      const nextSettings = await getSettings();
      setSettings(nextSettings);
      setLlmForm((current) => ({ ...current, api_key: "" }));
      setLlmConnection(null);
      setLlmCheckState("idle");
      notify("success", t("toasts.systemSettings.llmKeyCleared"));
    } catch (nextError) {
      setLlmError(getErrorMessage(nextError));
    }
  }, [llmForm.provider, t]);

  const applyLiepinAuth = useCallback((auth: LiepinAuthState) => {
    setSettings((current) => current ? { ...current, liepin_api: auth } : current);
    if (auth.state !== "valid") setLiepinResume(null);
  }, []);

  const handleLiepinCredential = useCallback(async (action: "set" | "check" | "clear") => {
    if (action === "set" && !liepinToken.trim()) return;
    if (action === "clear") {
      const confirmed = await confirmAction({
        title: t("confirmations.systemSettings.clearCredential.title"),
        description: t("confirmations.systemSettings.clearCredential.description"),
        confirmLabel: t("confirmations.systemSettings.clearCredential.confirm"),
        tone: "danger",
      });
      if (!confirmed) return;
    }
    setLiepinAction(action);
    setLiepinError(null);
    setLiepinResume(null);
    const payload = action === "set"
      ? { action, token: liepinToken.trim() } as const
      : { action };
    setLiepinToken("");
    try {
      const result = await updateLiepinCredential(payload);
      applyLiepinAuth(result.auth);
      if (result.auth.code !== "CREDENTIAL_STORAGE_ERROR") {
        if (action === "set") notify("success", t("toasts.systemSettings.credentialSaved"));
        if (action === "clear") notify("success", t("toasts.systemSettings.credentialCleared"));
      }
    } catch {
      setLiepinError(t("pages.systemSettings.liepinApi.requestError"));
    } finally {
      setLiepinAction(null);
    }
  }, [applyLiepinAuth, liepinToken, t]);

  const handleLiepinResume = useCallback(async () => {
    setLiepinAction("resume");
    setLiepinError(null);
    setLiepinResume(null);
    try {
      const result = await getLiepinResume();
      applyLiepinAuth(result.auth);
      if (result.status === "pass") {
        setLiepinResume(result.resume_text);
      } else {
        setLiepinError(t(`pages.systemSettings.liepinApi.codes.${result.code}`, {
          defaultValue: t("pages.systemSettings.liepinApi.requestBlocked"),
        }));
      }
    } catch {
      setLiepinError(t("pages.systemSettings.liepinApi.requestError"));
    } finally {
      setLiepinAction(null);
    }
  }, [applyLiepinAuth, t]);

  const handleLiepinAuthorization = useCallback(async () => {
    setLiepinError(null);
    try {
      await openLiepinAuthorization();
    } catch {
      setLiepinError(t("pages.systemSettings.liepinApi.authorizationFailed"));
    }
  }, [t]);

  const handleCheckLlmConnection = useCallback(async () => {
    setLlmCheckState("checking");
    setLlmError(null);
    setLlmConnection(null);
    try {
      const result = await checkLlmConnection(llmPayloadFromForm(llmForm));
      setLlmConnection(result);
      if (result.models.length > 0 && !llmForm.model.trim()) {
        setLlmForm((current) => ({
          ...current,
          model: result.models[0],
        }));
      }
      setLlmCheckState("checked");
      if (result.status === "pass") {
        notify("success", t("toasts.systemSettings.connectionOk"));
      } else {
        notify(
          "warning",
          t("toasts.systemSettings.connectionBlocked"),
          result.message
        );
      }
    } catch (nextError) {
      setLlmCheckState("idle");
      setLlmConnection(null);
      setLlmError(getErrorMessage(nextError));
    }
  }, [llmForm, t]);

  // ⌘R 重新加载（有草稿时先确认丢弃），⌘S 保存模型配置。
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.addEventListener !== "function") return;
    const onRefresh = () => void handleReload();
    const onSave = () => { if (activeSection === "llm" && llmSaveState !== "saving") void handleSaveLlmConfig(); };
    window.addEventListener("pipf:refresh", onRefresh);
    window.addEventListener("pipf:save", onSave);
    return () => {
      window.removeEventListener("pipf:refresh", onRefresh);
      window.removeEventListener("pipf:save", onSave);
    };
  }, [handleReload, handleSaveLlmConfig, activeSection, llmSaveState]);

  return (
    <div className="space-y-6">
      <header className="page-header">
        <div>
          <h1>{t("pages.systemSettings.title")}</h1>
          <p className="page-subtitle">{t("pages.systemSettings.subtitle")}</p>
        </div>
        <div className="page-actions">
          <button
            className="page-icon-button"
            onClick={() => void handleReload()}
            disabled={liepinAction !== null || loadState === "loading"}
            type="button"
            title={t("common.refreshShortcut")}
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            <span className="sr-only">{t("common.refresh")}</span>
          </button>
          <button
            className="inline-flex items-center gap-2 rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={activeSection !== "llm" || llmSaveState === "saving"}
            title={activeSection !== "llm" ? t("reasons.systemSettings.channelsNoSave") : t("common.saveShortcut")}
            onClick={() => void handleSaveLlmConfig()}
            type="button"
          >
            <Save className="h-4 w-4" aria-hidden="true" />
            {llmSaveState === "saving"
              ? t("pages.systemSettings.llm.saving")
              : t("pages.systemSettings.save")}
          </button>
        </div>
      </header>

      {loadState === "loading" ? (
        <section className="rounded-panel border border-border bg-bg-panel p-6 text-text-secondary shadow-[var(--shadow-panel)]">
          {t("common.loading")}
        </section>
      ) : null}

      {loadState === "error" ? (
        <section className="rounded-panel border border-error/50 bg-bg-panel p-6 shadow-[var(--shadow-panel)]">
          <p className="text-sm font-medium text-error">{t("common.error")}</p>
          <p className="mt-2 text-sm text-text-secondary">{error}</p>
        </section>
      ) : null}

      {loadState === "ready" && settings ? (
        <div className="grid gap-6 xl:grid-cols-[220px_minmax(0,1fr)]">
          <aside className="rounded-panel border border-border bg-bg-panel p-4 shadow-[var(--shadow-panel)]">
            <nav className="space-y-2" aria-label={t("pages.systemSettings.title")}>
              {(["channels", "materialSources", "evidenceInference", "llm"] as SectionId[]).map((section) => {
                const Icon = section === "channels" ? Wifi : section === "materialSources" ? FolderOpen : section === "evidenceInference" ? Sparkles : Settings2;
                const isActive = section === activeSection;
                return (
                  <button
                    key={section}
                    className={`flex h-11 w-full items-center gap-2 rounded-card border px-3 text-left text-sm font-medium transition-colors ${
                      isActive
                        ? "border-accent bg-accent/20 text-text-primary"
                        : "border-transparent bg-bg-primary/70 text-text-secondary hover:border-border hover:bg-bg-hover"
                    }`}
                    onClick={() => setActiveSection(section)}
                    type="button"
                  >
                    <Icon className="h-4 w-4" aria-hidden="true" />
                    {t(`pages.systemSettings.nav.${section}`)}
                  </button>
                );
              })}
            </nav>
          </aside>

          <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
            {activeSection === "channels" ? (
              <div className="space-y-5">
                <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border pb-4">
                  <div>
                    <h2 className="text-lg font-semibold text-text-primary">
                      {t("pages.systemSettings.channels.title")}
                    </h2>
                    <p className="mt-1 text-sm text-text-secondary">
                      {t("pages.systemSettings.channels.subtitle")}
                    </p>
                  </div>
                  <StatusChip value={connectionSummary} />
                </div>

                <article className="space-y-4 rounded-card border border-accent/40 bg-bg-primary/70 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h3 className="flex items-center gap-2 text-sm font-semibold text-text-primary">
                        <KeyRound className="h-4 w-4 text-accent" aria-hidden="true" />
                        {t("pages.systemSettings.liepinApi.title")}
                      </h3>
                      <p className="mt-2 text-sm text-text-secondary">{t("pages.systemSettings.liepinApi.scope")}</p>
                    </div>
                    <span className={`rounded-chip border px-2.5 py-1 text-xs ${statusClassName(
                      settings.liepin_api?.state === "valid" ? "success" :
                        settings.liepin_api?.state === "invalid" || settings.liepin_api?.state === "error" ? "error" : "warning"
                    )}`}>
                      {t(`pages.systemSettings.liepinApi.states.${settings.liepin_api?.state ?? "unconfigured"}`)}
                    </span>
                  </div>
                  <p className="text-sm text-text-secondary">{t("pages.systemSettings.liepinApi.storageHint")}</p>
                  <p className="break-all text-xs text-text-muted select-text">
                    {t("pages.systemSettings.liepinApi.storagePath")}: {formatNullable(settings.liepin_api?.storage_path)}
                  </p>
                  <button className="inline-flex items-center gap-2 text-sm text-accent underline" type="button" onClick={() => void handleLiepinAuthorization()}>
                    <Link2 className="h-4 w-4" aria-hidden="true" />
                    {t("pages.systemSettings.liepinApi.authorization")}
                  </button>
                  <p className="break-all text-xs text-text-muted select-text">https://www.liepin.com/mcp/auth</p>
                  <label className="block text-sm text-text-primary">
                    {t("pages.systemSettings.liepinApi.token")}
                    <input
                      autoComplete="off"
                      className="mt-2 w-full rounded-card border border-border bg-bg-hover px-3 py-2 outline-none focus:border-accent"
                      disabled={liepinAction !== null}
                      onChange={(event) => setLiepinToken(event.target.value)}
                      placeholder={t("pages.systemSettings.liepinApi.tokenPlaceholder")}
                      spellCheck={false}
                      type="password"
                      value={liepinToken}
                    />
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {(["set", "check", "clear"] as const).map((action) => (
                      <button
                        key={action}
                        className={action === "clear"
                          ? "rounded-card border border-error/60 px-3 py-2 text-sm text-error hover:bg-error/10 disabled:cursor-not-allowed disabled:opacity-50"
                          : "rounded-card border border-accent px-3 py-2 text-sm text-accent hover:bg-accent/10 disabled:cursor-not-allowed disabled:opacity-50"}
                        disabled={liepinAction !== null || (action === "set"
                          ? !liepinToken.trim()
                          : action === "clear"
                            ? !(settings.liepin_api?.configured || settings.liepin_api?.saved || settings.liepin_api?.code === "CREDENTIAL_STORAGE_ERROR")
                            : !settings.liepin_api?.configured)}
                        onClick={() => void handleLiepinCredential(action)}
                        type="button"
                      >
                        {t(`pages.systemSettings.liepinApi.${liepinAction === action ? "working" : action}`)}
                      </button>
                    ))}
                    <button
                      className="rounded-card border border-border px-3 py-2 text-sm text-text-primary hover:bg-bg-hover disabled:opacity-50"
                      disabled={liepinAction !== null || !settings.liepin_api?.configured}
                      onClick={() => void handleLiepinResume()}
                      type="button"
                    >
                      {t(`pages.systemSettings.liepinApi.${liepinAction === "resume" ? "working" : "readResume"}`)}
                    </button>
                  </div>
                  <p className="text-xs text-text-muted">
                    {t("pages.systemSettings.liepinApi.lastChecked")}: {formatNullable(settings.liepin_api?.last_checked_at)}
                  </p>
                  {settings.liepin_api?.last_error || settings.liepin_api?.code === "CREDENTIAL_STORAGE_ERROR" ? (
                    <p className="text-sm text-error" role="alert">
                      {settings.liepin_api.last_error || t(`pages.systemSettings.liepinApi.codes.${settings.liepin_api.code}`, {
                        defaultValue: t("pages.systemSettings.liepinApi.requestBlocked"),
                      })}
                    </p>
                  ) : null}
                  {liepinError ? <p className="text-sm text-error" role="alert">{liepinError}</p> : null}
                  {liepinResume !== null ? (
                    <details className="rounded-card border border-border p-3">
                      <summary className="cursor-pointer text-sm text-text-primary">{t("pages.systemSettings.liepinApi.resumePreview")}</summary>
                      <p className="mt-2 text-xs text-text-muted">{t("pages.systemSettings.liepinApi.resumeHint")}</p>
                      <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap break-words font-sans text-sm text-text-secondary">
                        {liepinResume || t("pages.systemSettings.liepinApi.resumeEmpty")}
                      </pre>
                    </details>
                  ) : null}
                </article>

                <p className="text-sm text-text-muted">{t("pages.systemSettings.liepinApi.legacyHint")}</p>
                <div className="grid gap-4">
                  {settings.channels.map((channel) => (
                    <ChannelCard
                      key={channel.id}
                      channel={channel}
                      fallbackLabel={t("pages.systemSettings.channels.none")}
                      labels={{
                        priority: t("pages.systemSettings.channels.priority"),
                        fallback: t("pages.systemSettings.channels.fallback"),
                        credential: t("pages.systemSettings.channels.credential"),
                        lastCheck: t("pages.systemSettings.channels.lastCheck"),
                        lastSuccess: t("pages.systemSettings.channels.lastSuccess"),
                        lastError: t("pages.systemSettings.channels.lastError"),
                      }}
                    />
                  ))}
                </div>

                <div className="grid gap-4 xl:grid-cols-3">
                  <div className="rounded-card border border-border bg-bg-primary/70 p-4">
                    <div className="flex items-center gap-2">
                      <Link2 className="h-4 w-4 text-accent" aria-hidden="true" />
                      <h3 className="text-sm font-semibold text-text-primary">
                        {t("pages.systemSettings.channels.fallbackOrder")}
                      </h3>
                    </div>
                    <p className="mt-3 break-all font-mono text-sm text-text-primary">
                      {fallbackOrder}
                    </p>
                  </div>
                  <div className="rounded-card border border-border bg-bg-primary/70 p-4">
                    <div className="flex items-center gap-2">
                      <Wifi className="h-4 w-4 text-accent" aria-hidden="true" />
                      <h3 className="text-sm font-semibold text-text-primary">
                        {t("pages.systemSettings.channels.connectionTests")}
                      </h3>
                    </div>
                    <p className="mt-3 break-all font-mono text-sm text-text-primary">
                      {connectionSummary}
                    </p>
                  </div>
                  <div className="rounded-card border border-border bg-bg-primary/70 p-4">
                    <div className="flex items-center gap-2">
                      <ShieldCheck className="h-4 w-4 text-accent" aria-hidden="true" />
                      <h3 className="text-sm font-semibold text-text-primary">
                        {t("pages.systemSettings.channels.credentialStore")}
                      </h3>
                    </div>
                    <p className="mt-3 text-sm text-text-primary">
                      {t("pages.systemSettings.channels.credentialStoreStatus")}
                    </p>
                  </div>
                </div>
              </div>
            ) : activeSection === "materialSources" ? (
              <div className="space-y-5" data-testid="settings-material-sources">
                <div className="border-b border-border pb-4">
                  <h2 className="text-lg font-semibold text-text-primary">
                    {t("pages.systemSettings.materialSources.title")}
                  </h2>
                  <p className="mt-1 text-sm text-text-secondary">
                    {t("pages.systemSettings.materialSources.subtitle")}
                  </p>
                </div>
                {(settings.material_source_roots ?? []).length === 0 ? (
                  <p className="text-sm text-text-secondary">{t("pages.systemSettings.materialSources.empty")}</p>
                ) : (
                  <ul className="divide-y divide-border" data-testid="material-root-list">
                    {(settings.material_source_roots ?? []).map((root) => (
                      <li className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm" key={root.id}>
                        <span className="min-w-0">
                          <span className="text-text-primary">{root.label}</span>
                          <span className="ml-2 break-all text-xs text-text-muted">{root.path}</span>
                        </span>
                        <button
                          className="text-error underline disabled:opacity-50"
                          disabled={rootsBusy}
                          onClick={() => void handleRemoveRoot(root.id)}
                          type="button"
                        >
                          {t("pages.systemSettings.materialSources.remove")}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                <div className="space-y-3 rounded-card border border-border p-4">
                  <label className="block text-sm text-text-primary">
                    {t("pages.systemSettings.materialSources.path")}
                    <input
                      className="mt-2 w-full rounded-card border border-border bg-bg-hover px-3 py-2 outline-none focus:border-accent"
                      data-testid="material-root-path"
                      disabled={rootsBusy}
                      onChange={(event) => setNewRootPath(event.target.value)}
                      placeholder="/Users/…/worklog-private"
                      value={newRootPath}
                    />
                  </label>
                  <label className="block text-sm text-text-primary">
                    {t("pages.systemSettings.materialSources.label")}
                    <input
                      className="mt-2 w-full rounded-card border border-border bg-bg-hover px-3 py-2 outline-none focus:border-accent"
                      disabled={rootsBusy}
                      onChange={(event) => setNewRootLabel(event.target.value)}
                      value={newRootLabel}
                    />
                  </label>
                  {rootsError ? <p className="text-sm text-error" role="alert">{rootsError}</p> : null}
                  <button
                    className="rounded-card border border-accent px-3 py-2 text-sm text-accent disabled:opacity-50"
                    data-testid="material-root-add"
                    disabled={rootsBusy || !newRootPath.trim()}
                    onClick={() => void handleAddRoot()}
                    type="button"
                  >
                    {t("pages.systemSettings.materialSources.add")}
                  </button>
                </div>

                <div className="space-y-3 rounded-card border border-border p-4" data-testid="material-reference-card">
                  <div>
                    <h3 className="text-sm font-semibold text-text-primary">{t("pages.evidence.materialSources.referenceOpen")}</h3>
                    <p className="mt-1 text-xs text-text-secondary">{t("pages.evidence.materialSources.stepsHint")}</p>
                  </div>
                  {(settings.material_source_roots ?? []).length === 0 ? (
                    <p className="text-sm text-warning">{t("pages.evidence.materialSources.referenceNoRoots")}</p>
                  ) : (
                    <>
                      <div className="grid gap-2 sm:grid-cols-2">
                        <label className="block text-sm text-text-primary">
                          {t("pages.evidence.materialSources.referenceRoot")}
                          <select
                            className="mt-2 w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                            data-testid="material-reference-root"
                            onChange={(event) => { setReferenceRootId(event.target.value); setReferenceScan(null); }}
                            value={referenceRootId}
                          >
                            {(settings.material_source_roots ?? []).map((root) => (
                              <option key={root.id} value={root.id}>{root.label} · {root.path}</option>
                            ))}
                          </select>
                        </label>
                        <label className="block text-sm text-text-primary">
                          {t("pages.evidence.materialSources.referenceRelpath")}
                          <input
                            className="mt-2 w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                            data-testid="material-reference-relpath"
                            disabled={referenceBusy}
                            onChange={(event) => { setReferenceRelpath(event.target.value); setReferenceScan(null); }}
                            placeholder="worklog/2023-03.md"
                            value={referenceRelpath}
                          />
                        </label>
                      </div>
                      <button
                        className="rounded-card border border-accent px-3 py-2 text-sm text-accent disabled:opacity-50"
                        data-testid="material-reference-scan"
                        disabled={referenceBusy || !referenceRootId || !referenceRelpath.trim()}
                        onClick={() => void handleReferenceScan()}
                        type="button"
                      >
                        {referenceBusy ? t("pages.evidence.materialSources.referenceScanning") : t("pages.evidence.materialSources.referenceScan")}
                      </button>
                      {referenceScan ? (
                        <div className="space-y-2 rounded-card border border-border bg-bg-primary/60 p-3">
                          <p className="text-sm text-text-primary">{t("pages.evidence.materialSources.referencePreview", { count: referenceScan.file_count, bytes: referenceScan.total_bytes })}</p>
                          {referenceScan.skipped_count > 0 ? (
                            <p className="text-xs text-warning">{t("pages.evidence.materialSources.referenceSkipped", { count: referenceScan.skipped_count })}</p>
                          ) : null}
                          {referenceScan.existing_materials.length > 0 ? (
                            <p className="text-xs text-warning">{t("pages.evidence.materialSources.referenceExisting")}</p>
                          ) : null}
                          <label className="block text-sm text-text-primary">
                            {t("pages.evidence.materialSources.referenceLabel")}
                            <input
                              className="mt-1 w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                              data-testid="material-reference-label"
                              disabled={referenceBusy}
                              onChange={(event) => setReferenceLabel(event.target.value)}
                              value={referenceLabel}
                            />
                          </label>
                          <button
                            className="rounded-card border border-accent bg-accent px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
                            data-testid="material-reference-create"
                            disabled={referenceBusy || !referenceLabel.trim() || referenceScan.existing_materials.length > 0}
                            onClick={() => void handleReferenceCreate()}
                            type="button"
                          >
                            {referenceBusy ? t("pages.evidence.materialSources.referenceCreating") : t("pages.evidence.materialSources.referenceCreate")}
                          </button>
                        </div>
                      ) : null}
                      {referenceError ? <p className="text-sm text-error" role="alert">{referenceError}</p> : null}
                    </>
                  )}
                  {referencesLoading ? <p className="text-sm text-text-secondary">{t("common.loading")}</p> : null}
                  {referencedItems.length > 0 ? (
                    <ul className="divide-y divide-border" data-testid="material-reference-list">
                      {referencedItems.map((item) => (
                        <li className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm" key={item.material_id}>
                          <span className="min-w-0">
                            <span className="text-text-primary">{item.label || item.filename}</span>
                            <span className="ml-2 text-xs text-text-muted">
                              {t("pages.evidence.materialSources.referenceBadge", { count: Number(item.file_count) || 0 })}
                            </span>
                          </span>
                          <span className="flex shrink-0 gap-2 text-xs">
                            <button className="text-accent underline" data-testid="material-reference-check" onClick={() => void handleReferenceCheck(item.material_id)} type="button">
                              {t("pages.evidence.materialSources.referenceCheck")}
                            </button>
                            <button className="text-accent underline" data-testid="material-reference-refresh" onClick={() => void handleReferenceRefresh(item.material_id)} type="button">
                              {t("pages.evidence.materialSources.referenceRefresh")}
                            </button>
                            <button className="text-error underline" data-testid="material-reference-remove" onClick={() => void handleReferenceRemove(item.material_id)} type="button">
                              {t("pages.evidence.materialSources.referenceRemove")}
                            </button>
                          </span>
                          {referenceStatus[item.material_id] ? (
                            <p className="w-full text-xs text-text-muted">{referenceStatus[item.material_id]}</p>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              </div>
            ) : activeSection === "evidenceInference" ? (
              <div className="space-y-5" data-testid="settings-evidence-inference">
                <div className="border-b border-border pb-4">
                  <h2 className="text-lg font-semibold text-text-primary">
                    {t("pages.systemSettings.evidenceInference.title")}
                  </h2>
                  <p className="mt-1 text-sm text-text-secondary">
                    {t("pages.systemSettings.evidenceInference.subtitle")}
                  </p>
                </div>
                <label className="flex items-start gap-3 rounded-card border border-border bg-bg-primary/70 p-4 text-sm">
                  <input
                    checked={settings.evidence_inference?.enabled !== false}
                    data-testid="evidence-inference-toggle"
                    disabled={inferenceToggleBusy}
                    onChange={(event) => void handleInferenceToggle(event.target.checked)}
                    type="checkbox"
                  />
                  <span>
                    <span className="block font-medium text-text-primary">{t("pages.systemSettings.evidenceInference.enabled")}</span>
                    <span className="mt-1 block text-text-secondary">{t("pages.systemSettings.evidenceInference.enabledHint")}</span>
                  </span>
                </label>
                <p className="text-xs text-text-muted">{t("pages.systemSettings.evidenceInference.note")}</p>
              </div>
            ) : (
              <div className="space-y-5">
                <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border pb-4">
                  <div>
                    <h2 className="text-lg font-semibold text-text-primary">
                      {t("pages.systemSettings.llm.title")}
                    </h2>
                    <p className="mt-1 text-sm text-text-secondary">
                      {t("pages.systemSettings.llm.subtitle")}
                    </p>
                  </div>
                  {llmDirty ? (
                    <span className="rounded-chip border border-warning/40 bg-warning/10 px-2.5 py-1 text-xs font-medium text-warning">
                      {t("pages.systemSettings.llm.unsaved")}
                    </span>
                  ) : null}
                </div>

                {llmError ? (
                  <div className="rounded-card border border-error/40 bg-error/10 px-4 py-3 text-sm text-error">
                    {llmError}
                  </div>
                ) : null}
                {llmSaveState === "saved" ? (
                  <div className="rounded-card border border-success/40 bg-success/10 px-4 py-3 text-sm text-success">
                    {t("pages.systemSettings.llm.saved")}
                  </div>
                ) : null}

                <div className="overflow-hidden rounded-card border border-border bg-bg-panel/50">
                  <div className="border-b border-border px-4 py-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className={LLM_FIELD_LABEL_CLASS}>
                        {t("pages.systemSettings.llm.provider")}
                      </span>
                      <span className="text-xs text-text-muted">
                        {t("pages.systemSettings.llm.providerHint")}
                      </span>
                    </div>
                    <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                      {LLM_PROVIDER_OPTIONS.map((option) => {
                        const active = llmForm.provider === option.id;
                        return (
                          <button
                            aria-pressed={active}
                            className={`flex items-center justify-between gap-2 rounded-card border px-3 py-2.5 text-left transition-colors ${
                              active
                                ? "border-accent bg-accent/10 text-text-primary"
                                : "border-border bg-bg-hover text-text-secondary hover:border-accent/40 hover:text-text-primary"
                            }`}
                            key={option.id}
                            onClick={() => handleProviderChange(option.id)}
                            type="button"
                          >
                            <span className="min-w-0">
                              <span className="block truncate text-sm font-medium">
                                {option.label}
                              </span>
                              <span className="mt-0.5 block truncate text-[11px] text-text-muted">
                                {t(`pages.systemSettings.llm.${option.hintKey}`)}
                              </span>
                            </span>
                            <span
                              aria-label={
                                providerKeyConfigured(option.id)
                                  ? t("pages.systemSettings.secretConfigured")
                                  : t("pages.systemSettings.secretMissing")
                              }
                              className={`h-2 w-2 shrink-0 rounded-full ${providerStatusDot(option.id)}`}
                              role="img"
                              title={
                                providerKeyConfigured(option.id)
                                  ? t("pages.systemSettings.secretConfigured")
                                  : t("pages.systemSettings.secretMissing")
                              }
                            />
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="grid gap-4 px-4 py-4 md:grid-cols-2">
                  <label className="space-y-1.5">
                    <span className={LLM_FIELD_LABEL_CLASS}>
                      {t("pages.systemSettings.llm.model")}
                    </span>
                    <input
                      className={LLM_FIELD_INPUT_CLASS}
                      onChange={(event) =>
                        setLlmForm((current) => ({
                          ...current,
                          model: event.target.value,
                        }))
                      }
                      placeholder={t("pages.systemSettings.llm.modelPlaceholder")}
                      type="text"
                      value={llmForm.model}
                    />
                  </label>
                  <label className="space-y-1.5">
                    <span className={LLM_FIELD_LABEL_CLASS}>
                      {t("pages.systemSettings.llm.detectedModels")}
                    </span>
                    <select
                      className={`${LLM_FIELD_INPUT_CLASS} disabled:cursor-not-allowed disabled:opacity-60`}
                      disabled={detectedModels.length === 0}
                      onChange={(event) => {
                        const model = event.target.value;
                        if (!model) return;
                        setLlmForm((current) => ({
                          ...current,
                          model,
                        }));
                      }}
                      value={
                        detectedModels.includes(llmForm.model.trim())
                          ? llmForm.model.trim()
                          : ""
                      }
                    >
                      <option value="">
                        {detectedModels.length > 0
                          ? t("pages.systemSettings.llm.chooseDetectedModel")
                          : t("pages.systemSettings.llm.noDetectedModels")}
                      </option>
                      {detectedModels.map((model) => (
                        <option key={model} value={model}>
                          {model}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="space-y-1.5 md:col-span-2">
                    <span className={LLM_FIELD_LABEL_CLASS}>
                      {t("pages.systemSettings.llm.baseUrl")}
                    </span>
                    <input
                      className={`${LLM_FIELD_INPUT_CLASS} font-mono`}
                      onChange={(event) =>
                        setLlmForm((current) => ({
                          ...current,
                          base_url: event.target.value,
                        }))
                      }
                      placeholder={
                        LLM_PROVIDER_DEFAULTS[llmForm.provider]?.base_url ||
                        "http://127.0.0.1:1234/v1"
                      }
                      type="url"
                      value={llmForm.base_url}
                    />
                  </label>
                  <div className="space-y-1.5 md:col-span-2">
                    <div className="flex items-center justify-between gap-3">
                      <span className={LLM_FIELD_LABEL_CLASS}>
                        {t("pages.systemSettings.llm.apiKey")}
                      </span>
                      {canClearProviderKey ? (
                        <button
                          className="text-xs font-medium text-error/90 transition-colors hover:text-error"
                          onClick={() => void handleClearLlmApiKey()}
                          type="button"
                        >
                          {t("pages.systemSettings.llm.clearKey")}
                        </button>
                      ) : null}
                    </div>
                    <input
                      className={`${LLM_FIELD_INPUT_CLASS} font-mono`}
                      onChange={(event) =>
                        setLlmForm((current) => ({
                          ...current,
                          api_key: event.target.value,
                        }))
                      }
                      placeholder={
                        providerKeyConfigured(llmForm.provider)
                          ? t("pages.systemSettings.llm.keepExistingSecret")
                          : llmForm.provider === "lm_studio"
                            ? "lm-studio"
                            : ""
                      }
                      type="password"
                      value={llmForm.api_key}
                    />
                    <div className="flex flex-wrap items-center gap-2 text-xs text-text-muted">
                      <span className={`h-1.5 w-1.5 rounded-full ${keyStatusDot()}`} />
                      <span>{keyStatusLabel(llmForm.provider)}</span>
                      {settings.llm_config.provider === llmForm.provider &&
                      settings.llm_config.api_key.updated_at ? (
                        <span className="text-text-muted">
                          · {formatShortTimestamp(settings.llm_config.api_key.updated_at)}
                        </span>
                      ) : null}
                    </div>
                  </div>
                  <label className="space-y-1.5">
                    <span className={LLM_FIELD_LABEL_CLASS}>
                      {t("pages.systemSettings.llm.timeout")}
                    </span>
                    <input
                      className={LLM_FIELD_INPUT_CLASS}
                      min={1}
                      onChange={(event) =>
                        setLlmForm((current) => ({
                          ...current,
                          timeout: event.target.value,
                        }))
                      }
                      type="number"
                      value={llmForm.timeout}
                    />
                  </label>
                  <label className="space-y-1.5">
                    <span className={LLM_FIELD_LABEL_CLASS}>
                      {t("pages.systemSettings.llm.temperature")}
                    </span>
                    <input
                      className={LLM_FIELD_INPUT_CLASS}
                      max={2}
                      min={0}
                      onChange={(event) =>
                        setLlmForm((current) => ({
                          ...current,
                          temperature: event.target.value,
                        }))
                      }
                      step={0.1}
                      type="number"
                      value={llmForm.temperature}
                    />
                  </label>
                </div>

                {llmForm.provider === "deepseek" ? (
                  <div className="flex flex-wrap items-center justify-between gap-4 border-t border-border px-4 py-3">
                    <div className="min-w-0">
                      <span className="flex flex-wrap items-center gap-2 text-sm font-medium text-text-primary">
                        {t("pages.systemSettings.llm.thinkingMode")}
                      </span>
                      <p className="mt-1 text-xs text-text-muted">
                        {t("pages.systemSettings.llm.thinkingModeHint")}
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-3">
                      <button
                        aria-checked={llmForm.thinking_enabled}
                        aria-label={t("pages.systemSettings.llm.thinkingMode")}
                        className={`relative h-6 w-11 rounded-full transition-colors ${
                          llmForm.thinking_enabled ? "bg-accent" : "bg-bg-hover"
                        }`}
                        onClick={() =>
                          setLlmForm((current) => ({
                            ...current,
                            thinking_enabled: !current.thinking_enabled,
                          }))
                        }
                        role="switch"
                        type="button"
                      >
                        <span
                          className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow-sm transition-all ${
                            llmForm.thinking_enabled ? "left-[22px]" : "left-0.5"
                          }`}
                        />
                      </button>
                      {llmForm.thinking_enabled ? (
                        <div
                          aria-label={t("pages.systemSettings.llm.thinkingEffort")}
                          className="inline-flex rounded-card border border-border bg-bg-hover p-0.5"
                          role="group"
                          title={t("pages.systemSettings.llm.thinkingEffortHint")}
                        >
                          {LLM_THINKING_EFFORTS.map((effort) => {
                            const active =
                              llmForm.thinking_effort === effort.value;
                            return (
                              <button
                                aria-pressed={active}
                                className={`rounded-[7px] px-2.5 py-1 text-xs font-medium transition-colors ${
                                  active
                                    ? "bg-accent text-white"
                                    : "text-text-secondary hover:text-text-primary"
                                }`}
                                key={effort.value}
                                onClick={() =>
                                  setLlmForm((current) => ({
                                    ...current,
                                    thinking_effort: effort.value,
                                  }))
                                }
                                type="button"
                              >
                                {t(`pages.systemSettings.llm.${effort.labelKey}`)}
                              </button>
                            );
                          })}
                        </div>
                      ) : null}
                    </div>
                  </div>
                ) : null}

                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border bg-bg-primary/40 px-4 py-3">
                  <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
                    {llmConnection ? (
                      <StatusChip value={llmConnection.status} />
                    ) : (
                      <span
                        className={`h-1.5 w-1.5 rounded-full ${
                          llmCheckState === "checking"
                            ? "bg-warning"
                            : "bg-text-muted/40"
                        }`}
                      />
                    )}
                    <span
                      className="min-w-0 truncate text-xs text-text-muted"
                      title={llmConnectionSummary}
                    >
                      {llmConnectionSummary}
                    </span>
                  </div>
                  <button
                    className="inline-flex items-center gap-2 rounded-card border border-border px-3 py-2 text-xs font-medium text-text-primary transition-colors hover:bg-bg-hover disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={llmCheckState === "checking"}
                    onClick={() => void handleCheckLlmConnection()}
                    type="button"
                  >
                    <Wifi className="h-3.5 w-3.5" aria-hidden="true" />
                    {llmCheckState === "checking"
                      ? t("pages.systemSettings.llm.checking")
                      : t("pages.systemSettings.llm.testConnection")}
                  </button>
                </div>
                </div>
                <p className="text-xs text-text-muted">
                  {t("pages.systemSettings.llm.providerStatusLegend")}
                </p>
              </div>
            )}
          </section>
        </div>
      ) : null}
    </div>
  );
}
