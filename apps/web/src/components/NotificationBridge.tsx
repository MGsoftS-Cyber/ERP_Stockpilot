// Notifications refresh cached data; they never carry authority to alter ERP records.
// The gateway authenticates the WebSocket and organization; React then refetches through normal APIs.
// notifications only invalidate cached data; authorized APIs return fresh records.
import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { getAccessToken } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { oidcEnabled } from "../auth/oidc";

export function NotificationBridge() {
  const { user, selectedMembership } = useAuth();
  const organization = selectedMembership?.organization.id;
  const cache = useQueryClient();
  useEffect(() => {
    if (!oidcEnabled || !user || !organization) return;
    let stopped = false;
    let socket: WebSocket;
    let retry: ReturnType<typeof setTimeout>;
    let delay = 1000;
    const connect = () => {
      const token = getAccessToken();
      if (!token || stopped) return;
      socket = new WebSocket(import.meta.env.VITE_WS_URL ?? "ws://localhost:3000/ws");
      socket.onopen = () => {
        socket.send(JSON.stringify({ type: "authenticate", token, organizationId: organization }));
      };
      socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          if (message.type === "data_changed" && message.organizationId === organization) {
            delay = 1000;
            void cache.invalidateQueries();
          }
        } catch { /* Ignore malformed hints; business data never comes from this socket. */ }
      };
      socket.onclose = (event) => {
        if (stopped) return;
        if (event.code === 4401 || event.code === 4403) {
          window.dispatchEvent(new Event("stockpilot-session-expired"));
          return;
        }
        retry = setTimeout(connect, delay);
        delay = Math.min(delay * 2, 30000);
      };
    };
    connect();
    return () => { stopped = true; clearTimeout(retry); socket?.close(); };
  }, [user, organization, cache]);
  return null;
}
