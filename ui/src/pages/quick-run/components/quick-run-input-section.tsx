import { useTranslation } from "react-i18next";
import type {
  EvidenceListItem,
  JobProfileListItem,
  FitPrecheck,
  QuickRunStartResult,
  MaterialSourceItem,
} from "@/lib/sidecar/types";
import type { RunState } from "../quick-run-helpers";

type QuickRunInputSectionProps = {
  providerSummary: { label: string; value: string }[];
  profileReady: boolean;
  targetAvailable: boolean;
  onOpenProfile: () => void;
  onOpenJobs: () => void;
  selectedProfileId: string;
  selectedProfile: JobProfileListItem | undefined;
  activeJobProfiles: JobProfileListItem[];
  rulePrecheck: FitPrecheck | null;
  precheckStateLabel: string;
  manualDeliveryOnly: boolean | undefined;
  resumePositioning: string;
  selectedMaterialId: string;
  materialSources: MaterialSourceItem[];
  useLlm: boolean;
  quickRunResult: QuickRunStartResult | null;
  evidenceCount: number;
  availableEvidence: EvidenceListItem[];
  eligibleEvidenceIds: string[];
  runState: RunState;
  onSelectedProfileChange: (value: string) => void;
  onResumePositioningChange: (value: string) => void;
  onSelectedMaterialChange: (value: string) => void;
  onUseLlmChange: (checked: boolean) => void;
  onToggleEvidence: (evidenceId: string, checked: boolean) => void;
};

