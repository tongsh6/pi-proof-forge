import type { LlmConfig } from "@/lib/sidecar/types";

/** Strata App 管理的统一推理后台：产品侧唯一入口，模型由 App 管理。 */
export const STRATA_UNIFIED_BASE_URL = "http://127.0.0.1:47831/v1";

/** 无密钥也可用的本地 provider：LM Studio 占位密钥与 Strata 本地免鉴权。 */
export const KEYLESS_PROVIDERS = new Set(["lm_studio", "strata"]);

export function isKeylessProvider(provider: string | null | undefined): boolean {
  return typeof provider === "string" && KEYLESS_PROVIDERS.has(provider);
}

type LlmConfigSummary = Pick<LlmConfig, "provider" | "model" | "api_key">;

/** 模型可用：已保存/环境变量密钥，或 keyless 本地 provider 且已选择模型。 */
export function isLlmConfigured(
  config: LlmConfigSummary | null | undefined
): boolean {
  if (!config) return false;
  if (config.api_key?.configured) return true;
  return isKeylessProvider(config.provider) && Boolean(config.model?.trim());
}

/** 密钥状态可用于展示：已保存/环境变量密钥，或 keyless 本地 provider 无密钥可用。 */
export function isLlmSecretConfigured(
  config: LlmConfigSummary | null | undefined
): boolean {
  if (!config) return false;
  if (config.api_key?.configured) return true;
  return isKeylessProvider(config.provider);
}
