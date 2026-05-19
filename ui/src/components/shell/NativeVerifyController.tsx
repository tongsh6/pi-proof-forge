import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";

const verifyScenario = import.meta.env.VITE_QUICK_RUN_VERIFY_AUTORUN;

export function NativeVerifyController() {
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    const targetPath =
      verifyScenario === "quick-run"
        ? "/quick-run"
        : verifyScenario === "overview"
          ? "/"
        : verifyScenario === "system-settings"
          ? "/system-settings"
          : verifyScenario === "policy"
            ? "/policy"
            : null;

    if (!targetPath || location.pathname === targetPath) {
      return;
    }

    navigate(targetPath, { replace: true });
  }, [location.pathname, navigate]);

  return null;
}
