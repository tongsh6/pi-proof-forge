import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { getErrorMessage } from "@/lib/errors";
import { getSettings, updateExclusionList } from "@/lib/sidecar/api";
import type { SettingsGetResult } from "@/lib/sidecar/types";

type LoadState = "loading" | "ready" | "error";

function formatNullable(value: string | null): string {
  return value && value.trim() ? value : "--";
}

export function SystemSettingsPage() {
  const { t } = useTranslation();
  const [settings, setSettings] = useState<SettingsGetResult | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [exclusionDraft, setExclusionDraft] = useState<string>("");
  const [exclusionSaveState, setExclusionSaveState] = useState<
    "idle" | "saving" | "saved" | "error"
  >("idle");
  const [exclusionError, setExclusionError] = useState<string | null>(null);

  const normalizeExclusions = useCallback((value: string): string[] => {
    return value
      .split("\n")
      .map((item) => item.trim())
      .filter((item) => item.length > 0);
  }, []);

  const listsEqual = useCallback((left: string[], right: string[]): boolean => {
    if (left.length !== right.length) {
      return false;
    }
    return left.every((item, index) => item === right[index]);
  }, []);

  const loadSettings = useCallback(async () => {
    setLoadState("loading");
    setError(null);
    setExclusionSaveState("idle");
    setExclusionError(null);

    try {
      const result = await getSettings();
      setSettings(result);
      setLoadState("ready");
      setExclusionDraft(result.exclusion_list.join("\n"));
    } catch (nextError) {
      setSettings(null);
      setLoadState("error");
      setError(getErrorMessage(nextError));
    }
  }, []);

  const handleSaveExclusions = useCallback(async () => {
    if (!settings) {
      return;
    }
    const entries = normalizeExclusions(exclusionDraft);
    setExclusionSaveState("saving");
    setExclusionError(null);
    try {
      await updateExclusionList(entries);
      setSettings({ ...settings, exclusion_list: entries });
      setExclusionSaveState("saved");
    } catch (nextError) {
      setExclusionSaveState("error");
      setExclusionError(getErrorMessage(nextError));
    }
  }, [exclusionDraft, normalizeExclusions, settings]);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

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
        <button
          className="rounded-card border border-border px-4 py-2 text-sm text-text-primary transition-colors hover:bg-bg-hover"
          onClick={() => void loadSettings()}
          type="button"
        >
          {t("common.retry")}
        </button>
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
        <div className="grid gap-6 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
          <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
            <div className="border-b border-border pb-4">
              <h2 className="text-lg font-semibold text-text-primary">
                {t("pages.systemSettings.gatePolicy.title")}
              </h2>
              <p className="mt-1 text-sm text-text-secondary">
                {t("pages.systemSettings.gatePolicy.subtitle")}
              </p>
            </div>
            <dl className="space-y-4 pt-4">
              <div className="flex items-center justify-between gap-4">
                <dt className="text-sm text-text-secondary">
                  {t("pages.systemSettings.gatePolicy.nPassRequired")}
                </dt>
                <dd className="text-sm font-medium text-text-primary">
                  {settings.gate_policy.n_pass_required}
                </dd>
              </div>
              <div className="flex items-center justify-between gap-4">
                <dt className="text-sm text-text-secondary">
                  {t("pages.systemSettings.gatePolicy.matchingThreshold")}
                </dt>
                <dd className="text-sm font-medium text-text-primary">
                  {settings.gate_policy.matching_threshold}
                </dd>
              </div>
              <div className="flex items-center justify-between gap-4">
                <dt className="text-sm text-text-secondary">
                  {t("pages.systemSettings.gatePolicy.evaluationThreshold")}
                </dt>
                <dd className="text-sm font-medium text-text-primary">
                  {settings.gate_policy.evaluation_threshold}
                </dd>
              </div>
              <div className="flex items-center justify-between gap-4">
                <dt className="text-sm text-text-secondary">
                  {t("pages.systemSettings.gatePolicy.maxRounds")}
                </dt>
                <dd className="text-sm font-medium text-text-primary">
                  {settings.gate_policy.max_rounds}
                </dd>
              </div>
              <div className="flex items-center justify-between gap-4">
                <dt className="text-sm text-text-secondary">
                  {t("pages.systemSettings.gatePolicy.mode")}
                </dt>
                <dd className="rounded-chip bg-accent/10 px-2.5 py-1 text-xs font-medium uppercase tracking-[0.12em] text-accent">
                  {settings.gate_policy.gate_mode}
                </dd>
              </div>
            </dl>
          </section>

          <section className="space-y-6">
            <div className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
              <div className="border-b border-border pb-4">
                <h2 className="text-lg font-semibold text-text-primary">
                  {t("pages.systemSettings.llm.title")}
                </h2>
                <p className="mt-1 text-sm text-text-secondary">
                  {t("pages.systemSettings.llm.subtitle")}
                </p>
              </div>
              <dl className="grid gap-4 pt-4 md:grid-cols-2">
                <div>
                  <dt className="text-xs uppercase tracking-[0.18em] text-text-muted">
                    {t("pages.systemSettings.llm.provider")}
                  </dt>
                  <dd className="mt-2 text-sm text-text-primary">
                    {formatNullable(settings.llm_config.provider)}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-[0.18em] text-text-muted">
                    {t("pages.systemSettings.llm.model")}
                  </dt>
                  <dd className="mt-2 text-sm text-text-primary">
                    {formatNullable(settings.llm_config.model)}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-[0.18em] text-text-muted">
                    {t("pages.systemSettings.llm.baseUrl")}
                  </dt>
                  <dd className="mt-2 break-all text-sm text-text-primary">
                    {formatNullable(settings.llm_config.base_url)}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-[0.18em] text-text-muted">
                    {t("pages.systemSettings.llm.apiKey")}
                  </dt>
                  <dd className="mt-2 text-sm text-text-primary">
                    {settings.llm_config.api_key.configured
                      ? t("pages.systemSettings.secretConfigured")
                      : t("pages.systemSettings.secretMissing")}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-[0.18em] text-text-muted">
                    {t("pages.systemSettings.llm.timeout")}
                  </dt>
                  <dd className="mt-2 text-sm text-text-primary">
                    {settings.llm_config.timeout}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-[0.18em] text-text-muted">
                    {t("pages.systemSettings.llm.temperature")}
                  </dt>
                  <dd className="mt-2 text-sm text-text-primary">
                    {settings.llm_config.temperature}
                  </dd>
                </div>
              </dl>
            </div>

            <div className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
              <div className="border-b border-border pb-4">
                <h2 className="text-lg font-semibold text-text-primary">
                  {t("pages.systemSettings.exclusionList.title")}
                </h2>
                <p className="mt-1 text-sm text-text-secondary">
                  {t("pages.systemSettings.exclusionList.subtitle")}
                </p>
              </div>
              <div className="space-y-3 pt-4">
                <textarea
                  className="min-h-[140px] w-full rounded-card border border-border bg-bg-primary/60 p-3 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent/40"
                  placeholder={t("pages.systemSettings.exclusionList.placeholder")}
                  value={exclusionDraft}
                  onChange={(event) => {
                    setExclusionDraft(event.target.value);
                    if (exclusionSaveState !== "idle") {
                      setExclusionSaveState("idle");
                      setExclusionError(null);
                    }
                  }}
                />
                <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-text-muted">
                  <span>
                    {t("pages.systemSettings.exclusionList.helper", {
                      count: normalizeExclusions(exclusionDraft).length,
                    })}
                  </span>
                  <button
                    className="rounded-card border border-border px-3 py-1.5 text-xs font-medium text-text-primary transition-colors hover:bg-bg-hover disabled:cursor-not-allowed disabled:opacity-60"
                    onClick={() => void handleSaveExclusions()}
                    type="button"
                    disabled={
                      exclusionSaveState === "saving" ||
                      listsEqual(
                        normalizeExclusions(exclusionDraft),
                        settings.exclusion_list
                      )
                    }
                  >
                    {exclusionSaveState === "saving"
                      ? t("pages.systemSettings.exclusionList.saving")
                      : t("pages.systemSettings.exclusionList.save")}
                  </button>
                </div>
                {exclusionSaveState === "error" && exclusionError ? (
                  <p className="text-xs text-error">{exclusionError}</p>
                ) : null}
                {exclusionSaveState === "saved" ? (
                  <p className="text-xs text-accent">
                    {t("pages.systemSettings.exclusionList.saved")}
                  </p>
                ) : null}
              </div>
            </div>

            <div className="grid gap-6 md:grid-cols-1">
              <div className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
                <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                  {t("pages.systemSettings.channels")}
                </p>
                <p className="mt-3 text-3xl font-semibold text-text-primary">
                  {settings.channels.length}
                </p>
              </div>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
