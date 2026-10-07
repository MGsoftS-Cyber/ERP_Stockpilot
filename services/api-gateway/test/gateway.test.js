// Week 11: real HTTP/WebSocket sockets, no browser or external service required.
import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { once } from "node:events";
import { generateKeyPair, exportJWK, SignJWT } from "jose";
import { WebSocket } from "ws";
import { createApp } from "../src/app.js";
import { notifications } from "../src/notifications.js";
import { tokenVerifier } from "../src/auth.js";

const org = "11111111-1111-1111-1111-111111111111";
const other = "22222222-2222-2222-2222-222222222222";
const origin = "http://localhost:5173";
const claims = { sub: other, org_roles: { [org]: "VIEWER" }, exp: Math.floor(Date.now() / 1000) + 300 };
const verify = async (token) => { if (token !== "valid") throw new Error(); return claims; };
async function listen(server, t) {
  server.listen(0, "127.0.0.1"); await once(server, "listening");
  t.after(() => { server.closeAllConnections(); server.close(); });
  return `http://127.0.0.1:${server.address().port}`;
}
const headers = { Authorization: "Bearer valid", "X-Organization-ID": org, Origin: origin };

test("route, identity, tenant and header boundaries", async (t) => {
  let seen;
  const upstream = await listen(http.createServer((req, res) => {
    seen = req.headers; res.setHeader("Content-Type", "application/json"); res.end('{"ok":true}');
  }), t);
  const base = await listen(http.createServer(createApp({ upstream, origin, verify })), t);
  assert.equal((await fetch(base + "/api/v1/catalog/products/")).status, 401);
  assert.equal((await fetch(base + "/api/v1/catalog/products/", { headers: { ...headers, "X-Organization-ID": other } })).status, 403);
  assert.equal((await fetch(base + "/api/v1/auth/token/", { headers })).status, 404);
  assert.equal((await fetch(base + "/admin/", { headers })).status, 404);
  assert.equal((await fetch(base + "/api/v1/auth/me/", { headers: { ...headers, Origin: "https://evil.test" } })).status, 403);
  const response = await fetch(base + "/api/v1/catalog/products/", { headers: { ...headers, "Accept-Language": "ar", "X-User-Role": "ADMINISTRATOR", Cookie: "session=evil" } });
  assert.equal(response.status, 200);
  assert.equal(seen["accept-language"], "ar");
  assert.equal(seen["x-user-role"], undefined); assert.equal(seen.cookie, undefined);
  assert.ok(response.headers.get("x-request-id"));
});

test("rate limiting does not trust caller forwarded address", async (t) => {
  const base = await listen(http.createServer(createApp({ upstream: "http://127.0.0.1:1", origin, verify, limit: 2 })), t);
  for (let i = 0; i < 2; i++) await fetch(base + "/api/v1/auth/me/");
  assert.equal((await fetch(base + "/api/v1/auth/me/", { headers: { "X-Forwarded-For": "10.2.3.4" } })).status, 429);
});

test("upstream failure uses envelope and writes are not retried", async (t) => {
  let count = 0;
  const upstream = await listen(http.createServer((_req, res) => { count++; res.destroy(); }), t);
  const base = await listen(http.createServer(createApp({ upstream, origin, verify })), t);
  const response = await fetch(base + "/api/v1/sales/orders/", { method: "POST", headers, body: "{}" });
  assert.equal(response.status, 502); assert.equal(count, 1);
  assert.equal((await response.json()).error.code, "upstream_unavailable");
});

