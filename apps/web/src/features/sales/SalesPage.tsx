// Sales workflow: drafts promise goods, confirmation reserves stock, shipment records delivery.
// React sends commands; Django sales and inventory services calculate totals and enforce quantities.
// Returns append compensating stock movements rather than editing shipment history.
import { t } from "../../i18n";
// React submits commands; Django owns stock, totals, permissions and statuses.
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Box, Button, Chip, MenuItem, Paper, Stack, Table, TableBody,
  TableCell, TableHead, TableRow, TextField, Typography,
} from "@mui/material";

import { api } from "../../api/client";
import { getApiErrorMessage } from "../../api/errors";

type Choice = { id: string; name: string; partner_type?: string; is_active?: boolean };
type DraftLine = { product: string; quantity: string; unit_price: string };
type OrderLine = DraftLine & { id: string; product_name: string; shipped_quantity: string };
type ShippedLine = { id: string; product_name: string; quantity: string; returned_quantity: string };
type ReturnDocument = { id: string; reason: string };
type Shipment = { id: string; lines: ShippedLine[]; returns: ReturnDocument[] };
type Order = {
  id: string; reference: string; customer: string; customer_name: string;
  warehouse: string; warehouse_name: string; status: string; notes: string;
  subtotal: string; lines: OrderLine[]; shipments: Shipment[];
  history: { action: string; detail: string; at: string }[];
};
type Page<T> = { results: T[]; next: string | null; previous: string | null };
const blankLine = (): DraftLine => ({ product: "", quantity: "1", unit_price: "0" });

async function allChoices(path: string): Promise<Choice[]> {
  // Follow pagination so the selector does not silently omit records after item 25.
  const rows: Choice[] = [];
  for (let page = 1; ; page += 1) {
    const { data } = await api.get<Page<Choice>>(path, { params: { page } });
    rows.push(...data.results.filter((row) => row.is_active !== false));
    if (!data.next) return rows;
  }
}

