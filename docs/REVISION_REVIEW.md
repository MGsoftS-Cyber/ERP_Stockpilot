# StockPilot revision review · 24 September 2026

## Scope and delivery

The full Weeks 1–14 codebase is retained. This revision adds languages, optional design
editing, a reviewed declarative plugin marketplace and a developer SDK. It does not
replace the application with a new prototype. No production data was accessed or migrated.

## Defects corrected

| Area | Problem | Correction |
|---|---|---|
| Tenant UI | Early module query keys omitted the organization | Add organization IDs to keys; clear caches and remount forms when switching organizations |
| Authentication | A retried request could acquire a newly selected organization header | Preserve the original request's organization header during token refresh |
| Login failure | Bad login credentials could enter the refresh path | Exclude token endpoints; notify the UI when a session expires |
| Lists | Early tables only exposed page one | Add table pagination for master data, products and inventory |
| Selectors | Products/units/warehouses beyond page one were missing | Load all pages for selection lists, using the original endpoint |
| Plugin validation | A list/dict hook could raise TypeError; boolean API version was accepted | Validate types before membership checks; require an integer API version |
| Master-data writes | Uniqueness constraints could become HTTP 500 errors | Return a consistent HTTP 409 envelope inside a transaction |
| Deletion | Removing referenced records could raise an unhandled protected-delete error | Return HTTP 409 while retaining the referenced record |
| Error display | Nested serializer errors could show `[object Object]` | Flatten field paths and nested line errors into readable messages |
| Decimal input | HTML number fields could reject fractional tax rates | Permit decimal input steps; server validation remains authoritative |
| Package installation | pnpm required an explicit esbuild build-script decision | Record `allowBuilds.esbuild: true` in the workspace configuration |
| Static verification | New JSON imports were not recognized by the checker | Check explicit file imports as well as TypeScript modules |

## Added behavior

Languages: a persistent browser choice, translated static screen text, translated normalized
status labels, MUI locales, Arabic RTL and `Accept-Language` propagation. Data and API contracts
remain stable. See the language guide for untranslated legacy/dynamic diagnostics and the
separate Spring sign-in page limitation.

Design: validated tokens and saved revisions per organization. Opening the editor does not
write anything. Preview is local; only an administrator's explicit Save persists changes.
Concurrent stale saves return HTTP 409 and successful saves are audited.

Marketplace: publisher-owned submissions, platform review, search/category filtering,
install/update actions and reuse of existing configuration/rollback history. Supported
extensions are JSON settings for two reviewed read-only hooks, not arbitrary executable code.

SDK: a local Python package with `init`, `validate`, `build`, `submit` and a small API client.
The CLI was exercised with a generated manifest and package. Its validation/checksum contract
is compared with the server in the backend suite.

## Verification and limits

Actual command outputs are in [review/](review/). The verification summary is generated in
`review/results.json`; consult it for the final test counts. Tests use synthetic data.

- Django functional tests cover stock transactions, purchasing, sales, finance, tenancy,
  OIDC validation, plugins and the new APIs. New checks exercise 22 dashboard GET routes
  and verify that their responses serialize as JSON.
- Django system checks, migration-drift detection, OpenAPI generation and Ruff pass.
- React TypeScript production build and ESLint pass. Vitest covers translations,
  Arabic direction, design preview/save, pagination and nested API error rendering.
- Express tests use real local HTTP/WebSocket sockets. AI service tests exercise its
  Python application independently.
- The SDK CLI init/validate/build commands and archive integrity are checked.

Open items are explicit:

1. **Strict mypy is not clean.** This run reports 561 errors, including missing annotations,
   Django/DRF generic and model typing issues. `review/mypy.txt` preserves the full output.
   These are not dismissed as proof of runtime failure or hidden with relaxed configuration.
   A dedicated typing pass is still needed.
2. **Four backend tests are skipped:** PostgreSQL-only concurrency tests and the opt-in live
   AI integration test. SQLite passes do not establish PostgreSQL lock behavior.
3. **Spring/complete Docker runtime is not verified here.** This environment has Java 17,
   while the identity project requires Java 21; Maven and Docker are unavailable.
4. **No full browser end-to-end run or new screenshots were produced.** UI behavior was
   tested with jsdom and the production bundle was built. Chromium is not available here.
5. Vite reports an approximately 829 kB main bundle (259 kB gzip). Route-level code splitting
   is a remaining performance improvement. AI tests report upstream deprecation warnings.

This is a source review with automated regression coverage, not a guarantee that every
possible defect or deployment-specific issue has been eliminated.

## Upgrade and test in a browser

Keep your database backup, environment configuration, uploaded documents, Compose project name
and persistent volumes. Extract this ZIP into a separate source directory first and compare
any local customizations. Do not overwrite your database or run `docker compose down -v`.

From the extracted `stockpilot` directory, using Docker Desktop/WSL2:

```bash
# Existing installation: preserve data; do not enable demo seeding.
SEED_DEMO=false docker compose up --build
```

The identity-bootstrap service applies migrations, including
`extensions/0002_appearance_marketplacerelease.py`, before starting the application.
For a disposable fresh demonstration only:

```bash
SEED_DEMO=true docker compose up --build
```

Open `http://localhost:5173`. Sign in through the identity page with the demo account
`admin@stockpilot.local` / `Admin123!` only when you deliberately created demo data.
API requests go through `http://localhost:3000`; identity is at `http://localhost:9000`.

Manual acceptance checks:

1. Switch English → French → Arabic. Check toolbar, tables, forms and RTL; reload to verify persistence.
2. Switch organizations with an unfinished form and verify that old tenant data/form state disappears.
3. Open Design. Confirm that the existing look is unchanged. Preview a color, cancel, then explicitly save.
4. Sign in as a viewer. Saving design and installing plugins must be denied by the API.
5. In Marketplace install StockPilot stock-alerts, configure it in Plugins, update and roll back.
6. Submit `sdk/example-plugin.json`. It must remain unpublished until a platform reviewer approves it.
7. Run the original purchase → receipt → sale → shipment → invoice → payment demo and inspect balances.

For local development and verification:

```bash
uv --project services/erp-core sync
uv --project services/ai-service sync
pnpm install --frozen-lockfile
cd services/api-gateway
npm ci --ignore-scripts
cd ../..
uv --project services/erp-core run pytest services/erp-core
pnpm --filter @stockpilot/web test
pnpm --filter @stockpilot/web lint
pnpm --filter @stockpilot/web build
```

Use `make check` after installing Java 21 and Maven as well. That command includes the
identity build and AI tests. It does not run mypy; use the project's existing strict
configuration separately to work through the included typing report.
