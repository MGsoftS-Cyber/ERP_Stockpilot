// AI review interface: uploads private invoice files and displays extraction/forecast results.
// Django calls the internal FastAPI service; this browser never receives the AI service secret.
// A user reviews OCR fields or recommendations; acceptance records intent, not automatic stock changes.
import { t } from "../../i18n";
// AI suggests; the authenticated human corrects or decides.
import { Alert, Button, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../api/client";
import { getApiErrorMessage } from "../../api/errors";
import { aiRoles, ChoiceField, emptyLine, financeRoles, LinesEditor, Pages, QueryError, today, useChoices, usePage } from "../finance/shared";
import type { Line } from "../finance/shared";

type Document = { id: string; original_name: string; status: string; error: string; invoice: string | null;
  extraction: { model_version?: string; raw_text?: string; fields?: Record<string,{ value: string; confidence: number }> } };
type Forecast = { id: string; product_name: string; warehouse_name: string; status: string; error: string; decision: string; decision_note: string;
  result: { model_version?: string; daily_forecast?: number; horizon_forecast?: number; mae?: number; wape_percent?: number | null;
    reorder_quantity?: number; limitations?: string; margin_flags?: { line_id: string; margin_percent: number | null; currency: string }[];
    anomaly_comparison?: { day_index: number; demand: number; isolation_forest: boolean; rule_spike: boolean }[] } };

export function IntelligencePage({ organizationId, role }: { organizationId: string; role: string }) {
  const canRun = aiRoles.includes(role);
  const canApprove = financeRoles.includes(role);
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [review, setReview] = useState("");
  const [partner, setPartner] = useState("");
  const [reference, setReference] = useState("");
  const [issued, setIssued] = useState(today());
  const [due, setDue] = useState(today());
  const [currency, setCurrency] = useState("DZD");
  const [lines, setLines] = useState<Line[]>([emptyLine()]);
  const [product, setProduct] = useState("");
  const [warehouse, setWarehouse] = useState("");
  const [lead, setLead] = useState("7");
  const [horizon, setHorizon] = useState("30");
  const [note, setNote] = useState("");
  const documents = usePage<Document>(organizationId, "/intelligence/documents/");
  const runs = usePage<Forecast>(organizationId, "/intelligence/forecasts/");
  const partners = useChoices(organizationId, "/partners/business-partners/");
  const products = useChoices(organizationId, "/catalog/products/");
  const warehouses = useChoices(organizationId, "/inventory/warehouses/");
  async function command(path: string, payload: object | FormData) {
    setBusy(true); setError(""); setMessage("");
    try {
      // Let the browser add its multipart boundary; never send JSON headers with a File.
      await api.post(path, payload, payload instanceof FormData ? { headers: { "Content-Type": "multipart/form-data" } } : undefined);
      setMessage(t("Your request was recorded. Check the document or analysis status before taking the next action."));
      return true;
    } catch (cause) { setError(getApiErrorMessage(cause)); return false; }
    finally { await client.invalidateQueries({ queryKey: ["week8", organizationId] }); setBusy(false); }
  }
  async function download(document: Document) {
    try {
      // Native links cannot attach JWT headers, so request the private file with Axios.
      const response = await api.get(`/intelligence/documents/${document.id}/download/`, { responseType: "blob" });
      const url = URL.createObjectURL(response.data);
      const anchor = window.document.createElement("a");
      anchor.href = url; anchor.download = document.original_name; anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (cause) { setError(getApiErrorMessage(cause)); }
  }
  return <Stack gap={3}>
    <Typography variant="h4">{t("Invoice OCR and recommendations")}</Typography>
    <Alert severity="info">{t("OCR proposes text and fields. Review every amount against the original document. Approval creates a supplier invoice draft; it does not post an invoice or change stock.")}</Alert>
    {error && <Alert severity="error">{error}</Alert>}{message && <Alert severity="success">{message}</Alert>}
    {[documents.error, runs.error, partners.error, products.error, warehouses.error].map((err,i) => <QueryError key={i} error={err} />)}
    {canRun && <Paper variant="outlined" sx={{ p: 2 }}><Stack gap={2}>
      <Typography variant="h6">{t("Upload invoice · PNG / JPEG / PDF · up to 10 MiB, 5 PDF pages")}</Typography>
      <input type="file" accept="image/png,image/jpeg,application/pdf" disabled={busy} onChange={e => setFile(e.target.files?.[0] ?? null)} />
      <Button disabled={busy || !file} variant="contained" onClick={() => { if (file) {
        if (file.size > 10*1024*1024) { setError("Maximum size is 10 MiB."); return; }
        const data = new FormData(); data.append("file", file); void command("/intelligence/documents/upload/", data);
      } }}>{t("Upload document")}</Button>
    </Stack></Paper>}
    {documents.data?.results.map(doc => <Paper key={doc.id} variant="outlined" sx={{ p: 2 }}><Stack gap={1}>
      <Typography fontWeight={700}>{doc.original_name} · {doc.status}</Typography>
      {doc.error && <Alert severity="error">{doc.error}</Alert>}
      <Stack direction="row" gap={1}><Button onClick={() => void download(doc)}>{t("Download original")}</Button>
        {canRun && ["UPLOADED", "FAILED", "PROCESSING"].includes(doc.status) && <Button disabled={busy} onClick={() => void command(`/intelligence/documents/${doc.id}/extract/`, {})}>{t("Extract / retry")}</Button>}
        {canApprove && doc.status === "REVIEW" && <Button disabled={busy} onClick={() => {
          setReview(doc.id); setReference(doc.extraction.fields?.reference?.value ?? ""); setLines([emptyLine()]);
        }}>{t("Correct and review")}</Button>}</Stack>
      {doc.status === "PROCESSING" && <Typography>{t("Extraction is running; interrupted attempts can be retried after five minutes.")}</Typography>}
      {Object.entries(doc.extraction.fields ?? {}).map(([name, field]) => <Typography key={name}>{name}: {field.value || "not detected"}{t("· OCR confidence")}{" "}{Math.round(field.confidence*100)}%</Typography>)}
      {doc.extraction.raw_text && <Typography component="pre" sx={{ whiteSpace: "pre-wrap", maxHeight: 220, overflow: "auto", fontSize: 13 }}>{doc.extraction.raw_text}</Typography>}
      {doc.invoice && <Typography>{t("Draft invoice created:")}{" "}{doc.invoice}{t(". Review and post it in Finance.")}</Typography>}
    </Stack></Paper>)}<Pages {...documents} />
    {canApprove && review && <Paper variant="outlined" sx={{ p: 2 }}><Stack gap={2} component="fieldset" disabled={busy} sx={{ border: 0 }}>
      <Typography variant="h6">{t("Human correction · document")}{" "}{review}</Typography>
      <Typography>{t("Enter the actual invoice lines, tax rates and dates. The detected total is a comparison aid, not an automatically trusted line.")}</Typography>
      <ChoiceField label={t("Supplier")} value={partner} onChange={setPartner} rows={partners.data?.filter(p => p.is_active !== false && p.partner_type !== "CUSTOMER")} />
      <TextField label={t("Correct invoice reference")} value={reference} onChange={e => setReference(e.target.value)} />
      <TextField select label={t("Currency")} value={currency} onChange={e => setCurrency(e.target.value)}>{["DZD","EUR","USD"].map(c => <MenuItem key={c} value={c}>{c}</MenuItem>)}</TextField>
      <Stack direction="row" gap={2}><TextField label={t("Issued")} type="date" value={issued} onChange={e => setIssued(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
        <TextField label={t("Due")} type="date" value={due} onChange={e => setDue(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} /></Stack>
      <LinesEditor lines={lines} setLines={setLines} />
      <Button disabled={busy || !partner || !reference} variant="contained" onClick={() => void (async () => {
        if (await command(`/intelligence/documents/${review}/approve/`, { partner_id: partner, reference, currency, issued_on: issued, due_on: due, lines })) setReview("");
      })()}>{t("I reviewed the document — create draft invoice")}</Button><Button onClick={() => setReview("")}>{t("Close review")}</Button>
    </Stack></Paper>}
    <Typography variant="h5">{t("Forecast and reorder analysis")}</Typography>
    <Alert severity="info">{t("Uses the previous 90 complete days of shipments. Reorder suggestions use lead time, minimum stock and available stock (on hand minus reserved). Acceptance records your decision; it does not place an order.")}</Alert>
    {canRun && <Paper variant="outlined" sx={{ p: 2 }}><Stack gap={2} component="fieldset" disabled={busy} sx={{ border: 0 }}>
      <ChoiceField label={t("Product")} value={product} onChange={setProduct} rows={products.data?.filter(p => p.is_active !== false)} />
      <ChoiceField label={t("Warehouse")} value={warehouse} onChange={setWarehouse} rows={warehouses.data?.filter(p => p.is_active !== false)} />
      <TextField label={t("Lead time (days)")} value={lead} onChange={e => setLead(e.target.value)} />
      <TextField label={t("Forecast horizon (days)")} value={horizon} onChange={e => setHorizon(e.target.value)} />
      <Button disabled={busy || !product || !warehouse} variant="contained" onClick={() => void command("/intelligence/forecasts/", { product_id: product, warehouse_id: warehouse, lead_time_days: Number(lead), horizon_days: Number(horizon) })}>{t("Run analysis")}</Button>
      <TextField label={t("Reason for accepting / rejecting a result")} value={note} onChange={e => setNote(e.target.value)} />
    </Stack></Paper>}
    {runs.data?.results.map(run => <Paper key={run.id} variant="outlined" sx={{ p: 2 }}><Stack gap={1}>
      <Typography fontWeight={700}>{run.product_name} · {run.warehouse_name} · {run.status} · {run.decision}</Typography>
      {run.error && <Alert severity="error">{run.error}</Alert>}
      {run.status === "READY" && <>
        <Typography>{t("Daily forecast:")}{" "}{run.result.daily_forecast}{t("· Horizon total:")}{" "}{run.result.horizon_forecast}{t("· Suggested reorder:")}{" "}{run.result.reorder_quantity}</Typography>
        <Typography>{t("Holdout MAE:")}{" "}{run.result.mae}{t("· WAPE:")}{" "}{run.result.wape_percent == null ? "undefined (zero demand)" : `${run.result.wape_percent}%`}</Typography>
        <Typography variant="body2">{t("Model:")}{" "}{run.result.model_version}</Typography><Typography variant="body2">{run.result.limitations}</Typography>
        <Typography>{t("Margin alerts (below 20% or zero revenue):")}{" "}{run.result.margin_flags?.length ?? 0}</Typography>
        {run.result.margin_flags?.map(row => <Typography key={row.line_id} variant="body2">{t("Line")}{" "}{row.line_id}: {row.margin_percent ?? "undefined"}% · {row.currency}</Typography>)}
        {run.result.anomaly_comparison?.map(row => <Typography key={row.day_index} variant="body2">{t("Day")}{" "}{row.day_index+1}: {row.demand}{t("units · rule spike:")}{" "}{row.rule_spike ? "yes" : "no"}{t("· IsolationForest anomaly:")}{" "}{row.isolation_forest ? "yes" : "no"}</Typography>)}
        {canRun && run.decision === "PENDING" && <Stack direction="row" gap={1}>{["ACCEPTED","REJECTED"].map(decision =>
          <Button key={decision} disabled={busy || !note.trim()} onClick={() => void command(`/intelligence/forecasts/${run.id}/decide/`, { decision, note })}>{decision === "ACCEPTED" ? "Accept recommendation" : "Reject recommendation"}</Button>)}</Stack>}
        {run.decision_note && <Typography>{t("Decision:")}{" "}{run.decision_note}</Typography>}
      </>}
    </Stack></Paper>)}<Pages {...runs} />
  </Stack>;
}
