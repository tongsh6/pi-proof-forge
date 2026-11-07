import { convertFileSrc } from "@tauri-apps/api/core";
import { Send } from "lucide-react";
import type { useTranslation } from "react-i18next";
import type { NativePdfPreparation } from "@/lib/sidecar/api";
import type { SubmissionListItem } from "@/lib/sidecar/types";

export type Translate = ReturnType<typeof useTranslation>["t"];
export type LoadState = "loading" | "ready" | "error";
export type RetryStrategy = "same_channel" | "fallback_email";
export type QuickRunOption = { id: string; label: string; updatedAt: string };

export const defaultSubmissionChannel = "liepin";

export type NativePdfAction = "authorizeSingle" | "preview" | "prepare" | "upload" | "inspect" | "target" | "communicate" | "inspectChat" | "prepareResume" | "send" | "receipt" | "remove" | "recheckRemoval";
/** 自动推进可写出后续阶段的阶段集合；其他阶段（success/final_send_pending/unknown/in_flight 等）只允许只读诊断。 */
export const autoAdvancePhases: string[] = ["prepared", "not_submitted", "uploaded_unverified", "attachment_verified", "communication_started", "resume_interaction_pending"];

/** PDF 投递步骤条：按阶段推导当前步骤；各按钮的启用逻辑不变，只决定哪一步显示为主按钮。 */
export const PDF_STEPS = ["prepare", "review", "upload", "verify", "target", "resume", "send", "receipt"] as const;
export function currentPdfStep(pdf: NativePdfPreparation | null, previewed: boolean, consented: boolean): number {
  if (!pdf) return 0;
  switch (pdf.phase as string) {
    case "prepared":
    case "not_submitted":
      return previewed && consented ? 2 : 1;
    case "in_flight":
    case "uploaded_unverified":
    case "unknown":
      return 3;
    case "attachment_verified":
      return 4;
    case "communication_started":
      return 5;
    case "resume_interaction_pending":
    case "delivery_in_flight":
      return 6;
    case "final_send_pending":
      return 7;
    case "success":
      return PDF_STEPS.length;
    default:
      return 0;
  }
}
export const checkModeConfirmationItems = [
  "check_mode_no_real_submit",
  "selected_submission_channel",
  "selected_channel_job_lead",
  "selected_resume_pdf",
  "selected_channel_session_metadata",
  "may_use_channel_shared_session",
  "final_confirm_disabled_and_forbidden",
  "must_stop_before_final_confirm",
];

export type StatItem = {
  key: "total" | "delivered" | "failed" | "fallback";
  value: number;
  icon: typeof Send;
  className: string;
};

export function formatDate(value: string, locale: string): string {
  if (!value.trim()) return "--";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString(locale);
}

export function isDelivered(status: string): boolean {
  return status === "success" || status === "done";
}

export function isFailed(status: string): boolean {
  return status === "failed";
}

export function isFallback(item: SubmissionListItem): boolean {
  const combined = `${item.channel} ${item.status} ${item.error} ${item.last_step.detail}`.toLowerCase();
  return combined.includes("fallback") || item.channel.toLowerCase() === "email";
}

export function statusClassName(status: string): string {
  if (isDelivered(status)) {
    return "border-success/40 bg-success/10 text-success";
  }
  if (status === "session_valid") {
    return "border-success/40 bg-success/10 text-success";
  }
  if (status === "blocked") {
    return "border-warning/40 bg-warning/10 text-warning";
  }
  if (status === "waiting_for_manual_login" || status === "session_unknown" || status === "login_required") {
    return "border-warning/40 bg-warning/10 text-warning";
  }
  if (status === "failed") {
    return "border-error/40 bg-error/10 text-error";
  }
  return "border-border bg-bg-primary text-text-secondary";
}

export function channelClassName(channel: string): string {
  if (channel.toLowerCase() === "email") {
    return "border-warning/40 bg-warning/10 text-warning";
  }
  if (channel.toLowerCase() === "liepin") {
    return "border-accent/40 bg-accent/10 text-accent";
  }
  return "border-border bg-bg-primary text-text-secondary";
}

export function channelLabel(item: SubmissionListItem, unknownChannel: string): string {
  const channel = item.channel || unknownChannel;
  return isFallback(item) && channel.toLowerCase() === "email" ? "Email ↩" : channel;
}

export function submissionStatusLabel(status: string, t: Translate): string {
  const normalized = status || "unknown";
  return t(`pages.submissions.status.${normalized}`, { defaultValue: normalized });
}

export function screenshotSource(path: string): string | null {
  if (!path) return null;
  try {
    return convertFileSrc(path);
  } catch {
    return path;
  }
}

/** 从后端错误里解析“已固定的同岗位投递流程”，用于一键载入继续，而不是让用户重新固定新 PDF。 */
export function parseExistingPreparedRun(message: string): { quick: string; pdf: string } | null {
  const match = /quick_run_id=([A-Za-z0-9_-]{1,160})(?:\|pdf=([^\]\s]*))?/.exec(message);
  if (!match) return null;
  return { quick: match[1], pdf: (match[2] || "").trim() };
}
