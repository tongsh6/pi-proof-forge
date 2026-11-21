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
        <div>
          <p className="text-xs uppercase tracking-[0.16em] text-text-muted">{t("pages.evidence.fields.context")}</p>
          <p className="mt-1 whitespace-pre-wrap break-words text-sm text-text-primary">{form.context || "--"}</p>
        </div>
        {(["actions", "results"] as const).map(field => (
          <div key={field}>
            <p className="text-xs uppercase tracking-[0.16em] text-text-muted">{t("pages.evidence.fields." + field)}</p>
            {form[field].length ? <ol className="mt-1 list-decimal space-y-2 pl-5">
              {form[field].map((value, index) => <li key={index} className={"whitespace-pre-wrap break-words text-sm " + (field === "results" ? "text-success" : "text-text-primary")}>{value || "--"}</li>)}
            </ol> : <p className="mt-1 text-sm text-text-muted">--</p>}
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

      <label className="block rounded-card border border-border bg-bg-hover/50 p-3">
        <span className="text-xs uppercase tracking-[0.16em] text-text-muted">{t("pages.evidence.fields.context")}</span>
        <textarea
          className="mt-2 min-h-20 w-full resize-y bg-transparent text-sm outline-none"
          disabled={busy}
          onChange={event => setForm(current => ({...current, context: event.target.value}))}
          value={form.context}
        />
      </label>
      {(["actions", "results"] as const).map(field => (
        <section key={field} className="space-y-3 rounded-card border border-border bg-bg-hover/50 p-3">
          <p className="text-xs uppercase tracking-[0.16em] text-text-muted">{t("pages.evidence.fields." + field)}</p>
          <p className="text-xs text-text-secondary">{t("pages.evidence.factEditor.hint")}</p>
          {form[field].map((value, index) => (
            <div key={index} className="space-y-1">
              <label className="block space-y-1">
                <span className="text-xs text-text-secondary">{t("pages.evidence.fields." + field)} {index + 1}</span>
                <textarea
                  data-field={field}
                  aria-label={t("pages.evidence.fields." + field) + " " + (index + 1)}
                  className={"min-h-24 w-full resize-y bg-transparent text-sm outline-none " + (field === "results" ? "text-success" : "")}
                  disabled={busy}
                  value={value}
                  onChange={event => {
                    const text = event.target.value;
                    setForm(current => ({...current, [field]: current[field].map((item, itemIndex) => itemIndex === index ? text : item)}));
                  }}
                />
              </label>
              <button
                type="button"
                data-testid={"evidence-remove-" + field + "-" + index}
                aria-label={t("pages.evidence.factEditor.remove") + " " + t("pages.evidence.fields." + field) + " " + (index + 1)}
                className="text-xs text-text-secondary disabled:opacity-40"
                disabled={busy}
                onClick={() => setForm(current => ({...current, [field]: current[field].filter((_, itemIndex) => itemIndex !== index)}))}
              >{t("pages.evidence.factEditor.remove")}</button>
            </div>
          ))}
          <button
            type="button"
            data-testid={"evidence-add-" + field}
            className="rounded-card border border-border px-3 py-2 text-xs text-accent disabled:opacity-40"
            disabled={busy}
            onClick={() => setForm(current => ({...current, [field]: [...current[field], ""]}))}
          >{t("pages.evidence.factEditor." + (field === "actions" ? "addAction" : "addResult"))}</button>
        </section>
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
