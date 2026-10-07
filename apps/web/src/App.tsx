// Application composition: AuthProvider exposes the current account and organization.
// DesignProvider applies saved appearance and language direction; Dashboard renders business modules.
// NotificationBridge refreshes queries after authorized change notifications.
// Teaching edition: Choose loading, authentication or the protected dashboard.
import { Box, CircularProgress } from "@mui/material";

import { AuthProvider, useAuth } from "./auth/AuthContext";
import { LoginPage } from "./auth/LoginPage";
import { Dashboard } from "./dashboard/Dashboard";
import { NotificationBridge } from "./components/NotificationBridge";
import { DesignProvider } from "./design/DesignProvider";
import { useLanguage } from "./i18n";

function AuthenticatedApp() {
  useLanguage();
  const { user, loading } = useAuth();
  if (loading) {
    return <Box sx={{ minHeight: "100vh", display: "grid", placeItems: "center" }}><CircularProgress /></Box>;
  }
  return user ? <><NotificationBridge /><Dashboard /></> : <LoginPage />;
}

export default function App() {
  return (
    <AuthProvider>
      <ThemedApp />
    </AuthProvider>
  );
}

function ThemedApp() {
  const { selectedMembership } = useAuth();
  return <DesignProvider key={selectedMembership?.organization.id ?? "login"}><AuthenticatedApp /></DesignProvider>;
}
