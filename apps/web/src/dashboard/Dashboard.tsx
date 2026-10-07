// Workspace navigation: chooses feature screens for the authenticated organization.
// UI role checks hide unavailable actions; Django independently enforces all write permissions.
// The organization/tab key discards unfinished forms when their workspace changes.
// Teaching edition: Connect navigation to the company-specific feature screens.
import Inventory2OutlinedIcon from "@mui/icons-material/Inventory2Outlined";
import LogoutIcon from "@mui/icons-material/Logout";
import {
  AppBar,
  Box,
  Button,
  Chip,
  Container,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Tab,
  Tabs,
  Toolbar,
  Typography,
} from "@mui/material";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { useAuth } from "../auth/AuthContext";
import { SimpleResourcePage } from "../components/SimpleResourcePage";
import { ProductsPage } from "../features/catalog/ProductsPage";
import { InventoryPage } from "../features/inventory/InventoryPage";
import { PurchasingPage } from "../features/purchasing/PurchasingPage";
import { SalesPage } from "../features/sales/SalesPage";
import { FinancePage } from "../features/finance/FinancePage";
import { IntelligencePage } from "../features/intelligence/IntelligencePage";
import { PluginsPage } from "../features/plugins/PluginsPage";
import { MarketplacePage } from "../features/plugins/MarketplacePage";
import { DesignEditor } from "../design/DesignEditor";
import { LanguageSelect } from "../i18n/LanguageSelect";
import { t } from "../i18n";

const tabs = [
  "Overview",
  "Products",
  "Categories",
  "Units",
  "Taxes",
  "Partners",
  "Warehouses",
  "Inventory",
  "Purchasing",
  "Sales",
  "Finance & audit",
  "OCR & forecasts",
  "Plugins",
  "Marketplace",
  "Design",
];

