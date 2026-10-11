import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAppShellStore } from "@/state/app-shell-store";
import { useSidecarStore } from "@/state/sidecar-store";
import {
  LayoutDashboard,
  FileText,
  FolderSearch,
  Briefcase,
  Zap,
  Bot,
  Send,
  Shield,
  Settings,
  Languages,
} from "lucide-react";

const navItems = [
  { path: "/", icon: LayoutDashboard, labelKey: "nav.overview" },
  { path: "/resumes", icon: FileText, labelKey: "nav.resumes" },
  { path: "/evidence", icon: FolderSearch, labelKey: "nav.evidence" },
  { path: "/jobs", icon: Briefcase, labelKey: "nav.jobs" },
  { path: "/quick-run", icon: Zap, labelKey: "nav.quickRun" },
  { path: "/agent-run", icon: Bot, labelKey: "nav.agentRun" },
  { path: "/submissions", icon: Send, labelKey: "nav.submissions" },
  { path: "/policy", icon: Shield, labelKey: "nav.policy" },
  { path: "/system-settings", icon: Settings, labelKey: "nav.systemSettings" },
] as const;

/** 导航路径顺序，供壳层的 ⌘1…9 快捷键使用。 */
export const NAV_PATHS = navItems.map((item) => item.path);

const stateToneMap = {
  starting: "bg-warning",
  ready: "bg-success",
  degraded: "bg-warning",
  reconnecting: "bg-warning",
  disconnected: "bg-error",
  stopped: "bg-text-muted",
} as const;

export function SideNav() {
  const { t, i18n } = useTranslation();
  const { language, setLanguage } = useAppShellStore();
  const state = useSidecarStore((store) => store.state);
  const sidecarVersion = useSidecarStore((store) => store.sidecarVersion);
  const lastHeartbeatAt = useSidecarStore((store) => store.lastHeartbeatAt);

  const heartbeatLabel = lastHeartbeatAt
    ? new Date(lastHeartbeatAt).toLocaleString(i18n.language)
    : t("shell.waitingForHeartbeat");
  const nextLanguageLabel = language === "en" ? "中文" : "English";

  const toggleLanguage = () => {
    const next = language === "en" ? "zh" : "en";
    setLanguage(next);
    void i18n.changeLanguage(next);
    document.documentElement.lang = next;
  };

  return (
    <nav className="flex flex-col h-full w-56 bg-bg-panel border-r border-border shrink-0">
      <div className="p-4 text-accent font-bold text-lg tracking-tight">
        PiProofForge
      </div>

      <div className="flex-1 overflow-y-auto px-2 space-y-0.5">
        {navItems.map(({ path, icon: Icon, labelKey }, index) => (
          <NavLink
            key={path}
            to={path}
            end={path === "/"}
            title={`${t(labelKey)} ⌘${index + 1}`}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-card text-sm transition-colors duration-[var(--duration-fast)] ${
                isActive
                  ? "bg-accent/10 text-accent"
                  : "text-text-secondary hover:bg-bg-hover hover:text-text-primary"
              }`
            }
          >
            <Icon size={18} />
            <span>{t(labelKey)}</span>
          </NavLink>
        ))}
      </div>

      <div className="space-y-1 border-t border-border p-3">
        <div
          className="flex items-center gap-2 px-3 py-2 text-xs text-text-secondary"
          title={`${t("shell.lastHeartbeat")}: ${heartbeatLabel}${sidecarVersion ? ` · v${sidecarVersion}` : ""}`}
          data-testid="sidecar-status"
        >
          <span className={`h-2 w-2 shrink-0 rounded-full ${stateToneMap[state]}`} />
          <span className="truncate">
            {t("shell.sidecar")} · {t(`sidecar.state.${state}`)}
          </span>
        </div>
        <button
          onClick={toggleLanguage}
          className="flex items-center gap-2 px-3 py-2 w-full rounded-card text-sm text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors"
          aria-label={t("shell.switchLanguage", { language: nextLanguageLabel })}
          title={t("shell.switchLanguage", { language: nextLanguageLabel })}
          type="button"
        >
          <Languages size={16} />
          <span>{nextLanguageLabel}</span>
        </button>
      </div>
    </nav>
  );
}
