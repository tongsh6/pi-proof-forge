import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  KeyRound,
  Link2,
  RefreshCw,
  Save,
  Server,
  Settings2,
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
  getLiepinResume,
  getSettings,
  openLiepinAuthorization,
  updateLiepinCredential,
  updateLlmConfig,
} from "@/lib/sidecar/api";
import type {
  ChannelConfig,
  LiepinAuthState,
  LlmConfig,
  LlmConnectionCheckResult,
  SettingsGetResult,
} from "@/lib/sidecar/types";

type LoadState = "loading" | "ready" | "error";
type SectionId = "channels" | "llm";
type LlmSaveState = "idle" | "saving" | "saved";
type LlmCheckState = "idle" | "checking" | "checked";

type LlmForm = {
  provider: string;
  model: string;
  base_url: string;
  api_key: string;
  timeout: string;
  temperature: string;
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
};

function formatNullable(value: string | null | undefined): string {
  return value && value.trim() ? value : "--";
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
  };
}

function applyProviderDefaults(
  current: LlmForm,
  nextProvider: string,
  apiKeyConfigured: boolean
): LlmForm {
  const previousDefaults =
    LLM_PROVIDER_DEFAULTS[current.provider] ?? LLM_PROVIDER_DEFAULTS.lm_studio;
  const nextDefaults =
    LLM_PROVIDER_DEFAULTS[nextProvider] ?? LLM_PROVIDER_DEFAULTS.openai_compatible;
  const currentModel = current.model.trim();
  const currentBaseUrl = current.base_url.trim();
  const currentApiKey = current.api_key.trim();
  const shouldReplaceModel =
    !currentModel || currentModel === previousDefaults.model;
  const shouldReplaceBaseUrl =
    !currentBaseUrl || currentBaseUrl === previousDefaults.base_url;
  const nextApiKeyIsSafeLocalDefault = nextDefaults.api_key === "lm-studio";
  const shouldReplaceApiKey =
    (nextApiKeyIsSafeLocalDefault || !apiKeyConfigured) &&
    (!currentApiKey || currentApiKey === previousDefaults.api_key);

  return {
    ...current,
    provider: nextProvider,
    model: shouldReplaceModel ? nextDefaults.model : current.model,
    base_url: shouldReplaceBaseUrl ? nextDefaults.base_url : current.base_url,
    api_key: shouldReplaceApiKey ? nextDefaults.api_key : current.api_key,
  };
}

