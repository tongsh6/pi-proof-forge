import { useTranslation } from "react-i18next";
import type {
  EvidenceInferenceCandidate,
  EvidenceInferenceResult,
  EvidenceReconcileItem,
  EvidenceTriageDecision,
} from "@/lib/sidecar/types";
import {
  buildReconcileReasons,
  inferenceCandidateKey,
} from "../evidence-helpers";

type InferenceCard = EvidenceInferenceResult["cards"][number];

type EvidenceDiagnosisPanelProps = {
  item: EvidenceReconcileItem;
  card: InferenceCard | undefined;
  inferenceEdits: Record<string, string>;
  inferenceBusy: boolean;
  showLowConfidence: boolean;
  onInferenceEditsChange: (
    updater: (current: Record<string, string>) => Record<string, string>
  ) => void;
  onShowLowConfidence: (value: boolean) => void;
  onInferenceDecision: (
    item: EvidenceReconcileItem,
    cardSha: string,
    candidate: EvidenceInferenceCandidate,
    action: "accept" | "reject",
    value?: string
  ) => void;
  onChangeTriage: (
    item: EvidenceReconcileItem,
    decision: EvidenceTriageDecision | ""
  ) => void;
};

/** 详情面板「对账发现」区：问题原因、推断候选、低置信展开与分流。 */
export function EvidenceDiagnosisPanel({
  item,
  card,
  inferenceEdits,
  inferenceBusy,
  showLowConfidence,
  onInferenceEditsChange,
  onShowLowConfidence,
  onInferenceDecision,
  onChangeTriage,
}: EvidenceDiagnosisPanelProps) {
  const { t } = useTranslation();
  const candidates = card?.candidates ?? [];
  const cardSha = card?.card_sha256 ?? "";
  const high = candidates.filter((candidate) => (candidate.confidence ?? 0) >= 0.5);
  const low = candidates.filter((candidate) => (candidate.confidence ?? 0) < 0.5);

  const renderCandidate = (candidate: EvidenceInferenceCandidate, lowConfidence = false) => {
    const key = inferenceCandidateKey(item.evidence_id, candidate.field, candidate.candidate_hash);
    return (
      <div className="mt-1 rounded-card border border-border bg-bg-primary/60 px-2 py-1 text-xs" data-testid="evidence-inference-candidate" data-field={candidate.field} key={key}>
        <p className="text-text-primary">
          {t(candidate.field === "time_range" ? "pages.evidence.reconcile.inference.time" : "pages.evidence.reconcile.inference.role")}：{candidate.value}
          <span className="ml-2 text-text-muted">{candidate.level}{typeof candidate.confidence === "number" ? ` · ${candidate.confidence.toFixed(2)}` : ""}{lowConfidence ? ` · ${t("pages.evidence.reconcile.inference.lowConfidence")}` : ""}</span>
        </p>
        <p className="mt-0.5 truncate text-text-muted">{(candidate.evidence[0]?.excerpt || candidate.evidence[0]?.key || "").slice(0, 120)}</p>
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5" role="group" aria-label={t("pages.evidence.reconcile.inference.editLabel")}>
          <input aria-label={t("pages.evidence.reconcile.inference.editLabel")} className="w-40 rounded-card border border-border bg-bg-primary px-2 py-1 text-xs"
            value={inferenceEdits[key] ?? candidate.value}
            onChange={(event) => onInferenceEditsChange((current) => ({ ...current, [key]: event.target.value }))} />
          <button type="button" className="rounded-card border border-accent bg-accent px-2 py-1 text-xs font-medium text-white disabled:opacity-50" disabled={inferenceBusy}
            onClick={() => onInferenceDecision(item, cardSha, candidate, "accept")}>{t("pages.evidence.reconcile.inference.accept")}</button>
          <button type="button" className="rounded-card border border-border px-2 py-1 text-xs text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={inferenceBusy}
            onClick={() => onInferenceDecision(item, cardSha, candidate, "accept", inferenceEdits[key] ?? candidate.value)}>{t("pages.evidence.reconcile.inference.acceptEdited")}</button>
          <button type="button" className="rounded-card border border-warning/60 px-2 py-1 text-xs text-warning hover:bg-warning/10 disabled:opacity-50" disabled={inferenceBusy}
            onClick={() => onInferenceDecision(item, cardSha, candidate, "reject")}>{t("pages.evidence.reconcile.inference.reject")}</button>
        </div>
      </div>
    );
  };

  return (
    <section className="rounded-card border border-warning/40 bg-bg-hover/40 p-3" data-testid="evidence-diagnosis">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-warning">{t("pages.evidence.diagnosis.title")}</h3>
        <span className="text-[10px] text-text-muted">{t("pages.evidence.diagnosis.hint")}</span>
      </div>
      <p className="mt-2 text-xs text-text-secondary">{buildReconcileReasons(t, item).join(" · ")}</p>
      {item.untraceable_results.length ? (
        <div className="mt-2">
          <p className="text-[10px] text-text-muted">{t("pages.evidence.reconcile.preview.untraceable")}</p>
          <ul className="mt-0.5 list-disc pl-4 text-xs text-text-primary">{item.untraceable_results.slice(0, 3).map((row) => <li key={row}>{row}</li>)}</ul>
        </div>
      ) : null}
      {item.verbatim_candidates.length ? (
        <div className="mt-2">
          <p className="text-[10px] text-text-muted">{t("pages.evidence.reconcile.preview.verbatim")}</p>
          <ul className="mt-0.5 space-y-0.5 text-xs text-text-primary">{item.verbatim_candidates.slice(0, 3).map((row) => (
            <li key={row.result}>{t("pages.evidence.reconcile.preview.verbatimLine", { text: row.verbatim, similarity: row.similarity.toFixed(2) })}</li>
          ))}</ul>
        </div>
      ) : null}
      {item.date_hints.length ? (
        <div className="mt-2 flex flex-wrap items-center gap-1">
          <span className="text-[10px] text-text-muted">{t("pages.evidence.reconcile.preview.dateHints")}</span>
          {item.date_hints.slice(0, 4).map((hint) => <span className="rounded bg-bg-hover px-1 py-0.5 font-mono text-[10px] text-text-secondary" key={hint}>{hint}</span>)}
        </div>
      ) : null}
      {item.possible_duplicates.length ? (
        <p className="mt-2 text-xs text-text-secondary">{t("pages.evidence.reconcile.preview.duplicates", { ids: item.possible_duplicates.join("、") })}</p>
      ) : null}
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <label className="text-[10px] text-text-muted" htmlFor="evidence-triage-select">{t("pages.evidence.reconcile.triage.label")}</label>
        <select
          className="w-36 truncate rounded-card border border-border bg-bg-primary px-2 py-1 text-xs"
          data-testid="evidence-triage-select"
          id="evidence-triage-select"
          onChange={(event) => onChangeTriage(item, event.target.value as EvidenceTriageDecision | "")}
          value={item.triage && !item.triage.stale ? item.triage.decision : ""}
        >
          <option value="">{t("pages.evidence.reconcile.triage.none")}</option>
          <option value="needs_fill">{t("pages.evidence.reconcile.triage.needs_fill")}</option>
          <option value="not_for_display">{t("pages.evidence.reconcile.triage.not_for_display")}</option>
          {item.possible_duplicates.length > 0 ? (
            <option value="duplicate">{t("pages.evidence.reconcile.triage.duplicate", { id: item.possible_duplicates[0] })}</option>
          ) : null}
        </select>
      </div>
      {card && candidates.length ? (
        <div className="mt-2" data-testid="evidence-inference-candidates">
          <p className="text-[10px] text-text-muted">{t("pages.evidence.reconcile.preview.diagnosis")} · {t("pages.evidence.reconcile.inference.time")} / {t("pages.evidence.reconcile.inference.role")}</p>
          {high.map((candidate) => renderCandidate(candidate))}
          {low.length > 0 ? (showLowConfidence ? (
            <>
              {low.map((candidate) => renderCandidate(candidate, true))}
              <button type="button" className="mt-1 text-xs text-text-muted underline" onClick={() => onShowLowConfidence(false)}>{t("pages.evidence.reconcile.inference.hideLow")}</button>
            </>
          ) : (
            <button type="button" className="mt-1 text-xs text-text-muted underline" data-testid="evidence-inference-show-low" onClick={() => onShowLowConfidence(true)}>
              {t("pages.evidence.reconcile.inference.showLow", { count: low.length })}
            </button>
          )) : null}
        </div>
      ) : null}
    </section>
  );
}
