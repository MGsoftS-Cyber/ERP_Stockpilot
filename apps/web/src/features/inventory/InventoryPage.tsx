// Inventory interface: submits adjustment, transfer and reservation commands to Django.
// An idempotency UUID identifies a write attempt so a repeated request cannot post stock twice.
// Balances are read views; only backend services append movements and update their projection.
import { allPages } from "../../api/pagination";
import { useAuth } from "../../auth/AuthContext";
import { Pages } from "../../features/finance/shared";
import { t } from "../../i18n";
// Teaching edition: Display balances/history and submit inventory commands.
import AddIcon from "@mui/icons-material/Add";
import BookmarkAddOutlinedIcon from "@mui/icons-material/BookmarkAddOutlined";
import SwapHorizIcon from "@mui/icons-material/SwapHoriz";
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Paper,
  Skeleton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../../api/client";
import { getApiErrorMessage } from "../../api/errors";
import type {
  PaginatedResponse,
  Product,
  StockBalance,
  StockMovement,
  StockReservation,
  Warehouse,
} from "../../types";

interface AdjustmentForm {
  warehouse: string;
  product: string;
  quantity: string;
  unitCost: string;
  reason: string;
}

interface TransferForm {
  sourceWarehouse: string;
  destinationWarehouse: string;
  product: string;
  quantity: string;
  unitCost: string;
  reason: string;
}

interface ReservationForm {
  warehouse: string;
  product: string;
  quantity: string;
}

const emptyAdjustment: AdjustmentForm = {
  warehouse: "",
  product: "",
  quantity: "",
  unitCost: "0.0000",
  reason: "",
};

const emptyTransfer: TransferForm = {
  sourceWarehouse: "",
  destinationWarehouse: "",
  product: "",
  quantity: "",
  unitCost: "0.0000",
  reason: "",
};

const emptyReservation: ReservationForm = {
  warehouse: "",
  product: "",
  quantity: "",
};

interface InventoryPageProps {
  canOperate: boolean;
  canReserve: boolean;
}