test("JWT checks use fixed issuer, audience, signature, expiry and access purpose", async (t) => {
  const keys = await generateKeyPair("RS256");
  const jwk = await exportJWK(keys.publicKey); jwk.kid = "test";
  const url = await listen(http.createServer((_req, res) => {
    res.setHeader("Content-Type", "application/json"); res.end(JSON.stringify({ keys: [jwk] }));
  }), t);
  const check = tokenVerifier({ issuer: "https://identity.test", jwksUrl: url });
  const sign = (overrides = {}) => new SignJWT({ sub: other, org_roles: { [org]: "VIEWER" }, scope: "erp", token_use: "access", ...overrides })
    .setProtectedHeader({ alg: "RS256", kid: "test" }).setIssuer("https://identity.test")
    .setAudience("stockpilot-api").setIssuedAt().setExpirationTime("5m").sign(keys.privateKey);
  assert.equal((await check(await sign())).sub, other);
  assert.equal((await check(await sign({ scope: ["openid", "erp"] }))).sub, other);
  await assert.rejects(check(await sign({ token_use: "id" })));
  await assert.rejects(check(await sign({ scope: "openid" })));
  const forged = await new SignJWT({ sub: other }).setProtectedHeader({ alg: "HS256" })
    .sign(new TextEncoder().encode("a sufficiently long forged shared secret"));
  await assert.rejects(check(forged));
  for (const override of [{ aud: "other-api" }, { iss: "https://evil.test" }, { exp: 1 }]) {
    const token = await new SignJWT({ sub: other, org_roles: { [org]: "VIEWER" },
      scope: "erp", token_use: "access", iss: "https://identity.test", aud: "stockpilot-api",
      iat: Math.floor(Date.now() / 1000), exp: Math.floor(Date.now() / 1000) + 300, ...override })
      .setProtectedHeader({ alg: "RS256", kid: "test" }).sign(keys.privateKey);
    await assert.rejects(check(token));
  }
});

test("timeouts terminate stalled upstream responses", async (t) => {
  const upstream = await listen(http.createServer(() => {}), t);
  const base = await listen(http.createServer(createApp({ upstream, origin, verify, timeout: 30 })), t);
  const response = await fetch(base + "/api/v1/auth/me/", { headers });
  assert.equal(response.status, 504);
  assert.equal((await response.json()).error.code, "upstream_timeout");
});

test("declared oversized uploads are rejected before proxying", async (t) => {
  let contacted = false;
  const upstream = await listen(http.createServer((_req, res) => { contacted = true; res.end(); }), t);
  const base = await listen(http.createServer(createApp({ upstream, origin, verify })), t);
  const status = await new Promise((resolve, reject) => {
    const request = http.request(base + "/api/v1/intelligence/uploads/", {
      method: "POST", headers: { ...headers, "Content-Length": 12 * 1024 * 1024 },
    }, (response) => { response.resume(); resolve(response.statusCode); request.destroy(); });
    request.on("error", reject); request.flushHeaders();
  });
  assert.equal(status, 413); assert.equal(contacted, false);
});

test("WebSocket authorization and tenant-scoped invalidation", async (t) => {
  let tenant;
  const upstream = await listen(http.createServer((req, res) => {
    tenant = req.headers["x-organization-id"];
    res.setHeader("Content-Type", "application/json"); res.end('{"revision":"event-1"}');
  }), t);
  const server = http.createServer();
  const wss = notifications(server, { verify, upstream, origin, interval: 50 });
  const base = await listen(server, t);
  t.after(() => { for (const ws of wss.clients) ws.terminate(); wss.close(); });
  const socket = new WebSocket(base.replace("http", "ws") + "/ws", { origin });
  await once(socket, "open");
  socket.send(JSON.stringify({ type: "authenticate", token: "valid", organizationId: org }));
  const [message] = await once(socket, "message");
  assert.deepEqual(JSON.parse(message), { type: "data_changed", organizationId: org });
  assert.equal(tenant, org); socket.close();
  const denied = new WebSocket(base.replace("http", "ws") + "/ws", { origin });
  await once(denied, "open");
  denied.send(JSON.stringify({ type: "authenticate", token: "valid", organizationId: other }));
  const [code] = await once(denied, "close"); assert.equal(code, 4401);
});
