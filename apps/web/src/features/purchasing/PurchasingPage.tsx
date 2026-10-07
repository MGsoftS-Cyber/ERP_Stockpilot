// Purchase workflow: edits drafts, requests approval and posts actual received quantities.
// Django purchasing services validate the order state and call the shared inventory posting rules.
// A receipt changes stock; the Finance module manages the related supplier invoice.
import { t } from "../../i18n";
// Teaching edition: Manage approval and receiving without computing stock in React.
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";

import { api } from "../../api/client";
import { getApiErrorMessage } from "../../api/errors";

interface Choice { id: string; name: string; partner_type?: string }
interface Line { id: string; product: string; product_name: string; quantity: string; received_quantity: string; unit_price: string }
interface Order { id: string; reference: string; supplier: string; supplier_name: string; status: string; notes: string; subtotal: string; lines: Line[]; history: { action: string; detail: string; at: string }[] }
interface DraftLine { product: string; quantity: string; unit_price: string }
const emptyLine = (): DraftLine => ({ product: "", quantity: "1", unit_price: "0" });

async function choices(path: string): Promise<Choice[]> {
  let page = 1;
  const result: Choice[] = [];
  while (true) {
    const { data } = await api.get<{ results: Choice[]; next: string | null }>(path, { params: { page } });
    result.push(...data.results);
    if (!data.next) return result;
    page += 1;
  }
}

