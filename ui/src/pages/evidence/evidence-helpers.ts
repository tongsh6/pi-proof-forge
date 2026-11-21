import type { useTranslation } from "react-i18next";
import type {
  EvidenceDetail,
  EvidenceFilters,
  EvidenceInferenceResult,
  EvidenceListItem,
  EvidenceReconcileItem,
  EvidenceReconcileResult,
} from "@/lib/sidecar/types";

/** 页面与子组件共享的翻译函数类型（来自 react-i18next 的 TFunction）。 */
export type Translate = ReturnType<typeof useTranslation>["t"];

export type LoadState = "loading" | "ready" | "error";
export type SaveState = "idle" | "saving" | "saved";
export type EvidenceImportMode = "create" | "append" | "replace";
export type ProblemFilter =
  | "all"
  | "eligible"
  | "incomplete"
  | "legacy"
  | "untraceable"
  | "missing_time"
  | "duplicate"
  | "inference"
  | "needs_fill"
  | "triaged";

export type EvidenceForm = {
  title: string;
  time_range: string;
  context: string;
  role_scope: string;
  actions: string[];
  results: string[];
  stackText: string;
  tagsText: string;
};

export type SummaryCount = { key: ProblemFilter; label: string; count: number };

export const DEFAULT_FILTERS: EvidenceFilters = {
  query: "",
  status: null,
  role: null,
  tags: [],
  date_range: null,
};

export function parseCommaList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

export function toForm(detail: EvidenceDetail | null): EvidenceForm {
  return {
    title: detail?.title ?? "",
    time_range: detail?.time_range ?? "",
    context: detail?.context ?? "",
    role_scope: detail?.role_scope ?? "",
    actions: detail?.actions ?? [],
    results: detail?.results ?? [],
    stackText: detail?.stack.join(", ") ?? "",
    tagsText: detail?.tags.join(", ") ?? "",
  };
}

export function formatFallback(value: string): string {
  return value.trim() ? value : "--";
}

