import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { invoke } from "@tauri-apps/api/core";
import {
  Ban,
  Building2,
  CheckCircle2,
  Gavel,
  ListChecks,
  RefreshCw,
  Save,
  ShieldCheck,
  SlidersHorizontal,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { getErrorMessage } from "@/lib/errors";
import {
  getSettings,
  updateDeliverySettings,
  updateExclusionList,
  updateLegalEntityExclusionList,
} from "@/lib/sidecar/api";
import type { SettingsGetResult } from "@/lib/sidecar/types";

type LoadState = "loading" | "ready" | "error";
type SaveState = "idle" | "saving" | "saved" | "error";
type PolicySection = "gate" | "exclusions";

type RulePreview = {
  value: string;
  mode: "exact" | "contains";
};

const verifyScenario = import.meta.env.VITE_QUICK_RUN_VERIFY_AUTORUN;

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

function parseRulePreview(entry: string): RulePreview {
  const trimmed = entry.trim();
  if (trimmed.toLowerCase().startsWith("contains:")) {
    return {
      mode: "contains",
      value: trimmed.slice("contains:".length).trim() || trimmed,
    };
  }
  if (trimmed.toLowerCase().startsWith("exact:")) {
    return {
      mode: "exact",
      value: trimmed.slice("exact:".length).trim() || trimmed,
    };
  }
  return { mode: "exact", value: trimmed };
}

function statusText(
  state: SaveState,
  labels: Record<string, string>
): string | null {
  if (state === "saving") return labels.saving;
  if (state === "saved") return labels.saved;
  if (state === "error") return labels.error;
  return null;
}

function recordVerifyEvent(
  event: string,
  details: Record<string, unknown> = {}
) {
  if (verifyScenario !== "policy") return;
  void invoke("quick_run_verify_event", {
    event: {
      event,
      ...details,
    },
  }).catch(() => undefined);
}

function FieldCard({
  label,
  description,
  children,
}: {
  label: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-card border border-border bg-bg-primary/70 p-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-sm font-medium text-text-primary">{label}</p>
          <p className="mt-1 max-w-2xl text-xs leading-5 text-text-secondary">
            {description}
          </p>
        </div>
        <div className="shrink-0">{children}</div>
      </div>
    </div>
  );
}

function ReadOnlyValue({ value }: { value: string | number }) {
  return (
    <span className="inline-flex min-w-[72px] justify-center rounded-card border border-border bg-bg-panel px-3 py-2 text-sm font-semibold text-text-primary">
      {value}
    </span>
  );
}

function SectionNavButton({
  active,
  icon: Icon,
  title,
  subtitle,
  onClick,
}: {
  active: boolean;
  icon: typeof ShieldCheck;
  title: string;
  subtitle: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`w-full rounded-card border p-3 text-left transition-colors ${
        active
          ? "border-accent/50 bg-accent/10 text-text-primary"
          : "border-border bg-bg-primary/60 text-text-secondary hover:bg-bg-hover"
      }`}
      onClick={onClick}
    >
      <span className="flex items-start gap-3">
        <Icon
          className={active ? "mt-0.5 h-4 w-4 text-accent" : "mt-0.5 h-4 w-4"}
          aria-hidden="true"
        />
        <span className="min-w-0">
          <span className="block text-sm font-semibold">{title}</span>
          <span className="mt-1 block text-xs leading-5 text-text-secondary">
            {subtitle}
          </span>
        </span>
      </span>
    </button>
  );
}

