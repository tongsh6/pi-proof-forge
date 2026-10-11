import { Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { ToastViewport } from "@/components/feedback/ToastViewport";
import { useSidecarStore } from "@/state/sidecar-store";
import { SideNav } from "./SideNav";

const bannerToneMap = {
  starting: "border-warning/40 bg-warning/10",
  degraded: "border-warning/40 bg-warning/10",
  reconnecting: "border-warning/40 bg-warning/10",
  disconnected: "border-error/50 bg-error/10",
  stopped: "border-border bg-bg-panel",
  ready: "",
} as const;

const dotToneMap = {
  starting: "bg-warning",
  ready: "bg-success",
  degraded: "bg-warning",
  reconnecting: "bg-warning",
  disconnected: "bg-error",
  stopped: "bg-text-muted",
} as const;

/**
 * 应用外壳。按设计规范，sidecar 处于 ready 时不占用页面顶部；
 * 其他状态才显示一条横幅，常驻状态放在侧栏底部。
 */
export function AppShell() {
  const { t } = useTranslation();
  const state = useSidecarStore((store) => store.state);
  const error = useSidecarStore((store) => store.error);
  const showBanner = state !== "ready";

  return (
    <div className="flex h-screen w-screen bg-bg-primary">
      <SideNav />
      <main className="flex-1 overflow-y-auto p-6">
        {showBanner ? (
          <section
            role={state === "disconnected" ? "alert" : "status"}
            data-testid="sidecar-banner"
            className={`mb-6 flex flex-wrap items-center justify-between gap-3 rounded-card border px-4 py-3 text-sm ${bannerToneMap[state]}`}
          >
            <div className="flex min-w-0 flex-wrap items-center gap-3">
              <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${dotToneMap[state]}`} />
              <span className="font-medium text-text-primary">
                {t("shell.sidecar")} · {t(`sidecar.state.${state}`)}
              </span>
              {error ? <span className="break-words text-text-secondary">{error}</span> : null}
            </div>
            <span className="text-xs text-text-muted">{t("shell.bannerHint")}</span>
          </section>
        ) : null}
        <Outlet />
      </main>
      <ToastViewport />
      <ConfirmDialog />
    </div>
  );
}
