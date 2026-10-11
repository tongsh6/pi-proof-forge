import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";
import { useFeedbackStore, type FeedbackTone, type ToastItem } from "@/lib/ui";

const toneMap: Record<FeedbackTone, { Icon: typeof Info; className: string }> = {
  success: { Icon: CheckCircle2, className: "border-success/50 text-success" },
  error: { Icon: XCircle, className: "border-error/50 text-error" },
  warning: { Icon: AlertTriangle, className: "border-warning/50 text-warning" },
  info: { Icon: Info, className: "border-accent/50 text-accent" },
};

function Toast({ toast }: { toast: ToastItem }) {
  const { t } = useTranslation();
  const dismiss = useFeedbackStore((state) => state.dismissToast);
  const { Icon, className } = toneMap[toast.tone];

  useEffect(() => {
    if (!toast.duration) return undefined;
    const timer = window.setTimeout(() => dismiss(toast.id), toast.duration);
    return () => window.clearTimeout(timer);
  }, [dismiss, toast.duration, toast.id]);

  return (
    <div
      role={toast.tone === "error" ? "alert" : "status"}
      data-testid={`toast-${toast.tone}`}
      className={`pointer-events-auto flex items-start gap-3 rounded-card border bg-bg-panel px-4 py-3 shadow-[var(--shadow-panel)] ${className}`}
    >
      <Icon size={18} className="mt-0.5 shrink-0" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-text-primary">{toast.title}</p>
        {toast.description ? (
          <p className="mt-1 break-words text-xs text-text-secondary">{toast.description}</p>
        ) : null}
      </div>
      <button
        type="button"
        aria-label={t("common.dismiss")}
        onClick={() => dismiss(toast.id)}
        className="shrink-0 rounded-card p-1 text-text-muted transition-colors hover:bg-bg-hover hover:text-text-primary"
      >
        <X size={14} aria-hidden="true" />
      </button>
    </div>
  );
}

export function ToastViewport() {
  const toasts = useFeedbackStore((state) => state.toasts);
  if (toasts.length === 0) return null;
  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed bottom-6 right-6 z-[var(--z-toast)] flex w-[360px] max-w-[calc(100vw-3rem)] flex-col gap-2"
    >
      {toasts.map((toast) => (
        <Toast key={toast.id} toast={toast} />
      ))}
    </div>
  );
}