/** Quick Run 输入摘要区：模型信息、目标/定位/材料选择、证据勾选。 */
export function QuickRunInputSection({
  providerSummary,
  profileReady,
  targetAvailable,
  onOpenProfile,
  onOpenJobs,
  selectedProfileId,
  selectedProfile,
  activeJobProfiles,
  rulePrecheck,
  precheckStateLabel,
  manualDeliveryOnly,
  resumePositioning,
  selectedMaterialId,
  materialSources,
  useLlm,
  quickRunResult,
  evidenceCount,
  availableEvidence,
  eligibleEvidenceIds,
  runState,
  onSelectedProfileChange,
  onResumePositioningChange,
  onSelectedMaterialChange,
  onUseLlmChange,
  onToggleEvidence,
}: QuickRunInputSectionProps) {
  const { t } = useTranslation();
  const running = runState === "running";
  return (
    <>
      <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-secondary">
        <span className="text-text-muted">{t("pages.quickRun.providerSummary")}</span>
        {providerSummary.map((item) => (
          <span key={item.label}>
            <span className="text-text-muted">{item.label}</span> {item.value}
          </span>
        ))}
      </p>

      <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
        <h2 className="text-lg font-semibold text-text-primary">
          {t("pages.quickRun.inputSummary")}
        </h2>
        <p role="status" className="mt-3 text-sm text-text-secondary">
          {t(profileReady ? "pages.quickRun.profileReady" : "pages.quickRun.profileRequired")}
          <button type="button" className="ml-3 text-accent underline" onClick={onOpenProfile}>{t("pages.quickRun.openProfile")}</button>
        </p>
        {!targetAvailable && <p role="alert" className="mt-2 text-sm text-warning">
          {t("pages.quickRun.targetUnavailable")}
          <button type="button" className="ml-3 text-accent underline" onClick={onOpenJobs}>{t("pages.quickRun.openJobs")}</button>
        </p>}
        <div className="mt-4 flex flex-wrap gap-3">
            <select
              value={selectedProfileId}
              disabled={running}
              onChange={(event) => onSelectedProfileChange(event.target.value)}
              className="h-10 min-w-[280px] max-w-full rounded-card border border-border bg-bg-panel px-3 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-accent/40"
              aria-label={t("pages.quickRun.selectProfile")}
            >
              {!targetAvailable ? (
                <option value={selectedProfileId}>{t(selectedProfileId ? "pages.quickRun.targetUnavailable" : "common.empty")}</option>
              ) : null}
              {activeJobProfiles.map((profile) => {
                const precheck = profile.fit_precheck;
                const suffix = precheck && precheck.source === "rule"
                  ? t("pages.quickRun.fitBadgePrecheck", {
                      label: t(`pages.jobs.precheck.state.${precheck.state}`, { defaultValue: precheck.state }),
                    })
                  : profile.fit_state === "failed"
                    ? t("pages.quickRun.fitBadgeFailed", { count: profile.fit_failures ?? 0 })
                    : profile.fit_state === "unassessed"
                      ? t("pages.quickRun.fitBadgeUnassessed")
                      : "";
                return (
                  <option key={profile.job_profile_id} value={profile.job_profile_id}>
                    {profile.company ? `${profile.company} · ${profile.title}` : profile.title}{suffix}
                    {profile.native_pdf_delivery?.supported === false ? ` ${t("pages.quickRun.manualDeliveryOnlyBadge")}` : ""}
                  </option>
                );
              })}
            </select>
            {selectedProfile && selectedProfile.fit_state === "failed" && !rulePrecheck &&
              <p role="status" className="text-xs text-warning">
                {t("pages.quickRun.fitHintFailed", { count: selectedProfile.fit_failures ?? 0 })}
              </p>}
            {manualDeliveryOnly &&
              <p role="status" data-testid="quick-run-manual-delivery-hint" className="text-xs text-warning">
                {t("pages.quickRun.manualDeliveryHintShort")}
              </p>}
            {selectedProfile && rulePrecheck &&
              <p role="status" className="text-xs text-text-secondary">
                {t("pages.quickRun.fitHintPrecheck", {
                  label: precheckStateLabel,
                  matched: rulePrecheck.matched_requirements ?? 0,
                  total: rulePrecheck.total_requirements ?? 0,
                })}
              </p>}
            {selectedProfile && selectedProfile.fit_state === "unassessed" && !rulePrecheck &&
              <p role="status" className="text-xs text-text-secondary">
                {t("pages.quickRun.fitHintUnassessed")}
              </p>}
            <select
              value={resumePositioning}
              disabled={running}
              onChange={(event) => onResumePositioningChange(event.target.value)}
              className="h-10 min-w-[220px] rounded-card border border-border bg-bg-panel px-3 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-accent/40"
              aria-label={t("pages.quickRun.resumePositioning")}
            >
              <option value="technical_depth">
                {t("pages.quickRun.positioningOptions.technicalDepth")}
              </option>
              <option value="delivery_owner">
                {t("pages.quickRun.positioningOptions.deliveryOwner")}
              </option>
            </select>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <div className="rounded-card border border-border bg-bg-primary/50 p-4">
            <p className="text-xs uppercase text-text-muted">
              {t("pages.quickRun.materialSource")}
            </p>
            <select aria-label={t("pages.quickRun.materialSource")} value={selectedMaterialId}
              disabled={running} onChange={event => onSelectedMaterialChange(event.target.value)}
              className="mt-2 w-full rounded-card border border-border bg-bg-primary px-2 py-2 text-sm text-text-primary">
              <option value="">{t("pages.quickRun.chooseMaterial")}</option>
              {materialSources.map(material => <option key={material.material_id} value={material.material_id}>{material.label || material.material_id}</option>)}
            </select>
            <label className="mt-3 flex items-center gap-2 text-sm text-text-secondary">
              <input type="checkbox" checked={useLlm} disabled={running}
                onChange={event => onUseLlmChange(event.target.checked)} />
              {t("pages.quickRun.useLlm")}
            </label>
          </div>
          <div className="rounded-card border border-border bg-bg-primary/50 p-4">
            <p className="text-xs uppercase text-text-muted">
              {t("pages.quickRun.traceableEvidence")}
            </p>
            <p className="mt-2 truncate text-sm font-medium text-text-primary">
              {quickRunResult?.traceability?.evidence_card_ids.length
                ? `${quickRunResult.traceability.evidence_card_ids.length} ${t("pages.quickRun.evidenceCards")}`
                : `${evidenceCount} ${t("pages.quickRun.evidenceCards")}`}
            </p>
          </div>
        </div>
        <fieldset className="mt-4 rounded-card border border-border p-3"><legend className="px-2 text-sm">{t('pages.quickRun.evidenceSelection')} ({eligibleEvidenceIds.length}/{evidenceCount})</legend><div className="grid gap-2 md:grid-cols-2">{availableEvidence.map(item=><label key={item.evidence_id} className="flex items-start gap-2 text-sm text-text-secondary"><input data-evidence-id={item.evidence_id} type="checkbox" checked={eligibleEvidenceIds.includes(item.evidence_id)} disabled={running} onChange={e=>onToggleEvidence(item.evidence_id,e.target.checked)}/>{item.title||item.evidence_id}</label>)}</div></fieldset>
      </section>
    </>
  );
}
