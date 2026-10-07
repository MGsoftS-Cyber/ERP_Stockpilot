// Marketplace screen: browses reviewed releases and submits declarative JSON packages.
// The Django marketplace API checks publisher ownership and platform-review permissions.
// Install/update reuse plugin commands; configuration and rollback stay on the Plugins page.
import { Alert, Button, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../api/client";
import { getApiErrorMessage } from "../../api/errors";
import { t } from "../../i18n";
type Release = {
  manifest: { id: string; name: string; version: string; hook: string; requires: Record<string, string> };
  checksum: string;
  summary: string;
  publisher: string;
  category: string;
  installed_version: string | null;
  revision: number;
  update_available: boolean;
};
type Submission = {
  id: string;
  slug: string;
  version: string;
  status: string;
  manifest: unknown;
  review_note: string;
};
export function MarketplacePage({ organizationId, role }: { organizationId: string; role: string }) {
  const admin = role === "ADMINISTRATOR";
  const client = useQueryClient();
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("All");
  const [source, setSource] = useState("");
  const [note, setNote] = useState("");
  const catalog = useQuery({
    queryKey: ["marketplace", organizationId],
    queryFn: async () =>
      (await api.get<{ results: Release[]; can_review: boolean }>("/plugins/marketplace/")).data,
  });
  const submissions = useQuery({
    queryKey: ["submissions", organizationId],
    enabled: admin,
    queryFn: async () => (await api.get<Submission[]>("/plugins/submissions/")).data,
  });
  const mutation = useMutation({
    mutationFn: async ({ path, data }: { path: string; data: unknown }) => api.post(path, data),
    onSuccess: () => client.invalidateQueries(),
  });
  const submit = useMutation({
    mutationFn: async () => api.post("/plugins/submissions/", JSON.parse(source)),
    onSuccess: () => {
      setSource("");
      return client.invalidateQueries({ queryKey: ["submissions"] });
    },
  });
  return (
    <Stack gap={2}>
      <Typography variant="h4">{t("Plugin marketplace")}</Typography>
      <Alert severity="info">
        {t("Reviewed add-ons use approved read-only hooks. Manage configuration and rollback in Plugins.")}
      </Alert>
      {[catalog.error, submissions.error, mutation.error, submit.error]
        .filter(Boolean)
        .map((error, index) => (
          <Alert key={index} severity="error">
            {getApiErrorMessage(error)}
          </Alert>
        ))}
      {mutation.isSuccess && <Alert severity="success">{t("Saved")}</Alert>}
      <Stack direction="row" gap={2}>
        <TextField label={t("Search")} value={search} onChange={(event) => setSearch(event.target.value)} />
        <TextField
          select
          label={t("Category")}
          value={category}
          onChange={(event) => setCategory(event.target.value)}
        >
          {["All", "Inventory", "Workspace"].map((value) => (
            <MenuItem key={value} value={value}>
              {t(value)}
            </MenuItem>
          ))}
        </TextField>
      </Stack>
      {catalog.data?.results
        .filter(
          (row) =>
            (category === "All" || row.category === category) &&
            `${row.manifest.name} ${row.summary}`.toLowerCase().includes(search.toLowerCase()),
        )
        .map((row) => (
          <Paper key={`${row.manifest.id}-${row.manifest.version}`} variant="outlined" sx={{ p: 2 }}>
            <Typography variant="h6">
              {row.manifest.name} · {row.manifest.version}
            </Typography>
            <Typography>{row.summary}</Typography>
            <Typography>
              {t(row.publisher)} · {t(row.category)} · {row.manifest.hook}
            </Typography>
            <Typography variant="caption" component="div" sx={{ overflowWrap: "anywhere" }}>
              SHA-256: {row.checksum}
            </Typography>
            <Typography>
              {t("Dependencies")}: {JSON.stringify(row.manifest.requires)}
            </Typography>
            <Typography>
              {t("Installed version")}: {row.installed_version ?? "—"}
            </Typography>
            <Button
              disabled={!admin || mutation.isPending || (!!row.installed_version && !row.update_available)}
              onClick={() =>
                mutation.mutate({
                  path: "/plugins/commands/",
                  data: {
                    slug: row.manifest.id,
                    version: row.manifest.version,
                    operation: row.installed_version ? "update" : "install",
                    expected_revision: row.revision,
                    idempotency_key: crypto.randomUUID(),
                  },
                })
              }
            >
              {t(row.installed_version ? "Update" : "Install")}
            </Button>
          </Paper>
        ))}
      {admin && (
        <>
          <Typography variant="h5">{t("Developer submissions")}</Typography>
          <Typography>{t("Paste the JSON package produced by the SDK build command.")}</Typography>
          <TextField
            multiline
            minRows={5}
            label={t("Package JSON")}
            value={source}
            onChange={(event) => setSource(event.target.value)}
          />
          <Button disabled={!source || submit.isPending} onClick={() => submit.mutate()}>
            {t("Submit for review")}
          </Button>
          {submit.isSuccess && <Alert severity="success">{t("Submitted for review")}</Alert>}
          {catalog.data?.can_review && (
            <TextField
              label={t("Review note")}
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          )}
          {submissions.data?.map((row) => (
            <Paper key={row.id} variant="outlined" sx={{ p: 2 }}>
              <Typography>
                {row.slug} · {row.version} · {t(row.status)}
              </Typography>
              <Typography>{row.review_note}</Typography>
              {catalog.data?.can_review && row.status === "pending" && (
                <>
                  <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
                    {JSON.stringify(row.manifest, null, 2)}
                  </pre>
                  {["approved", "rejected"].map((decision) => (
                    <Button
                      key={decision}
                      disabled={mutation.isPending}
                      onClick={() =>
                        mutation.mutate({
                          path: `/plugins/submissions/${row.id}/review/`,
                          data: { decision, note },
                        })
                      }
                    >
                      {t(decision === "approved" ? "Approve" : "Reject")}
                    </Button>
                  ))}
                </>
              )}
            </Paper>
          ))}
        </>
      )}
    </Stack>
  );
}
