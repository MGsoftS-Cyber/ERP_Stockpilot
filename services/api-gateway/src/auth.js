// Gateway token verifier: checks cryptographic signature and fixed access-token claims.
// Spring Identity publishes signing keys; Django separately verifies the token at the ERP boundary.
// A token must grant the selected organization before the gateway forwards a request.
// cryptographic verification is independent of Django's verification.
import { createRemoteJWKSet, jwtVerify } from "jose";

export const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export function tokenVerifier({ issuer, jwksUrl }) {
  const keys = createRemoteJWKSet(new URL(jwksUrl), {
    timeoutDuration: 3000, cooldownDuration: 10000, cacheMaxAge: 60000,
  });
  return async (token) => {
    const { payload } = await jwtVerify(token, keys, {
      issuer, audience: "stockpilot-api", algorithms: ["RS256"],
      requiredClaims: ["sub", "exp", "iat", "iss", "aud"], maxTokenAge: "6m",
    });
    const scopes = typeof payload.scope === "string" ? payload.scope.split(" ") : payload.scope;
    if (!UUID.test(payload.sub) || payload.token_use !== "access" ||
        !Array.isArray(scopes) || !scopes.includes("erp") ||
        !payload.org_roles || Array.isArray(payload.org_roles) ||
        typeof payload.org_roles !== "object") throw new Error("Invalid access claims");
    return payload;
  };
}

export function hasTenant(claims, organization) {
  return typeof organization === "string" && UUID.test(organization) &&
    Object.hasOwn(claims.org_roles, organization);
}
