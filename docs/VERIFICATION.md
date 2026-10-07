# Weeks 12-14 verification

Verified in the build environment:

* Django suite before the final API contract addition: 109 passing tests; four skips.
* Final plugin suite: 16 passing tests, including API install/update/rollback.
* Plugin install/configure/update/rollback history and idempotency.
* Stale revision rejection, dependency requirements, administrator-only writes.
* Failed health check preserves previous installation/history state.
* Invalid configuration, unsupported hooks and unknown release rejection.
* Organization-scoped history, disabled output and append-only history.
* Frontend TypeScript/Vite build and ESLint passed.
* Django system check, migration consistency and OpenAPI warnings-as-errors passed.

Not verified here:

* Docker image build/run and Java 21; inherited identity/gateway sources are unchanged.
* PostgreSQL-only concurrency tests (three skips); live AI integration (one skip).
* Backup/restore execution on PostgreSQL.
* Browser install/update/rollback automation: Chromium launch was denied a required
  socket by the environment. Screenshots/video remain pending local capture.

The demo recorder reached database migration and Week 8 seeding successfully,
then stopped at the browser launch. It uses a disposable SQLite database.
No downloaded credentials, demo database or signing keys are packaged.

Limits: curated declarative releases only; no executable package upload,
marketplace, destructive uninstall, schema rollback or remote package signing.
Rollback restores plugin state and adds history; it never undoes ERP transactions.
