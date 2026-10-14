# Verification evidence

Checks performed on 11 October 2026 against this revision. Full command outputs
are in [review/](review/); machine-readable results are in
[results.json](review/results.json).

| Check | Result |
|---|---|
| Django functional suite | 164 passed, 7 skipped; 2 warnings |
| Seed compatibility regression | 1 passed separately after descriptive seed changes |
| Live Django → FastAPI integration | 1 passed separately; OCR approval, invoice/payment and forecast flow |
| React/Vitest | 8 passed across 4 files |
| Gateway HTTP/WebSocket tests | 9 passed |
| FastAPI service | 11 passed, 2 upstream deprecation warnings; real image/PDF OCR exercised |
| Identity Maven verification with Java 21 | Build successful; 3 unit tests passed |
| Spring → gateway → Django integration | Passed: discovery, CSRF, PKCE, code replay rejection, JWT validation, tenant denial, writes and notifications |
| Existing identity schema upgrade | Passed; existing ERP rows preserved |
| Django system check | No issues |
| Migration drift | No changes detected |
| OpenAPI generation | Passed with warnings treated as failure |
| Ruff, backend and AI | Passed |
| ESLint and TypeScript/Vite build | Passed |
| Source syntax/configuration/relative imports | Passed |
| SDK CLI | Init, validate, build and refusal to overwrite existing files passed |
| Strict mypy | 564 errors in 63 files; complete output in mypy.txt |

## Skipped and unavailable checks

Six Django tests require PostgreSQL row locks: purchasing, sales, finance and
three inventory retry concurrency scenarios. The default SQLite test run skips
them. The seventh skip is opt-in live AI, which passed in a separate real-service
run. SQLite regression results do not prove PostgreSQL concurrency behavior.

Docker is unavailable in the review environment, so images and the full Compose
stack have not been built or run. PostgreSQL backup/restore has not been exercised.
Chromium installation failed, so no real browser end-to-end run, new screenshots
or demo video is included. Frontend tests use jsdom and the build compiles TypeScript.

## Reproduction

Run the commands in README from the repository root. To exercise PostgreSQL
concurrency, point DATABASE_URL at a dedicated disposable PostgreSQL database,
then run the Django suite. Do not use a production database.

For live AI, start the FastAPI service with Tesseract and Poppler installed.
Set the same AI_SERVICE_TOKEN on both services, set AI_SERVICE_URL on Django,
and run AI_INTEGRATION=1 with tests/test_ai_live.py.

For OIDC protocol integration, first build services/identity with Java 21 and
Maven, install gateway dependencies, then run:

```bash
uv --project services/erp-core run python scripts/test_identity_integration.py
```

That script uses disposable databases and starts real local services. It tests
protocol behavior, not a visual browser session or PostgreSQL locking.

## Performance evidence

Frontend feature screens are split into independent chunks. This build reports
347.85 kB / 113.84 kB gzip for the main index, plus a 299.57 kB / 92.78 kB gzip UI
vendor chunk. These sizes are not a browser latency measurement.

Regression tests verify the finance summary's three queries, selected plugin
resolution, immutable cached manifests, shared notification authorization and
fresh request-specific margin evaluation after a cached anomaly result.
No production load benchmark or forecast accuracy study has been performed.
