import { useTranslation } from "react-i18next";
import { statusTone } from "../evidence-helpers";

/** 证据状态徽标：未知状态回落到本地化 key，最后回落到原值。 */
export function EvidenceStatusBadge({ status }: { status: string }) {
  const { t } = useTranslation();
  const normalized = status || "ready";
  const label =
    normalized === "ready"
      ? t("pages.evidence.status.ready")
      : t(`pages.evidence.status.${normalized}`, { defaultValue: normalized });
  return (
    <span
      className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium ${statusTone(
        normalized
      )}`}
    >
      {label}
    </span>
  );
}
