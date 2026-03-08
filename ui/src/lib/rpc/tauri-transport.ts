import { invoke } from "@tauri-apps/api/core";
import type { RpcTransport } from "./transport";
import type { RpcResponse, RpcResultBase } from "./types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isTauriAvailable(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

function parseRpcResponse<T extends RpcResultBase>(value: unknown): RpcResponse<T> {
  if (!isRecord(value) || value.jsonrpc !== "2.0" || typeof value.id !== "string") {
    throw new Error("Invalid RPC response envelope");
  }

  if ("error" in value) {
    return value as unknown as RpcResponse<T>;
  }

  if (!isRecord(value.result)) {
    throw new Error("Invalid RPC response result");
  }

  return value as unknown as RpcResponse<T>;
}

export class TauriRpcTransport implements RpcTransport {
  async send<T extends RpcResultBase>(request: string): Promise<RpcResponse<T>> {
    if (!isTauriAvailable()) {
      throw new Error("Tauri bridge unavailable. Open the desktop shell.");
    }

    const rawResponse = await invoke<string>("sidecar_request", { request });
    const parsed: unknown = JSON.parse(rawResponse);
    return parseRpcResponse<T>(parsed);
  }

  close(): void {
    if (!isTauriAvailable()) {
      return;
    }

    void invoke("sidecar_shutdown").catch(() => undefined);
  }
}
