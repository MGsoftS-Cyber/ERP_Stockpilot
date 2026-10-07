// Theme composition: maps saved design tokens and language into a MUI theme.
// Emotion RTL processing, document direction and MUI locale change together for Arabic.
// DesignEditor supplies optional preview tokens; the appearance API persists explicit saves.
import createCache from "@emotion/cache";
import { CacheProvider } from "@emotion/react";
import rtlPlugin from "@mui/stylis-plugin-rtl";
import { prefixer } from "stylis";
import { CssBaseline, ThemeProvider, createTheme } from "@mui/material";
import { arSD, enUS, frFR } from "@mui/material/locale";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useLanguage } from "../i18n";
import { defaults, DesignContext, type Tokens } from "./context";

const ltr = createCache({ key: "stockpilot" });
const rtl = createCache({ key: "stockpilot-rtl", stylisPlugins: [prefixer, rtlPlugin] });
export function DesignProvider({ children }: { children: ReactNode }) {
  const language = useLanguage();
  const { selectedMembership } = useAuth();
  const organization = selectedMembership?.organization.id;
  const query = useQuery({
    queryKey: ["appearance", organization],
    enabled: !!organization,
    queryFn: async () =>
      (await api.get<{ settings: Tokens; revision: number; customized: boolean }>("/plugins/appearance/"))
        .data,
  });
  const [draft, preview] = useState<Tokens | null>(null);
  const settings = draft ?? query.data?.settings ?? defaults;
  const customized = (Object.keys(defaults) as (keyof Tokens)[]).some(
    (key) => settings[key] !== defaults[key],
  );
  useEffect(() => {
    document.documentElement.lang = language;
    document.documentElement.dir = language === "ar" ? "rtl" : "ltr";
  }, [language]);
  const theme = useMemo(
    () =>
      createTheme(
        {
          direction: language === "ar" ? "rtl" : "ltr",
          palette: {
            mode: settings.mode,
            primary: { main: settings.primary },
            secondary: { main: settings.secondary },
            background: { default: settings.background },
          },
          shape: { borderRadius: settings.radius },
          typography: {
            fontSize: settings.font_size,
            fontFamily: "Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
          },
          ...(customized
            ? {
                components: {
                  MuiCssBaseline: {
                    styleOverrides: {
                      ...(settings.background !== defaults.background
                        ? { "[data-workspace]": { backgroundColor: `${settings.background} !important` } }
                        : {}),
                      ...(settings.density === "compact"
                        ? { "[data-workspace] .MuiTableCell-root": { padding: "4px 8px" } }
                        : {}),
                    },
                  },
                },
              }
            : {}),
        },
        language === "ar" ? arSD : language === "fr" ? frFR : enUS,
      ),
    [language, settings, customized],
  );
  return (
    <CacheProvider value={language === "ar" ? rtl : ltr}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <DesignContext.Provider
          value={{ settings: query.data?.settings ?? defaults, revision: query.data?.revision ?? 0, preview }}
        >
          {children}
        </DesignContext.Provider>
      </ThemeProvider>
    </CacheProvider>
  );
}
