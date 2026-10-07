# StockPilot ERP - Weeks 1-14

The latest message update replaces development-week headings with feature descriptions
and adds source comments explaining responsibilities and connected modules. Read
[Code responsibilities](docs/CODE_RESPONSIBILITIES.md) and
[Message update verification](docs/MESSAGE_UPDATE_VERIFICATION.md) for this revision.

A commented Django / React ERP with PostgreSQL, internal FastAPI AI, an Express
gateway, Spring OIDC identity, and organization-scoped plugins.

## Current revision: languages, design settings, marketplace and SDK

This ZIP contains the complete Weeks 1–14 application, plus:

- English/French/Arabic UI selection and Arabic RTL layout.
- Optional, organization-specific design editing with preview, cancel and explicit save.
- Searchable plugin marketplace, developer submissions and platform review.
- A local Python SDK for creating, validating, packaging and submitting add-ons.
- Fixes for tenant cache isolation, pagination, malformed plugin input, protected deletion,
  duplicate master data, token retry headers and nested serializer error messages.

Start with [Revision review and verification](docs/REVISION_REVIEW.md),
[Languages and design](docs/LANGUAGE_AND_DESIGN.md) and
[Marketplace and SDK](docs/MARKETPLACE_AND_SDK.md).
The latest review report supersedes test counts and limitations in earlier weekly reports.
The existing default visual design is retained until you preview or save new settings.

## Start a fresh demonstration (Docker Desktop + WSL2)

Open a WSL terminal in the extracted `stockpilot` directory:

```bash
SEED_DEMO=true docker compose up --build
```

Open http://localhost:5173 and choose secure sign-in.
Demo account: `admin@stockpilot.local`, password `Admin123!`.
Identity opens at http://localhost:9000; ERP API requests use http://localhost:3000.
The demo flag creates sample data and may reset demo-account passwords. Leave it
false when continuing an existing database. Keep the same Compose project name
and existing volumes to retain your data; do not run `docker compose down -v`.

On an existing Weeks 1-11 installation, rebuild the application with the new source:
`docker compose up --build`. The bootstrap service runs migrations and refreshes
the private identity snapshot. If identities change later, run
`docker compose run --rm identity-bootstrap` and `docker compose restart identity`.

## What changed

| Week | Deliverable |
|---|---|
| 12 | Compose package, this guide, demo checklist and capture script; screenshots/video pending local capture |
| 13 | Versioned manifests, explicit hook registry, tenant-owned installations, permissions and plugin output |
| 14 | Install, configure, enable/disable, update, rollback, dependency checks, history and audit |

## Try the plugin lifecycle

1. Open **Plugins** as an organization administrator.
2. Select `stock-alerts`, version `1.0.0`, and **Install**.
3. Set a threshold, then **Save configuration**; inspect the stock-alert output.
4. Select `1.1.0`, then **Update**. Existing configuration is preserved.
5. Select an earlier revision, then **Restore selected revision**.
6. Install `warehouse-notice`; it requires enabled `stock-alerts`.
7. Disabling `stock-alerts` now fails until its dependent plugin is disabled.

This is a curated, declarative plugin foundation. Release manifests ship with the
application; administrators install them per organization without restarting.
It is not a WordPress-compatible marketplace or an arbitrary Python/JavaScript
uploader. Custom executable hooks require a reviewed application deployment.

## Checks

```bash
uv --project services/erp-core sync --frozen
uv --project services/erp-core run pytest services/erp-core
pnpm install --frozen-lockfile --ignore-scripts
pnpm lint:web
pnpm test:web
pnpm build:web
cd services/api-gateway && npm ci --ignore-scripts && npm test
```

Java 21: run `mvn verify` inside `services/identity`.
The independent real OIDC test is `scripts/test_identity_integration.py`.
PostgreSQL runs the row-lock tests in CI; SQLite cannot prove concurrent locking.

See `docs/PLUGIN_DEVELOPMENT.md`, `docs/DEMO.md`, and `docs/VERIFICATION.md`.