export function PurchasingPage({ organizationId, role }: { organizationId: string; role: string }) {
  const qc = useQueryClient();
  const manager = ["ADMINISTRATOR", "MANAGER"].includes(role);
  const buyer = manager || role === "PURCHASING_AGENT";
  const receiver = buyer || role === "STOCK_OPERATOR";
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string>("");
  const [editing, setEditing] = useState<string>("");
  const [supplier, setSupplier] = useState("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<DraftLine[]>([emptyLine()]);
  const [warehouse, setWarehouse] = useState("");
  const [quantities, setQuantities] = useState<Record<string, string>>({});
  const [reason, setReason] = useState("");
  const [receiptKey, setReceiptKey] = useState(() => crypto.randomUUID());
  const [message, setMessage] = useState("");
  // Include the organization so purchasing cache entries cannot mix tenants.
  const queryKey = ["purchasing", organizationId];
  const orders = useQuery({ queryKey: [...queryKey, "orders", page], queryFn: async () =>
    (await api.get<{ results: Order[]; next: string | null }>("/purchasing/orders/", { params: { page } })).data });
  const detail = useQuery({ queryKey: [...queryKey, selected], enabled: Boolean(selected), queryFn: async () =>
    (await api.get<Order>(`/purchasing/orders/${selected}/`)).data });
  const suppliers = useQuery({ queryKey: [...queryKey, "suppliers"], queryFn: () => choices("/partners/business-partners/") });
  const products = useQuery({ queryKey: [...queryKey, "products"], queryFn: () => choices("/catalog/products/") });
  const warehouses = useQuery({ queryKey: [...queryKey, "warehouses"], queryFn: () => choices("/inventory/warehouses/") });
  const refresh = async () => {
    await qc.invalidateQueries({ queryKey });
    await qc.invalidateQueries({ queryKey: ["stock-balances"] });
    await qc.invalidateQueries({ queryKey: ["stock-movements"] });
  };
  const save = useMutation({ mutationFn: () => api.post(
    editing ? `/purchasing/orders/${editing}/revise/` : "/purchasing/orders/", { supplier, notes, lines }),
    onSuccess: async ({ data }: { data: Order }) => {
      setSelected(data.id); setEditing(""); setLines([emptyLine()]); setMessage(t("Purchase draft saved. Review its lines before submitting it for approval.")); await refresh();
    } });
  // The backend checks the action, role and source state.
  const transition = useMutation({ mutationFn: (action: string) =>
    api.post(`/purchasing/orders/${selected}/transition/`, { action, reason }),
    onSuccess: async () => { setReason(""); setMessage(t("Purchase status updated. The available actions now follow the order's new status.")); await refresh(); } });
  // Retain a command key for retries of the same delivery.
  const receive = useMutation({ mutationFn: () => api.post(`/purchasing/orders/${selected}/receive/`, {
    warehouse, idempotency_key: receiptKey,
    lines: Object.entries(quantities).filter(([, q]) => Number(q) > 0).map(([order_line, quantity]) => ({ order_line, quantity })),
  }), onSuccess: async () => {
    setReceiptKey(crypto.randomUUID()); setQuantities({}); setMessage(t("Goods receipt recorded. Stock balances and movement history now include the received quantities.")); await refresh();
  } });
  const order = detail.data;
  const pending = save.isPending || transition.isPending || receive.isPending;
  const error = save.error || transition.error || receive.error || orders.error || detail.error || suppliers.error || products.error || warehouses.error;
  const changeReceipt = () => { setReceiptKey(crypto.randomUUID()); receive.reset(); };

  return <Stack spacing={3}>
    <Typography variant="h5">{t("Purchasing and goods receipts")}</Typography>
    <Alert severity="info">{t("Create a purchase draft, submit it for approval, then record the quantities actually received. Receipts increase warehouse stock. Create the supplier invoice in Finance.")}</Alert>
    {message && <Alert severity="success" onClose={() => setMessage("")}>{message}</Alert>}
    {error && <Alert severity="error">{getApiErrorMessage(error)}</Alert>}
    {buyer && <Paper sx={{ p: 2 }}><Stack spacing={2}>
      <Typography variant="h6">{editing ? "Edit draft" : "Create draft purchase order"}</Typography>
      <TextField select label={t("Supplier")} value={supplier} onChange={e => setSupplier(e.target.value)}>
        {(suppliers.data ?? []).filter(s => s.partner_type !== "CUSTOMER").map(s => <MenuItem key={s.id} value={s.id}>{s.name}</MenuItem>)}
      </TextField>
      <TextField label={t("Notes")} value={notes} onChange={e => setNotes(e.target.value)} />
      {lines.map((line, i) => <Stack key={i} direction={{ xs: "column", md: "row" }} spacing={1}>
        <TextField select label={t("Product")} sx={{ minWidth: 240 }} value={line.product} onChange={e => setLines(lines.map((l, j) => j === i ? { ...l, product: e.target.value } : l))}>
          {(products.data ?? []).map(p => <MenuItem key={p.id} value={p.id}>{p.name}</MenuItem>)}
        </TextField>
        {(["quantity", "unit_price"] as const).map(field => <TextField key={field} label={field} value={line[field]} onChange={e => setLines(lines.map((l, j) => j === i ? { ...l, [field]: e.target.value } : l))} />)}
        <Button disabled={lines.length === 1} onClick={() => setLines(lines.filter((_, j) => j !== i))}>{t("Remove")}</Button>
      </Stack>)}
      <Stack direction="row" spacing={1}>
        <Button onClick={() => setLines([...lines, emptyLine()])}>{t("Add line")}</Button>
        <Button variant="contained" disabled={pending || !supplier || lines.some(l => !l.product || !(Number(l.quantity) > 0) || !(Number(l.unit_price) >= 0))} onClick={() => save.mutate()}>{t("Save draft")}</Button>
        {editing && <Button onClick={() => { setEditing(""); setLines([emptyLine()]); }}>{t("Cancel editing")}</Button>}
      </Stack>
    </Stack></Paper>}
    <Paper sx={{ p: 2 }}><Stack spacing={1}>
      <Typography variant="h6">{t("Purchase orders")}</Typography>
      {orders.isPending && <Typography>{t("Loading orders...")}</Typography>}
      {orders.data?.results.length === 0 && <Typography>{t("No orders yet.")}</Typography>}
      {orders.data?.results.map(o => <Button key={o.id} sx={{ justifyContent: "flex-start" }} onClick={() => { setSelected(o.id); setQuantities({}); changeReceipt(); transition.reset(); }}>
        {o.reference} | {o.supplier_name} | {o.status}
      </Button>)}
      <Stack direction="row"><Button disabled={page === 1} onClick={() => setPage(page - 1)}>{t("Previous")}</Button><Button disabled={!orders.data?.next} onClick={() => setPage(page + 1)}>{t("Next")}</Button></Stack>
    </Stack></Paper>
    {order && <Paper sx={{ p: 2 }}><Stack spacing={2}>
      <Typography variant="h6">{order.reference} - {t(order.status)}</Typography>
      <Typography>{t("Net subtotal:")}{" "}{order.subtotal}</Typography>
      {order.lines.map(l => <Typography key={l.id}>{l.product_name}{t(": ordered")}{" "}{l.quantity}{t(", received")}{" "}{l.received_quantity}{t(", unit price")}{" "}{l.unit_price}</Typography>)}
      <TextField label={t("Correction / closure reason")} value={reason} onChange={e => setReason(e.target.value)} />
      <Stack direction="row" flexWrap="wrap" gap={1}>
        {buyer && order.status === "DRAFT" && <><Button disabled={pending} onClick={() => transition.mutate("submit")}>{t("Submit")}</Button><Button onClick={() => { setEditing(order.id); setSupplier(order.supplier); setNotes(order.notes); setLines(order.lines.map(l => ({ product: l.product, quantity: l.quantity, unit_price: l.unit_price }))); }}>{t("Load draft for editing")}</Button></>}
        {manager && order.status === "SUBMITTED" && <><Button disabled={pending} onClick={() => transition.mutate("approve")}>{t("Approve")}</Button><Button disabled={pending || !reason.trim()} onClick={() => transition.mutate("return_to_draft")}>{t("Return for correction")}</Button></>}
        {buyer && ["DRAFT", "SUBMITTED", "APPROVED"].includes(order.status) && <Button disabled={pending} onClick={() => transition.mutate("cancel")}>{t("Cancel order")}</Button>}
        {manager && order.status === "RECEIVED" && <Button disabled={pending || !reason.trim()} onClick={() => transition.mutate("close")}>{t("Close with review note")}</Button>}
      </Stack>
      {receiver && ["APPROVED", "PARTIALLY_RECEIVED"].includes(order.status) && <Stack spacing={2}>
        <Typography variant="h6">{t("Receive goods (enter only quantities received today)")}</Typography>
        <TextField disabled={receive.isPending} select label={t("Warehouse")} value={warehouse} onChange={e => { setWarehouse(e.target.value); changeReceipt(); }}>
          {(warehouses.data ?? []).map(w => <MenuItem key={w.id} value={w.id}>{w.name}</MenuItem>)}
        </TextField>
        {order.lines.filter(l => Number(l.received_quantity) < Number(l.quantity)).map(l => <TextField disabled={receive.isPending} key={l.id} label={`${l.product_name} - received now`} value={quantities[l.id] ?? ""} onChange={e => { setQuantities({ ...quantities, [l.id]: e.target.value }); changeReceipt(); }} />)}
        <Button variant="contained" disabled={pending || !warehouse || !Object.values(quantities).some(q => Number(q) > 0)} onClick={() => receive.mutate()}>{t("Post goods receipt")}</Button>
        <Typography variant="caption">{t("An unchanged retry reuses its command key. If a request timed out, retry without changing fields first.")}</Typography>
      </Stack>}
      <Typography variant="h6">{t("History")}</Typography>
      {order.history.map((h, i) => <Typography key={i} variant="body2">{h.at} - {h.action} {h.detail}</Typography>)}
    </Stack></Paper>}
  </Stack>;
}
