import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAppShellStore } from "@/state/app-shell-store";
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

export function SideNav() {
  const { t, i18n } = useTranslation();
  const { language, setLanguage } = useAppShellStore();

  const toggleLanguage = () => {
    const next = language === "en" ? "zh" : "en";
    setLanguage(next);
    i18n.changeLanguage(next);
  };

  return (
    <nav className="flex flex-col h-full w-56 bg-bg-panel border-r border-border shrink-0">
      <div className="p-4 text-accent font-bold text-lg tracking-tight">
        PiProofForge
      </div>

      <div className="flex-1 overflow-y-auto px-2 space-y-0.5">
        {navItems.map(({ path, icon: Icon, labelKey }) => (
          <NavLink
            key={path}
            to={path}
            end={path === "/"}
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

      <div className="p-3 border-t border-border">
        <button
          onClick={toggleLanguage}
          className="flex items-center gap-2 px-3 py-2 w-full rounded-card text-sm text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors"
        >
          <Languages size={16} />
          <span>{language === "en" ? "EN" : "中"}</span>
        </button>
      </div>
    </nav>
  );
}
