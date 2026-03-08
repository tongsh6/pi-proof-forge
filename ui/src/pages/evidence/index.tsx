import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { getErrorMessage } from "@/lib/errors";
import { getEvidence, listEvidence } from "@/lib/sidecar/api";
import type { EvidenceDetail, EvidenceListItem } from "@/lib/sidecar/types";

type LoadState = "loading" | "ready" | "error";

function formatFallback(value: string): string {
  return value.trim() ? value : "--";
}

export function EvidencePage() {
  const { t } = useTranslation();
  const [items, setItems] = useState<EvidenceListItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<EvidenceDetail | null>(null);
  const [listState, setListState] = useState<LoadState>("loading");
  const [detailState, setDetailState] = useState<LoadState>("loading");
  const [listError, setListError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  const loadDetail = useCallback(async (evidenceId: string) => {
    setSelectedId(evidenceId);
    setDetailState("loading");
    setDetailError(null);

    try {
      const result = await getEvidence(evidenceId);
      setDetail(result.evidence);
      setDetailState("ready");
    } catch (error) {
      setDetail(null);
      setDetailState("error");
      setDetailError(getErrorMessage(error));
    }
  }, []);

  const loadEvidence = useCallback(async () => {
    setListState("loading");
    setListError(null);

    try {
      const result = await listEvidence();
      setItems(result.items);
      setListState("ready");

      if (result.items.length > 0) {
        void loadDetail(result.items[0].evidence_id);
      } else {
        setSelectedId(null);
        setDetail(null);
        setDetailState("ready");
      }
    } catch (error) {
      setItems([]);
      setListState("error");
      setListError(getErrorMessage(error));
    }
  }, [loadDetail]);

  useEffect(() => {
    void loadEvidence();
  }, [loadEvidence]);

  return (
    <div className="space-y-6">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">
            {t("pages.evidence.title")}
          </h1>
          <p className="mt-2 text-sm text-text-secondary">
            {t("pages.evidence.subtitle")}
          </p>
        </div>
        <button
          className="rounded-card border border-border px-4 py-2 text-sm text-text-primary transition-colors hover:bg-bg-hover"
          onClick={() => void loadEvidence()}
          type="button"
        >
          {t("common.retry")}
        </button>
      </header>

      {listState === "loading" ? (
        <section className="rounded-panel border border-border bg-bg-panel p-6 text-text-secondary shadow-[var(--shadow-panel)]">
          {t("common.loading")}
        </section>
      ) : null}

      {listState === "error" ? (
        <section className="rounded-panel border border-error/50 bg-bg-panel p-6 shadow-[var(--shadow-panel)]">
          <p className="text-sm font-medium text-error">{t("common.error")}</p>
          <p className="mt-2 text-sm text-text-secondary">{listError}</p>
        </section>
      ) : null}

      {listState === "ready" && items.length === 0 ? (
        <section className="rounded-panel border border-border bg-bg-panel p-6 text-text-secondary shadow-[var(--shadow-panel)]">
          {t("common.empty")}
        </section>
      ) : null}

      {listState === "ready" && items.length > 0 ? (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(360px,0.9fr)]">
          <section className="rounded-panel border border-border bg-bg-panel shadow-[var(--shadow-panel)]">
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <div>
                <h2 className="text-lg font-semibold text-text-primary">
                  {t("pages.evidence.listTitle")}
                </h2>
                <p className="mt-1 text-sm text-text-secondary">
                  {t("pages.evidence.listCount", { count: items.length })}
                </p>
              </div>
            </div>
            <div className="divide-y divide-border">
              {items.map((item) => {
                const isSelected = item.evidence_id === selectedId;

                return (
                  <button
                    key={item.evidence_id}
                    className={`flex w-full items-start justify-between gap-4 px-5 py-4 text-left transition-colors ${
                      isSelected ? "bg-accent/10" : "hover:bg-bg-hover/60"
                    }`}
                    onClick={() => void loadDetail(item.evidence_id)}
                    type="button"
                  >
                    <div className="space-y-2">
                      <div>
                        <p className="text-base font-medium text-text-primary">
                          {item.title}
                        </p>
                        <p className="text-xs text-text-muted">{item.evidence_id}</p>
                      </div>
                      <div className="flex flex-wrap gap-2 text-xs text-text-secondary">
                        <span>{formatFallback(item.time_range)}</span>
                        <span>•</span>
                        <span>{formatFallback(item.role_scope)}</span>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-semibold text-accent">{item.score}</p>
                      <p className="mt-1 text-xs uppercase tracking-[0.16em] text-text-muted">
                        {item.status}
                      </p>
                    </div>
                  </button>
                );
              })}
            </div>
          </section>

          <section className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]">
            <div className="border-b border-border pb-4">
              <h2 className="text-lg font-semibold text-text-primary">
                {t("pages.evidence.detailTitle")}
              </h2>
              <p className="mt-1 text-sm text-text-secondary">
                {selectedId ?? t("common.empty")}
              </p>
            </div>

            {detailState === "loading" ? (
              <p className="pt-4 text-sm text-text-secondary">{t("common.loading")}</p>
            ) : null}

            {detailState === "error" ? (
              <div className="pt-4">
                <p className="text-sm font-medium text-error">{t("common.error")}</p>
                <p className="mt-2 text-sm text-text-secondary">{detailError}</p>
              </div>
            ) : null}

            {detailState === "ready" && detail ? (
              <div className="space-y-5 pt-4">
                <div>
                  <p className="text-xl font-semibold text-text-primary">{detail.title}</p>
                  <p className="mt-1 text-sm text-text-secondary">{detail.evidence_id}</p>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                      {t("pages.evidence.fields.timeRange")}
                    </p>
                    <p className="mt-2 text-sm text-text-primary">
                      {formatFallback(detail.time_range)}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                      {t("pages.evidence.fields.role")}
                    </p>
                    <p className="mt-2 text-sm text-text-primary">
                      {formatFallback(detail.role_scope)}
                    </p>
                  </div>
                </div>

                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                    {t("pages.evidence.fields.context")}
                  </p>
                  <p className="mt-2 whitespace-pre-wrap text-sm text-text-primary">
                    {formatFallback(detail.context)}
                  </p>
                </div>

                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                    {t("pages.evidence.fields.actions")}
                  </p>
                  <p className="mt-2 whitespace-pre-wrap text-sm text-text-primary">
                    {formatFallback(detail.actions)}
                  </p>
                </div>

                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                    {t("pages.evidence.fields.results")}
                  </p>
                  <p className="mt-2 whitespace-pre-wrap text-sm text-success">
                    {formatFallback(detail.results)}
                  </p>
                </div>

                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                    {t("pages.evidence.fields.stack")}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {detail.stack.length > 0 ? (
                      detail.stack.map((item) => (
                        <span
                          key={item}
                          className="rounded-chip border border-border px-2.5 py-1 text-xs text-text-primary"
                        >
                          {item}
                        </span>
                      ))
                    ) : (
                      <span className="text-sm text-text-secondary">--</span>
                    )}
                  </div>
                </div>

                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                    {t("pages.evidence.fields.tags")}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {detail.tags.length > 0 ? (
                      detail.tags.map((item) => (
                        <span
                          key={item}
                          className="rounded-chip bg-accent/10 px-2.5 py-1 text-xs text-accent"
                        >
                          {item}
                        </span>
                      ))
                    ) : (
                      <span className="text-sm text-text-secondary">--</span>
                    )}
                  </div>
                </div>

                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-text-muted">
                    {t("pages.evidence.fields.artifacts")}
                  </p>
                  {detail.artifacts.length > 0 ? (
                    <div className="mt-3 space-y-2">
                      {detail.artifacts.map((artifact) => (
                        <div
                          key={
                            artifact.resource_id ??
                            artifact.filename ??
                            `${detail.evidence_id}-artifact-${artifact.mime_type ?? "unknown"}`
                          }
                          className="rounded-card border border-border px-3 py-2"
                        >
                          <p className="text-sm text-text-primary">
                            {artifact.filename ?? t("pages.evidence.artifactFallback")}
                          </p>
                          <p className="mt-1 text-xs text-text-secondary">
                            {artifact.mime_type ?? "--"}
                          </p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-2 text-sm text-text-secondary">{t("common.empty")}</p>
                  )}
                </div>
              </div>
            ) : null}
          </section>
        </div>
      ) : null}
    </div>
  );
}
