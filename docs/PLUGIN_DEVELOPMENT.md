# Plugin conception and extension contract

React Plugins screen -> tenant-scoped Django API -> lifecycle service -> validated
registry -> explicit read-only hook -> organization-scoped ERP query.

Express and Spring retain their existing responsibilities. All plugin routes are
under `/api/v1/plugins/`, so requests receive the existing token and tenant checks.

## Week 13 foundation

`apps/extensions/registry.py` defines plugin API 1. A release is a JSON manifest
with `id`, `name`, stable `version`, API version, inclusive `core_min`, exclusive
`core_max`, an allowed `hook`, dependency minimum versions and default `settings`.

Supported hooks:

* `inventory.low_stock`: integer `threshold` from 0 to 100000. Queries balances
  for the active organization; available = on_hand - reserved. Returns at most
  100 rows. Products without a balance record are not included.
* `dashboard.notice`: plain `message`, 1-200 characters. React renders it as text.
  Output appears in the Plugins screen; it does not inject navigation or HTML.

Add a uniquely named JSON file in `apps/extensions/releases/`, then rebuild the
backend image. No user-provided import paths, SQL, scripts or code are executed.
The included 1.1.0 stock-alert release changes the default threshold for NEW
installs. Updates preserve an existing organization's customized threshold.

SHA-256 detects changed manifest content in stored snapshots. It is NOT a digital
signature or proof of publisher trust. Trust comes from the reviewed deployment.
Do not edit an already published manifest in place: publish a new version.

## Week 14 lifecycle

Installation has one row per organization and plugin ID. History holds immutable
snapshots of version, configuration, checksum and enabled state. Only active
organization ADMINISTRATOR memberships can change lifecycle state. OIDC grants
must also match. Other tenant members can read catalog, history and hook output.

Every POST `/plugins/commands/` includes:

```json
{
  "slug": "stock-alerts",
  "operation": "install",
  "version": "1.0.0",
  "expected_revision": 0,
  "idempotency_key": "11111111-1111-4111-8111-111111111111"
}
```

Use a fresh UUID for each intended change; reuse the SAME command and UUID to
recover after a network failure. Replaying returns the original revision.
Stale expected_revision returns 409. The UI refreshes state after every attempt.

Allowed operations: install, update, configure, enable, disable, rollback.
Update requires a greater version and compatible settings. Rollback requires
`target_revision`, restores its snapshot and appends a NEW history entry. It never
deletes orders, reverses finance/stock, or runs reverse schema migrations.

The service locks the organization first, validates dependencies in both
directions, rejects cycles, runs a read-only health check and commits state,
history and audit together. Failed validation/health leaves the old state intact.
Hook failures on reads are isolated to the affected plugin card.

There is no destructive uninstall in this release: disable retains settings and
history. Arbitrary third-party code, signed marketplace packages, custom tables,
and asynchronous extension workers need additional contracts and isolation.

## Development order

1. Write a manifest and its settings contract.
2. For a new capability, add a trusted hook implementation with explicit tenant input.
3. Add validation and compatibility rules before exposing the release.
4. Test install/update/rollback, failure, dependency and tenant boundaries.
5. Build and deploy the reviewed catalog, then enable per organization.