function RulePreviewList({
  title,
  emptyLabel,
  entries,
}: {
  title: string;
  emptyLabel: string;
  entries: string[];
}) {
  const previews = entries.map(parseRulePreview);
  return (
    <div className="rounded-card border border-border bg-bg-primary/70 p-4">
      <div className="flex items-center gap-2">
        <ListChecks className="h-4 w-4 text-accent" aria-hidden="true" />
        <h3 className="text-sm font-semibold text-text-primary">{title}</h3>
      </div>
      {previews.length === 0 ? (
        <p className="mt-3 text-sm text-text-secondary">{emptyLabel}</p>
      ) : (
        <div className="mt-3 flex flex-wrap gap-2">
          {previews.map((preview, index) => (
            <span
              key={`${preview.mode}-${preview.value}-${index}`}
              className="inline-flex max-w-full items-center gap-2 rounded-chip border border-border bg-bg-panel px-3 py-1.5 text-xs text-text-secondary"
            >
              <span className="uppercase tracking-[0.12em] text-accent">
                {preview.mode}
              </span>
              <span className="truncate text-text-primary">{preview.value}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export function PolicyPage() {
  const { t } = useTranslation();
  const [settings, setSettings] = useState<SettingsGetResult | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState<PolicySection>("gate");
  const [companyDraft, setCompanyDraft] = useState<string>("");
  const [legalEntityDraft, setLegalEntityDraft] = useState<string>("");
  const [companySaveState, setCompanySaveState] = useState<SaveState>("idle");
  const [legalEntitySaveState, setLegalEntitySaveState] =
    useState<SaveState>("idle");
  const [deliverySaveState, setDeliverySaveState] = useState<SaveState>("idle");
  const [companyError, setCompanyError] = useState<string | null>(null);
  const [legalEntityError, setLegalEntityError] = useState<string | null>(null);
  const [deliveryError, setDeliveryError] = useState<string | null>(null);

  const companyEntries = useMemo(
    () => normalizeEntries(companyDraft),
    [companyDraft]
  );
  const legalEntityEntries = useMemo(
    () => normalizeEntries(legalEntityDraft),
    [legalEntityDraft]
  );
  const companyDirty = Boolean(
    settings && !listsEqual(companyEntries, settings.exclusion_list)
  );
  const legalEntityDirty = Boolean(
    settings && !listsEqual(legalEntityEntries, settings.excluded_legal_entities)
  );
  const gateStatus = statusText(deliverySaveState, {
    saving: t("pages.policy.saveState.saving"),
    saved: t("pages.policy.saveState.saved"),
    error: t("pages.policy.saveState.error"),
  });
  const exclusionStatus =
    statusText(companySaveState, {
      saving: t("pages.policy.saveState.saving"),
      saved: t("pages.policy.saveState.saved"),
      error: t("pages.policy.saveState.error"),
    }) ||
    statusText(legalEntitySaveState, {
      saving: t("pages.policy.saveState.saving"),
      saved: t("pages.policy.saveState.saved"),
      error: t("pages.policy.saveState.error"),
    });

  const loadSettings = useCallback(async () => {
    setLoadState("loading");
    setError(null);
    setCompanySaveState("idle");
    setLegalEntitySaveState("idle");
    setDeliverySaveState("idle");
    setCompanyError(null);
    setLegalEntityError(null);
    setDeliveryError(null);

    try {
      const result = await getSettings();
      setSettings(result);
      setCompanyDraft(result.exclusion_list.join("\n"));
      setLegalEntityDraft(result.excluded_legal_entities.join("\n"));
      setLoadState("ready");
      recordVerifyEvent("policy.load.ready", {
        delivery_mode: result.gate_policy.delivery_mode,
        batch_review: result.gate_policy.batch_review,
        company_rule_count: result.exclusion_list.length,
        legal_entity_rule_count: result.excluded_legal_entities.length,
      });
    } catch (nextError) {
      setSettings(null);
      setLoadState("error");
      setError(getErrorMessage(nextError));
      recordVerifyEvent("policy.load.error", {
        error: getErrorMessage(nextError),
      });
    }
  }, []);

  const handleSaveDeliverySettings = useCallback(async () => {
    if (!settings) return;
    setDeliverySaveState("saving");
    setDeliveryError(null);
    try {
      await updateDeliverySettings(
        settings.gate_policy.delivery_mode,
        settings.gate_policy.batch_review
      );
      setDeliverySaveState("saved");
    } catch (nextError) {
      setDeliverySaveState("error");
      setDeliveryError(getErrorMessage(nextError));
    }
  }, [settings]);

  const handleSaveCompanies = useCallback(async () => {
    if (!settings) return;
    setCompanySaveState("saving");
    setCompanyError(null);
    try {
      await updateExclusionList(companyEntries);
      setSettings((current) =>
        current ? { ...current, exclusion_list: companyEntries } : current
      );
      setCompanySaveState("saved");
    } catch (nextError) {
      setCompanySaveState("error");
      setCompanyError(getErrorMessage(nextError));
    }
  }, [companyEntries, settings]);

  const handleSaveLegalEntities = useCallback(async () => {
    if (!settings) return;
    setLegalEntitySaveState("saving");
    setLegalEntityError(null);
    try {
      await updateLegalEntityExclusionList(legalEntityEntries);
      setSettings((current) =>
        current
          ? { ...current, excluded_legal_entities: legalEntityEntries }
          : current
      );
      setLegalEntitySaveState("saved");
    } catch (nextError) {
      setLegalEntitySaveState("error");
      setLegalEntityError(getErrorMessage(nextError));
    }
  }, [legalEntityEntries, settings]);

  const handleSaveActiveSection = useCallback(async () => {
    if (activeSection === "gate") {
      await handleSaveDeliverySettings();
      return;
    }
    if (companyDirty) {
      await handleSaveCompanies();
    }
    if (legalEntityDirty) {
      await handleSaveLegalEntities();
    }
  }, [
    activeSection,
    companyDirty,
    handleSaveCompanies,
    handleSaveDeliverySettings,
    handleSaveLegalEntities,
    legalEntityDirty,
  ]);

  const setDeliveryMode = useCallback(
    (value: "auto" | "manual") => {
      if (settings) {
        setSettings({
          ...settings,
          gate_policy: {
            ...settings.gate_policy,
            delivery_mode: value,
            batch_review:
              value === "auto" ? false : settings.gate_policy.batch_review,
          },
        });
      }
      if (deliverySaveState !== "idle") setDeliverySaveState("idle");
      setDeliveryError(null);
    },
    [deliverySaveState, settings]
  );

  const setBatchReview = useCallback(
    (value: boolean) => {
      if (settings) {
        setSettings({
          ...settings,
          gate_policy: { ...settings.gate_policy, batch_review: value },
        });
      }
      if (deliverySaveState !== "idle") setDeliverySaveState("idle");
      setDeliveryError(null);
    },
    [deliverySaveState, settings]
  );

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  const activeSaving =
    activeSection === "gate"
      ? deliverySaveState === "saving"
      : companySaveState === "saving" || legalEntitySaveState === "saving";
  const activeSaveDisabled =
    loadState !== "ready" ||
    !settings ||
    activeSaving ||
    (activeSection === "exclusions" && !companyDirty && !legalEntityDirty);

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">
            {t("pages.policy.title")}
          </h1>
          <p className="mt-2 text-sm text-text-secondary">
            {t("pages.policy.subtitle")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button
            className="inline-flex items-center gap-2 rounded-card border border-border px-4 py-2 text-sm text-text-primary transition-colors hover:bg-bg-hover"
            onClick={() => void loadSettings()}
            type="button"
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            {t("common.retry")}
          </button>
          <button
            className="inline-flex items-center gap-2 rounded-card border border-accent/60 bg-accent px-4 py-2 text-sm font-semibold text-bg-primary transition-colors hover:bg-accent-cyan disabled:cursor-not-allowed disabled:opacity-60"
            onClick={() => void handleSaveActiveSection()}
            type="button"
            disabled={activeSaveDisabled}
          >
            <Save className="h-4 w-4" aria-hidden="true" />
            {t("pages.policy.save")}
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
          <aside className="space-y-3">
            <SectionNavButton
              active={activeSection === "gate"}
              icon={ShieldCheck}
              title={t("pages.policy.nav.gate")}
              subtitle={t("pages.policy.nav.gateHint")}
              onClick={() => setActiveSection("gate")}
            />
            <SectionNavButton
              active={activeSection === "exclusions"}
              icon={Ban}
              title={t("pages.policy.nav.exclusions")}
              subtitle={t("pages.policy.nav.exclusionsHint")}
              onClick={() => setActiveSection("exclusions")}
            />
            <div className="rounded-card border border-border bg-bg-panel p-3 text-xs leading-5 text-text-secondary">
              <p className="font-medium text-text-primary">
                {t("pages.policy.audit.title")}
              </p>
              <p className="mt-1">{t("pages.policy.audit.description")}</p>
            </div>
          </aside>

          {activeSection === "gate" ? (
            <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
              <div className="flex flex-wrap items-start justify-between gap-4 border-b border-border pb-4">
                <div>
                  <div className="flex items-center gap-2">
                    <Gavel className="h-5 w-5 text-accent" aria-hidden="true" />
                    <h2 className="text-lg font-semibold text-text-primary">
                      {t("pages.policy.gatePolicy.title")}
                    </h2>
                  </div>
                  <p className="mt-1 text-sm text-text-secondary">
                    {t("pages.policy.gatePolicy.subtitle")}
                  </p>
                </div>
                {gateStatus ? (
                  <span className="rounded-chip border border-border bg-bg-primary px-3 py-1 text-xs text-text-secondary">
                    {gateStatus}
                  </span>
                ) : null}
              </div>

              <div className="mt-5 grid gap-4">
                <FieldCard
                  label={t("pages.policy.gatePolicy.nPassRequired")}
                  description={t("pages.policy.gatePolicyDescriptions.nPassRequired")}
                >
                  <ReadOnlyValue value={settings.gate_policy.n_pass_required} />
                </FieldCard>
                <FieldCard
                  label={t("pages.policy.gatePolicy.matchingThreshold")}
                  description={t(
                    "pages.policy.gatePolicyDescriptions.matchingThreshold"
                  )}
                >
                  <ReadOnlyValue
                    value={settings.gate_policy.matching_threshold}
                  />
                </FieldCard>
                <FieldCard
                  label={t("pages.policy.gatePolicy.evaluationThreshold")}
                  description={t(
                    "pages.policy.gatePolicyDescriptions.evaluationThreshold"
                  )}
                >
                  <ReadOnlyValue
                    value={settings.gate_policy.evaluation_threshold}
                  />
                </FieldCard>
                <FieldCard
                  label={t("pages.policy.gatePolicy.maxRounds")}
                  description={t("pages.policy.gatePolicyDescriptions.maxRounds")}
                >
                  <ReadOnlyValue value={settings.gate_policy.max_rounds} />
                </FieldCard>
                <FieldCard
                  label={t("pages.policy.gatePolicy.mode")}
                  description={t("pages.policy.gatePolicyDescriptions.mode")}
                >
                  <span className="inline-flex rounded-chip border border-accent/40 bg-accent/10 px-3 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-accent">
                    {settings.gate_policy.gate_mode}
                  </span>
                </FieldCard>
                <FieldCard
                  label={t("pages.policy.gatePolicy.deliveryMode")}
                  description={t(
                    "pages.policy.gatePolicyDescriptions.deliveryMode"
                  )}
                >
                  <select
                    className="rounded-card border border-border bg-bg-primary/80 px-3 py-2 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-accent/40"
                    value={settings.gate_policy.delivery_mode}
                    onChange={(event) =>
                      setDeliveryMode(event.target.value as "auto" | "manual")
                    }
                    aria-label={t("pages.policy.gatePolicy.deliveryMode")}
                  >
                    <option value="auto">
                      {t("pages.policy.gatePolicy.deliveryModeAuto")}
                    </option>
                    <option value="manual">
                      {t("pages.policy.gatePolicy.deliveryModeManual")}
                    </option>
                  </select>
                </FieldCard>
                <FieldCard
                  label={t("pages.policy.gatePolicy.batchReview")}
                  description={t(
                    settings.gate_policy.delivery_mode === "manual"
                      ? "pages.policy.gatePolicyDescriptions.batchReviewManual"
                      : "pages.policy.gatePolicyDescriptions.batchReviewAuto"
                  )}
                >
                  <button
                    type="button"
                    role="switch"
                    aria-checked={settings.gate_policy.batch_review}
                    aria-label={t("pages.policy.gatePolicy.batchReview")}
                    disabled={settings.gate_policy.delivery_mode === "auto"}
                    className={`relative inline-flex h-7 w-12 shrink-0 rounded-full border transition-colors focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:cursor-not-allowed disabled:opacity-50 ${
                      settings.gate_policy.batch_review
                        ? "border-accent bg-accent"
                        : "border-border bg-bg-panel"
                    }`}
                    onClick={() =>
                      settings.gate_policy.delivery_mode === "manual" &&
                      setBatchReview(!settings.gate_policy.batch_review)
                    }
                  >
                    <span
                      className={`pointer-events-none inline-block h-6 w-6 rounded-full bg-white shadow-sm transition-transform ${
                        settings.gate_policy.batch_review
                          ? "translate-x-5"
                          : "translate-x-0.5"
                      }`}
                    />
                  </button>
                </FieldCard>
              </div>

              {deliveryError ? (
                <p className="mt-4 text-sm text-error">{deliveryError}</p>
              ) : null}
            </section>
          ) : (
            <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
              <div className="flex flex-wrap items-start justify-between gap-4 border-b border-border pb-4">
                <div>
                  <div className="flex items-center gap-2">
                    <Building2 className="h-5 w-5 text-accent" aria-hidden="true" />
                    <h2 className="text-lg font-semibold text-text-primary">
                      {t("pages.policy.exclusionList.title")}
                    </h2>
                  </div>
                  <p className="mt-1 text-sm text-text-secondary">
                    {t("pages.policy.exclusionList.subtitle")}
                  </p>
                </div>
                {exclusionStatus ? (
                  <span className="rounded-chip border border-border bg-bg-primary px-3 py-1 text-xs text-text-secondary">
                    {exclusionStatus}
                  </span>
                ) : null}
              </div>

              <div className="mt-5 grid gap-5 xl:grid-cols-2">
                <div className="space-y-3">
                  <div>
                    <h3 className="text-sm font-semibold text-text-primary">
                      {t("pages.policy.excludedCompanies.title")}
                    </h3>
                    <p className="mt-1 text-xs leading-5 text-text-secondary">
                      {t("pages.policy.excludedCompanies.subtitle")}
                    </p>
                  </div>
                  <textarea
                    className="min-h-[180px] w-full rounded-card border border-border bg-bg-primary/70 p-3 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent/40"
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
                        count: companyEntries.length,
                      })}
                    </span>
                    <button
                      className="inline-flex items-center gap-2 rounded-card border border-border px-3 py-1.5 text-xs font-medium text-text-primary transition-colors hover:bg-bg-hover disabled:cursor-not-allowed disabled:opacity-60"
                      onClick={() => void handleSaveCompanies()}
                      type="button"
                      disabled={companySaveState === "saving" || !companyDirty}
                    >
                      <Save className="h-3.5 w-3.5" aria-hidden="true" />
                      {t("pages.policy.excludedCompanies.save")}
                    </button>
                  </div>
                  {companyError ? (
                    <p className="text-xs text-error">{companyError}</p>
                  ) : null}
                </div>

                <div className="space-y-3">
                  <div>
                    <h3 className="text-sm font-semibold text-text-primary">
                      {t("pages.policy.excludedLegalEntities.title")}
                    </h3>
                    <p className="mt-1 text-xs leading-5 text-text-secondary">
                      {t("pages.policy.excludedLegalEntities.subtitle")}
                    </p>
                  </div>
                  <textarea
                    className="min-h-[180px] w-full rounded-card border border-border bg-bg-primary/70 p-3 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent/40"
                    placeholder={t(
                      "pages.policy.excludedLegalEntities.placeholder"
                    )}
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
                        count: legalEntityEntries.length,
                      })}
                    </span>
                    <button
                      className="inline-flex items-center gap-2 rounded-card border border-border px-3 py-1.5 text-xs font-medium text-text-primary transition-colors hover:bg-bg-hover disabled:cursor-not-allowed disabled:opacity-60"
                      onClick={() => void handleSaveLegalEntities()}
                      type="button"
                      disabled={
                        legalEntitySaveState === "saving" || !legalEntityDirty
                      }
                    >
                      <Save className="h-3.5 w-3.5" aria-hidden="true" />
                      {t("pages.policy.excludedLegalEntities.save")}
                    </button>
                  </div>
                  {legalEntityError ? (
                    <p className="text-xs text-error">{legalEntityError}</p>
                  ) : null}
                </div>
              </div>

              <div className="mt-5 grid gap-4 xl:grid-cols-2">
                <RulePreviewList
                  title={t("pages.policy.exclusionList.companyPreview")}
                  emptyLabel={t("pages.policy.exclusionList.emptyCompanies")}
                  entries={companyEntries}
                />
                <RulePreviewList
                  title={t("pages.policy.exclusionList.legalEntityPreview")}
                  emptyLabel={t("pages.policy.exclusionList.emptyLegalEntities")}
                  entries={legalEntityEntries}
                />
              </div>

              <div className="mt-5 rounded-card border border-border bg-bg-primary/70 p-4">
                <div className="flex items-start gap-3">
                  <SlidersHorizontal
                    className="mt-0.5 h-4 w-4 text-accent"
                    aria-hidden="true"
                  />
                  <div>
                    <h3 className="text-sm font-semibold text-text-primary">
                      {t("pages.policy.exclusionList.matchingTitle")}
                    </h3>
                    <p className="mt-1 text-sm leading-6 text-text-secondary">
                      {t("pages.policy.exclusionList.matchingDescription")}
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <span className="inline-flex items-center gap-1.5 rounded-chip border border-success/40 bg-success/10 px-3 py-1 text-xs text-success">
                        <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                        {t("pages.policy.exclusionList.discoveryGuard")}
                      </span>
                      <span className="inline-flex items-center gap-1.5 rounded-chip border border-warning/40 bg-warning/10 px-3 py-1 text-xs text-warning">
                        <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
                        {t("pages.policy.exclusionList.gateFallback")}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </section>
          )}
        </div>
      ) : null}
    </div>
  );
}
