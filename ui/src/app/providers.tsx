import { useEffect } from "react";
import { RouterProvider } from "react-router-dom";
import { getErrorMessage } from "@/lib/errors";
import {
  bootstrapSidecar,
  pingSidecar,
  shutdownSidecar,
} from "@/lib/sidecar/api";
import { useSidecarStore } from "@/state/sidecar-store";
import { router } from "./routes";

export function AppProviders() {
  const setStarting = useSidecarStore((state) => state.setStarting);
  const setConnected = useSidecarStore((state) => state.setConnected);
  const setHeartbeat = useSidecarStore((state) => state.setHeartbeat);
  const setError = useSidecarStore((state) => state.setError);
  const setStopped = useSidecarStore((state) => state.setStopped);

  useEffect(() => {
    let cancelled = false;
    let heartbeatTimer: number | undefined;

    const connect = async () => {
      setStarting();

      try {
        const { handshake, ping } = await bootstrapSidecar();
        if (cancelled) {
          return;
        }

        setConnected({
          state: ping.state,
          sidecarVersion: handshake.sidecar_version,
          protocolVersion: handshake.accepted_protocol_version,
          capabilities: handshake.capabilities,
          lastHeartbeatAt: ping.timestamp,
        });

        heartbeatTimer = window.setInterval(async () => {
          try {
            const nextPing = await pingSidecar();
            if (!cancelled) {
              setHeartbeat(nextPing.state, nextPing.timestamp);
            }
          } catch (error) {
            if (!cancelled) {
              setError("degraded", getErrorMessage(error));
            }
          }
        }, 15000);
      } catch (error) {
        if (!cancelled) {
          setError("disconnected", getErrorMessage(error));
        }
      }
    };

    const handleBeforeUnload = () => {
      shutdownSidecar();
      setStopped();
    };

    void connect();
    window.addEventListener("beforeunload", handleBeforeUnload);

    return () => {
      cancelled = true;
      if (heartbeatTimer) {
        window.clearInterval(heartbeatTimer);
      }
      window.removeEventListener("beforeunload", handleBeforeUnload);
    };
  }, [setConnected, setError, setHeartbeat, setStarting, setStopped]);

  return <RouterProvider router={router} />;
}
