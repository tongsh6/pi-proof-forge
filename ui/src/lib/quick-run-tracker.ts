import { getErrorMessage } from "@/lib/errors";
import { getQuickRun } from "@/lib/sidecar/api";
import { notify } from "@/lib/ui";
import { useTaskStore } from "@/state/task-store";
import type { QuickRunStartResult } from "@/lib/sidecar/types";

/**
 * 后端异步执行 Quick Run 后，由本模块轮询 run.quick.get 并持续写入全局任务 store。
 * 轮询不绑定页面生命周期：用户切到其他页面时仍会推进进度并在完成时更新侧栏/结果。
 */
export const QUICK_RUN_TERMINAL_STATUSES = new Set([
  "DONE",
  "SKIPPED",
  "FAILED",
  "TIMEOUT",
  "stopped",
]);

const DEFAULT_POLL_INTERVAL_MS = 1000;
const DEFAULT_MAX_POLL_ERRORS = 5;

export function isQuickRunTerminal(status: string): boolean {
  return QUICK_RUN_TERMINAL_STATUSES.has(status);
}

export type QuickRunTrackOptions = {
  /** 弹出完成/失败提醒所需的本地化文案；不传则不提醒（测试或静默恢复场景）。 */
  doneMessage?: string;
  failedMessage?: string;
  intervalMs?: number;
  maxPollErrors?: number;
  sleep?: (ms: number) => Promise<void>;
  getRun?: (runId: string) => Promise<QuickRunStartResult>;
};

function defaultSleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    if (typeof window !== "undefined" && typeof window.setTimeout === "function") {
      window.setTimeout(resolve, ms);
      return;
    }
    setTimeout(resolve, ms);
  });
}

/**
 * 轮询一次 Quick Run 直到终态。返回终态结果；如果连续多次读取失败则返回 null。
 * 每次读取都会把 progress 写入任务 store，页面切走再回来也能看到真实阶段。
 */
export async function trackQuickRun(
  runId: string,
  options: QuickRunTrackOptions = {}
): Promise<QuickRunStartResult | null> {
  const sleep = options.sleep ?? defaultSleep;
  const getRun = options.getRun ?? getQuickRun;
  const maxPollErrors = options.maxPollErrors ?? DEFAULT_MAX_POLL_ERRORS;
  useTaskStore.getState().attachRunId("quickRun", runId);
  let consecutiveErrors = 0;
  for (;;) {
    await sleep(options.intervalMs ?? DEFAULT_POLL_INTERVAL_MS);
    let current: QuickRunStartResult;
    try {
      current = await getRun(runId);
      consecutiveErrors = 0;
    } catch (error) {
      consecutiveErrors += 1;
      if (consecutiveErrors < maxPollErrors) continue;
      const detail = getErrorMessage(error);
      useTaskStore.getState().fail("quickRun", detail);
      if (options.failedMessage) notify("error", options.failedMessage, detail);
      return null;
    }
    useTaskStore.getState().setProgress("quickRun", current.progress);
    if (!isQuickRunTerminal(current.status)) continue;
    const finished = current.status === "DONE" || current.status === "SKIPPED";
    const failureDetail = current.reason || `${current.status}`;
    if (finished) {
      useTaskStore.getState().finish("quickRun", current);
      if (options.doneMessage) notify("success", options.doneMessage);
    } else {
      useTaskStore.getState().fail("quickRun", failureDetail);
      if (options.failedMessage) notify("error", options.failedMessage, failureDetail);
    }
    return current;
  }
}
