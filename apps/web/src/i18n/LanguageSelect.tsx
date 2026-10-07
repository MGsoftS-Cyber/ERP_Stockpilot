import { MenuItem, TextField } from "@mui/material";
import { setLanguage, useLanguage, type Language } from "./index";
export function LanguageSelect() {
  const language = useLanguage();
  return (
    <TextField
      select
      size="small"
      label={language === "ar" ? "اللغة" : language === "fr" ? "Langue" : "Language"}
      value={language}
      onChange={(event) => setLanguage(event.target.value as Language)}
      sx={{ minWidth: 110, bgcolor: "background.paper", borderRadius: 1 }}
    >
      <MenuItem value="en">English</MenuItem>
      <MenuItem value="fr">Français</MenuItem>
      <MenuItem value="ar">العربية</MenuItem>
    </TextField>
  );
}
