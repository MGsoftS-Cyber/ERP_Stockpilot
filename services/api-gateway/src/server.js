import http from "node:http";
import { createApp } from "./app.js";
import { tokenVerifier } from "./auth.js";
import { notifications } from "./notifications.js";

const issuer = process.env.OIDC_ISSUER ?? "http://localhost:9000";
const options = {
  upstream: process.env.ERP_URL ?? "http://localhost:8000",
  origin: process.env.WEB_ORIGIN ?? "http://localhost:5173",
  verify: tokenVerifier({ issuer, jwksUrl: process.env.OIDC_JWKS_URL ?? `${issuer}/oauth2/jwks` }),
};
const server = http.createServer(createApp(options));
server.headersTimeout = 10000;
server.requestTimeout = 200000;
const sockets = notifications(server, options);
server.listen(Number(process.env.PORT ?? 3000), "0.0.0.0", () => console.log("StockPilot gateway ready"));
for (const signal of ["SIGTERM", "SIGINT"]) process.on(signal, () => {
  for (const socket of sockets.clients) socket.close(1001, "Server restarting");
  sockets.close(); server.close();
  setTimeout(() => process.exit(0), 5000).unref();
});
