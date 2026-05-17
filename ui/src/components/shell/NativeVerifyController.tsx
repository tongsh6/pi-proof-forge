import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";

const verifyScenario = import.meta.env.VITE_QUICK_RUN_VERIFY_AUTORUN;

export function NativeVerifyController() {
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    if (verifyScenario !== "quick-run" || location.pathname === "/quick-run") {
      return;
    }

    navigate("/quick-run", { replace: true });
  }, [location.pathname, navigate]);

  return null;
}
