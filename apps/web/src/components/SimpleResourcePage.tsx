import { useAuth } from "../auth/AuthContext";
import { Pages } from "../features/finance/shared";
import { t } from "../i18n";
// Teaching edition: Reuse one list/create screen for simple master data.
import AddIcon from "@mui/icons-material/Add";
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
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
import { useState, type FormEvent } from "react";

import { api } from "../api/client";
import { getApiErrorMessage } from "../api/errors";
import type { PaginatedResponse } from "../types";

type ResourceRecord = Record<string, unknown> & { id: string };

export interface ColumnDefinition {
  key: string;
  label: string;
  render?: (record: ResourceRecord) => string;
}

export interface FieldDefinition {
  name: string;
  label: string;
  type?: "text" | "email" | "number" | "multiline" | "select" | "checkbox";
  required?: boolean;
  defaultValue?: string | boolean;
  options?: Array<{ value: string; label: string }>;
}

interface SimpleResourcePageProps {
  title: string;
  description: string;
  endpoint: string;
  columns: ColumnDefinition[];
  fields: FieldDefinition[];
  canCreate: boolean;
}


export function SimpleResourcePage({
  title,
  description,
  endpoint,
  columns,
  fields,
  canCreate,
}: SimpleResourcePageProps) {
  const queryClient = useQueryClient();
  const { selectedMembership } = useAuth();
  const organizationId = selectedMembership?.organization.id;
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<Record<string, string | boolean>>(() =>
    Object.fromEntries(fields.map((field) => [field.name, field.defaultValue ?? ""])),
  );

  const query = useQuery({
    queryKey: [endpoint, organizationId, page],
    queryFn: async () => (await api.get<PaginatedResponse<ResourceRecord>>(endpoint, { params: { page } })).data,
  });

  // Perform a write and refresh the list after success.
  const createMutation = useMutation({
    mutationFn: async (payload: Record<string, string | boolean>) => api.post(endpoint, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: [endpoint] });
      setOpen(false);
      setForm(Object.fromEntries(fields.map((field) => [field.name, field.defaultValue ?? ""])));
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    createMutation.mutate(form);
  };

  return (
    <Stack spacing={3}>
      <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" gap={2}>
        <Box>
          <Typography variant="h5" fontWeight={700}>{title}</Typography>
          <Typography color="text.secondary">{description}</Typography>
        </Box>
        {canCreate && (
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setOpen(true)}>{t("Add")}{" "}{" "}{title}
          </Button>
        )}
      </Stack>

      {query.isError && <Alert severity="error">{getApiErrorMessage(query.error)}</Alert>}

      <Pages page={page} setPage={setPage} data={query.data} />
      <Paper variant="outlined" sx={{ overflowX: "auto" }}>
        {query.isLoading ? (
          <Stack spacing={1} p={3}><Skeleton /><Skeleton /><Skeleton /></Stack>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>{columns.map((column) => <TableCell key={column.key}>{column.label}</TableCell>)}</TableRow>
            </TableHead>
            <TableBody>
              {query.data?.results.map((record) => (
                <TableRow key={record.id} hover>
                  {columns.map((column) => (
                    <TableCell key={column.key}>
                      {column.render ? column.render(record) : String(record[column.key] ?? "—")}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
              {query.data?.results.length === 0 && (
                <TableRow><TableCell colSpan={columns.length}>{t("No records yet.")}</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        )}
      </Paper>

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <Box component="form" onSubmit={submit}>
          <DialogTitle>{t("Add")}{" "}{" "}{title}</DialogTitle>
          <DialogContent>
            <Stack spacing={2} mt={1}>
              {createMutation.isError && <Alert severity="error">{getApiErrorMessage(createMutation.error)}</Alert>}
              {fields.map((field) => {
                if (field.type === "checkbox") {
                  return (
                    <FormControlLabel
                      key={field.name}
                      control={
                        <Checkbox
                          checked={Boolean(form[field.name])}
                          onChange={(event) => setForm({ ...form, [field.name]: event.target.checked })}
                        />
                      }
                      label={field.label}
                    />
                  );
                }
                return (
                  <TextField
                    key={field.name}
                    label={field.label}
                    value={String(form[field.name] ?? "")}
                    onChange={(event) => setForm({ ...form, [field.name]: event.target.value })}
                    slotProps={{ htmlInput: { step: "any" } }}
                    required={field.required}
                    type={field.type === "number" ? "number" : field.type === "email" ? "email" : "text"}
                    multiline={field.type === "multiline"}
                    minRows={field.type === "multiline" ? 3 : undefined}
                    select={field.type === "select"}
                    fullWidth
                  >
                    {field.options?.map((option) => (
                      <MenuItem key={option.value} value={option.value}>{option.label}</MenuItem>
                    ))}
                  </TextField>
                );
              })}
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