export function Dashboard() {
  const { user, selectedMembership, selectOrganization, logout } = useAuth();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState(0);

  if (!user || !selectedMembership) {
    return <Container sx={{ py: 8 }}><Typography>{t("No active organization membership is available.")}</Typography></Container>;
  }

  const canManageMasterData = ["ADMINISTRATOR", "MANAGER"].includes(selectedMembership.role);
  const canManageWarehouses = ["ADMINISTRATOR", "MANAGER", "STOCK_OPERATOR"].includes(
    selectedMembership.role,
  );
  const canReserveStock = [
    "ADMINISTRATOR",
    "MANAGER",
    "STOCK_OPERATOR",
    "SALES_AGENT",
  ].includes(selectedMembership.role);

  // Invalidate cached reads when changing the tenant header.
  const changeOrganization = async (organizationId: string) => {
    selectOrganization(organizationId);
    await queryClient.invalidateQueries();
  };

  return (
    <Box data-workspace sx={{ minHeight: "100vh", bgcolor: "grey.50" }}>
      <AppBar position="static" elevation={0}>
        <Toolbar sx={{ gap: 2 }}>
          <Inventory2OutlinedIcon />
          <Typography variant="h6" fontWeight={700} sx={{ flexGrow: 1 }}>StockPilot AI</Typography>
          <LanguageSelect />
          <Chip label={t(selectedMembership.role_label)} color="default" size="small" />
          <Button color="inherit" startIcon={<LogoutIcon />} onClick={logout}>{t("Logout")}</Button>
        </Toolbar>
      </AppBar>

      <Paper square elevation={0} sx={{ borderBottom: 1, borderColor: "divider" }}>
        <Container maxWidth="xl">
          <Stack direction={{ xs: "column", md: "row" }} alignItems={{ md: "center" }} gap={2} py={1}>
            <FormControl size="small" sx={{ minWidth: 240 }}>
              <InputLabel>{t("Organization")}</InputLabel>
              <Select
                label={t("Organization")}
                value={selectedMembership.organization.id}
                onChange={(event) => void changeOrganization(event.target.value)}
              >
                {user.memberships.map((membership) => (
                  <MenuItem key={membership.id} value={membership.organization.id}>
                    {membership.organization.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <Tabs value={tab} onChange={(_, value) => setTab(value)} variant="scrollable" scrollButtons="auto">
              {tabs.map((label) => <Tab key={label} label={t(label)} />)}
            </Tabs>
          </Stack>
        </Container>
      </Paper>

      <Container key={`${selectedMembership.organization.id}-${tab}`} component="main" maxWidth="xl" sx={{ py: 4 }}>
        {tab === 13 && <MarketplacePage organizationId={selectedMembership.organization.id} role={selectedMembership.role} />}
        {tab === 14 && <DesignEditor canEdit={selectedMembership.role === "ADMINISTRATOR"} />}
        {tab === 12 && <PluginsPage key={selectedMembership.organization.id}
          organizationId={selectedMembership.organization.id} role={selectedMembership.role} />}
        {tab === 10 && <FinancePage key={selectedMembership.organization.id}
          organizationId={selectedMembership.organization.id} role={selectedMembership.role} />}
        {tab === 11 && <IntelligencePage key={selectedMembership.organization.id}
          organizationId={selectedMembership.organization.id} role={selectedMembership.role} />}
        {tab === 9 && <SalesPage key={selectedMembership.organization.id}
          organizationId={selectedMembership.organization.id} role={selectedMembership.role} />}
        {tab === 8 && <PurchasingPage key={selectedMembership.organization.id}
          organizationId={selectedMembership.organization.id} role={selectedMembership.role} />}
        {tab === 0 && <Overview />}
        {tab === 1 && <ProductsPage canCreate={canManageMasterData} />}
        {tab === 2 && (
          <SimpleResourcePage
            title={t("Categories")}
            description={t("Product classification owned by the selected organization.")}
            endpoint="/catalog/categories/"
            canCreate={canManageMasterData}
            columns={[{ key: "code", label: t("Code") }, { key: "name", label: t("Name") }, { key: "description", label: t("Description") }]}
            fields={[{ name: "code", label: t("Code"), required: true }, { name: "name", label: t("Name"), required: true }, { name: "description", label: t("Description"), type: "multiline" }]}
          />
        )}
        {tab === 3 && (
          <SimpleResourcePage
            title={t("Units")}
            description={t("Units of measure used by product quantities.")}
            endpoint="/catalog/units/"
            canCreate={canManageMasterData}
            columns={[{ key: "name", label: t("Name") }, { key: "symbol", label: t("Symbol") }, { key: "allows_decimals", label: t("Decimals"), render: (record) => record.allows_decimals ? t("Yes") : t("No") }]}
            fields={[{ name: "name", label: t("Name"), required: true }, { name: "symbol", label: t("Symbol"), required: true }, { name: "allows_decimals", label: t("Allow decimal quantities"), type: "checkbox", defaultValue: true }]}
          />
        )}
        {tab === 4 && (
          <SimpleResourcePage
            title={t("Taxes")}
            description={t("Tax rates expressed as percentages.")}
            endpoint="/catalog/tax-rates/"
            canCreate={canManageMasterData}
            columns={[{ key: "name", label: t("Name") }, { key: "rate", label: t("Rate"), render: (record) => `${record.rate}%` }]}
            fields={[{ name: "name", label: t("Name"), required: true }, { name: "rate", label: t("Rate (%)"), type: "number", required: true }]}
          />
        )}
        {tab === 5 && (
          <SimpleResourcePage
            title={t("Partners")}
            description={t("Customers, suppliers, or organizations that are both.")}
            endpoint="/partners/business-partners/"
            canCreate={canManageMasterData}
            columns={[{ key: "code", label: t("Code") }, { key: "name", label: t("Name") }, { key: "partner_type_label", label: t("Type") }, { key: "email", label: t("Email") }, { key: "phone", label: t("Phone") }]}
            fields={[{ name: "code", label: t("Code"), required: true }, { name: "name", label: t("Name"), required: true }, { name: "partner_type", label: t("Type"), type: "select", required: true, defaultValue: "CUSTOMER", options: [{ value: "CUSTOMER", label: t("Customer") }, { value: "SUPPLIER", label: t("Supplier") }, { value: "BOTH", label: t("Customer and supplier") }] }, { name: "email", label: t("Email"), type: "email" }, { name: "phone", label: t("Phone") }, { name: "address", label: t("Address"), type: "multiline" }]}
          />
        )}
        {tab === 6 && (
          <SimpleResourcePage
            title={t("Warehouses")}
            description={t("Physical locations used by inventory balances and transfers.")}
            endpoint="/inventory/warehouses/"
            canCreate={canManageWarehouses}
            columns={[{ key: "code", label: t("Code") }, { key: "name", label: t("Name") }, { key: "address", label: t("Address") }]}
            fields={[{ name: "code", label: t("Code"), required: true }, { name: "name", label: t("Name"), required: true }, { name: "address", label: t("Address"), type: "multiline" }]}
          />
        )}
        {tab === 7 && (
          <InventoryPage
            canOperate={canManageWarehouses}
            canReserve={canReserveStock}
          />
        )}
      </Container>
    </Box>
  );
}

function Overview() {
  const modules = [
    ["Tenancy", "Organizations, memberships, roles and tenant-isolated requests."],
    ["Catalog", "Products, categories, units and tax rates."],
    ["Partners", "Customers, suppliers and dual-purpose business partners."],
    ["Inventory", "Immutable ledger, balances, adjustments, transfers and reservations."],
    ["Purchasing", "Draft orders, approval, partial receipts and purchasing history."],
    ["Sales", "Reservations, partial shipments, cancellation and customer returns."],
    ["Finance", "Invoices, payments, expenses, currency-separated summaries and audit history."],
    ["Invoice OCR", "Private uploads, field confidence and human-corrected supplier drafts."],
    ["Recommendations", "Moving-average forecasts, reorder suggestions and recorded human decisions."],
  ];

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h4" fontWeight={700}>{t("StockPilot - business management")}</Typography>
        <Typography color="text.secondary">{t("A secure, transactional base for the complete StockPilot ERP.")}</Typography>
      </Box>
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(2, 1fr)" }, gap: 2 }}>
        {modules.map(([title, description]) => (
          <Paper key={title} variant="outlined" sx={{ p: 3 }}>
            <Typography variant="h6" fontWeight={700}>{t(title)}</Typography>
            <Typography color="text.secondary">{t(description)}</Typography>
          </Paper>
        ))}
      </Box>
    </Stack>
  );
}