export function SalesPage({ organizationId, role }: { organizationId: string; role: string }) {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState("");
  const [editing, setEditing] = useState("");
  const [customer, setCustomer] = useState("");
  const [warehouse, setWarehouse] = useState("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<DraftLine[]>([blankLine()]);
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState("");
  const [shipQuantities, setShipQuantities] = useState<Record<string, string>>({});
  const [shipKey, setShipKey] = useState(() => crypto.randomUUID());
  const [returnShipment, setReturnShipment] = useState("");
  const [returnQuantities, setReturnQuantities] = useState<Record<string, string>>({});
  const [returnReason, setReturnReason] = useState("");
  const [returnKey, setReturnKey] = useState(() => crypto.randomUUID());
  const canSell = ["ADMINISTRATOR", "MANAGER", "SALES_AGENT"].includes(role);
  const canShip = ["ADMINISTRATOR", "MANAGER", "STOCK_OPERATOR"].includes(role);
  // Every sales cache key includes the selected organization to isolate tenants.
  const key = ["sales", organizationId];
  const orders = useQuery({ queryKey: [...key, "orders", page], queryFn: async () =>
    (await api.get<Page<Order>>("/sales/orders/", { params: { page } })).data });
  const detail = useQuery({ queryKey: [...key, "detail", selected], enabled: Boolean(selected),
    queryFn: async () => (await api.get<Order>(`/sales/orders/${selected}/`)).data });
  const customers = useQuery({ queryKey: [...key, "customers"], queryFn: () => allChoices("/partners/business-partners/") });
  const products = useQuery({ queryKey: [...key, "products"], queryFn: () => allChoices("/catalog/products/") });
  const warehouses = useQuery({ queryKey: [...key, "warehouses"], queryFn: () => allChoices("/inventory/warehouses/") });
  const order = detail.data;
  const chosenShipment = order?.shipments.find((s) => s.id === returnShipment);

  const command = useMutation({
    mutationFn: async ({ path, payload }: { path: string; payload: unknown }) =>
      (await api.post<{ id: string }>(path, payload)).data,
    onSuccess: async () => {
      // Shipment and returns affect both the document screen and inventory screens.
      await Promise.all([
        qc.invalidateQueries({ queryKey: key }),
        ...["stock-balances", "stock-movements", "stock-reservations"].map((name) =>
          qc.invalidateQueries({ queryKey: [name] })),
      ]);
    },
  });
  const busy = command.isPending;

  async function run(path: string, payload: unknown, success: string) {
    setMessage("");
    try {
      const result = await command.mutateAsync({ path, payload });
      setMessage(t(success));
      return result;
    } catch {
      // Keep inputs and the command UUID unchanged after network errors for safe retry.
      return null;
    }
  }

  function selectOrder(id: string) {
    setSelected(id); setShipQuantities({}); setShipKey(crypto.randomUUID());
    setReturnShipment(""); setReturnQuantities({}); setReturnReason("");
    setReturnKey(crypto.randomUUID()); setReason(""); setMessage(""); command.reset();
  }

  async function saveDraft() {
    // Draft creation itself is not idempotent. Check the order list after ambiguous failures.
    const saved = await run(editing ? `/sales/orders/${editing}/revise/` : "/sales/orders/",
      { customer, warehouse, notes, lines }, editing ? "Draft updated." : "Draft created.");
    if (saved) { setSelected(saved.id); setEditing(""); setLines([blankLine()]); setNotes(""); }
  }

  async function ship() {
    const shipment = await run(`/sales/orders/${selected}/ship/`, {
      idempotency_key: shipKey,
      lines: Object.entries(shipQuantities).filter(([, q]) => q.trim() !== "" && q !== "0")
        .map(([order_line, quantity]) => ({ order_line, quantity })),
    }, "Shipment posted and stock updated.");
    if (shipment) { setShipQuantities({}); setShipKey(crypto.randomUUID()); }
  }

  async function returnGoods() {
    const returned = await run(`/sales/shipments/${returnShipment}/return/`, {
      idempotency_key: returnKey, reason: returnReason,
      lines: Object.entries(returnQuantities).filter(([, q]) => q.trim() !== "" && q !== "0")
        .map(([shipment_line, quantity]) => ({ shipment_line, quantity })),
    }, "Customer return posted to the original warehouse.");
    if (returned) { setReturnQuantities({}); setReturnKey(crypto.randomUUID()); setReturnReason(""); }
  }

  return <Stack spacing={3}>
    <Typography variant="h4">{t("Sales and fulfilment")}</Typography>
    <Typography color="text.secondary">{t("Draft orders, reserve stock, ship quantities and record customer returns.")}</Typography>
    {message && <Alert severity="success">{message}</Alert>}
    {command.error && <Alert severity="error">{getApiErrorMessage(command.error)}</Alert>}
    {[orders, detail, customers, products, warehouses].some((q) => q.isError) &&
      <Alert severity="error">{t("Could not load sales data. Check the connection and selected organization.")}</Alert>}

    {/* This fieldset prevents edits while any command is pending. */}
    {canSell && <Paper variant="outlined" sx={{ p: 2 }}>
      <Box component="fieldset" disabled={busy} sx={{ border: 0, m: 0, p: 0 }}>
        <Stack spacing={2}>
          <Typography variant="h6">{editing ? "Edit draft" : "New sales order"}</Typography>
          <TextField select label={t("Customer")} value={customer} onChange={(e) => setCustomer(e.target.value)}>
            {(customers.data ?? []).filter((c) => c.partner_type !== "SUPPLIER").map((c) =>
              <MenuItem key={c.id} value={c.id}>{c.name}</MenuItem>)}
          </TextField>
          <TextField select label={t("Shipping warehouse")} value={warehouse} onChange={(e) => setWarehouse(e.target.value)}>
            {(warehouses.data ?? []).map((w) => <MenuItem key={w.id} value={w.id}>{w.name}</MenuItem>)}
          </TextField>
          {lines.map((line, i) => <Stack key={i} direction={{ xs: "column", md: "row" }} spacing={1}>
            <TextField select label={t("Product")} value={line.product} sx={{ minWidth: 220 }}
              onChange={(e) => setLines(lines.map((v, j) => j === i ? { ...v, product: e.target.value } : v))}>
              {(products.data ?? []).map((p) => <MenuItem key={p.id} value={p.id}>{p.name}</MenuItem>)}
            </TextField>
            <TextField label={t("Quantity")} value={line.quantity}
              onChange={(e) => setLines(lines.map((v, j) => j === i ? { ...v, quantity: e.target.value } : v))} />
            <TextField label={t("Unit selling price")} value={line.unit_price}
              onChange={(e) => setLines(lines.map((v, j) => j === i ? { ...v, unit_price: e.target.value } : v))} />
            <Button disabled={lines.length === 1} onClick={() => setLines(lines.filter((_, j) => j !== i))}>{t("Remove")}</Button>
          </Stack>)}
          <Button onClick={() => setLines([...lines, blankLine()])}>{t("Add product line")}</Button>
          <TextField label={t("Notes")} value={notes} onChange={(e) => setNotes(e.target.value)} />
          <Stack direction="row" spacing={1}>
            <Button variant="contained" disabled={busy || !customer || !warehouse || lines.some((l) => !l.product)}
              onClick={() => void saveDraft()}>{t("Save draft")}</Button>
            {editing && <Button onClick={() => { setEditing(""); setLines([blankLine()]); setNotes(""); }}>{t("Stop editing")}</Button>}
          </Stack>
        </Stack>
      </Box>
    </Paper>}

    <Paper variant="outlined" sx={{ p: 2, overflowX: "auto" }}>
      <Typography variant="h6">{t("Orders")}</Typography>
      {orders.isPending && <Typography>{t("Loading orders...")}</Typography>}
      {orders.data?.results.length === 0 && <Typography>{t("No sales orders yet.")}</Typography>}
      <Table size="small"><TableHead><TableRow>
        <TableCell>{t("Reference")}</TableCell><TableCell>{t("Customer")}</TableCell><TableCell>{t("Status")}</TableCell><TableCell />
      </TableRow></TableHead><TableBody>{orders.data?.results.map((row) => <TableRow key={row.id} selected={selected === row.id}>
        <TableCell>{row.reference}</TableCell><TableCell>{row.customer_name}</TableCell><TableCell>{t(row.status)}</TableCell>
        <TableCell><Button disabled={busy} onClick={() => selectOrder(row.id)}>{t("Open")}</Button></TableCell>
      </TableRow>)}</TableBody></Table>
      <Button disabled={page === 1 || busy} onClick={() => setPage(page - 1)}>{t("Previous")}</Button>
      <Button disabled={!orders.data?.next || busy} onClick={() => setPage(page + 1)}>{t("Next")}</Button>
    </Paper>

    {order && <Paper variant="outlined" sx={{ p: 2 }}><Stack spacing={2}>
      <Typography variant="h6">{order.reference}</Typography><Chip label={t(order.status)} sx={{ alignSelf: "start" }} />
      <Typography>{order.customer_name} / {order.warehouse_name}{t("/ Subtotal")}{" "}{order.subtotal}</Typography>
      <Table size="small"><TableHead><TableRow><TableCell>{t("Product")}</TableCell><TableCell>{t("Ordered")}</TableCell><TableCell>{t("Shipped")}</TableCell></TableRow></TableHead>
        <TableBody>{order.lines.map((line) => <TableRow key={line.id}><TableCell>{line.product_name}</TableCell><TableCell>{line.quantity}</TableCell><TableCell>{line.shipped_quantity}</TableCell></TableRow>)}</TableBody>
      </Table>
      {canSell && order.status === "DRAFT" && <Stack direction="row" spacing={1}>
        <Button disabled={busy} onClick={() => { setEditing(order.id); setCustomer(order.customer); setWarehouse(order.warehouse); setNotes(order.notes); setLines(order.lines.map(({ product, quantity, unit_price }) => ({ product, quantity, unit_price }))); }}>{t("Edit draft")}</Button>
        <Button variant="contained" disabled={busy} onClick={() => void run(`/sales/orders/${selected}/confirm/`, {}, "Order confirmed and stock reserved.")}>{t("Confirm and reserve")}</Button>
      </Stack>}
      {canSell && ["DRAFT", "CONFIRMED", "PARTIALLY_SHIPPED"].includes(order.status) && <Stack direction={{ xs: "column", md: "row" }} spacing={1}>
        <TextField label={t("Cancellation reason")} value={reason} disabled={busy} onChange={(e) => setReason(e.target.value)} />
        <Button color="warning" disabled={busy || !reason.trim()} onClick={() => void run(`/sales/orders/${selected}/cancel/`, { reason }, "Unshipped remainder cancelled and reservation released.")}>{t("Cancel remaining order")}</Button>
      </Stack>}

      {canShip && ["CONFIRMED", "PARTIALLY_SHIPPED"].includes(order.status) && <Stack spacing={1}>
        <Typography variant="h6">{t("Post a shipment")}</Typography>
        {order.lines.filter((l) => Number(l.shipped_quantity) < Number(l.quantity)).map((line) =>
          <TextField key={line.id} label={`${line.product_name}: quantity to ship`} disabled={busy} value={shipQuantities[line.id] ?? ""}
            onChange={(e) => { setShipQuantities({ ...shipQuantities, [line.id]: e.target.value }); setShipKey(crypto.randomUUID()); }} />)}
        <Button variant="contained" disabled={busy || !Object.values(shipQuantities).some((q) => Number(q) > 0)} onClick={() => void ship()}>{t("Ship entered quantities")}</Button>
      </Stack>}

      {/* Returns restore physical stock but do not reopen a shipped/cancelled order. */}
      <Typography variant="h6">{t("Shipments and returns")}</Typography>
      {order.shipments.map((s) => <Box key={s.id}>
        <Typography variant="body2">{t("Shipment")}{" "}{s.id}</Typography>
        {s.lines.map((l) => <Typography key={l.id} variant="body2">{l.product_name}{t(": shipped")}{" "}{l.quantity}{t(", returned")}{" "}{l.returned_quantity}</Typography>)}
        {s.returns.map((r) => <Typography key={r.id} variant="body2">{t("Return")}{" "}{r.id}: {r.reason}</Typography>)}
        {canShip && <Button disabled={busy} onClick={() => { setReturnShipment(s.id); setReturnQuantities({}); setReturnReason(""); setReturnKey(crypto.randomUUID()); }}>{t("Record customer return")}</Button>}
      </Box>)}
      {canShip && chosenShipment && <Stack spacing={1}>
        {chosenShipment.lines.filter((l) => Number(l.returned_quantity) < Number(l.quantity)).map((line) =>
          <TextField key={line.id} label={`${line.product_name}: quantity to return`} disabled={busy} value={returnQuantities[line.id] ?? ""}
            onChange={(e) => { setReturnQuantities({ ...returnQuantities, [line.id]: e.target.value }); setReturnKey(crypto.randomUUID()); }} />)}
        <TextField label={t("Return reason")} value={returnReason} disabled={busy} onChange={(e) => { setReturnReason(e.target.value); setReturnKey(crypto.randomUUID()); }} />
        <Button disabled={busy || !returnReason.trim() || !Object.values(returnQuantities).some((q) => Number(q) > 0)} onClick={() => void returnGoods()}>{t("Post return")}</Button>
      </Stack>}
      <Typography variant="h6">{t("History")}</Typography>
      {order.history.map((e, i) => <Typography key={i} variant="body2">{new Date(e.at).toLocaleString()} - {e.action}: {e.detail}</Typography>)}
    </Stack></Paper>}
  </Stack>;
}
