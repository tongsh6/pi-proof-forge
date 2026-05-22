import { Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useSidecarStore } from "@/state/sidecar-store";
import { SideNav } from "./SideNav";

const stateToneMap = {
  starting: "bg-warning",
  ready: "bg-success",
  degraded: "bg-warning",
  reconnecting: "bg-warning",
  disconnected: "bg-error",
  stopped: "bg-text-muted",
} as const;

export function AppShell() {
  const { t, i18n } = useTranslation();
  const state = useSidecarStore((store) => store.state);
  const sidecarVersion = useSidecarStore((store) => store.sidecarVersion);
  const lastHeartbeatAt = useSidecarStore((store) => store.lastHeartbeatAt);
  const error = useSidecarStore((store) => store.error);

  const heartbeatLabel = lastHeartbeatAt
    ? new Date(lastHeartbeatAt).toLocaleString(i18n.language)
    : t("shell.waitingForHeartbeat");

  return (
    <div className="flex h-screen w-screen bg-bg-primary">
      <SideNav />
      <main className="flex-1 overflow-y-auto p-6">
        <section className="mb-6 rounded-panel border border-border bg-bg-panel px-5 py-4 shadow-[var(--shadow-panel)]">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-text-muted">
                {t("shell.sidecar")}
              </p>
              <div className="mt-2 flex items-center gap-3">
                <span
                  className={`h-2.5 w-2.5 rounded-full ${stateToneMap[state]}`}
                />
                <span className="text-sm font-semibold text-text-primary">
                  {t(`sidecar.state.${state}`)}
                </span>
                {sidecarVersion ? (
                  <span className="rounded-chip border border-border px-2 py-0.5 text-xs text-text-secondary">
                    v{sidecarVersion}
                  </span>
                ) : null}
              </div>
            </div>
            <div className="text-right text-sm text-text-secondary">
              <p>{t("shell.lastHeartbeat")}</p>
              <p className="mt-1 text-text-primary">{heartbeatLabel}</p>
            </div>
          </div>
          {error ? (
            <p className="mt-3 text-sm text-warning">{error}</p>
          ) : null}
        </section>
        <Outlet />
      </main>
    </div>
  );
}
