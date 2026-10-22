import { create } from "zustand";
import type { QuickRunProgress, QuickRunStartResult } from "@/lib/sidecar/types";

/**
 * 全局长任务：让快速运行这类在后端异步执行、页面切走后仍在进行的任务
 * 能在侧栏看到进度、完成后能在回到页面时读回结果。
 * 任务按 kind 唯一；目前只有 quickRun。
 */
export type TaskKind = "quickRun";
export type TaskStatus = "running" | "done" | "error";

export interface BackgroundTask {
  kind: TaskKind;
  label: string;
  path: string;
  status: TaskStatus;
  startedAt: number;
  finishedAt?: number;
  /** 任务所属的岗位画像，回到页面时只在目标一致时读回结果。 */
  profileId?: string;
  /** 后端 Quick Run 编号；页面切走后轮询仍会用它完成同一任务。 */
  runId?: string;
  /** 最近一次轮询到的真实阶段进度。 */
  progress?: QuickRunProgress;
  detail?: string;
  result?: QuickRunStartResult;
}

interface TaskState {
  tasks: Partial<Record<TaskKind, BackgroundTask>>;
  start: (task: Pick<BackgroundTask, "kind" | "label" | "path" | "profileId">) => void;
  attachRunId: (kind: TaskKind, runId: string) => void;
  setProgress: (kind: TaskKind, progress?: QuickRunProgress) => void;
  finish: (kind: TaskKind, result?: QuickRunStartResult) => void;
  fail: (kind: TaskKind, detail?: string) => void;
  clear: (kind: TaskKind) => void;
}

export const useTaskStore = create<TaskState>((set) => ({
  tasks: {},
  start: (task) =>
    set((state) => ({
      tasks: { ...state.tasks, [task.kind]: { ...task, status: "running", startedAt: Date.now() } },
    })),
  attachRunId: (kind, runId) =>
    set((state) => {
      const current = state.tasks[kind];
      if (!current) return state;
      return { tasks: { ...state.tasks, [kind]: { ...current, runId } } };
    }),
  setProgress: (kind, progress) =>
    set((state) => {
      const current = state.tasks[kind];
      if (!current) return state;
      return { tasks: { ...state.tasks, [kind]: { ...current, progress } } };
    }),
  finish: (kind, result) =>
    set((state) => {
      const current = state.tasks[kind];
      if (!current) return state;
      return { tasks: { ...state.tasks, [kind]: { ...current, status: "done", finishedAt: Date.now(), result } } };
    }),
  fail: (kind, detail) =>
    set((state) => {
      const current = state.tasks[kind];
      if (!current) return state;
      return { tasks: { ...state.tasks, [kind]: { ...current, status: "error", finishedAt: Date.now(), detail } } };
    }),
  clear: (kind) =>
    set((state) => {
      const next = { ...state.tasks };
      delete next[kind];
      return { tasks: next };
    }),
}));
