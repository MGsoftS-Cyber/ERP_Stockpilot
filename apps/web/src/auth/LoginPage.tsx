// Login screen: gathers credentials only in local legacy mode, or starts the OIDC redirect.
// AuthContext performs login and fetches memberships; this component only controls form feedback.
import { t } from "../i18n";
// Teaching edition: Capture credentials and send them to the JWT endpoint.
import { Alert, Box, Button, Paper, Stack, TextField, Typography } from "@mui/material";
import { useState, type FormEvent } from "react";

import { getApiErrorMessage } from "../api/errors";
import { useAuth } from "./AuthContext";
import { oidcEnabled } from "./oidc";
import { LanguageSelect } from "../i18n/LanguageSelect";

export function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("admin@stockpilot.local");
  const [password, setPassword] = useState("Admin123!");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(email, password);
    } catch (loginError) {
      setError(getApiErrorMessage(loginError));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Box
      component="main"
      sx={{ minHeight: "100vh", display: "grid", placeItems: "center", bgcolor: "grey.100", p: 2 }}
    >
      <Paper component="form" onSubmit={handleSubmit} elevation={3} sx={{ width: "100%", maxWidth: 440, p: 4 }}>
        <Stack spacing={3}>
          <LanguageSelect />
          <Box>
            <Typography variant="h4" fontWeight={700}>StockPilot AI</Typography>
            <Typography color="text.secondary">{t("Multi-tenant ERP workspace")}</Typography>
          </Box>
          {error && <Alert severity="error">{error}</Alert>}
          {!oidcEnabled && <><TextField
            label={t("Email")}
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
            fullWidth
          />
          <TextField
            label={t("Password")}
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            fullWidth
          />
          </>}
          {oidcEnabled && <Typography>{t("Sign in securely with StockPilot Identity. Your existing ERP account is preserved.")}</Typography>}
          <Button type="submit" variant="contained" size="large" disabled={submitting}>
            {submitting ? t("Signing in…") : oidcEnabled ? t("Continue to secure sign-in") : t("Sign in")}
          </Button>
        </Stack>
      </Paper>
    </Box>
  );
}
