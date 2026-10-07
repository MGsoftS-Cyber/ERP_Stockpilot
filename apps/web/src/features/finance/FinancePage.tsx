// Finance interface: submits invoice, payment and expense commands and reads audit events.
// Decimal amounts travel as strings; Django calculates final financial values and allocations.
// After a write, related tenant queries are refreshed so balances come from the server.
import { t } from "../../i18n";
// model forms as commands, then refresh server-owned invoice balances.
import { Alert, Button, Divider, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api } from "../../api/client";
import { getApiErrorMessage as apiErrorMessage } from "../../api/errors";
import { ChoiceField, emptyLine, financeRoles, LinesEditor, Pages, QueryError, today, useChoices, usePage } from "./shared";
import type { Line } from "./shared";

type Invoice = { id: string; reference: string; partner_name: string; kind: string; status: string; currency: string; total: string; paid: string; balance: string; lines: Line[] };
type Expense = { id: string; description: string; amount: string; currency: string; is_void: boolean };
type Payment = { id: string; reference: string; amount: string; currency: string; kind: string };
type Event = { id: string; created_at: string; action: string; entity_type: string; detail: Record<string, unknown> };

export function FinancePage({ organizationId, role }: { organizationId: string; role: string }) {
  const canWrite = financeRoles.includes(role);
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [currency, setCurrency] = useState("DZD");
  const [kind, setKind] = useState("CUSTOMER");
  const [partner, setPartner] = useState("");
  const [reference, setReference] = useState("");
  const [issued, setIssued] = useState(today());
  const [due, setDue] = useState(today());
  const [sourceMode, setSourceMode] = useState("manual");
  const [sourceId, setSourceId] = useState("");
  const [lines, setLines] = useState<Line[]>([emptyLine()]);
  const [reason, setReason] = useState("");
  const [paidOn, setPaidOn] = useState(today());
  const [paymentRef, setPaymentRef] = useState("");
  const [allocations, setAllocations] = useState([{ invoice_id: "", amount: "" }]);
  const [expense, setExpense] = useState({ description: "", category: "", amount: "", spent_on: today() });
  const partners = useChoices(organizationId, "/partners/business-partners/");
  const sources = useChoices(organizationId, kind === "CUSTOMER" ? "/sales/orders/" : "/purchasing/orders/");
  const invoices = usePage<Invoice>(organizationId, "/billing/invoices/");
  const expenses = usePage<Expense>(organizationId, "/finance/expenses/");
  const payments = usePage<Payment>(organizationId, "/billing/payments/");
  const events = usePage<Event>(organizationId, "/audit/events/");
  const summary = useQuery({ queryKey: ["week8", organizationId, "summary", currency], queryFn: async () =>
    (await api.get<Record<string,string>>("/finance/summary/", { params: { currency } })).data });
  // Retain a command UUID after a network failure; editing the payload creates a new one.
  const keys = useRef(new Map<string, { body: string; key: string }>());
  async function command(path: string, payload: object, idempotent = false) {
    setBusy(true); setError(""); setMessage("");
    const body = JSON.stringify(payload);
    const prior = keys.current.get(path);
    const key = prior?.body === body ? prior.key : crypto.randomUUID();
    keys.current.set(path, { body, key });
    try {
      await api.post(path, idempotent ? { ...payload, idempotency_key: key } : payload);
      keys.current.delete(path);
      setMessage(t("Financial operation saved. Invoice balances, payment records and audit history have been refreshed."));
      await client.invalidateQueries({ queryKey: ["week8", organizationId] });
      return true;
    } catch (cause) { setError(apiErrorMessage(cause)); return false; }
    finally { setBusy(false); }
  }
  return <Stack spacing={3}>
    <Typography variant="h4">{t("Billing, finance and audit")}</Typography>
    <Alert severity="info">{t("Operational finance: totals use posted invoices and captured costs. Returns do not automatically create credit notes. Currencies are never combined.")}</Alert>
    {error && <Alert severity="error">{error}</Alert>}{message && <Alert severity="success">{message}</Alert>}
    {[partners.error, sources.error, invoices.error, expenses.error, payments.error, events.error, summary.error].map((err, i) => <QueryError key={i} error={err} />)}
    <TextField select label={t("Currency")} value={currency} onChange={e => setCurrency(e.target.value)} sx={{ width: 180 }}>
      {["DZD", "EUR", "USD"].map(c => <MenuItem key={c} value={c}>{c}</MenuItem>)}
    </TextField>
    <Paper variant="outlined" sx={{ p: 2 }}><Typography variant="h6">{t("All-time summary (")}{" "}{currency})</Typography>
      <Stack direction="row" flexWrap="wrap" gap={3}>{Object.entries(summary.data ?? {}).filter(([name]) => name !== "currency").map(([name, value]) =>
        <div key={name}><Typography color="text.secondary">{name.replaceAll("_", " ")}</Typography><Typography>{value}</Typography></div>)}</Stack>
    </Paper>
    {canWrite && <Paper variant="outlined" sx={{ p: 2 }}><Stack spacing={2} component="fieldset" disabled={busy} sx={{ border: 0 }}>
      <Typography variant="h6">{t("Create draft invoice")}</Typography>
      <Stack direction="row" flexWrap="wrap" gap={2}>
        <TextField select label={t("Kind")} value={kind} onChange={e => { setKind(e.target.value); setPartner(""); setSourceId(""); }}>
          <MenuItem value="CUSTOMER">{t("Customer")}</MenuItem><MenuItem value="SUPPLIER">{t("Supplier")}</MenuItem></TextField>
        <ChoiceField label={t("Partner")} value={partner} onChange={setPartner} rows={partners.data?.filter(p => p.is_active !== false && (p.partner_type === kind || p.partner_type === "BOTH"))} />
        <TextField label={t("Invoice reference")} value={reference} onChange={e => setReference(e.target.value)} />
        <TextField label={t("Issued on")} type="date" value={issued} onChange={e => setIssued(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
        <TextField label={t("Due on")} type="date" value={due} onChange={e => setDue(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
        <TextField select label={t("Lines from")} value={sourceMode} onChange={e => setSourceMode(e.target.value)}>
          <MenuItem value="manual">{t("Manual lines")}</MenuItem><MenuItem value="order">{t("Whole order")}</MenuItem></TextField>
      </Stack>
      {sourceMode === "manual" ? <LinesEditor lines={lines} setLines={setLines} /> : <>
        <ChoiceField label={t("Source order")} value={sourceId} onChange={setSourceId} rows={sources.data} />
        <Typography>{t("Creates one full-order invoice; only approved purchases or confirmed sales are eligible.")}</Typography></>}
      <Button variant="contained" disabled={busy || !partner || !reference || (sourceMode === "order" && !sourceId)} onClick={() => void (async () => {
        const ok = await command("/billing/invoices/", { kind, partner_id: partner, reference, currency, issued_on: issued, due_on: due,
          lines: sourceMode === "manual" ? lines : [], ...(sourceMode === "order" ? { [kind === "CUSTOMER" ? "sales_order_id" : "purchase_order_id"]: sourceId } : {}) }, true);
        if (ok) { setReference(""); setLines([emptyLine()]); }
      })()}>{t("Create draft")}</Button>
    </Stack></Paper>}
    <Paper variant="outlined" sx={{ p: 2 }}><Typography variant="h6">{t("Invoices")}</Typography>
      {canWrite && <TextField label={t("Reason for voiding")} value={reason} onChange={e => setReason(e.target.value)} fullWidth sx={{ my: 2 }} />}
      {invoices.data?.results.map(row => <Stack key={row.id} gap={1} sx={{ py: 2, borderBottom: "1px solid #ddd" }}>
        <Typography fontWeight={700}>{row.reference} · {row.partner_name} · {row.kind} · {t(row.status)}</Typography>
        <Typography>{t("Total")}{" "}{row.total}{t("· Paid")}{" "}{row.paid}{t("· Remaining")}{" "}{row.balance} {row.currency}</Typography>
        <Typography variant="caption">{t("Invoice ID:")}{" "}{row.id}</Typography>
        {row.lines.map((line, i) => <Typography key={i} variant="body2">{line.description}: {line.quantity} × {line.unit_price} + {line.tax_rate}{t("% tax")}</Typography>)}
        {canWrite && <Stack direction="row" gap={1}>
          {row.status === "DRAFT" && <Button disabled={busy} onClick={() => void command(`/billing/invoices/${row.id}/post/`, {})}>{t("Post invoice")}</Button>}
          {row.status !== "VOID" && Number(row.paid) === 0 && <Button disabled={busy || !reason.trim()} onClick={() => void command(`/billing/invoices/${row.id}/void/`, { reason })}>{t("Void invoice")}</Button>}
          {row.status === "POSTED" && Number(row.balance) > 0 && <Button onClick={() => setAllocations([{ invoice_id: row.id, amount: row.balance }])}>{t("Use in payment")}</Button>}
        </Stack>}
      </Stack>)}<Pages {...invoices} />
    </Paper>
    {canWrite && <Paper variant="outlined" sx={{ p: 2 }}><Stack gap={2} component="fieldset" disabled={busy} sx={{ border: 0 }}>
      <Typography variant="h6">{t("Record and allocate payment")}</Typography>
      <Typography>{t("Each row must use a posted invoice from the same partner and currency. This records a payment already made; it does not transfer money.")}</Typography>
      <TextField label={t("Payment reference")} value={paymentRef} onChange={e => setPaymentRef(e.target.value)} />
      <TextField type="date" label={t("Paid on")} value={paidOn} onChange={e => setPaidOn(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
      {allocations.map((row, index) => <Stack key={index} direction="row" gap={1}>
        <TextField fullWidth label={t("Invoice UUID")} value={row.invoice_id} onChange={e => setAllocations(allocations.map((r,i) => i === index ? { ...r, invoice_id: e.target.value } : r))} />
        <TextField label={t("Amount")} value={row.amount} onChange={e => setAllocations(allocations.map((r,i) => i === index ? { ...r, amount: e.target.value } : r))} />
        <Button disabled={allocations.length === 1} onClick={() => setAllocations(allocations.filter((_,i) => i !== index))}>{t("Remove")}</Button>
      </Stack>)}
      <Button onClick={() => setAllocations([...allocations, { invoice_id: "", amount: "" }])}>{t("Add allocation")}</Button>
      <Button disabled={busy || !paymentRef} variant="contained" onClick={() => void (async () => {
        if (await command("/billing/payments/", { paid_on: paidOn, reference: paymentRef, allocations }, true)) { setPaymentRef(""); setAllocations([{ invoice_id: "", amount: "" }]); }
      })()}>{t("Record payment")}</Button>
    </Stack></Paper>}
    <Paper variant="outlined" sx={{ p: 2 }}><Typography variant="h6">{t("Payment history")}</Typography>
      {payments.data?.results.map(row => <Typography key={row.id}>{row.reference} · {row.kind} · {row.amount} {row.currency}</Typography>)}<Pages {...payments} />
    </Paper>
    <Paper variant="outlined" sx={{ p: 2 }}><Stack gap={2}>
      <Typography variant="h6">{t("Cash expenses")}</Typography>
      {canWrite && <Stack gap={2} component="fieldset" disabled={busy} sx={{ border: 0 }}>
        {(["description", "category", "amount", "spent_on"] as const).map(field => <TextField key={field} label={t(field.replaceAll("_", " "))} value={expense[field]}
          onChange={e => setExpense({ ...expense, [field]: e.target.value })} />)}
        <Button disabled={busy} onClick={() => void (async () => {
          if (await command("/finance/expenses/", { ...expense, currency }, true)) setExpense({ ...expense, description: "", amount: "" });
        })()}>{t("Record expense")}</Button>
      </Stack>}
      {expenses.data?.results.map(row => <Stack key={row.id} direction="row" gap={2}><Typography>{row.description} · {row.amount} {row.currency} {row.is_void ? "(void)" : ""}</Typography>
        {canWrite && !row.is_void && <Button disabled={busy || !reason.trim()} onClick={() => void command(`/finance/expenses/${row.id}/void/`, { reason })}>{t("Void with reason above")}</Button>}</Stack>)}
      <Pages {...expenses} />
    </Stack></Paper>
    <Divider /><Typography variant="h6">{t("Audit history")}</Typography>
    {events.data?.results.map(event => <Paper key={event.id} variant="outlined" sx={{ p: 1 }}>
      <Typography>{event.created_at} · {event.action} · {event.entity_type}</Typography><Typography variant="body2">{JSON.stringify(event.detail)}</Typography>
    </Paper>)}<Pages {...events} />
  </Stack>;
}
