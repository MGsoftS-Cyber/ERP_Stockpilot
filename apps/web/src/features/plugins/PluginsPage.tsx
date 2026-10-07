// Plugin control screen: sends install, update, configure, enable and rollback commands.
// Manifests are validated data; this UI never evaluates uploaded JavaScript.
// Django creates immutable revisions and runs only the explicitly registered read-only hooks.
import { t } from "../../i18n";
// catalog manifests are data. React never evaluates plugin JavaScript.
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Chip, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { api } from "../../api/client";
import { getApiErrorMessage } from "../../api/errors";

type Manifest = { id: string; name: string; version: string; hook: string;
  settings: Record<string, string | number>; requires: Record<string, string> };
type Installed = { slug: string; release: Manifest; configuration: Record<string, string | number>;
  revision: number; enabled: boolean };
type Catalog = { catalog: { manifest: Manifest; checksum: string }[]; installed: Installed[] };
type History = { number: number; operation: string; created_at: string;
  snapshot: { release: Manifest; enabled: boolean } };
type Insight = { slug: string; error?: string; data?: { kind: string; message?: string;
  rows?: { sku: string; warehouse: string; available: string }[] } };

export function PluginsPage({ organizationId, role }: { organizationId: string; role: string }) {
  const cache = useQueryClient();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState("stock-alerts");
  const [release, setRelease] = useState("1.0.0");
  const [setting, setSetting] = useState("");
  const [target, setTarget] = useState("");
  const [message, setMessage] = useState("");
  const query = useQuery({ queryKey: ["plugins", organizationId],
    queryFn: async () => (await api.get<Catalog>("/plugins/")).data });
  const history = useQuery({ queryKey: ["plugin-history", organizationId, selected],
    queryFn: async () => (await api.get<History[]>(`/plugins/${selected}/history/`)).data });
  const insights = useQuery({ queryKey: ["plugin-insights", organizationId],
    queryFn: async () => (await api.get<{ results: Insight[] }>("/plugins/insights/")).data.results });
  const installed = query.data?.installed.find(p => p.slug === selected);
  const manifests = query.data?.catalog.map(c => c.manifest) ?? [];
  const options = manifests.filter(m => m.id === selected);
  const canManage = role === "ADMINISTRATOR";
  async function command(operation: string) {
    setBusy(true); setError(""); setMessage("");
    try {
      const payload: Record<string, unknown> = {
        slug: selected, operation, expected_revision: installed?.revision ?? 0,
        idempotency_key: crypto.randomUUID(),
      };
      if (operation === "install" || operation === "update") payload.version = release;
      if (operation === "rollback") payload.target_revision = Number(target);
      if (operation === "configure") payload.configuration = installed?.release.hook === "inventory.low_stock"
        ? { threshold: Number(setting) } : { message: setting };
      await api.post("/plugins/commands/", payload);
      setMessage(t("Plugin change saved as a new revision. Review its configuration, output and history below."));
    } catch (reason) { setError(getApiErrorMessage(reason)); }
    finally { await cache.invalidateQueries(); setBusy(false); }
  }
  return <Stack gap={3}>
    <Typography variant="h4">{t("Plugins")}</Typography>
    <Typography>{t("Install reviewed extensions for this organization. Every change creates a history revision.")}</Typography>
    {(error || query.error) && <Alert severity="error">{error || getApiErrorMessage(query.error)}</Alert>}
    {message && <Alert severity="success">{message}</Alert>}
    {!canManage && <Alert severity="info">{t("Only organization administrators can manage plugins.")}</Alert>}
    <Paper sx={{ p: 3 }}><Stack gap={2}>
      <TextField select label={t("Plugin")} value={selected} onChange={e => {
        setSelected(e.target.value); setRelease(manifests.find(m => m.id === e.target.value)?.version ?? "");
        setSetting(""); setTarget("");
      }}>{[...new Set(manifests.map(m => m.id))].map(id => <MenuItem key={id} value={id}>{id}</MenuItem>)}</TextField>
      <TextField select label={t("Catalog version")} value={release} onChange={e => setRelease(e.target.value)}>
        {options.map(m => <MenuItem key={m.version} value={m.version}>{m.version} - {m.name}</MenuItem>)}
      </TextField>
      <Typography>{installed ? `Installed ${installed.release.version}, revision ${installed.revision}` : "Not installed"}</Typography>
      {installed && <><Chip label={t(installed.enabled ? "Enabled" : "Disabled")} />
        <Typography>{t("Configuration:")}{" "}{JSON.stringify(installed.configuration)}</Typography></>}
      {canManage && <><Stack direction="row" gap={1} flexWrap="wrap">
        <Button disabled={busy || !!installed} onClick={() => void command("install")}>{t("Install")}</Button>
        <Button disabled={busy || !installed} onClick={() => void command("update")}>{t("Update")}</Button>
        <Button disabled={busy || !installed} onClick={() => void command(installed?.enabled ? "disable" : "enable")}>{t(installed?.enabled ? "Disable" : "Enable")}</Button>
      </Stack>
      <TextField label={installed?.release.hook === "inventory.low_stock" ? "New threshold" : "New message"}
        value={setting} onChange={e => setSetting(e.target.value)} />
      <Button disabled={busy || !installed || !setting.trim()} onClick={() => void command("configure")}>{t("Save configuration")}</Button>
      <TextField select label={t("Rollback to revision")} value={target} onChange={e => setTarget(e.target.value)}>
        {(history.data ?? []).filter(h => h.number < (installed?.revision ?? 0)).map(h =>
          <MenuItem key={h.number} value={String(h.number)}>{t("Revision")}{" "}{h.number}: {h.snapshot.release.version} ({h.operation})</MenuItem>)}
      </TextField>
      <Button disabled={busy || !target} color="warning" onClick={() => void command("rollback")}>{t("Restore selected revision")}</Button>
      <Typography variant="caption">{t("Rollback restores plugin configuration and version. It does not reverse ERP transactions.")}</Typography></>}
    </Stack></Paper>
    <Typography variant="h6">{t("Version history")}</Typography>
    {history.error && <Alert severity="error">{getApiErrorMessage(history.error)}</Alert>}
    {(history.data ?? []).map(h => <Typography key={h.number}>#{h.number} - {h.operation} - {h.snapshot.release.version} - {new Date(h.created_at).toLocaleString()}</Typography>)}
    <Typography variant="h6">{t("Plugin output")}</Typography>
    {insights.error && <Alert severity="error">{getApiErrorMessage(insights.error)}</Alert>}
    {(insights.data ?? []).map(item => <Paper key={item.slug} sx={{ p: 2 }}>
      <Typography fontWeight={700}>{item.slug}</Typography>
      {item.error ? <Alert severity="warning">{item.error}</Alert> : <>
        <Typography>{item.data?.message}</Typography>
        {item.data?.rows?.map(row => <Typography key={`${row.sku}-${row.warehouse}`}>{row.sku} / {row.warehouse}: {row.available}{t("available")}</Typography>)}
        {item.data?.rows?.length === 0 && <Typography>{t("No low-stock balances match this threshold.")}</Typography>}
      </>}
    </Paper>)}
  </Stack>;
}
