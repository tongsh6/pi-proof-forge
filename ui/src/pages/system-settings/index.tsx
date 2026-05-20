import { useCallback, useEffect, useMemo, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
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
import { getErrorMessage } from "@/lib/errors";
import { checkLlmConnection, getSettings, updateLlmConfig } from "@/lib/sidecar/api";
import type {
  ChannelConfig,
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
const verifyScenario = import.meta.env.VITE_QUICK_RUN_VERIFY_AUTORUN;

function formatNullable(value: string | null | undefined): string {
  return value && value.trim() ? value : "--";
}

function toLlmForm(config: LlmConfig | null): LlmForm {
  return {
    provider: config?.provider ?? "lm_studio",
    model: config?.model ?? "",
    base_url: config?.base_url ?? "",
    api_key: "",
    timeout: String(config?.timeout ?? 60),
    temperature: String(config?.temperature ?? 0.2),
  };
}

function llmPayloadFromForm(form: LlmForm): {
  provider: string;
  model: string;
  base_url: string;
  api_key?: string;
  timeout: number;
  temperature: number;
} {
  const payload: {
    provider: string;
    model: string;
    base_url: string;
    api_key?: string;
    timeout: number;
    temperature: number;
  } = {
    provider: form.provider.trim(),
    model: form.model.trim(),
    base_url: form.base_url.trim(),
    timeout: Number(form.timeout),
    temperature: Number(form.temperature),
  };
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

function recordVerifyEvent(
  event: string,
  details: Record<string, unknown> = {}
) {
  if (verifyScenario !== "system-settings") return;
  void invoke("quick_run_verify_event", {
    event: {
      event,
      ...details,
    },
  }).catch(() => undefined);
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
  const [activeSection, setActiveSection] = useState<SectionId>("channels");
  const [llmForm, setLlmForm] = useState<LlmForm>(() => toLlmForm(null));
  const [llmSaveState, setLlmSaveState] = useState<LlmSaveState>("idle");
  const [llmCheckState, setLlmCheckState] = useState<LlmCheckState>("idle");
  const [llmConnection, setLlmConnection] =
    useState<LlmConnectionCheckResult | null>(null);
  const [llmError, setLlmError] = useState<string | null>(null);

  const loadSettings = useCallback(async () => {
    setLoadState("loading");
    setError(null);

    try {
      const result = await getSettings();
      setSettings(result);
      setLlmForm(toLlmForm(result.llm_config));
      setLoadState("ready");
      recordVerifyEvent("system_settings.load.ready", {
        channel_count: result.channels.length,
        channel_ids: result.channels.map((channel) => channel.id),
        llm_provider: result.llm_config.provider,
        api_key_configured: result.llm_config.api_key.configured,
      });
    } catch (nextError) {
      setSettings(null);
      setLoadState("error");
      setError(getErrorMessage(nextError));
      recordVerifyEvent("system_settings.load.error", {
        error: getErrorMessage(nextError),
      });
    }
  }, []);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  useEffect(() => {
    if (verifyScenario !== "system-settings" || loadState !== "ready" || !settings) {
      return;
    }
    setActiveSection("llm");
    recordVerifyEvent("system_settings.llm.form.ready", {
      has_provider: Boolean(llmForm.provider),
      has_model: Boolean(llmForm.model),
      has_base_url_field: true,
      has_timeout: Boolean(llmForm.timeout),
      has_temperature: Boolean(llmForm.temperature),
      api_key_configured: settings.llm_config.api_key.configured,
    });
  }, [llmForm, loadState, settings]);

  const fallbackOrder = useMemo(() => {
    if (!settings || settings.channels.length === 0) {
      return "--";
    }
    return [...settings.channels]
      .sort((left, right) => left.priority - right.priority)
      .map((channel) => channel.id)
      .join(" -> ");
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

  const handleSaveLlmConfig = useCallback(async () => {
    setLlmSaveState("saving");
    setLlmError(null);
    try {
      await updateLlmConfig(llmPayloadFromForm(llmForm));
      const nextSettings = await getSettings();
      setSettings(nextSettings);
      setLlmForm(toLlmForm(nextSettings.llm_config));
      setLlmSaveState("saved");
      recordVerifyEvent("system_settings.llm.save.result", {
        provider: nextSettings.llm_config.provider,
        api_key_configured: nextSettings.llm_config.api_key.configured,
      });
    } catch (nextError) {
      setLlmSaveState("idle");
      setLlmError(getErrorMessage(nextError));
      recordVerifyEvent("system_settings.llm.save.error", {
        error: getErrorMessage(nextError),
      });
    }
  }, [llmForm]);

  const handleCheckLlmConnection = useCallback(async () => {
    setLlmCheckState("checking");
    setLlmError(null);
    try {
      const result = await checkLlmConnection(llmPayloadFromForm(llmForm));
      setLlmConnection(result);
      setLlmCheckState("checked");
      recordVerifyEvent("system_settings.llm.check.result", {
        status: result.status,
        code: result.code,
        model_count: result.model_count,
      });
    } catch (nextError) {
      setLlmCheckState("idle");
      setLlmError(getErrorMessage(nextError));
      recordVerifyEvent("system_settings.llm.check.error", {
        error: getErrorMessage(nextError),
      });
    }
  }, [llmForm]);

  return (
    <div className="space-y-6">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">
            {t("pages.systemSettings.title")}
          </h1>
          <p className="mt-2 text-sm text-text-secondary">
            {t("pages.systemSettings.subtitle")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="inline-flex items-center gap-2 rounded-card border border-border px-4 py-2 text-sm text-text-primary transition-colors hover:bg-bg-hover"
            onClick={() => void loadSettings()}
            type="button"
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            {t("common.retry")}
          </button>
          <button
            className="inline-flex items-center gap-2 rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={activeSection !== "llm" || llmSaveState === "saving"}
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
                        setLlmForm((current) => ({
                          ...current,
                          provider: event.target.value,
                        }))
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
                          : "lm-studio"
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
                          {llmConnection.code} · {llmConnection.model_count}
                        </p>
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
