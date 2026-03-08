import type { RpcResponse, RpcResultBase } from "./types";

export interface RpcTransport {
  send<T extends RpcResultBase>(request: string): Promise<RpcResponse<T>>;
  close(): void;
}
