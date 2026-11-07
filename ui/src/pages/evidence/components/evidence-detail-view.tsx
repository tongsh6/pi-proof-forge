import { useTranslation } from "react-i18next";
import type { Dispatch, SetStateAction } from "react";
import type { EvidenceDetail } from "@/lib/sidecar/types";
import { parseCommaList } from "../evidence-helpers";
import type { EvidenceForm } from "../evidence-helpers";

type EvidenceDetailViewProps = {
  detail: EvidenceDetail | null;
  form: EvidenceForm;
  editing: boolean;
  busy: boolean;
  setForm: Dispatch<SetStateAction<EvidenceForm>>;
};

/** 详情栏主体：只读展示（默认）与编辑表单（编辑/草稿/重审时）。 */
export function EvidenceDetailView({
  detail,
  form,
  editing,
  busy,
  setForm,
}: EvidenceDetailViewProps) {
  const { t } = useTranslation();

  if (!editing) {
    return (
      <div className="space-y-4" data-testid="evidence-detail-view">
        <div>
          <h3 className="text-lg font-semibold text-text-primary">{form.title || t("pages.evidence.fields.title")}</h3>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-text-secondary">
            <span>{form.time_range || "—"}<span className="ml-1 rounded bg-bg-hover px-1 py-0.5 font-mono text-[10px] text-text-muted">{detail?.time_range_provenance?.level ?? "L1"}</span></span>
            <span>·</span>
            <span>{form.role_scope || "—"}<span className="ml-1 rounded bg-bg-hover px-1 py-0.5 font-mono text-[10px] text-text-muted">{detail?.role_scope_provenance?.level ?? "L1"}</span></span>
          </p>
          {detail?.source_documents?.length ? (
            <p className="mt-1 truncate text-xs text-text-muted">
              {t("pages.evidence.fields.sourceMaterials")}：{detail.source_documents.map((doc) => doc.label).join("、")}
            </p>
          ) : null}
        </div>
        {(
          [
            ["context", form.context, "text-text-primary"],
            ["actions", form.actions, "text-text-primary"],
            ["results", form.results, "text-success"],
          ] as const
        ).map(([field, value, className]) => (
          <div key={field}>
            <p className="text-xs uppercase tracking-[0.16em] text-text-muted">{t(`pages.evidence.fields.${field}`)}</p>
            <p className={`mt-1 whitespace-pre-wrap break-words text-sm ${className}`}>{value || "--"}</p>
          </div>
        ))}
        {form.stackText || form.tagsText ? (
          <div className="flex flex-wrap gap-2">
            {parseCommaList(`${form.stackText},${form.tagsText}`).map((item) => (
              <span key={item} className="rounded-chip border border-border bg-bg-hover px-2.5 py-1 text-xs text-text-secondary">
                {item}
              </span>
            ))}
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <>
      <label className="block rounded-card border border-border bg-bg-hover/50 p-3">
        <span className="text-xs uppercase tracking-[0.16em] text-text-muted">
          {t("pages.evidence.fields.title")}
        </span>
        <input
          className="mt-2 w-full bg-transparent text-base font-semibold text-text-primary outline-none"
          disabled={busy}
          onChange={(event) =>
            setForm((current) => ({
              ...current,
              title: event.target.value,
            }))
          }
          placeholder={t("pages.evidence.fields.title")}
          type="text"
          value={form.title}
        />
      </label>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-1">
        <label className="block rounded-card border border-border bg-bg-hover/50 p-3">
          <span className="text-xs uppercase tracking-[0.16em] text-text-muted">
            {t("pages.evidence.fields.timeRange")}
          </span>
          <input
            className="mt-2 w-full bg-transparent text-sm text-text-primary outline-none"
            disabled={busy}
            onChange={(event) =>
              setForm((current) => ({
                ...current,
                time_range: event.target.value,
              }))
            }
            type="text"
            value={form.time_range}
          />
        </label>
        <label className="block rounded-card border border-border bg-bg-hover/50 p-3">
          <span className="text-xs uppercase tracking-[0.16em] text-text-muted">
            {t("pages.evidence.fields.role")}
          </span>
          <input
            className="mt-2 w-full bg-transparent text-sm text-text-primary outline-none"
            disabled={busy}
            onChange={(event) =>
              setForm((current) => ({
                ...current,
                role_scope: event.target.value,
              }))
            }
            type="text"
            value={form.role_scope}
          />
        </label>
      </div>

      {[
        ["context", "min-h-20"],
        ["actions", "min-h-24"],
        ["results", "min-h-24 text-success"],
      ].map(([field, className]) => (
        <label
          key={field}
          className="block rounded-card border border-border bg-bg-hover/50 p-3"
        >
          <span className="text-xs uppercase tracking-[0.16em] text-text-muted">
            {t(`pages.evidence.fields.${field}`)}
          </span>
          <textarea
            className={`mt-2 w-full resize-y bg-transparent text-sm outline-none ${className}`}
            disabled={busy}
            onChange={(event) =>
              setForm((current) => ({
                ...current,
                [field]: event.target.value,
              }))
            }
            value={form[field as keyof EvidenceForm]}
          />
        </label>
      ))}

      <label className="block rounded-card border border-border bg-bg-hover/50 p-3">
        <span className="text-xs uppercase tracking-[0.16em] text-text-muted">
          {t("pages.evidence.fields.stackTags")}
        </span>
        <input
          className="mt-2 w-full bg-transparent text-sm text-text-primary outline-none"
          disabled={busy}
          onChange={(event) =>
            setForm((current) => ({
              ...current,
              stackText: event.target.value,
            }))
          }
          type="text"
          value={form.stackText}
        />
        <input
          className="mt-3 w-full bg-transparent text-sm text-text-secondary outline-none"
          disabled={busy}
          onChange={(event) =>
            setForm((current) => ({
              ...current,
              tagsText: event.target.value,
            }))
          }
          placeholder={t("pages.evidence.fields.tags")}
          type="text"
          value={form.tagsText}
        />
      </label>
    </>
  );
}
