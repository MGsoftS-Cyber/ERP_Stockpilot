// Identity state: loads the account and memberships from Django after login.
// OIDC mode uses the Spring-issued token; local legacy mode uses Django JWT for development.
// Organization changes clear query caches; Dashboard remounts forms for the selected company.
// Teaching edition: Share identity and company selection with descendant components.
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { api, storageKeys, tokenStore } from "../api/client";
import { initializeOidc, oidc } from "./oidc";
import type { CurrentUser, Membership } from "../types";
import { useQueryClient } from "@tanstack/react-query";

interface AuthContextValue {
  user: CurrentUser | null;
  selectedMembership: Membership | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  selectOrganization: (organizationId: string) => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedOrganizationId, setSelectedOrganizationId] = useState<string | null>(
    localStorage.getItem(storageKeys.organizationId),
  );

  const selectFromUser = useCallback((nextUser: CurrentUser) => {
    const existing = nextUser.memberships.find(
      (membership) => membership.organization.id === localStorage.getItem(storageKeys.organizationId),
    );
    const selected = existing ?? nextUser.memberships[0] ?? null;
    if (selected) {
      localStorage.setItem(storageKeys.organizationId, selected.organization.id);
      setSelectedOrganizationId(selected.organization.id);
    }
  }, []);

  // Read server identity instead of trusting cached role claims.
  const loadUser = useCallback(async () => {
    const response = await api.get<CurrentUser>("/auth/me/");
    setUser(response.data);
    selectFromUser(response.data);
  }, [selectFromUser]);

  useEffect(() => {
    if (oidc) {
      const expire = () => {
        tokenStore.removeItem(storageKeys.accessToken);
        queryClient.clear();
        setUser(null);
      };
      oidc.events.addAccessTokenExpired(expire);
      window.addEventListener("stockpilot-session-expired", expire);
      initializeOidc().then(async (token) => {
        if (token) {
          tokenStore.setItem(storageKeys.accessToken, token);
          await loadUser();
        }
      }).catch(expire).finally(() => setLoading(false));
      return () => {
        oidc?.events.removeAccessTokenExpired(expire);
        window.removeEventListener("stockpilot-session-expired", expire);
      };
    }
    const token = localStorage.getItem(storageKeys.accessToken);
    if (!token) {
      setLoading(false);
      return;
    }
    loadUser()
      .catch(() => {
        Object.values(storageKeys).forEach((key) => localStorage.removeItem(key));
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, [loadUser, queryClient]);

  // Save issued tokens after successful login, then load memberships.
  const login = useCallback(async (email: string, password: string) => {
    if (oidc) { await oidc.signinRedirect(); return; }
    const response = await api.post<{ access: string; refresh: string }>("/auth/token/", {
      email,
      password,
    });
    localStorage.setItem(storageKeys.accessToken, response.data.access);
    localStorage.setItem(storageKeys.refreshToken, response.data.refresh);
    await loadUser();
  }, [loadUser]);

  // Remove credentials and tenant selection from this browser.
  const logout = useCallback(() => {
    queryClient.clear();
    tokenStore.removeItem(storageKeys.accessToken);
    if (oidc) void oidc.signoutRedirect().catch(() => oidc?.removeUser());
    Object.values(storageKeys).forEach((key) => localStorage.removeItem(key));
    setUser(null);
    setSelectedOrganizationId(null);
  }, [queryClient]);

  // Select the company; the server still verifies membership.
  const selectOrganization = useCallback((organizationId: string) => {
    queryClient.clear();
    localStorage.setItem(storageKeys.organizationId, organizationId);
    setSelectedOrganizationId(organizationId);
  }, [queryClient]);

  useEffect(() => {
    const expired = () => { queryClient.clear(); setUser(null); };
    window.addEventListener("stockpilot-session-expired", expired);
    return () => window.removeEventListener("stockpilot-session-expired", expired);
  }, [queryClient]);

  const selectedMembership =
    user?.memberships.find((membership) => membership.organization.id === selectedOrganizationId) ?? null;

  return (
    <AuthContext.Provider
      value={{ user, selectedMembership, loading, login, logout, selectOrganization }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider.");
  }
  return context;
}