function llmPayloadFromForm(form: LlmForm): {
  provider: string;
  model?: string;
  base_url?: string;
  api_key?: string;
  timeout: number;
  temperature: number;
} {
  const payload: {
    provider: string;
    model?: string;
    base_url?: string;
    api_key?: string;
    timeout: number;
    temperature: number;
  } = {
    provider: form.provider.trim(),
    timeout: Number(form.timeout),
    temperature: Number(form.temperature),
  };
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
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [searchParams] = useSearchParams();
  // 总览“配置模型”等入口可用 ?section=llm 直接打开模型分组。
  const [activeSection, setActiveSection] = useState<SectionId>(searchParams.get("section") === "llm" ? "llm" : "channels");
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

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

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
      setLlmSaveState("saved");
      notify("success", t("toasts.systemSettings.saved"));
    } catch (nextError) {
      setLlmSaveState("idle");
      setLlmError(getErrorMessage(nextError));
    }
  }, [llmForm]);

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
      notify("success", t("toasts.systemSettings.connectionOk"));
    } catch (nextError) {
      setLlmCheckState("idle");
      setLlmError(getErrorMessage(nextError));
    }
  }, [llmForm]);

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
              {(["channels", "llm"] as SectionId[]).map((section) => {
                const Icon = section === "channels" ? Wifi : Settings2;
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
                  <StatusChip
                    value={
                      settings.llm_config.api_key.configured
                        ? t("pages.systemSettings.secretConfigured")
                        : t("pages.systemSettings.secretMissing")
                    }
                  />
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

                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  <label className="space-y-1.5">
                    <span className="text-xs font-medium text-text-secondary">
                      {t("pages.systemSettings.llm.provider")}
                    </span>
                    <select
                      className="w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                      onChange={(event) =>
                        setLlmForm((current) =>
                          applyProviderDefaults(
                            current,
                            event.target.value,
                            settings.llm_config.api_key.configured
                          )
                        )
                      }
                      value={llmForm.provider}
                    >
                      <option value="lm_studio">LM Studio</option>
                      <option value="openai">OpenAI</option>
                      <option value="openai_compatible">OpenAI Compatible</option>
                    </select>
                  </label>
                  <label className="space-y-1.5">
                    <span className="text-xs font-medium text-text-secondary">
                      {t("pages.systemSettings.llm.model")}
                    </span>
                    <input
                      className="w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
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
                    <span className="text-xs font-medium text-text-secondary">
                      {t("pages.systemSettings.llm.detectedModels")}
                    </span>
                    <select
                      className="w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent disabled:cursor-not-allowed disabled:opacity-60"
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
                  <label className="space-y-1.5">
                    <span className="text-xs font-medium text-text-secondary">
                      {t("pages.systemSettings.llm.baseUrl")}
                    </span>
                    <input
                      className="w-full rounded-card border border-border bg-bg-hover px-3 py-2 font-mono text-sm text-text-primary outline-none focus:border-accent"
                      onChange={(event) =>
                        setLlmForm((current) => ({
                          ...current,
                          base_url: event.target.value,
                        }))
                      }
                      placeholder="http://127.0.0.1:1234/v1"
                      type="url"
                      value={llmForm.base_url}
                    />
                  </label>
                  <label className="space-y-1.5">
                    <span className="text-xs font-medium text-text-secondary">
                      {t("pages.systemSettings.llm.apiKey")}
                    </span>
                    <input
                      className="w-full rounded-card border border-border bg-bg-hover px-3 py-2 font-mono text-sm text-text-primary outline-none focus:border-accent"
                      onChange={(event) =>
                        setLlmForm((current) => ({
                          ...current,
                          api_key: event.target.value,
                        }))
                      }
                      placeholder={
                        settings.llm_config.api_key.configured
                          ? t("pages.systemSettings.llm.keepExistingSecret")
                          : llmForm.provider === "lm_studio"
                            ? "lm-studio"
                            : ""
                      }
                      type="password"
                      value={llmForm.api_key}
                    />
                  </label>
                  <label className="space-y-1.5">
                    <span className="text-xs font-medium text-text-secondary">
                      {t("pages.systemSettings.llm.timeout")}
                    </span>
                    <input
                      className="w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
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
                    <span className="text-xs font-medium text-text-secondary">
                      {t("pages.systemSettings.llm.temperature")}
                    </span>
                    <input
                      className="w-full rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
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

                <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                  <div className="rounded-card border border-border bg-bg-primary/70 p-4">
                    <div className="flex items-center gap-2">
                      <KeyRound className="h-4 w-4 text-accent" aria-hidden="true" />
                      <h3 className="text-sm font-semibold text-text-primary">
                        {t("pages.systemSettings.secretStatus.title")}
                      </h3>
                    </div>
                    <dl className="mt-4 grid gap-3">
                      <div className="flex items-center justify-between gap-3">
                        <dt className="text-sm text-text-secondary">
                          {t("pages.systemSettings.llm.apiKey")}
                        </dt>
                        <dd>
                          <StatusChip
                            value={
                              settings.llm_config.api_key.configured
                                ? t("pages.systemSettings.secretConfigured")
                                : t("pages.systemSettings.secretMissing")
                            }
                          />
                        </dd>
                      </div>
                      <div className="flex items-center justify-between gap-3">
                        <dt className="text-sm text-text-secondary">
                          {t("pages.systemSettings.secretStatus.updatedAt")}
                        </dt>
                        <dd className="font-mono text-sm text-text-primary">
                          {formatNullable(settings.llm_config.api_key.updated_at)}
                        </dd>
                      </div>
                    </dl>
                  </div>

                  <div className="rounded-card border border-border bg-bg-primary/70 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="flex items-center gap-2">
                        <Wifi className="h-4 w-4 text-accent" aria-hidden="true" />
                        <h3 className="text-sm font-semibold text-text-primary">
                          {t("pages.systemSettings.llm.connectionTest")}
                        </h3>
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
                    <p className="mt-4 break-all font-mono text-sm text-text-primary">
                      {llmForm.base_url
                        ? llmForm.base_url
                        : t("pages.systemSettings.llm.defaultEndpoint")}
                    </p>
                    <div className="mt-3">
                      <StatusChip
                        value={
                          llmConnection?.status ??
                          (settings.llm_config.api_key.configured ? "configured" : "missing")
                        }
                      />
                    </div>
                    {llmConnection ? (
                      <div className="mt-3 space-y-2 text-sm text-text-secondary">
                        <p className="break-words">{llmConnection.message}</p>
                        <p className="font-mono text-xs text-text-muted">
                          {llmConnection.code} ·{" "}
                          {t("pages.systemSettings.llm.modelCount", {
                            count: llmConnection.model_count,
                          })}
                        </p>
                        {detectedModels.length > 0 ? (
                          <div className="flex flex-wrap gap-2">
                            {detectedModels.map((model) => (
                              <span
                                className="rounded-chip border border-border bg-bg-hover px-2 py-1 font-mono text-xs text-text-primary"
                                key={model}
                              >
                                {model}
                              </span>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                </div>
              </div>
            )}
          </section>
        </div>
      ) : null}
    </div>
  );
}
