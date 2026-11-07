import type { TFunction } from "react-i18next";
import { Plus, RefreshCw, Sparkles } from "lucide-react";

type EvidencePageHeaderProps = {
  t: TFunction;
  busy: boolean;
  refreshing: boolean;
  onRefresh: () => void;
  onOpenDrawer: () => void;
  onCreateDraft: () => void;
};

/** 证据页页头：标题、刷新、材料蒸馏抽屉入口与新建草稿。 */
export function EvidencePageHeader({
  t,
  busy,
  refreshing,
  onRefresh,
  onOpenDrawer,
  onCreateDraft,
}: EvidencePageHeaderProps) {
  return (
    <header className="page-header">
      <div>
        <h1>{t("pages.evidence.title")}</h1>
        <p className="page-subtitle">{t("pages.evidence.subtitle")}</p>
      </div>
      <div className="page-actions">
        <button
          type="button"
          className="page-icon-button"
          disabled={busy || refreshing}
          onClick={onRefresh}
          title={t("common.refreshShortcut")}
        >
          <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} />
          <span className="sr-only">{refreshing ? t("common.refreshing") : t("pages.evidence.actions.refresh")}</span>
        </button>
        <button
          className="inline-flex items-center gap-2 rounded-card border border-border px-4 py-2 text-sm text-text-primary transition-colors hover:bg-bg-hover disabled:cursor-not-allowed disabled:opacity-50"
          data-testid="evidence-open-drawer"
          disabled={busy}
          onClick={onOpenDrawer}
          type="button"
        >
          <Sparkles size={16} />
          {t("pages.evidence.actions.distill")}
        </button>
        <button
          className="inline-flex items-center gap-2 rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={busy}
          onClick={onCreateDraft}
          type="button"
        >
          <Plus size={16} />
          {t("pages.evidence.actions.new")}
        </button>
      </div>
    </header>
  );
}
