// Product form: React Hook Form and Zod validate editing; Django validates the submitted values again.
// TanStack Query caches tenant-specific products; allPages loads complete category/unit/tax choices.
// Product records describe goods; inventory quantities are maintained by the stock ledger.
import { allPages } from "../../api/pagination";
import { useAuth } from "../../auth/AuthContext";
import { Pages } from "../../features/finance/shared";
import { t } from "../../i18n";
// Teaching edition: Manage product fields with schema-validated form input.
import AddIcon from "@mui/icons-material/Add";
import {
  Alert,
  Box,
  Button,
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
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Controller, useForm } from "react-hook-form";
import { useState } from "react";
import { z } from "zod";

import { api } from "../../api/client";
import { getApiErrorMessage } from "../../api/errors";
import type { Category, PaginatedResponse, Product, TaxRate, UnitOfMeasure } from "../../types";

// Zod improves form feedback; Django validates the same input again.
const productSchema = z.object({
  sku: z.string().min(1, "SKU is required."),
  name: z.string().min(1, "Name is required."),
  category: z.string().optional(),
  unit: z.string().min(1, "Unit is required."),
  tax_rate: z.string().optional(),
  purchase_price: z.number().min(0),
  selling_price: z.number().min(0),
  minimum_stock: z.number().min(0),
});

type ProductForm = z.infer<typeof productSchema>;

export function ProductsPage({ canCreate }: { canCreate: boolean }) {
  const queryClient = useQueryClient();
  const { selectedMembership } = useAuth();
  const organizationId = selectedMembership?.organization.id;
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);
  const products = useQuery({
    queryKey: ["products", organizationId, page],
    queryFn: async () => (await api.get<PaginatedResponse<Product>>("/catalog/products/", { params: { page } })).data,
  });
  const categories = useQuery({
    queryKey: ["categories", organizationId],
    queryFn: async () => allPages<Category>("/catalog/categories/"),
  });
  const units = useQuery({
    queryKey: ["units", organizationId],
    queryFn: async () => allPages<UnitOfMeasure>("/catalog/units/"),
  });
  const taxes = useQuery({
    queryKey: ["tax-rates", organizationId],
    queryFn: async () => allPages<TaxRate>("/catalog/tax-rates/"),
  });

  // Bind fields, validate submission and expose form errors.
  const { control, handleSubmit, reset, formState: { errors } } = useForm<ProductForm>({
    resolver: zodResolver(productSchema),
    defaultValues: {
      sku: "",
      name: "",
      category: "",
      unit: "",
      tax_rate: "",
      purchase_price: 0,
      selling_price: 0,
      minimum_stock: 0,
    },
  });

  // Perform a write and refresh the list after success.
  const createMutation = useMutation({
    mutationFn: async (data: ProductForm) =>
      api.post("/catalog/products/", {
        ...data,
        category: data.category || null,
        tax_rate: data.tax_rate || null,
        purchase_price: data.purchase_price.toFixed(4),
        selling_price: data.selling_price.toFixed(4),
        minimum_stock: data.minimum_stock.toFixed(4),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["products"] });
      reset();
      setOpen(false);
    },
  });

  return (
    <Stack spacing={3}>
      <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" gap={2}>
        <Box>
          <Typography variant="h5" fontWeight={700}>{t("Products")}</Typography>
          <Typography color="text.secondary">{t("Catalog prices and minimum-stock configuration.")}</Typography>
        </Box>
        {canCreate && (
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setOpen(true)}>{t("Add product")}</Button>
        )}
      </Stack>

      {products.isError && <Alert severity="error">{getApiErrorMessage(products.error)}</Alert>}
      <Pages page={page} setPage={setPage} data={products.data} />
      <Paper variant="outlined" sx={{ overflowX: "auto" }}>
        {products.isLoading ? (
          <Stack p={3}><Skeleton /><Skeleton /><Skeleton /></Stack>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t("SKU")}</TableCell><TableCell>{t("Name")}</TableCell><TableCell>{t("Category")}</TableCell>
                <TableCell>{t("Unit")}</TableCell><TableCell align="right">{t("Purchase")}</TableCell>
                <TableCell align="right">{t("Selling")}</TableCell><TableCell align="right">{t("Minimum")}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {products.data?.results.map((product) => (
                <TableRow key={product.id} hover>
                  <TableCell>{product.sku}</TableCell><TableCell>{product.name}</TableCell>
                  <TableCell>{product.category_name || "—"}</TableCell><TableCell>{product.unit_symbol}</TableCell>
                  <TableCell align="right">{product.purchase_price}</TableCell>
                  <TableCell align="right">{product.selling_price}</TableCell>
                  <TableCell align="right">{product.minimum_stock}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Paper>

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="md">
        <Box component="form" onSubmit={handleSubmit((data) => createMutation.mutate(data))}>
          <DialogTitle>{t("Add product")}</DialogTitle>
          <DialogContent>
            <Stack spacing={2} mt={1}>
              {createMutation.isError && <Alert severity="error">{getApiErrorMessage(createMutation.error)}</Alert>}
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                <Controller name="sku" control={control} render={({ field }) => (
                  <TextField {...field} label={t("SKU")} error={Boolean(errors.sku)} helperText={errors.sku?.message} fullWidth />
                )} />
                <Controller name="name" control={control} render={({ field }) => (
                  <TextField {...field} label={t("Name")} error={Boolean(errors.name)} helperText={errors.name?.message} fullWidth />
                )} />
              </Stack>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                <Controller name="category" control={control} render={({ field }) => (
                  <TextField {...field} label={t("Category")} select fullWidth>
                    <MenuItem value="">{t("No category")}</MenuItem>
                    {categories.data?.results.map((item) => <MenuItem key={item.id} value={item.id}>{item.name}</MenuItem>)}
                  </TextField>
                )} />
                <Controller name="unit" control={control} render={({ field }) => (
                  <TextField {...field} label={t("Unit")} select error={Boolean(errors.unit)} helperText={errors.unit?.message} fullWidth>
                    {units.data?.results.map((item) => <MenuItem key={item.id} value={item.id}>{item.name} ({item.symbol})</MenuItem>)}
                  </TextField>
                )} />
                <Controller name="tax_rate" control={control} render={({ field }) => (
                  <TextField {...field} label={t("Tax")} select fullWidth>
                    <MenuItem value="">{t("No tax")}</MenuItem>
                    {taxes.data?.results.map((item) => <MenuItem key={item.id} value={item.id}>{item.name}</MenuItem>)}
                  </TextField>
                )} />
              </Stack>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                {(["purchase_price", "selling_price", "minimum_stock"] as const).map((name) => (
                  <Controller key={name} name={name} control={control} render={({ field }) => (
                    <TextField
                      {...field}
                      onChange={(event) => field.onChange(Number(event.target.value))}
                      label={name.split("_").map((word) => word[0].toUpperCase() + word.slice(1)).join(" ")}
                      type="number"
                      inputProps={{ min: 0, step: "0.0001" }}
                      error={Boolean(errors[name])}
                      helperText={errors[name]?.message}
                      fullWidth
                    />
                  )} />
                ))}
              </Stack>
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setOpen(false)}>{t("Cancel")}</Button>
            <Button type="submit" variant="contained" disabled={createMutation.isPending}>{t("Create")}</Button>
          </DialogActions>
        </Box>
      </Dialog>
    </Stack>
  );
}
