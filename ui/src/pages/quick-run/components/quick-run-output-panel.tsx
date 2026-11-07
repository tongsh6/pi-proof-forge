import { useTranslation } from "react-i18next";
import type { QuickRunStartResult } from "@/lib/sidecar/types";

type QuickRunOutputPanelProps = {
  quickRunStatus: string | null;
  quickRunId: string | null;
  selectedProfileTitle: string;
  evidenceCount: number;
  quickRunResult: QuickRunStartResult | null;
  terminalLines: string[];
  manualDeliveryOnly: boolean | undefined;
  onNavigate: (path: string) => void;
};

/** Quick Run 阶段输出：结果提示、准备 PDF 动作与终端日志。 */
export function QuickRunOutputPanel({
  quickRunStatus,
  quickRunId,
  selectedProfileTitle,
  evidenceCount,
  quickRunResult,
  terminalLines,
  manualDeliveryOnly,
  onNavigate,
}: QuickRunOutputPanelProps) {
  const { t } = useTranslation();
  return (
    <article className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-text-primary">
            {t("pages.quickRun.stageOutput")}
          </h2>
          <p className="mt-1 text-xs text-text-secondary">
            {quickRunStatus
              ? t("pages.quickRun.runStatus", {
                  status: quickRunStatus,
                  runId: quickRunId,
                })
              : `${selectedProfileTitle} · ${evidenceCount} ${t(
                  "pages.quickRun.evidenceCards"
                )}`}
          </p>
        </div>
      </div>
      {quickRunResult && <div className="mt-4 space-y-2 text-sm">
        {quickRunResult.career_direction&&<div className={`rounded-card border p-3 ${quickRunResult.career_direction.status === "excluded" ? "border-warning/50 bg-warning/10" : "border-border"}`} data-testid="career-direction-result">
          <p className="font-semibold">{t(`pages.quickRun.direction.${quickRunResult.career_direction.status}`)}</p>
          <p>{quickRunResult.career_direction.reason}</p>
          <p className="mt-2 text-xs text-text-secondary">{t('pages.quickRun.direction.preference')}：{quickRunResult.career_direction.preference.text}</p>
          <blockquote className="mt-2 border-l-2 border-accent pl-2 text-xs">{quickRunResult.career_direction.jd_quote}</blockquote>
          <p className="mt-2 text-xs text-text-secondary">{t('pages.quickRun.direction.advisory')}</p>
        </div>}
        <p>{t(quickRunResult.resume_readiness?.status === "NOT_GENERATED" ? "pages.quickRun.notGenerated" : quickRunResult.resume_readiness?.content_ready ? "pages.quickRun.reviewNext" : "pages.quickRun.needsEvidence")}</p>
        {quickRunResult.status === "DONE" && quickRunResult.resume_readiness?.content_ready === true &&
          quickRunResult.traceability?.resume_traceable === true && quickRunResult.resume_pdf ?
          (manualDeliveryOnly ? (
            <div className="space-y-2">
              <p className="text-xs text-warning" data-testid="quick-run-manual-delivery-result">
                {t("pages.quickRun.manualDeliveryHint", { path: quickRunResult.resume_pdf })}
              </p>
              <button type="button" data-testid="quick-run-record-manual" className="rounded-card border border-border px-3 py-2 text-text-primary"
                onClick={() => onNavigate("/jobs")}>{t("pages.quickRun.goRecordManual")}</button>
            </div>
          ) : (
            <div className="space-y-2">
              <button type="button" data-testid="quick-run-prepare-pdf" className="rounded-card border border-accent px-3 py-2 text-accent"
                onClick={() => onNavigate(`/submissions?quick_run_id=${encodeURIComponent(quickRunResult.run_id)}`)}>{t(quickRunResult.resume_readiness?.quality_passed === false ? "pages.quickRun.preparePdfAnyway" : "pages.quickRun.preparePdf")}</button>
              {quickRunResult.resume_readiness?.quality_passed === false &&
                <p className="text-xs text-warning">{t("pages.quickRun.qualityNotPassedCanContinue")}</p>}
            </div>
          )) :
          <button type="button" className="text-accent underline" onClick={() => onNavigate(quickRunResult.status === "SKIPPED" ? "/jobs" : "/evidence")}>{t(quickRunResult.status === "SKIPPED" ? "pages.quickRun.chooseAnotherJob" : "pages.quickRun.openEvidence")}</button>}
      </div>}
      <div className="mt-4 h-[360px] overflow-auto rounded-card border border-border bg-bg-primary p-4 font-mono text-xs leading-6 text-text-secondary">
        {terminalLines.length > 0 ? (
          terminalLines.map((line, index) => (
            <p key={`${index}-${line}`} className="whitespace-pre-wrap break-words">
              <span className="text-text-muted">
                {String(index + 1).padStart(3, "0")}
              </span>{" "}
              {line}
            </p>
          ))
        ) : (
          <p className="text-text-muted">{t("pages.quickRun.noLogs")}</p>
        )}
      </div>
    </article>
  );
}
