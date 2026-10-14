// Authenticated, tenant-scoped cache invalidation with shared polling per identity.
import { WebSocketServer, WebSocket } from "ws";
import { hasTenant } from "./auth.js";

export function notifications(server, { verify, upstream, origin, interval = 5000, maxInterval = 30000 }) {
  const wss = new WebSocketServer({ noServer: true, maxPayload: 16384, perMessageDeflate: false });
  const counts = new Map();
  const groups = new Map();
  const credentials = new WeakMap();

  function detach(ws, group) {
    if (!group) return;
    group.clients.delete(ws);
    if (!group.clients.size) {
      clearTimeout(group.timer);
      group.abort?.abort();
      groups.delete(group.key);
    }
  }

  async function poll(group) {
    for (const ws of group.clients) {
      if (Date.now() >= credentials.get(ws).expires) {
        group.clients.delete(ws);
        ws.close(4401, "Token expired");
      }
    }
    if (!group.clients.size) { groups.delete(group.key); return; }
    const representative = [...group.clients].find((ws) => ws.readyState === WebSocket.OPEN);
    if (!representative) { groups.delete(group.key); return; }
    group.abort = new AbortController();
    const timeout = setTimeout(() => group.abort.abort(), 4000);
    try {
      // Shared clients have the same verified subject, tenant and granted role.
      // Django still rechecks local activity/membership on every polling cycle.
      const response = await fetch(new URL("/api/v1/notifications/revision/", upstream), {
        headers: {
          Authorization: `Bearer ${credentials.get(representative).token}`,
          "X-Organization-ID": group.organization,
        },
        signal: group.abort.signal,
      });
      if (response.status === 401 || response.status === 403) {
        for (const ws of group.clients) ws.close(4403, "Access revoked");
        detach(representative, group);
        return;
      }
      if (!response.ok) throw new Error("unavailable");
      const data = await response.json();
      const changed = !group.initialized || group.revision !== data.revision;
      group.initialized = true;
      group.revision = data.revision;
      group.delay = changed ? interval : Math.min(group.delay * 2, Math.max(interval, maxInterval));
      for (const ws of group.clients) {
        const client = credentials.get(ws);
        if (ws.readyState === WebSocket.OPEN && (!client.initialized || client.revision !== data.revision)) {
          client.initialized = true;
          client.revision = data.revision;
          ws.send(JSON.stringify({ type: "data_changed", organizationId: group.organization }));
        }
      }
    } catch {
      group.delay = Math.min(group.delay * 2, Math.max(interval, maxInterval));
      for (const ws of group.clients) {
        if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "unavailable" }));
      }
    } finally { clearTimeout(timeout); }
    if (group.clients.size && groups.get(group.key) === group) {
      group.timer = setTimeout(() => poll(group), group.delay);
    }
  }

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
    let authenticating = false, group;
    const deadline = setTimeout(() => ws.close(4401, "Authenticate first"), 5000);
    let alive = true;
    ws.on("pong", () => { alive = true; });
    let heartbeatTicks = 0;
    // Check expiry every second; send heartbeat pings every 30 seconds.
    const expiryAndHeartbeat = setInterval(() => {
      if (group && Date.now() >= credentials.get(ws).expires) return ws.close(4401, "Token expired");
      if (++heartbeatTicks % 30 === 0) {
        if (!alive) return ws.terminate();
        alive = false; ws.ping();
      }
    }, 1000);
    ws.on("message", async (buffer) => {
      if (authenticating) return ws.close(4400, "Only one authentication frame is allowed");
      authenticating = true;
      try {
        const data = JSON.parse(buffer.toString());
        if (data.type !== "authenticate" || typeof data.token !== "string") throw new Error();
        const claims = await verify(data.token);
        if (!hasTenant(claims, data.organizationId) || !claims.sub || !Number.isFinite(claims.exp)) throw new Error();
        if (ws.readyState !== WebSocket.OPEN || claims.exp * 1000 <= Date.now()) return ws.close(4401, "Token expired");
        credentials.set(ws, { token: data.token, expires: claims.exp * 1000, initialized: false });
        clearTimeout(deadline);
        const key = JSON.stringify([claims.sub, data.organizationId, claims.org_roles[data.organizationId]]);
        group = groups.get(key);
        if (!group) {
          group = { key, organization: data.organizationId, clients: new Set(), delay: interval, initialized: false };
          groups.set(key, group);
          group.clients.add(ws);
          void poll(group);
        } else {
          group.clients.add(ws);
          // Catch up on the next authorized poll; do not disclose a cached hint before rechecking membership.
        }
      } catch { ws.close(4401, "Invalid credentials"); }
    });
    ws.on("close", () => { clearTimeout(deadline); clearInterval(expiryAndHeartbeat); detach(ws, group); });
    ws.on("error", () => ws.terminate());
  });
  wss.on("close", () => {
    for (const group of groups.values()) { clearTimeout(group.timer); group.abort?.abort(); }
    groups.clear();
  });
  return wss;
}
