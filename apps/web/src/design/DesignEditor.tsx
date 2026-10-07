// Appearance form: maintains a draft separately from the organization’s saved design tokens.
// Preview changes only local theme state; Save sends validated settings and expected_revision to Django.
// The revision check protects another administrator’s newer changes from being overwritten.
import { Alert, Button, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { getApiErrorMessage } from "../api/errors";
import { t } from "../i18n";
import { defaults, useDesign, type Tokens } from "./context";
export function DesignEditor({ canEdit }: { canEdit: boolean }) {
  const { settings, revision, preview } = useDesign();
  const [draft, setDraft] = useState(settings);
  const client = useQueryClient();
  useEffect(() => {
    setDraft(settings);
  }, [settings]);
  useEffect(() => () => preview(null), [preview]);
  const save = useMutation({
    mutationFn: () => api.put("/plugins/appearance/", { settings: draft, expected_revision: revision }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["appearance"] });
      preview(null);
    },
  });
  const valid =
    [draft.primary, draft.secondary, draft.background].every((value) => /^#[\da-f]{6}$/i.test(value)) &&
    draft.radius >= 0 &&
    draft.radius <= 24 &&
    draft.font_size >= 12 &&
    draft.font_size <= 20;
  return (
    <Stack gap={2} maxWidth={640}>
      <Typography variant="h4">{t("Design settings")}</Typography>
      <Alert severity="info">{t("The current design stays unchanged until you preview or save.")}</Alert>
      {save.error && <Alert severity="error">{getApiErrorMessage(save.error)}</Alert>}
      {save.isSuccess && <Alert severity="success">{t("Saved")}</Alert>}
      {(["primary", "secondary", "background"] as const).map((key) => (
        <TextField
          key={key}
          disabled={!canEdit}
          label={t(key)}
          value={draft[key]}
          onChange={(event) => setDraft({ ...draft, [key]: event.target.value })}
        />
      ))}
      {(["radius", "font_size"] as const).map((key) => (
        <TextField
          key={key}
          disabled={!canEdit}
          type="number"
          label={t(key)}
          value={draft[key]}
          onChange={(event) => setDraft({ ...draft, [key]: Number(event.target.value) })}
        />
      ))}
      <TextField
        select
        label={t("Theme")}
        disabled={!canEdit}
        value={draft.mode}
        onChange={(event) => setDraft({ ...draft, mode: event.target.value as Tokens["mode"] })}
      >
        <MenuItem value="light">{t("Light")}</MenuItem>
        <MenuItem value="dark">{t("Dark")}</MenuItem>
      </TextField>
      <TextField
        select
        label={t("Density")}
        disabled={!canEdit}
        value={draft.density}
        onChange={(event) => setDraft({ ...draft, density: event.target.value as Tokens["density"] })}
      >
        <MenuItem value="standard">{t("Standard")}</MenuItem>
        <MenuItem value="compact">{t("Compact")}</MenuItem>
      </TextField>
      <Stack direction="row" gap={1} flexWrap="wrap">
        <Button disabled={!canEdit || !valid} onClick={() => preview(draft)}>
          {t("Preview")}
        </Button>
        <Button
          onClick={() => {
            setDraft(settings);
            preview(null);
          }}
        >
          {t("Cancel preview")}
        </Button>
        <Button disabled={!canEdit} onClick={() => setDraft(defaults)}>
          {t("Restore defaults")}
        </Button>
        <Button
          variant="contained"
          disabled={!canEdit || !valid || save.isPending}
          onClick={() => save.mutate()}
        >
          {t("Save design")}
        </Button>
      </Stack>
    </Stack>
  );
}
