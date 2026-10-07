// WebSocket transport: authorizes identity and selected organization before sending change hints.
// Django provides a tenant revision; React invalidates queries and fetches fresh authorized data.
// This is a refresh signal, not durable event delivery or a stock-write endpoint.
// authenticated WebSocket invalidation hints, not a second business API.
import { WebSocketServer, WebSocket } from "ws";
import { hasTenant } from "./auth.js";

export function notifications(server, { verify, upstream, origin, interval = 5000 }) {
  const wss = new WebSocketServer({ noServer: true, maxPayload: 16384, perMessageDeflate: false });
  const counts = new Map();
  server.on("upgrade", (req, socket, head) => {
    const ip = req.socket.remoteAddress;
    if (req.url !== "/ws" || req.headers.origin !== origin || wss.clients.size >= 100 ||
        (counts.get(ip) ?? 0) >= 5) {
      socket.end("HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n"); return;
    }
    counts.set(ip, (counts.get(ip) ?? 0) + 1);
    wss.handleUpgrade(req, socket, head, (ws) => {
      ws.on("close", () => {
        const count = (counts.get(ip) ?? 1) - 1;
        if (count) counts.set(ip, count); else counts.delete(ip);
      });
      wss.emit("connection", ws);
    });
  });
  wss.on("connection", (ws) => {
    let token, organization, expires, polling, authenticating = false, revision;
    const deadline = setTimeout(() => ws.close(4401, "Authenticate first"), 5000);
    let alive = true;
    ws.on("pong", () => { alive = true; });
    const heartbeat = setInterval(() => {
      if (!alive) return ws.terminate();
      alive = false; ws.ping();
    }, 30000);
    async function poll() {
      if (Date.now() >= expires) return ws.close(4401, "Token expired");
      try {
        // Django rechecks active local membership on every poll, including revocations.
        const response = await fetch(new URL("/api/v1/notifications/revision/", upstream), {
          headers: { Authorization: `Bearer ${token}`, "X-Organization-ID": organization },
          signal: AbortSignal.timeout(4000),
        });
        if (response.status === 401 || response.status === 403)
          return ws.close(4403, "Access revoked");
        if (!response.ok) throw new Error("unavailable");
        const data = await response.json();
        if (ws.readyState !== WebSocket.OPEN) return;
        if (revision !== data.revision) {
          revision = data.revision;
          ws.send(JSON.stringify({ type: "data_changed", organizationId: organization }));
        }
      } catch {
        if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "unavailable" }));
      }
      if (ws.readyState === WebSocket.OPEN) polling = setTimeout(poll, interval);
    }
    ws.on("message", async (buffer) => {
      if (authenticating) return ws.close(4400, "Only one authentication frame is allowed");
      authenticating = true;
      try {
        const data = JSON.parse(buffer.toString());
        if (data.type !== "authenticate" || typeof data.token !== "string") throw new Error();
        const claims = await verify(data.token);
        if (!hasTenant(claims, data.organizationId)) throw new Error();
        token = data.token; organization = data.organizationId; expires = claims.exp * 1000;
        clearTimeout(deadline);
        await poll();
      } catch { ws.close(4401, "Invalid credentials"); }
    });
    ws.on("close", () => { clearTimeout(deadline); clearTimeout(polling); clearInterval(heartbeat); });
    ws.on("error", () => ws.terminate());
  });
  return wss;
}
