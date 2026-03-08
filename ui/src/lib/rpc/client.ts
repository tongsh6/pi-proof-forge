import type {
  RpcRequest,
  RpcResultBase,
  RpcSuccessResponse,
  RpcErrorResponse,
} from "./types";
import type { RpcTransport } from "./transport";

let requestCounter = 0;

function generateId(): string {
  return `req_${++requestCounter}_${Date.now()}`;
}

function generateCorrelationId(): string {
  return `corr_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

export class RpcClient {
  constructor(private transport: RpcTransport) {}

  async call<T extends RpcResultBase>(
    method: string,
    params: Record<string, unknown> = {}
  ): Promise<RpcSuccessResponse<T>["result"]> {
    const id = generateId();
    const correlationId = generateCorrelationId();

    const request: RpcRequest = {
      jsonrpc: "2.0",
      id,
      method,
      params: {
        meta: { correlation_id: correlationId },
        ...params,
      },
    };

    const response = await this.transport.send<T>(JSON.stringify(request));

    if ("error" in response) {
      throw new RpcError(
        response.error.code,
        response.error.message,
        response.error.details
      );
    }

    return response.result;
  }

  close(): void {
    this.transport.close();
  }
}

export class RpcError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly details: RpcErrorResponse["error"]["details"]
  ) {
    super(`[${code}] ${message}`);
    this.name = "RpcError";
  }

  get retryable(): boolean {
    return this.details.retryable;
  }
}
