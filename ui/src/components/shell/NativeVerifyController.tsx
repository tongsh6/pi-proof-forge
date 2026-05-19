import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";

const verifyScenario = import.meta.env.VITE_QUICK_RUN_VERIFY_AUTORUN;
const verifyRoutes: Record<string, string> = {
  "quick-run": "/quick-run",
  overview: "/",
  "system-settings": "/system-settings",
  policy: "/policy",
  resumes: "/resumes",
};

export function NativeVerifyController() {
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    const targetPath = verifyRoutes[verifyScenario] ?? null;

    if (!targetPath || location.pathname === targetPath) {
      return;
    }

    navigate(targetPath, { replace: true });
  }, [location.pathname, navigate]);

  return null;
}
