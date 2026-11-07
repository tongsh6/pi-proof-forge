import { useTranslation } from "react-i18next";
import { LoaderCircle, Play, RefreshCw } from "lucide-react";

type QuickRunPageHeaderProps = {
  running: boolean;
  canStartRun: boolean;
  startBlockerText: string;
  onRefresh: () => void;
  onStart: () => void;
};

/** Quick Run 页头：刷新与启动按钮（启动按钮带阻塞原因 title）。 */
export function QuickRunPageHeader({
  running,
  canStartRun,
  startBlockerText,
  onRefresh,
  onStart,
}: QuickRunPageHeaderProps) {
  const { t } = useTranslation();
  return (
    <header className="page-header">
      <div>
        <h1>{t("pages.quickRun.title")}</h1>
        <p className="page-subtitle">{t("pages.quickRun.subtitle")}</p>
      </div>
      <div className="page-actions">
        <button
          type="button"
          className="page-icon-button"
          onClick={onRefresh}
          disabled={running}
          title={t("common.refreshShortcut")}
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          <span className="sr-only">{t("common.refresh")}</span>
        </button>
        <button
          type="button"
          data-automation-id="quick-run-start"
          onClick={onStart}
          disabled={!canStartRun}
          title={canStartRun ? undefined : `${t("reasons.quickRun.title")}${startBlockerText}`}
          className="inline-flex h-10 items-center gap-2 rounded-card border border-accent bg-accent px-4 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {running ? (
            <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <Play className="h-4 w-4" aria-hidden="true" />
          )}
          {running
            ? t("pages.quickRun.running")
            : t("pages.quickRun.startRun")}
        </button>
      </div>
    </header>
  );
}
