export interface RpcRequest {
  jsonrpc: "2.0";
  id: string;
  method: string;
  params: {
    meta: { correlation_id: string };
    [key: string]: unknown;
  };
}

export interface RpcResultMeta {
  correlation_id: string;
}

export interface RpcResultBase {
  meta: RpcResultMeta;
}

export interface RpcSuccessResponse<T extends RpcResultBase = RpcResultBase> {
  jsonrpc: "2.0";
  id: string;
  result: T;
}

export interface RpcErrorDetail {
  correlation_id: string;
  retryable: boolean;
  field_errors?: Record<string, string>;
  resource_id?: string;
}

export interface RpcErrorResponse {
  jsonrpc: "2.0";
  id: string;
  error: {
    code: string;
    message: string;
    details: RpcErrorDetail;
  };
}

export type RpcResponse<T extends RpcResultBase = RpcResultBase> =
  | RpcSuccessResponse<T>
  | RpcErrorResponse;

export type RpcErrorCode =
  | "UNSUPPORTED_VERSION"
  | "SIDECAR_UNAVAILABLE"
  | "TIMEOUT"
  | "VALIDATION_ERROR"
  | "NOT_FOUND"
  | "CONFLICT"
  | "STORAGE_ERROR"
  | "PERMISSION_DENIED"
  | "INTERNAL_ERROR";
