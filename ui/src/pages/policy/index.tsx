import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { getErrorMessage } from "@/lib/errors";
import {
  getSettings,
  updateExclusionList,
  updateLegalEntityExclusionList,
} from "@/lib/sidecar/api";
import type { SettingsGetResult } from "@/lib/sidecar/types";

type LoadState = "loading" | "ready" | "error";
type SaveState = "idle" | "saving" | "saved" | "error";

function normalizeEntries(value: string): string[] {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

function listsEqual(left: string[], right: string[]): boolean {
  if (left.length !== right.length) {
    return false;
  }

  return left.every((item, index) => item === right[index]);
}

export function PolicyPage() {
  const { t } = useTranslation();
  const [settings, setSettings] = useState<SettingsGetResult | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [companyDraft, setCompanyDraft] = useState<string>("");
  const [legalEntityDraft, setLegalEntityDraft] = useState<string>("");
  const [companySaveState, setCompanySaveState] = useState<SaveState>("idle");
  const [legalEntitySaveState, setLegalEntitySaveState] =
    useState<SaveState>("idle");
  const [companyError, setCompanyError] = useState<string | null>(null);
  const [legalEntityError, setLegalEntityError] = useState<string | null>(null);

  const loadSettings = useCallback(async () => {
    setLoadState("loading");
    setError(null);
    setCompanySaveState("idle");
    setLegalEntitySaveState("idle");
    setCompanyError(null);
    setLegalEntityError(null);

    try {
      const result = await getSettings();
      setSettings(result);
      setCompanyDraft(result.exclusion_list.join("\n"));
      setLegalEntityDraft(result.excluded_legal_entities.join("\n"));
      setLoadState("ready");
    } catch (nextError) {
      setSettings(null);
      setLoadState("error");
      setError(getErrorMessage(nextError));
    }
  }, []);

  const handleSaveCompanies = useCallback(async () => {
    if (!settings) {
      return;
    }

    const entries = normalizeEntries(companyDraft);
    setCompanySaveState("saving");
    setCompanyError(null);
    try {
      await updateExclusionList(entries);
      setSettings({ ...settings, exclusion_list: entries });
      setCompanySaveState("saved");
    } catch (nextError) {
      setCompanySaveState("error");
      setCompanyError(getErrorMessage(nextError));
    }
  }, [companyDraft, settings]);

  const handleSaveLegalEntities = useCallback(async () => {
    if (!settings) {
      return;
    }

    const entries = normalizeEntries(legalEntityDraft);
    setLegalEntitySaveState("saving");
    setLegalEntityError(null);
    try {
      await updateLegalEntityExclusionList(entries);
      setSettings({ ...settings, excluded_legal_entities: entries });
      setLegalEntitySaveState("saved");
    } catch (nextError) {
      setLegalEntitySaveState("error");
      setLegalEntityError(getErrorMessage(nextError));
    }
  }, [legalEntityDraft, settings]);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  return (
    <div className="space-y-6">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">
            {t("pages.policy.title")}
          </h1>
          <p className="mt-2 text-sm text-text-secondary">
            {t("pages.policy.subtitle")}
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
        <div className="grid gap-6 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
            <div className="border-b border-border pb-4">
              <h2 className="text-lg font-semibold text-text-primary">
                {t("pages.policy.gatePolicy.title")}
              </h2>
              <p className="mt-1 text-sm text-text-secondary">
                {t("pages.policy.gatePolicy.subtitle")}
              </p>
            </div>
            <dl className="space-y-4 pt-4">
              <div className="flex items-center justify-between gap-4">
                <dt className="text-sm text-text-secondary">
                  {t("pages.policy.gatePolicy.nPassRequired")}
                </dt>
                <dd className="text-sm font-medium text-text-primary">
                  {settings.gate_policy.n_pass_required}
                </dd>
              </div>
              <div className="flex items-center justify-between gap-4">
                <dt className="text-sm text-text-secondary">
                  {t("pages.policy.gatePolicy.matchingThreshold")}
                </dt>
                <dd className="text-sm font-medium text-text-primary">
                  {settings.gate_policy.matching_threshold}
                </dd>
              </div>
              <div className="flex items-center justify-between gap-4">
                <dt className="text-sm text-text-secondary">
                  {t("pages.policy.gatePolicy.evaluationThreshold")}
                </dt>
                <dd className="text-sm font-medium text-text-primary">
                  {settings.gate_policy.evaluation_threshold}
                </dd>
              </div>
              <div className="flex items-center justify-between gap-4">
                <dt className="text-sm text-text-secondary">
                  {t("pages.policy.gatePolicy.maxRounds")}
                </dt>
                <dd className="text-sm font-medium text-text-primary">
                  {settings.gate_policy.max_rounds}
                </dd>
              </div>
              <div className="flex items-center justify-between gap-4">
                <dt className="text-sm text-text-secondary">
                  {t("pages.policy.gatePolicy.mode")}
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
                  {t("pages.policy.excludedCompanies.title")}
                </h2>
                <p className="mt-1 text-sm text-text-secondary">
                  {t("pages.policy.excludedCompanies.subtitle")}
                </p>
              </div>
              <div className="space-y-3 pt-4">
                <textarea
                  className="min-h-[140px] w-full rounded-card border border-border bg-bg-primary/60 p-3 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent/40"
                  placeholder={t("pages.policy.excludedCompanies.placeholder")}
                  value={companyDraft}
                  onChange={(event) => {
                    setCompanyDraft(event.target.value);
                    if (companySaveState !== "idle") {
                      setCompanySaveState("idle");
                      setCompanyError(null);
                    }
                  }}
                />
                <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-text-muted">
                  <span>
                    {t("pages.policy.excludedCompanies.helper", {
                      count: normalizeEntries(companyDraft).length,
                    })}
                  </span>
                  <button
                    className="rounded-card border border-border px-3 py-1.5 text-xs font-medium text-text-primary transition-colors hover:bg-bg-hover disabled:cursor-not-allowed disabled:opacity-60"
                    onClick={() => void handleSaveCompanies()}
                    type="button"
                    disabled={
                      companySaveState === "saving" ||
                      listsEqual(
                        normalizeEntries(companyDraft),
                        settings.exclusion_list
                      )
                    }
                  >
                    {companySaveState === "saving"
                      ? t("pages.policy.excludedCompanies.saving")
                      : t("pages.policy.excludedCompanies.save")}
                  </button>
                </div>
                {companySaveState === "error" && companyError ? (
                  <p className="text-xs text-error">{companyError}</p>
                ) : null}
                {companySaveState === "saved" ? (
                  <p className="text-xs text-accent">
                    {t("pages.policy.excludedCompanies.saved")}
                  </p>
                ) : null}
              </div>
            </div>

            <div className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
              <div className="border-b border-border pb-4">
                <h2 className="text-lg font-semibold text-text-primary">
                  {t("pages.policy.excludedLegalEntities.title")}
                </h2>
                <p className="mt-1 text-sm text-text-secondary">
                  {t("pages.policy.excludedLegalEntities.subtitle")}
                </p>
              </div>
              <div className="space-y-3 pt-4">
                <textarea
                  className="min-h-[140px] w-full rounded-card border border-border bg-bg-primary/60 p-3 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent/40"
                  placeholder={t("pages.policy.excludedLegalEntities.placeholder")}
                  value={legalEntityDraft}
                  onChange={(event) => {
                    setLegalEntityDraft(event.target.value);
                    if (legalEntitySaveState !== "idle") {
                      setLegalEntitySaveState("idle");
                      setLegalEntityError(null);
                    }
                  }}
                />
                <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-text-muted">
                  <span>
                    {t("pages.policy.excludedLegalEntities.helper", {
                      count: normalizeEntries(legalEntityDraft).length,
                    })}
                  </span>
                  <button
                    className="rounded-card border border-border px-3 py-1.5 text-xs font-medium text-text-primary transition-colors hover:bg-bg-hover disabled:cursor-not-allowed disabled:opacity-60"
                    onClick={() => void handleSaveLegalEntities()}
                    type="button"
                    disabled={
                      legalEntitySaveState === "saving" ||
                      listsEqual(
                        normalizeEntries(legalEntityDraft),
                        settings.excluded_legal_entities
                      )
                    }
                  >
                    {legalEntitySaveState === "saving"
                      ? t("pages.policy.excludedLegalEntities.saving")
                      : t("pages.policy.excludedLegalEntities.save")}
                  </button>
                </div>
                {legalEntitySaveState === "error" && legalEntityError ? (
                  <p className="text-xs text-error">{legalEntityError}</p>
                ) : null}
                {legalEntitySaveState === "saved" ? (
                  <p className="text-xs text-accent">
                    {t("pages.policy.excludedLegalEntities.saved")}
                  </p>
                ) : null}
              </div>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
