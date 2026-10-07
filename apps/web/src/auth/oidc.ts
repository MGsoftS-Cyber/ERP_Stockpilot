// OIDC adapter: oidc-client-ts handles redirects and the authorization-code flow with PKCE.
// Spring Identity authenticates the user; AuthContext stores the resulting access token for API calls.
// Authorization still depends on server-validated organization membership, not browser labels.
// the standard OIDC library owns state, nonce and PKCE verification.
import { UserManager, WebStorageStateStore } from "oidc-client-ts";

export const oidcEnabled = import.meta.env.VITE_AUTH_MODE === "oidc";
export const oidc = oidcEnabled ? new UserManager({
  authority: import.meta.env.VITE_OIDC_ISSUER ?? "http://localhost:9000",
  client_id: "stockpilot-web",
  redirect_uri: `${window.location.origin}/callback`,
  post_logout_redirect_uri: `${window.location.origin}/`,
  response_type: "code",
  scope: "openid profile erp",
  automaticSilentRenew: false,
  loadUserInfo: false,
  userStore: new WebStorageStateStore({ store: window.sessionStorage }),
}) : null;

let initialization: Promise<string | null> | undefined;
export function initializeOidc(): Promise<string | null> {
  // React StrictMode mounts effects twice; exchange an authorization code only once.
  initialization ??= (async () => {
    if (!oidc) return null;
    const callback = window.location.pathname === "/callback";
    try {
      const user = callback ? await oidc.signinRedirectCallback() : await oidc.getUser();
      return user && !user.expired ? user.access_token : null;
    } finally {
      if (callback) window.history.replaceState({}, "", "/");
    }
  })();
  return initialization;
}