export function formatBytes(value: number | undefined): string {
  if (!value || value <= 0) return "--";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.round(value / 102.4) / 10} KB`;
  return `${Math.round(value / 1024 / 102.4) / 10} MB`;
}

export function statusTone(status: string): string {
  if (status === "ready" || status === "pass") {
    return "border-success/40 bg-success/10 text-success";
  }
  if (
    status === "gap" ||
    status === "needs_review" ||
    status === "saved_incomplete"
  ) {
    return "border-warning/40 bg-warning/10 text-warning";
  }
  if (status === "draft" || status === "draft_incomplete") {
    return "border-border bg-bg-hover text-text-secondary";
  }
  if (status === "saved_eligible" || status === "draft_ready_for_review") {
    return "border-success/40 bg-success/10 text-success";
  }
  return "border-accent/40 bg-accent/10 text-accent";
}

export function inferenceCandidateKey(
  evidenceId: string,
  field: string,
  candidateHash: string
): string {
  return `${evidenceId}:${field}:${candidateHash}`;
}

/** 详情面板「对账发现」区的可读原因列表。 */
export function buildReconcileReasons(
  t: Translate,
  item: EvidenceReconcileItem
): string[] {
  const reasons: string[] = [];
  if (item.untraceable_results.length > 0)
    reasons.push(
      t("pages.evidence.reconcile.reasons.untraceable", {
        count: item.untraceable_results.length,
      })
    );
  if (!item.has_source) reasons.push(t("pages.evidence.reconcile.reasons.noSource"));
  if (item.missing_fields.includes("time_range"))
    reasons.push(
      item.date_hints.length > 0
        ? t("pages.evidence.reconcile.reasons.missingTimeHint", {
            hints: item.date_hints.slice(0, 3).join("、"),
          })
        : t("pages.evidence.reconcile.reasons.missingTime")
    );
  if (item.missing_fields.includes("role_scope"))
    reasons.push(t("pages.evidence.reconcile.reasons.missingRole"));
  if (item.missing_fields.includes("results"))
    reasons.push(t("pages.evidence.reconcile.reasons.missingResults"));
  if (item.missing_fields.includes("artifacts"))
    reasons.push(t("pages.evidence.reconcile.reasons.missingArtifacts"));
  if (item.possible_duplicates.length > 0)
    reasons.push(
      t("pages.evidence.reconcile.reasons.duplicate", {
        ids: item.possible_duplicates.join("、"),
      })
    );
  return reasons;
}

/** 汇总条计数；对账未完成时回落到本地列表长度。 */
export function buildSummaryCounts(
  t: Translate,
  input: {
    itemsLength: number;
    reconcile: EvidenceReconcileResult | null;
    inference: EvidenceInferenceResult | null;
  }
): SummaryCount[] {
  const summary = input.reconcile?.summary;
  return [
    {
      key: "all",
      label: t("pages.evidence.summary.all"),
      count: summary?.total ?? input.itemsLength,
    },
    { key: "eligible", label: t("pages.evidence.reconcile.pool.eligible"), count: summary?.eligible ?? 0 },
    { key: "incomplete", label: t("pages.evidence.reconcile.pool.incomplete"), count: summary?.incomplete ?? 0 },
    { key: "legacy", label: t("pages.evidence.reconcile.pool.legacy"), count: summary?.legacy ?? 0 },
    { key: "untraceable", label: t("pages.evidence.summary.untraceable"), count: summary?.untraceable_cards ?? 0 },
    { key: "missing_time", label: t("pages.evidence.summary.missingTime"), count: summary?.missing_time_range ?? 0 },
    { key: "duplicate", label: t("pages.evidence.summary.duplicate"), count: summary?.duplicate_cards ?? 0 },
    { key: "inference", label: t("pages.evidence.summary.inference"), count: input.inference?.summary.candidates ?? 0 },
    { key: "needs_fill", label: t("pages.evidence.summary.needsFill"), count: summary?.needs_fill ?? 0 },
    { key: "triaged", label: t("pages.evidence.summary.triaged"), count: summary?.triaged_out ?? 0 },
  ];
}

/** 列表行的问题标签（与汇总条筛选同源）。 */
export function buildProblemTags(
  evidenceId: string,
  input: {
    reconcileItemByCard: Map<string, EvidenceReconcileItem>;
    inferenceByCard: Map<string, EvidenceInferenceResult["cards"][number]>;
  }
): string[] {
  const tags: string[] = [];
  const item = input.reconcileItemByCard.get(evidenceId);
  if (item) {
    if (item.untraceable_results.length > 0) tags.push("untraceable");
    if (item.missing_fields.includes("time_range")) tags.push("missing_time");
    if (item.possible_duplicates.length > 0) tags.push("duplicate");
    if (item.triage && !item.triage.stale)
      tags.push(item.triage.decision === "needs_fill" ? "needs_fill" : "triaged");
  }
  if ((input.inferenceByCard.get(evidenceId)?.candidates ?? []).length > 0)
    tags.push("inference");
  return tags;
}

/** 按汇总条问题类型过滤列表。 */
export function filterEvidenceItems(
  items: EvidenceListItem[],
  problemFilter: ProblemFilter,
  tagsFor: (evidenceId: string) => string[]
): EvidenceListItem[] {
  if (problemFilter === "all") return items;
  return items.filter((item) => {
    const tags = tagsFor(item.evidence_id);
    switch (problemFilter) {
      case "eligible": return item.candidate_pool_eligible === true;
      case "incomplete": return ["saved_incomplete", "needs_review"].includes(item.status);
      case "legacy": return !["saved_eligible", "ready", "pass"].includes(item.status);
      case "untraceable": return tags.includes("untraceable");
      case "missing_time": return tags.includes("missing_time");
      case "duplicate": return tags.includes("duplicate");
      case "inference": return tags.includes("inference");
      case "needs_fill": return tags.includes("needs_fill");
      case "triaged": return tags.includes("triaged");
      default: return true;
    }
  });
}
