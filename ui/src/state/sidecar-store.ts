import { create } from "zustand";
import type { SidecarConnectionState } from "@/lib/sidecar/types";

interface SidecarStore {
  state: SidecarConnectionState;
  sidecarVersion: string | null;
  protocolVersion: string | null;
  capabilities: string[];
  lastHeartbeatAt: string | null;
  error: string | null;
  setStarting: () => void;
  setConnected: (payload: {
    state: SidecarConnectionState;
    sidecarVersion: string;
    protocolVersion: string;
    capabilities: string[];
    lastHeartbeatAt: string;
  }) => void;
  setHeartbeat: (state: SidecarConnectionState, timestamp: string) => void;
  setError: (state: SidecarConnectionState, error: string) => void;
  setStopped: () => void;
}

export const useSidecarStore = create<SidecarStore>((set) => ({
  state: "disconnected",
  sidecarVersion: null,
  protocolVersion: null,
  capabilities: [],
  lastHeartbeatAt: null,
  error: null,
  setStarting: () =>
    set((current) => ({
      ...current,
      state: current.state === "ready" ? "reconnecting" : "starting",
      error: null,
    })),
  setConnected: ({
    state,
    sidecarVersion,
    protocolVersion,
    capabilities,
    lastHeartbeatAt,
  }) =>
    set({
      state,
      sidecarVersion,
      protocolVersion,
      capabilities,
      lastHeartbeatAt,
      error: null,
    }),
  setHeartbeat: (state, timestamp) =>
    set((current) => ({
      ...current,
      state,
      lastHeartbeatAt: timestamp,
      error: state === "ready" ? null : current.error,
    })),
  setError: (state, error) =>
    set((current) => ({
      ...current,
      state,
      error,
    })),
  setStopped: () =>
    set((current) => ({
      ...current,
      state: "stopped",
    })),
}));
