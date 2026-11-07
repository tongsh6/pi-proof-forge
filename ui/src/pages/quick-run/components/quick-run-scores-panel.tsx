import { useTranslation } from "react-i18next";
import { PdfQualitySummary } from "@/components/pdf-quality-summary";
import { QualityReportPanel } from "@/components/quality-report";
import type { QuickRunStartResult } from "@/lib/sidecar/types";
import { SCORE_MAX } from "../quick-run-helpers";

type QuickRunScoresPanelProps = {
  quickRunResult: QuickRunStartResult | null;
  scoreBars: { key: string; score: number; reason: string; width: string }[];
  qualityDecisionNotice: string;
  onHighlightDecision: (highlightId: string, action: "reject" | "select") => void;
};

/** Quick Run 评分侧栏：总分、四层质量报告、语义评审与 K/D/S/Q/E/R 分项。 */
export function QuickRunScoresPanel({
  quickRunResult,
  scoreBars,
  qualityDecisionNotice,
  onHighlightDecision,
}: QuickRunScoresPanelProps) {
  const { t } = useTranslation();
  return (
    <aside className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
      <h2 className="text-lg font-semibold text-text-primary">
        {t("pages.quickRun.scores")}
      </h2>
      <div className="mt-4 rounded-card border border-border bg-bg-primary/60 p-4">
        <p className="text-xs uppercase text-text-muted">
          {t(quickRunResult?.semantic_review ? "pages.quickRun.semantic.fit" : "pages.quickRun.scoreLabels.total")}
        </p>
        <p className="mt-2 text-3xl font-semibold text-text-primary">
          {quickRunResult?.score_total ?? "--"}
        </p>
      </div>
      {quickRunResult?.quality_report && (
        <div className="mt-5">
          <QualityReportPanel report={quickRunResult.quality_report} onHighlightDecision={onHighlightDecision}/>
          {qualityDecisionNotice && <p role="status" className="mt-2 text-xs text-text-secondary">{qualityDecisionNotice}</p>}
        </div>
      )}
      {quickRunResult?.semantic_review ? (
        <div className="mt-5 space-y-4" data-testid="quick-run-semantic-review">
          <p className="text-xs text-text-secondary">{t("pages.quickRun.semantic.basis", { count: quickRunResult.semantic_review.reviewed_card_count ?? 0 })}</p>
          <PdfQualitySummary quality={{status:'current',matching_score:quickRunResult.semantic_review.fit_score,
            resume_score:quickRunResult.semantic_review.resume_score,expression_score:quickRunResult.semantic_review.expression_score,
            content_ready:quickRunResult.resume_readiness?.content_ready,quality_passed:quickRunResult.resume_readiness?.quality_passed,
            gap_tasks:quickRunResult.resume_readiness?.gap_tasks}}/>
          <div className="max-h-[38rem] space-y-2 overflow-auto">
            {quickRunResult.semantic_review.assessment_scope&&<p className="text-xs text-text-secondary">{t('quality.scope',{...quickRunResult.semantic_review.assessment_scope})}</p>}
            {quickRunResult.semantic_review.requirements.map((row) => (
              <details key={row.requirement_id} className="rounded-card border border-border p-3 text-xs">
                <summary className="cursor-pointer break-words font-medium text-text-primary">{row.text.slice(0, 80)}{row.text.length > 80 ? "…" : ""}<span className="mt-1 block text-text-secondary">{t(`pages.quickRun.semantic.status.${row.resume_status}`)}</span></summary>
                <p className="mt-3 break-words">{row.text}</p>
                <p className="mt-2 text-text-secondary">{t("pages.quickRun.semantic.poolStatus")}: {t(`pages.quickRun.semantic.status.${row.status}`)}</p>
                <p className="mt-2 break-words text-text-secondary">{row.reason}</p>
                {row.checks?.map(check=><div className="mt-3 border-t border-border pt-2" key={check.requirement_id}>
                  <p className="break-words font-medium">{check.criterion}</p>
                  <p className="mt-1 text-text-secondary">{t('pages.quickRun.semantic.poolStatus')}: {t(`pages.quickRun.semantic.status.${check.status}`)} · {t('quality.inResume')}: {t(`pages.quickRun.semantic.status.${check.resume_status}`)}</p>
                  <p className="mt-1 break-words text-text-secondary">{check.reason}</p>
                </div>)}
                {row.citations.map((citation, index) => (
                  <blockquote key={`${citation.fact_id}-${index}`} className="mt-3 break-words border-l-2 border-accent pl-2 text-text-secondary">
                    <p>{citation.quote}</p>
                    <footer className="mt-1 text-text-muted">{citation.source_id} · {citation.field} · {t(citation.in_resume ? "pages.quickRun.semantic.present" : "pages.quickRun.semantic.absent")}</footer>
                  </blockquote>
                ))}
              </details>
            ))}
          </div>
        </div>
      ) : quickRunResult ? (
      <div className="mt-5 space-y-4">
        {scoreBars.map((item) => (
          <div key={item.key}>
            <div className="mb-1 flex items-center justify-between gap-2 text-xs">
              <span
                className="truncate font-medium text-text-primary"
                title={t(`pages.quickRun.scoreLabelsFull.${item.key}`)}
              >
                {item.key} · {t(`pages.quickRun.scoreLabelsFull.${item.key}`)}
              </span>
              <span className="shrink-0 text-text-secondary">{item.score}</span>
            </div>
            <div
              className="h-2 overflow-hidden rounded-chip bg-bg-primary"
              role="progressbar"
              aria-label={t(`pages.quickRun.scoreLabelsFull.${item.key}`)}
              aria-valuemin={0}
              aria-valuemax={SCORE_MAX}
              aria-valuenow={item.score}
            >
              <div
                className="h-full rounded-chip bg-accent"
                style={{ width: item.width }}
              />
            </div>
            {item.reason ? (
              <p className="mt-1 line-clamp-2 text-xs text-text-muted">
                {item.reason}
              </p>
            ) : null}
          </div>
        ))}
      </div>
      ) : null}
      {quickRunResult?.score_total == null ? (
        <p className="mt-5 text-xs text-text-secondary">
          {t("pages.quickRun.scoreLabels.empty")}
        </p>
      ) : null}
    </aside>
  );
}
