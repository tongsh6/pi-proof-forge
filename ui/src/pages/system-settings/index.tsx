import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { getErrorMessage } from "@/lib/errors";
import { getSettings } from "@/lib/sidecar/api";
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

  const loadSettings = useCallback(async () => {
    setLoadState("loading");
    setError(null);

    try {
      const result = await getSettings();
      setSettings(result);
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
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
          <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
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
          </section>

          <section className="space-y-6">
            <div className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
              <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                {t("pages.systemSettings.channels")}
              </p>
              <p className="mt-3 text-3xl font-semibold text-text-primary">
                {settings.channels.length}
              </p>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
