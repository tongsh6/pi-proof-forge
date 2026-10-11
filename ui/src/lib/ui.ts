import { create } from "zustand";

/**
 * 全局反馈层：Toast 通知、确认对话框、按钮层级。
 * 页面只调用 notify / confirmAction 两个函数；视图组件挂在 AppShell。
 */

export type FeedbackTone = "success" | "error" | "warning" | "info";

export interface ToastItem {
  id: string;
  tone: FeedbackTone;
  title: string;
  description?: string;
  /** 毫秒；0 表示需要手动关闭。 */
  duration: number;
}

export interface ConfirmOptions {
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: "default" | "danger";
}

interface ConfirmRequest extends ConfirmOptions {
  id: string;
  resolve: (confirmed: boolean) => void;
}

interface FeedbackState {
  toasts: ToastItem[];
  confirm: ConfirmRequest | null;
  pushToast: (
    toast: Omit<ToastItem, "id" | "duration"> & { duration?: number }
  ) => string;
  dismissToast: (id: string) => void;
  requestConfirm: (options: ConfirmOptions) => Promise<boolean>;
  settleConfirm: (confirmed: boolean) => void;
}

const MAX_TOASTS = 4;
let counter = 0;
const nextId = () => `fb_${Date.now().toString(36)}_${++counter}`;

export const useFeedbackStore = create<FeedbackState>((set, get) => ({
  toasts: [],
  confirm: null,
  pushToast: (toast) => {
    const current = get().toasts;
    const last = current[current.length - 1];
    if (
      last &&
      last.tone === toast.tone &&
      last.title === toast.title &&
      last.description === toast.description
    ) {
      return last.id;
    }
    const id = nextId();
    const duration = toast.duration ?? (toast.tone === "error" ? 0 : 5000);
    set((state) => ({
      toasts: [...state.toasts, { ...toast, id, duration }].slice(-MAX_TOASTS),
    }));
    return id;
  },
  dismissToast: (id) =>
    set((state) => ({ toasts: state.toasts.filter((item) => item.id !== id) })),
  requestConfirm: (options) =>
    new Promise<boolean>((resolve) => {
      // 同一时刻只保留一个确认框，旧的按取消处理。
      get().confirm?.resolve(false);
      set({ confirm: { ...options, id: nextId(), resolve } });
    }),
  settleConfirm: (confirmed) => {
    const current = get().confirm;
    if (!current) return;
    set({ confirm: null });
    current.resolve(confirmed);
  },
}));

export function notify(tone: FeedbackTone, title: string, description?: string): string {
  return useFeedbackStore.getState().pushToast({ tone, title, description });
}

export function confirmAction(options: ConfirmOptions): Promise<boolean> {
  return useFeedbackStore.getState().requestConfirm(options);
}

/** 按钮层级：同一视图同一时刻只应有一个 primary；危险操作用 danger。 */
export const buttonClass = {
  primary:
    "inline-flex items-center justify-center gap-2 rounded-card border border-accent bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50",
  secondary:
    "inline-flex items-center justify-center gap-2 rounded-card border border-border px-4 py-2 text-sm text-text-primary transition-colors hover:bg-bg-hover disabled:cursor-not-allowed disabled:opacity-50",
  ghost:
    "inline-flex items-center justify-center gap-2 rounded-card px-3 py-2 text-sm text-text-secondary transition-colors hover:bg-bg-hover hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-50",
  danger:
    "inline-flex items-center justify-center gap-2 rounded-card border border-error/60 px-4 py-2 text-sm font-medium text-error transition-colors hover:bg-error/10 disabled:cursor-not-allowed disabled:opacity-50",
  dangerSolid:
    "inline-flex items-center justify-center gap-2 rounded-card border border-error bg-error px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50",
  link: "text-accent underline underline-offset-2 transition-colors hover:text-accent-cyan disabled:cursor-not-allowed disabled:opacity-50",
} as const;