export function InventoryPage({ canOperate, canReserve }: InventoryPageProps) {
  const queryClient = useQueryClient();
  const { selectedMembership } = useAuth();
  const organizationId = selectedMembership?.organization.id;
  const [adjustmentOpen, setAdjustmentOpen] = useState(false);
  const [transferOpen, setTransferOpen] = useState(false);
  const [reservationOpen, setReservationOpen] = useState(false);
  const [adjustment, setAdjustment] = useState(emptyAdjustment);
  const [transfer, setTransfer] = useState(emptyTransfer);
  const [reservation, setReservation] = useState(emptyReservation);
  const [adjustmentKey, setAdjustmentKey] = useState(() => crypto.randomUUID());
  const [transferKey, setTransferKey] = useState(() => crypto.randomUUID());
  const [reservationKey, setReservationKey] = useState(() => crypto.randomUUID());
  const [reservationSourceId, setReservationSourceId] = useState(
    () => crypto.randomUUID(),
  );

  const [balancePage, setBalancePage] = useState(1);
  const balances = useQuery({
    queryKey: ["stock-balances", organizationId, balancePage],
    queryFn: async () =>
      (await api.get<PaginatedResponse<StockBalance>>("/inventory/stock-balances/", { params: { page: balancePage } }))
        .data,
  });
  const [movementPage, setMovementPage] = useState(1);
  const movements = useQuery({
    queryKey: ["stock-movements", organizationId, movementPage],
    queryFn: async () =>
      (await api.get<PaginatedResponse<StockMovement>>("/inventory/stock-movements/", { params: { page: movementPage } }))
        .data,
  });
  const [reservationPage, setReservationPage] = useState(1);
  const reservations = useQuery({
    queryKey: ["stock-reservations", organizationId, reservationPage],
    queryFn: async () =>
      (await api.get<PaginatedResponse<StockReservation>>("/inventory/stock-reservations/", { params: { page: reservationPage } }))
        .data,
  });
  const products = useQuery({
    queryKey: ["product-choices", organizationId],
    queryFn: async () =>
      allPages<Product>("/catalog/products/"),
  });
  const warehouses = useQuery({
    queryKey: ["warehouses", organizationId],
    queryFn: async () =>
      allPages<Warehouse>("/inventory/warehouses/"),
  });

  const refreshInventory = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["stock-balances"] }),
      queryClient.invalidateQueries({ queryKey: ["stock-movements"] }),
      queryClient.invalidateQueries({ queryKey: ["stock-reservations"] }),
    ]);
  };

  // Send a signed correction document, not an overwritten balance.
  const adjustmentMutation = useMutation({
    mutationFn: async (form: AdjustmentForm) =>
      api.post("/inventory/stock-adjustments/", {
        warehouse: form.warehouse,
        reason: form.reason,
        idempotency_key: adjustmentKey,
        lines: [
          {
            product: form.product,
            quantity_signed: form.quantity,
            unit_cost: form.unitCost || "0.0000",
          },
        ],
      }),
    onSuccess: async () => {
      await refreshInventory();
      setAdjustment(emptyAdjustment);
      setAdjustmentKey(crypto.randomUUID());
      setAdjustmentOpen(false);
    },
  });

  // Send one command for both warehouse stock movements.
  const transferMutation = useMutation({
    mutationFn: async (form: TransferForm) =>
      api.post("/inventory/stock-transfers/", {
        source_warehouse: form.sourceWarehouse,
        destination_warehouse: form.destinationWarehouse,
        reason: form.reason,
        idempotency_key: transferKey,
        lines: [
          {
            product: form.product,
            quantity: form.quantity,
            unit_cost: form.unitCost || "0.0000",
          },
        ],
      }),
    onSuccess: async () => {
      await refreshInventory();
      setTransfer(emptyTransfer);
      setTransferKey(crypto.randomUUID());
      setTransferOpen(false);
    },
  });

  // Reserve availability without changing on-hand quantity.
  const reservationMutation = useMutation({
    mutationFn: async (form: ReservationForm) =>
      api.post("/inventory/stock-reservations/", {
        warehouse: form.warehouse,
        product: form.product,
        quantity: form.quantity,
        source_type: "MANUAL",
        source_id: reservationSourceId,
        idempotency_key: reservationKey,
      }),
    onSuccess: async () => {
      await refreshInventory();
      setReservation(emptyReservation);
      setReservationKey(crypto.randomUUID());
      setReservationSourceId(crypto.randomUUID());
      setReservationOpen(false);
    },
  });

  // Release a manual allocation; sales allocations use cancellation.
  const releaseMutation = useMutation({
    mutationFn: async (reservationId: string) =>
      api.post(`/inventory/stock-reservations/${reservationId}/release/`),
    onSuccess: refreshInventory,
  });

  const adjustmentValid = Boolean(
    adjustment.warehouse
      && adjustment.product
      && adjustment.reason.trim()
      && Number(adjustment.quantity) !== 0,
  );
  const transferValid = Boolean(
    transfer.sourceWarehouse
      && transfer.destinationWarehouse
      && transfer.sourceWarehouse !== transfer.destinationWarehouse
      && transfer.product
      && Number(transfer.quantity) > 0,
  );
  const reservationValid = Boolean(
    reservation.warehouse
      && reservation.product
      && Number(reservation.quantity) > 0,
  );

  return (
    <Stack spacing={4}>
      <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" gap={2}>
        <Box>
          <Typography variant="h5" fontWeight={700}>{t("Inventory ledger")}</Typography>
          <Typography color="text.secondary">{t("Immutable movements with current, reserved and available stock by warehouse.")}</Typography>
        </Box>
        {(canOperate || canReserve) && (
          <Stack direction="row" spacing={1}>
            {canReserve && (
              <Button
                variant="outlined"
                startIcon={<BookmarkAddOutlinedIcon />}
                onClick={() => setReservationOpen(true)}
              >{t("Reserve")}</Button>
            )}
            {canOperate && (
              <>
                <Button
                  variant="outlined"
                  startIcon={<AddIcon />}
                  onClick={() => setAdjustmentOpen(true)}
                >{t("Adjustment")}</Button>
                <Button
                  variant="contained"
                  startIcon={<SwapHorizIcon />}
                  onClick={() => setTransferOpen(true)}
                >{t("Transfer")}</Button>
              </>
            )}
          </Stack>
        )}
      </Stack>

      {(balances.isError || movements.isError || reservations.isError || releaseMutation.isError) && (
        <Alert severity="error">
          {getApiErrorMessage(
            balances.error
              ?? movements.error
              ?? reservations.error
              ?? releaseMutation.error,
          )}
        </Alert>
      )}

      <Box>
        <Typography variant="h6" fontWeight={700} mb={1}>{t("Stock balances")}</Typography>
        <Pages page={balancePage} setPage={setBalancePage} data={balances.data} />
        <Paper variant="outlined" sx={{ overflowX: "auto" }}>
          {balances.isLoading ? (
            <LoadingRows />
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{t("SKU")}</TableCell>
                  <TableCell>{t("Product")}</TableCell>
                  <TableCell>{t("Warehouse")}</TableCell>
                  <TableCell align="right">{t("On hand")}</TableCell>
                  <TableCell align="right">{t("Reserved")}</TableCell>
                  <TableCell align="right">{t("Available")}</TableCell>
                  <TableCell>{t("Status")}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {balances.data?.results.map((balance) => (
                  <TableRow key={balance.id} hover>
                    <TableCell>{balance.product_sku}</TableCell>
                    <TableCell>{balance.product_name}</TableCell>
                    <TableCell>{balance.warehouse_code}</TableCell>
                    <TableCell align="right">{balance.on_hand}</TableCell>
                    <TableCell align="right">{balance.reserved}</TableCell>
                    <TableCell align="right">
                      {balance.available}
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={balance.is_low_stock ? "Low stock" : "Healthy"}
                        size="small"
                        color={balance.is_low_stock ? "warning" : "success"}
                      />
                    </TableCell>
                  </TableRow>
                ))}
                {balances.data?.results.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={7}>{t("No stock has been posted yet.")}</TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </Paper>
      </Box>

      <Box>
        <Typography variant="h6" fontWeight={700} mb={1}>{t("Reservations")}</Typography>
        <Pages page={reservationPage} setPage={setReservationPage} data={reservations.data} />
        <Paper variant="outlined" sx={{ overflowX: "auto" }}>
          {reservations.isLoading ? (
            <LoadingRows />
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{t("Created")}</TableCell>
                  <TableCell>{t("SKU")}</TableCell>
                  <TableCell>{t("Warehouse")}</TableCell>
                  <TableCell align="right">{t("Quantity")}</TableCell>
                  <TableCell>{t("Status")}</TableCell>
                  <TableCell align="right">{t("Action")}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {reservations.data?.results.map((item) => (
                  <TableRow key={item.id} hover>
                    <TableCell>{new Date(item.created_at).toLocaleString()}</TableCell>
                    <TableCell>{item.product_sku}</TableCell>
                    <TableCell>{item.warehouse_code}</TableCell>
                    <TableCell align="right">
                      {item.quantity}{t("(fulfilled")}{" "}{item.fulfilled_quantity})
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={item.status_label}
                        size="small"
                        color={item.status === "ACTIVE" ? "info" : "default"}
                      />
                    </TableCell>
                    <TableCell align="right">
                      {canReserve && item.status === "ACTIVE" && item.source_type !== "SALES_ORDER" ? (
                        <Button
                          size="small"
                          disabled={releaseMutation.isPending}
                          onClick={() => releaseMutation.mutate(item.id)}
                        >{t("Release")}</Button>
                      ) : "—"}
                    </TableCell>
                  </TableRow>
                ))}
                {reservations.data?.results.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6}>{t("No stock is reserved.")}</TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </Paper>
      </Box>

      <Box>
        <Typography variant="h6" fontWeight={700} mb={1}>{t("Movement history")}</Typography>
        <Pages page={movementPage} setPage={setMovementPage} data={movements.data} />
        <Paper variant="outlined" sx={{ overflowX: "auto" }}>
          {movements.isLoading ? (
            <LoadingRows />
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{t("Date")}</TableCell>
                  <TableCell>{t("SKU")}</TableCell>
                  <TableCell>{t("Warehouse")}</TableCell>
                  <TableCell>{t("Movement")}</TableCell>
                  <TableCell align="right">{t("Quantity")}</TableCell>
                  <TableCell align="right">{t("Unit cost")}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {movements.data?.results.map((movement) => (
                  <TableRow key={movement.id} hover>
                    <TableCell>{new Date(movement.occurred_at).toLocaleString()}</TableCell>
                    <TableCell>{movement.product_sku}</TableCell>
                    <TableCell>{movement.warehouse_code}</TableCell>
                    <TableCell>{movement.movement_type_label}</TableCell>
                    <TableCell
                      align="right"
                      sx={{ color: Number(movement.quantity_signed) < 0 ? "error.main" : "success.main" }}
                    >
                      {movement.quantity_signed}
                    </TableCell>
                    <TableCell align="right">{movement.unit_cost}</TableCell>
                  </TableRow>
                ))}
                {movements.data?.results.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6}>{t("No movements have been posted yet.")}</TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </Paper>
      </Box>

      <AdjustmentDialog
        open={adjustmentOpen}
        form={adjustment}
        products={products.data?.results ?? []}
        warehouses={warehouses.data?.results ?? []}
        error={adjustmentMutation.error}
        pending={adjustmentMutation.isPending}
        valid={adjustmentValid}
        onChange={setAdjustment}
        onClose={() => {
          adjustmentMutation.reset();
          setAdjustment(emptyAdjustment);
          setAdjustmentKey(crypto.randomUUID());
          setAdjustmentOpen(false);
        }}
        onSubmit={() => adjustmentMutation.mutate(adjustment)}
      />
      <TransferDialog
        open={transferOpen}
        form={transfer}
        products={products.data?.results ?? []}
        warehouses={warehouses.data?.results ?? []}
        error={transferMutation.error}
        pending={transferMutation.isPending}
        valid={transferValid}
        onChange={setTransfer}
        onClose={() => {
          transferMutation.reset();
          setTransfer(emptyTransfer);
          setTransferKey(crypto.randomUUID());
          setTransferOpen(false);
        }}
        onSubmit={() => transferMutation.mutate(transfer)}
      />
      <ReservationDialog
        open={reservationOpen}
        form={reservation}
        products={products.data?.results ?? []}
        warehouses={warehouses.data?.results ?? []}
        error={reservationMutation.error}
        pending={reservationMutation.isPending}
        valid={reservationValid}
        onChange={setReservation}
        onClose={() => {
          reservationMutation.reset();
          setReservation(emptyReservation);
          setReservationKey(crypto.randomUUID());
          setReservationSourceId(crypto.randomUUID());
          setReservationOpen(false);
        }}
        onSubmit={() => reservationMutation.mutate(reservation)}
      />
    </Stack>
  );
}

function LoadingRows() {
  return <Stack p={3}><Skeleton /><Skeleton /><Skeleton /></Stack>;
}

interface AdjustmentDialogProps {
  open: boolean;
  form: AdjustmentForm;
  products: Product[];
  warehouses: Warehouse[];
  error: unknown;
  pending: boolean;
  valid: boolean;
  onChange: (form: AdjustmentForm) => void;
  onClose: () => void;
  onSubmit: () => void;
}

function AdjustmentDialog(props: AdjustmentDialogProps) {
  const { open, form, products, warehouses, error, pending, valid } = props;
  return (
    <Dialog open={open} onClose={props.onClose} fullWidth maxWidth="sm">
      <DialogTitle>{t("Post stock adjustment")}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} mt={1}>
          {error ? <Alert severity="error">{getApiErrorMessage(error)}</Alert> : null}
          <TextField
            select
            label={t("Warehouse")}
            value={form.warehouse}
            onChange={(event) => props.onChange({ ...form, warehouse: event.target.value })}
          >
            {warehouses.map((warehouse) => (
              <MenuItem key={warehouse.id} value={warehouse.id}>
                {warehouse.code} — {warehouse.name}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            select
            label={t("Product")}
            value={form.product}
            onChange={(event) => props.onChange({ ...form, product: event.target.value })}
          >
            {products.map((product) => (
              <MenuItem key={product.id} value={product.id}>
                {product.sku} — {product.name}
              </MenuItem>
            ))}
          </TextField>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField
              label={t("Signed quantity")}
              type="number"
              value={form.quantity}
              inputProps={{ step: "0.0001" }}
              helperText={t("Positive adds stock; negative removes stock.")}
              onChange={(event) => props.onChange({ ...form, quantity: event.target.value })}
              fullWidth
            />
            <TextField
              label={t("Unit cost")}
              type="number"
              value={form.unitCost}
              inputProps={{ min: 0, step: "0.0001" }}
              onChange={(event) => props.onChange({ ...form, unitCost: event.target.value })}
              fullWidth
            />
          </Stack>
          <TextField
            label={t("Reason")}
            value={form.reason}
            onChange={(event) => props.onChange({ ...form, reason: event.target.value })}
            multiline
            minRows={2}
            required
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={props.onClose}>{t("Cancel")}</Button>
        <Button variant="contained" disabled={!valid || pending} onClick={props.onSubmit}>{t("Post adjustment")}</Button>
      </DialogActions>
    </Dialog>
  );
}

interface TransferDialogProps {
  open: boolean;
  form: TransferForm;
  products: Product[];
  warehouses: Warehouse[];
  error: unknown;
  pending: boolean;
  valid: boolean;
  onChange: (form: TransferForm) => void;
  onClose: () => void;
  onSubmit: () => void;
}

function TransferDialog(props: TransferDialogProps) {
  const { open, form, products, warehouses, error, pending, valid } = props;
  return (
    <Dialog open={open} onClose={props.onClose} fullWidth maxWidth="md">
      <DialogTitle>{t("Transfer stock between warehouses")}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} mt={1}>
          {error ? <Alert severity="error">{getApiErrorMessage(error)}</Alert> : null}
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField
              select
              label={t("Source warehouse")}
              value={form.sourceWarehouse}
              onChange={(event) => props.onChange({ ...form, sourceWarehouse: event.target.value })}
              fullWidth
            >
              {warehouses.map((warehouse) => (
                <MenuItem key={warehouse.id} value={warehouse.id}>{warehouse.code}</MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label={t("Destination warehouse")}
              value={form.destinationWarehouse}
              onChange={(event) => props.onChange({ ...form, destinationWarehouse: event.target.value })}
              fullWidth
            >
              {warehouses.map((warehouse) => (
                <MenuItem key={warehouse.id} value={warehouse.id}>{warehouse.code}</MenuItem>
              ))}
            </TextField>
          </Stack>
          <TextField
            select
            label={t("Product")}
            value={form.product}
            onChange={(event) => props.onChange({ ...form, product: event.target.value })}
          >
            {products.map((product) => (
              <MenuItem key={product.id} value={product.id}>
                {product.sku} — {product.name}
              </MenuItem>
            ))}
          </TextField>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField
              label={t("Quantity")}
              type="number"
              value={form.quantity}
              inputProps={{ min: "0.0001", step: "0.0001" }}
              onChange={(event) => props.onChange({ ...form, quantity: event.target.value })}
              fullWidth
            />
            <TextField
              label={t("Unit cost")}
              type="number"
              value={form.unitCost}
              inputProps={{ min: 0, step: "0.0001" }}
              onChange={(event) => props.onChange({ ...form, unitCost: event.target.value })}
              fullWidth
            />
          </Stack>
          <TextField
            label={t("Reason (optional)")}
            value={form.reason}
            onChange={(event) => props.onChange({ ...form, reason: event.target.value })}
            multiline
            minRows={2}
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={props.onClose}>{t("Cancel")}</Button>
        <Button variant="contained" disabled={!valid || pending} onClick={props.onSubmit}>{t("Transfer stock")}</Button>
      </DialogActions>
    </Dialog>
  );
}

interface ReservationDialogProps {
  open: boolean;
  form: ReservationForm;
  products: Product[];
  warehouses: Warehouse[];
  error: unknown;
  pending: boolean;
  valid: boolean;
  onChange: (form: ReservationForm) => void;
  onClose: () => void;
  onSubmit: () => void;
}

function ReservationDialog(props: ReservationDialogProps) {
  const { open, form, products, warehouses, error, pending, valid } = props;
  return (
    <Dialog open={open} onClose={props.onClose} fullWidth maxWidth="sm">
      <DialogTitle>{t("Reserve available stock")}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} mt={1}>
          {error ? <Alert severity="error">{getApiErrorMessage(error)}</Alert> : null}
          <TextField
            select
            label={t("Warehouse")}
            value={form.warehouse}
            onChange={(event) => props.onChange({ ...form, warehouse: event.target.value })}
          >
            {warehouses.map((warehouse) => (
              <MenuItem key={warehouse.id} value={warehouse.id}>
                {warehouse.code} — {warehouse.name}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            select
            label={t("Product")}
            value={form.product}
            onChange={(event) => props.onChange({ ...form, product: event.target.value })}
          >
            {products.map((product) => (
              <MenuItem key={product.id} value={product.id}>
                {product.sku} — {product.name}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            label={t("Quantity")}
            type="number"
            value={form.quantity}
            inputProps={{ min: "0.0001", step: "0.0001" }}
            helperText={t("The quantity must not exceed currently available stock.")}
            onChange={(event) => props.onChange({ ...form, quantity: event.target.value })}
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={props.onClose}>{t("Cancel")}</Button>
        <Button variant="contained" disabled={!valid || pending} onClick={props.onSubmit}>{t("Reserve stock")}</Button>
      </DialogActions>
    </Dialog>
  );
}
