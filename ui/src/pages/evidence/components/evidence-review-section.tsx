import { useTranslation } from "react-i18next";
import type { EvidenceDraftPayload } from "@/lib/sidecar/types";
import { EvidenceStatusBadge } from "./evidence-status-badge";

type EvidenceReviewSectionProps = {
  generatedDraft: EvidenceDraftPayload;
  reviewMissingItems: (string | false)[];
  busy: boolean;
  onSaveReviewedDraft: (saveMode: "incomplete" | "eligible") => void;
};

/** 模型草稿/重审区：缺失项提示与「保存不完整/保存合格」两个保存动作。 */
export function EvidenceReviewSection({
  generatedDraft,
  reviewMissingItems,
  busy,
  onSaveReviewedDraft,
}: EvidenceReviewSectionProps) {
  const { t } = useTranslation();
  return (
    <section className="rounded-card border border-success/40 bg-success/10 p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-text-primary">
            {t("pages.evidence.review.title")}
          </p>
          <p className="mt-1 text-xs text-text-secondary">
            {t("pages.evidence.review.source", {
              count: generatedDraft.source_material_ids.length,
            })}
          </p>
        </div>
        <EvidenceStatusBadge
          status={
            reviewMissingItems.length
              ? "draft_incomplete"
              : "draft_ready_for_review"
          }
        />
      </div>
      {reviewMissingItems.length ? (
        <p className="mt-3 text-xs text-warning">
          {t("pages.evidence.review.missing", {
            items: reviewMissingItems.join(", "),
          })}
        </p>
      ) : (
        <p className="mt-3 text-xs text-success">
          {t("pages.evidence.review.eligible")}
        </p>
      )}
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <button
          className="rounded-card border border-border px-3 py-2 text-sm text-text-primary transition-colors hover:bg-bg-hover disabled:cursor-not-allowed disabled:opacity-50"
          disabled={busy}
          onClick={() => onSaveReviewedDraft("incomplete")}
          type="button"
        >
          {t("pages.evidence.actions.saveIncomplete")}
        </button>
        <button
          className="rounded-card border border-success bg-success px-3 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={busy}
          onClick={() => onSaveReviewedDraft("eligible")}
          type="button"
        >
          {t("pages.evidence.actions.saveEligible")}
        </button>
      </div>
    </section>
  );
}
