# Understanding the code and feature messages

The application now names features by their business purpose. For example, the
purchasing screen describes drafting, approval, receipts and supplier invoices instead
of displaying a sprint number. Success messages describe the recorded operation and
the next check. New UI messages have French and Arabic translations.

## Follow a request through the application

1. **React feature screen** collects input and displays the result. Read its introductory
   comments for the feature's responsibility and related backend module.
2. **`apps/web/src/api/client.ts`** adds identity, company selection and language headers.
3. **Express `src/app.js`** checks transport access and forwards the permitted request.
4. **Django URLs/views** choose the endpoint and resolve organization membership.
5. **DRF serializer** converts the REST contract into validated Python values.
6. **Domain service** authorizes the business operation and validates its state/quantities.
7. **Django models/PostgreSQL** persist data and enforce constraints inside a transaction.
8. **Audit and query refresh** record the action and show fresh authorized results in React.

Authentication is a separate connection: React OIDC -> Spring Identity -> signed access
token -> verification by Express and Django. A valid token alone does not grant access
to another organization; active membership and operation roles still apply.

## Main connections

| Feature | React screen | Django responsibility | Related part |
|---|---|---|---|
| Catalog | ProductsPage | Products, units, categories, prices | Inventory refers to products |
| Stock | InventoryPage | Ledger, balances, transfers, reservations | Purchasing/sales reuse posting services |
| Purchasing | PurchasingPage | Draft, approval, receipt | Receipt increases stock; billing manages invoice |
| Sales | SalesPage | Reserve, ship, cancel, return | Inventory fulfilment protects quantities |
| Finance | FinancePage | Invoices, payments, expenses | Source orders and audit events |
| AI review | IntelligencePage | Private upload, call AI, store review | FastAPI extracts/predicts; billing receives reviewed draft |
| Plugins | PluginsPage | Validated lifecycle and history | Registry chooses reviewed hooks |
| Marketplace | MarketplacePage | Publisher ownership and review | Approved releases enter registry |
| Appearance | DesignEditor | Validated per-company settings | DesignProvider maps tokens to MUI theme |

## Why these libraries/patterns appear

- **React `useState`** keeps editable local form values. It does not save the database.
- **TanStack Query `useQuery`** fetches/caches server results. Tenant keys prevent mixing
  companies; `invalidateQueries` asks for refreshed records after a command.
- **Axios** centralizes HTTP headers and error handling across feature screens.
- **React Hook Form/Zod** improve product-form feedback; Django repeats validation.
- **MUI/Emotion** render shared components and the configurable theme, including RTL.
- **Django ORM** maps domain models to database tables and relationships.
- **DRF serializers** define and validate the JSON contract consumed by React.
- **`transaction.atomic`** commits related records together or rolls them back together.
- **`Decimal`** handles exact quantities and money without binary float rounding.
- **Idempotency UUID** identifies an unchanged write so retries do not duplicate it.
- **Spring Security/OIDC** authenticate accounts and issue access tokens; Django memberships
  determine which organization's operations those accounts may perform.
- **FastAPI/Tesseract/forecasting code** produce suggestions. A human must review business
  decisions; AI has no direct stock-write permission.

Developer explanations are comments in the source files. Customer-facing messages explain
operations and next actions without displaying implementation details. Historical migration
names, seed command names, idempotency identifiers and stored demo markers remain stable.

This edit changes explanatory text and comments. It introduces no database migration or
new external API. Historical test outputs in `docs/review/` belong to the preceding revision;
see `MESSAGE_UPDATE_VERIFICATION.md` for the checks run for this text update.
