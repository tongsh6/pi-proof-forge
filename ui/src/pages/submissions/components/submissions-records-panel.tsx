import { useTranslation } from "react-i18next";
import { Eye, RotateCcw } from "lucide-react";
import type { SubmissionListItem } from "@/lib/sidecar/types";
import type { LoadState, StatItem } from "../submissions-helpers";
import {
  channelClassName,
  channelLabel,
  formatDate,
  statusClassName,
  submissionStatusLabel,
} from "../submissions-helpers";

type SubmissionsStatsStripProps = {
  stats: StatItem[];
};

/** 投递记录统计条。 */
export function SubmissionsStatsStrip({ stats }: SubmissionsStatsStripProps) {
  const { t } = useTranslation();
  return (
    <section className="stat-strip" data-testid="submissions-stats">
      {stats.map((stat) => {
        const Icon = stat.icon;
        return (
          <span key={stat.key} className="inline-flex items-baseline gap-1.5">
            <Icon className={`h-3.5 w-3.5 self-center ${stat.className.split(" ").find((name) => name.startsWith("text-")) ?? ""}`} aria-hidden="true" />
            <strong>{stat.value}</strong>
            {t(`pages.submissions.stats.${stat.key}`)}
          </span>
        );
      })}
    </section>
  );
}

type SubmissionsRunsPanelProps = {
  items: SubmissionListItem[];
  selectedId: string | null;
  detailState: LoadState;
  retryingId: string | null;
  onSelect: (submissionId: string) => void;
  onRetry: (submissionId: string) => void;
};

/** 投递运行记录列表。 */
export function SubmissionsRunsPanel({
  items,
  selectedId,
  detailState,
  retryingId,
  onSelect,
  onRetry,
}: SubmissionsRunsPanelProps) {
  const { t, i18n } = useTranslation();
  return (
    <section className="rounded-panel border border-border bg-bg-panel shadow-[var(--shadow-panel)]">
      <div className="border-b border-border px-5 py-4">
        <h2 className="text-lg font-semibold text-text-primary">{t("pages.submissions.runsTitle")}</h2>
      </div>
      <div className="overflow-x-auto">
        <div className="min-w-[640px]">
          <div className="grid grid-cols-[minmax(110px,1.05fr)_minmax(120px,1.05fr)_76px_118px_70px_58px] gap-3 border-b border-border px-5 py-3 text-xs font-medium uppercase tracking-[0.08em] text-text-muted">
            <span>{t("pages.submissions.table.company")}</span>
            <span>{t("pages.submissions.table.position")}</span>
            <span>{t("pages.submissions.table.channel")}</span>
            <span>{t("pages.submissions.table.date")}</span>
            <span>{t("pages.submissions.table.status")}</span>
            <span className="text-right">{t("pages.submissions.table.action")}</span>
          </div>
          <div className="divide-y divide-border">
            {items.map((item) => (
              <div key={item.submission_id} className={`grid grid-cols-[minmax(110px,1.05fr)_minmax(120px,1.05fr)_76px_118px_70px_58px] gap-3 px-5 py-4 text-sm ${selectedId === item.submission_id ? "bg-accent/5" : ""}`}>
                <div className="min-w-0">
                  <p className="truncate font-medium text-text-primary">{item.company || item.submission_id}</p>
                </div>
                <div className="min-w-0">
                  <p className="truncate text-text-primary">{item.position || "--"}</p>
                  <p className="mt-1 truncate text-xs text-text-secondary">{item.mode ? t(`codes.mode.${item.mode}`, { defaultValue: item.mode }) : "--"}</p>
                </div>
                <div className="min-w-0">
                  <span className={`inline-flex max-w-full rounded-chip border px-2 py-0.5 text-xs font-medium ${channelClassName(item.channel)}`}>
                    <span className="truncate">{t(`codes.platform.${item.channel}`, { defaultValue: channelLabel(item, t("pages.submissions.unknownChannel")) })}</span>
                  </span>
                </div>
                <p className="truncate text-text-secondary">{formatDate(item.submitted_at, i18n.language)}</p>
                <div>
                  <span className={`rounded-chip border px-2 py-0.5 text-xs font-medium ${statusClassName(item.status)}`}>
                    {submissionStatusLabel(item.status, t)}
                  </span>
                  {item.platform_feedback?.status && <p className="mt-1 truncate text-xs text-text-secondary">{t(`pages.submissions.platformFeedback.status.${item.platform_feedback.status}`, {defaultValue: item.platform_feedback.status})}{item.platform_feedback.time_label ? ` · ${item.platform_feedback.time_label}` : ""}</p>}
                </div>
                <div className="flex justify-end gap-2">
                  <button className="grid h-9 w-9 place-items-center rounded-card border border-border text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={detailState === "loading" && selectedId === item.submission_id} onClick={() => onSelect(item.submission_id)} title={t("pages.submissions.details")} type="button" aria-label={t("pages.submissions.details")}>
                    <Eye className="h-4 w-4" aria-hidden="true" />
                  </button>
                  <button className="grid h-9 w-9 place-items-center rounded-card border border-border text-text-primary hover:bg-bg-hover disabled:opacity-50" disabled={retryingId !== null || item.retry_allowed === false} onClick={() => onRetry(item.submission_id)} title={item.retry_allowed === false ? t("pages.submissions.apiRetryBlocked") : retryingId === item.submission_id ? t("pages.submissions.retrying") : t("common.retry")} type="button" aria-label={retryingId === item.submission_id ? t("pages.submissions.retrying") : t("common.retry")}>
                    <RotateCcw className={`h-4 w-4 ${retryingId === item.submission_id ? "animate-spin" : ""}`} aria-hidden="true" />
                  </button>
                </div>
              </div>
            ))}
            {items.length === 0 ? <div className="p-5 text-sm text-text-secondary">{t("pages.submissions.empty")}</div> : null}
          </div>
        </div>
      </div>
    </section>
  );
}
