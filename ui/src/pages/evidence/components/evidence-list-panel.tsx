import { useTranslation } from "react-i18next";
import { Search } from "lucide-react";
import type { EvidenceListItem } from "@/lib/sidecar/types";
import { formatFallback } from "../evidence-helpers";
import type { ProblemFilter, SummaryCount } from "../evidence-helpers";
import { EvidenceStatusBadge } from "./evidence-status-badge";

type EvidenceListPanelProps = {
  items: EvidenceListItem[];
  filteredItems: EvidenceListItem[];
  selectedId: string | null;
  listTruncated: boolean;
  problemFilter: ProblemFilter;
  summaryCounts: SummaryCount[];
  queryInput: string;
  roleInput: string;
  tagInput: string;
  onProblemFilterChange: (filter: ProblemFilter) => void;
  onQueryInputChange: (value: string) => void;
  onRoleInputChange: (value: string) => void;
  onTagInputChange: (value: string) => void;
  onApplyFilters: () => void;
  onResetFilters: () => void;
  onSelect: (evidenceId: string) => void;
  problemTagsFor: (evidenceId: string) => string[];
};

/** 证据列表：筛选表单、截断提示与问题标签表格。 */
export function EvidenceListPanel({
  items,
  filteredItems,
  selectedId,
  listTruncated,
  problemFilter,
  summaryCounts,
  queryInput,
  roleInput,
  tagInput,
  onProblemFilterChange,
  onQueryInputChange,
  onRoleInputChange,
  onTagInputChange,
  onApplyFilters,
  onResetFilters,
  onSelect,
  problemTagsFor,
}: EvidenceListPanelProps) {
  const { t } = useTranslation();
  return (
    <section className="overflow-hidden rounded-panel border border-border bg-bg-panel shadow-[var(--shadow-panel)]">
      <div className="border-b border-border px-5 py-4">
        <div className="flex items-baseline gap-3">
          <h2 className="text-lg font-semibold text-text-primary">
            {t("pages.evidence.listTitle")}
          </h2>
          <p className="text-sm text-text-secondary">
            {t("pages.evidence.listCount", { count: filteredItems.length })}
          </p>
          {listTruncated ? (
            <p className="text-xs text-warning" data-testid="evidence-list-truncated">
              {t("pages.evidence.listTruncated", { count: items.length })}
            </p>
          ) : null}
        </div>
        <form
          className="mt-3 flex flex-wrap items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            onApplyFilters();
          }}
        >
          <label className="relative min-w-[220px] flex-1">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-muted"
              size={16}
            />
            <input
              className="w-full rounded-card border border-border bg-bg-hover py-2 pl-9 pr-3 text-sm text-text-primary outline-none focus:border-accent"
              onChange={(event) => onQueryInputChange(event.target.value)}
              placeholder={t("pages.evidence.filters.queryPlaceholder")}
              type="text"
              value={queryInput}
            />
          </label>
          <select
            className="rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
            aria-label={t("pages.evidence.summary.filterLabel")}
            data-testid="evidence-problem-filter"
            onChange={(event) => onProblemFilterChange(event.target.value as ProblemFilter)}
            value={problemFilter}
          >
            {summaryCounts.map((entry) => (
              <option key={entry.key} value={entry.key}>{entry.label}</option>
            ))}
          </select>
          <input
            className="w-36 rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
            onChange={(event) => onRoleInputChange(event.target.value)}
            placeholder={t("pages.evidence.filters.rolePlaceholder")}
            type="text"
            value={roleInput}
          />
          <input
            className="w-44 rounded-card border border-border bg-bg-hover px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
            onChange={(event) => onTagInputChange(event.target.value)}
            placeholder={t("pages.evidence.filters.tagsPlaceholder")}
            type="text"
            value={tagInput}
          />
          <button
            className="rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90"
            type="submit"
          >
            {t("pages.evidence.actions.apply")}
          </button>
          <button
            className="rounded-card border border-border px-4 py-2 text-sm text-text-primary transition-colors hover:bg-bg-hover"
            onClick={onResetFilters}
            type="button"
          >
            {t("pages.evidence.actions.reset")}
          </button>
        </form>
      </div>

      {filteredItems.length === 0 ? (
        <div className="p-8 text-sm text-text-secondary" data-testid="evidence-list-empty-filter">
          {t("pages.evidence.empty.filtered")}
        </div>
      ) : (
        <div className="max-h-[calc(100vh-20rem)] overflow-auto">
          <table className="w-full min-w-[640px] table-fixed text-left">
            <thead className="sticky top-0 z-10 bg-bg-panel text-xs uppercase tracking-[0.14em] text-text-muted">
              <tr className="bg-bg-hover/70">
                <th className="w-[36%] px-5 py-3 font-semibold">
                  {t("pages.evidence.fields.title")}
                </th>
                <th className="w-[17%] px-4 py-3 font-semibold">
                  {t("pages.evidence.fields.timeRange")}
                </th>
                <th className="w-[19%] px-4 py-3 font-semibold">
                  {t("pages.evidence.fields.role")}
                </th>
                <th className="w-[8%] px-3 py-3 font-semibold">
                  {t("pages.evidence.fields.sourceCount")}
                </th>
                <th className="w-[20%] px-4 py-3 font-semibold">
                  {t("pages.evidence.fields.status")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filteredItems.map((item) => {
                const isSelected = item.evidence_id === selectedId;
                const tags = problemTagsFor(item.evidence_id);
                return (
                  <tr
                    key={item.evidence_id}
                    className={`cursor-pointer transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/40 ${
                      isSelected ? "bg-accent/10" : "hover:bg-bg-hover/50"
                    }`}
                    aria-selected={isSelected}
                    tabIndex={0}
                    onClick={() => onSelect(item.evidence_id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onSelect(item.evidence_id);
                      }
                    }}
                  >
                    <td className="px-5 py-4">
                      <p className="truncate text-sm font-medium text-text-primary" title={item.title}>
                        {item.title}
                      </p>
                    </td>
                    <td className="whitespace-nowrap px-4 py-4 text-sm text-text-secondary">
                      <span className="inline-flex items-center gap-1.5">
                        {formatFallback(item.time_range)}
                        <span className="rounded bg-bg-hover px-1 py-0.5 font-mono text-[10px] text-text-muted">{item.time_range_level ?? "L1"}</span>
                      </span>
                    </td>
                    <td className="px-4 py-4 text-sm text-text-secondary">
                      <p className="truncate" title={formatFallback(item.role_scope)}>
                        {formatFallback(item.role_scope)}
                      </p>
                      <span className="mt-0.5 inline-block rounded bg-bg-hover px-1 py-0.5 font-mono text-[10px] text-text-muted">{item.role_scope_level ?? "L1"}</span>
                    </td>
                    <td className="px-3 py-4 text-sm text-text-secondary">
                      {item.source_document_count ? `${item.source_document_count} 份` : "—"}
                    </td>
                    <td className="px-4 py-4">
                      <div className="flex flex-wrap items-center gap-1">
                        <EvidenceStatusBadge status={item.candidate_pool_eligible === false && ["ready", "pass"].includes(item.status) ? "needs_review" : item.status} />
                        {tags.slice(0, 3).map((tag) => (
                          <span key={tag} className="rounded border border-border px-1 py-0.5 text-[10px] text-text-muted">
                            {t(`pages.evidence.summary.tags.${tag}`, { defaultValue: tag })}
                          </span>
                        ))}
                        {tags.length > 3 ? <span className="text-[10px] text-text-muted">+{tags.length - 3}</span> : null}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
