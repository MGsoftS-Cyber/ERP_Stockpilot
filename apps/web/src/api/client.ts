// Shared HTTP boundary: Axios attaches the access token, selected organization and UI language.
// React feature components call this client; Express routes requests and Django rechecks membership.
// A retry retains the original tenant header so changing companies cannot redirect an in-flight write.
// Teaching edition: Attach JWT and tenant headers consistently to API requests.
import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";
import { oidcEnabled } from "../auth/oidc";
import { getLanguage } from "../i18n";

const apiBaseUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

export const storageKeys = {
  accessToken: "stockpilot.accessToken",
  refreshToken: "stockpilot.refreshToken",
  organizationId: "stockpilot.organizationId",
};

// OIDC access tokens live only for this browser tab; legacy mode remains available locally.
export const tokenStore = oidcEnabled ? sessionStorage : localStorage;
export const getAccessToken = () => tokenStore.getItem(storageKeys.accessToken);

export const api = axios.create({
  baseURL: apiBaseUrl,
  headers: { "Content-Type": "application/json" },
});

// Attach identity and company selection to every request.
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getAccessToken();
  const organizationId = localStorage.getItem(storageKeys.organizationId);

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  config.headers["Accept-Language"] = getLanguage();
  if (organizationId && !config.headers["X-Organization-ID"]) {
    config.headers["X-Organization-ID"] = organizationId;
  }
  return config;
});

let refreshPromise: Promise<string> | null = null;

// Share a refresh Promise between simultaneous failed requests.
async function refreshAccessToken(): Promise<string> {
  const refresh = localStorage.getItem(storageKeys.refreshToken);
  if (!refresh) {
    throw new Error("No refresh token is available.");
  }
  const response = await axios.post<{ access: string; refresh?: string }>(
    `${apiBaseUrl}/auth/token/refresh/`,
    { refresh },
  );
  localStorage.setItem(storageKeys.accessToken, response.data.access);
  if (response.data.refresh) {
    localStorage.setItem(storageKeys.refreshToken, response.data.refresh);
  }
  return response.data.access;
}

// Refresh on 401 once, then retry the original request.
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    if (oidcEnabled) {
      if (error.response?.status === 401) window.dispatchEvent(new Event("stockpilot-session-expired"));
      return Promise.reject(error); // Public OIDC clients do not use the old Django refresh grant.
    }
    const original = error.config as (InternalAxiosRequestConfig & { _retried?: boolean }) | undefined;
    if (error.response?.status !== 401 || !original || original._retried || original.url?.startsWith("/auth/token/")) {
      return Promise.reject(error);
    }

    original._retried = true;
    refreshPromise ??= refreshAccessToken().finally(() => {
      refreshPromise = null;
    });

    try {
      const access = await refreshPromise;
      original.headers.Authorization = `Bearer ${access}`;
      return api(original);
    } catch (refreshError) {
      Object.values(storageKeys).forEach((key) => localStorage.removeItem(key));
      window.dispatchEvent(new Event("stockpilot-session-expired"));
      return Promise.reject(refreshError);
    }
  },
);
