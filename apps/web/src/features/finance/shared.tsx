// Shared finance/AI controls: paginated lists, complete selectors and editable decimal lines.
// Forms reuse these controls; tenant-aware query keys keep organization records separate.
// Displayed rows are API projections, not permission or accounting authorities.
import { t } from "../../i18n";
// Shared teaching helpers: React owns form state; Django owns business validation.
import { Alert, Button, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../api/client";
import { getApiErrorMessage as apiErrorMessage } from "../../api/errors";

export type Page<T> = { results: T[]; next: string | null; previous: string | null; count: number };
export type Choice = { id: string; name: string; reference?: string; partner_type?: string; is_active?: boolean };
export type Line = { description: string; quantity: string; unit_price: string; unit_cost: string; tax_rate: string; product_id?: string };
export const emptyLine = (): Line => ({ description: "", quantity: "1", unit_price: "0", unit_cost: "0", tax_rate: "0" });
export const today = () => {
  const date = new Date();
  return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,"0")}-${String(date.getDate()).padStart(2,"0")}`;
};
export const financeRoles = ["ADMINISTRATOR", "MANAGER", "ACCOUNTANT"];
export const aiRoles = [...financeRoles, "PURCHASING_AGENT"];

export function useChoices(organizationId: string, endpoint: string) {
  return useQuery({ queryKey: ["choices", organizationId, endpoint], queryFn: async () => {
    const rows: Choice[] = [];
    // Fetch every page so a supplier does not disappear merely because there are >25.
    for (let page = 1; ; page++) {
      const { data } = await api.get<Page<Choice>>(endpoint, { params: { page } });
      rows.push(...data.results);
      if (!data.next) return rows;
    }
  } });
}

export function usePage<T>(organizationId: string, endpoint: string) {
  const [page, setPage] = useState(1);
  const query = useQuery({ queryKey: ["week8", organizationId, endpoint, page], queryFn: async () =>
    (await api.get<Page<T>>(endpoint, { params: { page } })).data });
  return { ...query, page, setPage };
}

export function Pages({ page, setPage, data }: { page: number; setPage: (page: number) => void; data?: { next: string | null; previous: string | null } }) {
  return <Stack direction="row" gap={2}><Button disabled={!data?.previous} onClick={() => setPage(page-1)}>{t("Previous")}</Button>
    <Typography sx={{ py: 1 }}>{t("Page")}{" "}{page}</Typography><Button disabled={!data?.next} onClick={() => setPage(page+1)}>{t("Next")}</Button></Stack>;
}

export function QueryError({ error }: { error: unknown }) {
  return error ? <Alert severity="error">{apiErrorMessage(error)}</Alert> : null;
}

export function ChoiceField({ label, value, onChange, rows }: { label: string; value: string; onChange: (value: string) => void; rows?: Choice[] }) {
  return <TextField select label={label} value={value} onChange={e => onChange(e.target.value)} sx={{ minWidth: 220 }}>
    <MenuItem value="">{t("Select…")}</MenuItem>{rows?.map(row => <MenuItem key={row.id} value={row.id}>{row.reference || row.name}</MenuItem>)}
  </TextField>;
}

export function LinesEditor({ lines, setLines }: { lines: Line[]; setLines: (lines: Line[]) => void }) {
  // Decimal values remain strings during editing and transport, avoiding float rounding.
  const edit = (index: number, field: keyof Line, value: string) => setLines(lines.map((line, i) => i === index ? { ...line, [field]: value } : line));
  return <Stack gap={2}>{lines.map((line, index) => <Stack key={index} direction={{ xs: "column", md: "row" }} gap={1}>
    <TextField label={t("Description")} value={line.description} onChange={e => edit(index, "description", e.target.value)} />
    {(["quantity", "unit_price", "unit_cost", "tax_rate"] as const).map(field => <TextField key={field} label={t(field.replaceAll("_", " "))}
      value={line[field]} onChange={e => edit(index, field, e.target.value)} sx={{ width: 140 }} />)}
    <Button disabled={lines.length === 1} onClick={() => setLines(lines.filter((_, i) => i !== index))}>{t("Remove")}</Button>
  </Stack>)}<Button disabled={lines.length >= 100} onClick={() => setLines([...lines, emptyLine()])}>{t("Add line")}</Button></Stack>;
}
