import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";
import type { LoadState } from "../submissions-helpers";

type SubmissionsPageHeaderProps = {
  activeTab: "deliver" | "records";
  onTabChange: (tab: "deliver" | "records") => void;
  refreshing: boolean;
  retryingId: string | null;
  loadState: LoadState;
  error: string | null;
  onRefresh: () => void;
};

/** 投递记录页头：deliver/records 标签页与刷新；下方是加载/错误提示。 */
export function SubmissionsPageHeader({
  activeTab,
  onTabChange,
  refreshing,
  retryingId,
  loadState,
  error,
  onRefresh,
}: SubmissionsPageHeaderProps) {
  const { t } = useTranslation();
  return (
    <>
      <header className="page-header">
        <div>
          <h1>{t("pages.submissions.title")}</h1>
          <p className="page-subtitle">{t("pages.submissions.subtitle")}</p>
        </div>
        <div className="page-actions">
          <div className="seg-tabs" role="tablist" data-testid="submissions-tabs">
            {(["deliver", "records"] as const).map((tab) => (
              <button key={tab} type="button" role="tab" aria-selected={activeTab === tab} onClick={() => onTabChange(tab)}>
                {t(`pages.submissions.tabs.${tab}`)}
              </button>
            ))}
          </div>
          <button className="page-icon-button" disabled={retryingId !== null || refreshing} onClick={onRefresh} type="button" title={t("common.refreshShortcut")}>
            <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} aria-hidden="true" />
            <span className="sr-only">{refreshing ? t("common.refreshing") : t("pages.submissions.refresh")}</span>
          </button>
        </div>
      </header>

      {loadState === "loading" ? <p className="text-sm text-text-secondary">{t("common.loading")}</p> : null}
      {loadState === "error" ? <p className="text-sm text-error">{error}</p> : null}
      {error && loadState === "ready" ? <p className="text-sm text-error">{error}</p> : null}
    </>
  );
}
