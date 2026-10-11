import { useEffect, useRef } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ConfirmDialog } from "@/components/feedback/ConfirmDialog";
import { ToastViewport } from "@/components/feedback/ToastViewport";
import { useSidecarStore } from "@/state/sidecar-store";
import { NAV_PATHS, SideNav } from "./SideNav";

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
  const mainRef = useRef<HTMLElement>(null);
  const { pathname } = useLocation();
  const navigate = useNavigate();

  // 主内容区是唯一滚动容器，切换页面时回到顶部，避免带着上一页的滚动位置进入新页。
  useEffect(() => {
    mainRef.current?.scrollTo({ top: 0 });
  }, [pathname]);

  // 桌面快捷键：⌘/Ctrl+1…9 切换页面，⌘R 刷新当前页，⌘S 保存当前页。
  // 页面通过监听 window 上的 pipf:refresh / pipf:save 事件接入，不需要注册回调。
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!(event.metaKey || event.ctrlKey) || event.altKey) return;
      const target = event.target as HTMLElement | null;
      const editing = target?.tagName === "INPUT" || target?.tagName === "TEXTAREA" || target?.isContentEditable;
      const key = event.key.toLowerCase();
      if (key >= "1" && key <= "9" && !editing) {
        const path = NAV_PATHS[Number(key) - 1];
        if (path) {
          event.preventDefault();
          navigate(path);
        }
        return;
      }
      if (key === "r" && !event.shiftKey) {
        event.preventDefault();
        window.dispatchEvent(new CustomEvent("pipf:refresh"));
      } else if (key === "s" && !event.shiftKey) {
        event.preventDefault();
        window.dispatchEvent(new CustomEvent("pipf:save"));
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [navigate]);

  return (
    <div className="flex h-screen w-screen bg-bg-primary">
      <SideNav />
      <main ref={mainRef} className="flex-1 overflow-y-auto p-6">
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
