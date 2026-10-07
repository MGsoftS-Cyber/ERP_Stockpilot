// Transport gateway: Express authenticates requests, enforces limits and proxies allowed API paths.
// Django owns ERP business logic and repeats tenant authorization; forwarding is not a permission bypass.
// Only allowed headers cross the proxy; browser-supplied role headers are discarded.
// gateway owns transport concerns only. All ERP writes stay in Django.
import { randomUUID } from "node:crypto";
import http from "node:http";
import https from "node:https";
import express from "express";
import helmet from "helmet";
import { rateLimit } from "express-rate-limit";
import { hasTenant } from "./auth.js";

export const failure = (res, status, code, requestId) =>
  res.status(status).json({ error: { status, code, detail: code, request_id: requestId } });

export function createApp({ upstream, origin, verify, limit = 120, timeout = 190000 }) {
  const app = express();
  app.disable("x-powered-by");
  app.set("trust proxy", false); // Do not let X-Forwarded-For bypass the limiter.
  app.use(helmet());
  app.use((req, res, next) => {
    req.requestId = randomUUID(); // Ignore caller-controlled correlation IDs.
    res.setHeader("X-Request-ID", req.requestId);
    res.setHeader("Cache-Control", "no-store");
    if (req.headers.origin && req.headers.origin !== origin)
      return failure(res, 403, "origin_denied", req.requestId);
    res.setHeader("Access-Control-Allow-Origin", origin);
    res.setHeader("Vary", "Origin");
    res.setHeader("Access-Control-Expose-Headers", "X-Request-ID,Retry-After");
    res.setHeader("Access-Control-Allow-Headers", "Authorization,Content-Type,X-Organization-ID,Accept-Language");
    res.setHeader("Access-Control-Allow-Methods", "GET,POST,PUT,PATCH,DELETE,OPTIONS");
    if (req.method === "OPTIONS") return res.sendStatus(204);
    next();
  });
  app.get("/healthz", (_req, res) => res.json({ status: "ok" }));
  // This store is deliberately single-instance. Use a shared store before scaling replicas.
  app.use(rateLimit({ windowMs: 60000, limit, standardHeaders: "draft-8", legacyHeaders: false,
    handler: (req, res) => failure(res, 429, "rate_limited", req.requestId) }));
  app.use(async (req, res) => {
    // A fixed route prefix and fixed upstream prevent an open proxy / arbitrary AI access.
    if (!req.originalUrl.startsWith("/api/v1/") || /[\\\\]/.test(req.originalUrl))
      return failure(res, 404, "route_not_found", req.requestId);
    const pathname = new URL(req.originalUrl, "http://gateway").pathname;
    if (pathname.startsWith("/api/v1/auth/token"))
      return failure(res, 404, "legacy_login_disabled", req.requestId);
    const authorization = req.headers.authorization ?? "";
    if (!authorization.startsWith("Bearer ")) return failure(res, 401, "token_required", req.requestId);
    let claims;
    try { claims = await verify(authorization.slice(7)); }
    catch { return failure(res, 401, "invalid_token", req.requestId); }
    const organization = req.headers["x-organization-id"];
    const unscoped = pathname === "/api/v1/auth/me/" || pathname.startsWith("/api/v1/organizations/");
    if (!unscoped && !hasTenant(claims, organization))
      return failure(res, 403, "tenant_denied", req.requestId);
    const maximum = 11 * 1024 * 1024;
    if (Number(req.headers["content-length"]) > maximum)
      return failure(res, 413, "request_too_large", req.requestId);
    // Django's development WSGI server requires a known body length. Browsers send it.
    // Explicitly reject chunked uploads instead of silently forwarding an empty body.
    if (req.headers["transfer-encoding"] && !req.headers["content-length"])
      return failure(res, 411, "content_length_required", req.requestId);
    const target = new URL(req.originalUrl, upstream);
    if (target.origin !== new URL(upstream).origin || !target.pathname.startsWith("/api/v1/"))
      return failure(res, 400, "invalid_path", req.requestId);
    // Only forward an allowlist. Cookies, Host and invented role headers are discarded.
    const headers = { authorization, "x-request-id": req.requestId };
    for (const name of ["content-type", "content-length", "accept", "accept-language", "x-organization-id"])
      if (req.headers[name]) headers[name] = req.headers[name];
    const transport = target.protocol === "https:" ? https : http;
    const proxy = transport.request(target, { method: req.method, headers }, (response) => {
      res.status(response.statusCode ?? 502);
      for (const name of ["content-type", "content-disposition", "retry-after"])
        if (response.headers[name]) res.setHeader(name, response.headers[name]);
      response.on("error", () => res.destroy());
      response.pipe(res);
    });
    const timer = setTimeout(() => {
      if (!res.headersSent) failure(res, 504, "upstream_timeout", req.requestId);
      else res.destroy();
      proxy.destroy();
    }, timeout);
    res.on("close", () => { clearTimeout(timer); proxy.destroy(); });
    proxy.on("error", () => {
      clearTimeout(timer);
      if (!res.headersSent) failure(res, 502, "upstream_unavailable", req.requestId);
      else res.destroy();
    });
    let received = 0;
    req.on("data", (chunk) => {
      received += chunk.length;
      if (received > maximum) {
        if (!res.headersSent) failure(res, 413, "request_too_large", req.requestId);
        req.unpipe(proxy); proxy.destroy();
      }
    });
    req.on("aborted", () => proxy.destroy());
    req.pipe(proxy); // Stream OCR uploads. Never automatically retry an ERP write.
  });
  return app;
}
