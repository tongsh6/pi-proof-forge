import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";
import { buttonClass, useFeedbackStore } from "@/lib/ui";

/** 全局确认对话框：Esc 取消，焦点默认落在“取消”上，Tab 在两个按钮间循环。 */
export function ConfirmDialog() {
  const { t } = useTranslation();
  const request = useFeedbackStore((state) => state.confirm);
  const settle = useFeedbackStore((state) => state.settleConfirm);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!request) return undefined;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    cancelRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        settle(false);
        return;
      }
      if (event.key === "Tab") {
        const order = [cancelRef.current, confirmRef.current].filter(Boolean) as HTMLElement[];
        if (order.length === 0) return;
        const index = order.indexOf(document.activeElement as HTMLElement);
        const next = event.shiftKey
          ? order[(index - 1 + order.length) % order.length]
          : order[(index + 1) % order.length];
        event.preventDefault();
        next.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      previouslyFocused?.focus?.();
    };
  }, [request, settle]);

  if (!request) return null;
  const danger = request.tone === "danger";

  return (
    <div
      className="fixed inset-0 z-[var(--z-modal)] flex items-center justify-center bg-black/60 p-6"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) settle(false);
      }}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby={request.description ? "confirm-dialog-description" : undefined}
        data-testid="confirm-dialog"
        className="w-full max-w-md rounded-panel border border-border bg-bg-panel p-6 shadow-[var(--shadow-panel)]"
      >
        <div className="flex items-start gap-3">
          {danger ? (
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-error" aria-hidden="true" />
          ) : null}
          <div className="min-w-0">
            <h2 id="confirm-dialog-title" className="text-base font-semibold text-text-primary">
              {request.title}
            </h2>
            {request.description ? (
              <p id="confirm-dialog-description" className="mt-2 text-sm text-text-secondary">
                {request.description}
              </p>
            ) : null}
          </div>
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <button
            ref={cancelRef}
            type="button"
            className={buttonClass.secondary}
            onClick={() => settle(false)}
          >
            {request.cancelLabel ?? t("common.cancel")}
          </button>
          <button
            ref={confirmRef}
            type="button"
            data-testid="confirm-dialog-accept"
            className={danger ? buttonClass.dangerSolid : buttonClass.primary}
            onClick={() => settle(true)}
          >
            {request.confirmLabel ?? t("common.confirm")}
          </button>
        </div>
      </div>
    </div>
  );
}
