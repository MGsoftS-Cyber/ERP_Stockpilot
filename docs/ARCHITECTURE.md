# Architecture and business rules

## Request boundaries

The React client selects an organization and attaches its ID to requests.
Express verifies access tokens, origin and request limits, then forwards a fixed
API prefix to Django. Django verifies the token again and checks current active
local membership. Data and business commands remain organization-scoped.

Spring issues five-minute RS256 access tokens through a public PKCE client.
Its account directory is a private exported snapshot. Role/password changes
require a refreshed export and identity restart; local revocations fail closed.

AI accepts a service token and is reachable internally. User uploads and human
approval are handled by Django. No browser receives the internal AI credential.

## Transaction contracts

- Inventory movements append history and update a locked balance together.
- Available stock is on-hand minus reserved; movements cannot consume reserved stock.
- Inventory retries compare persisted command contents; changed input conflicts.
- Purchase receipts cannot exceed remaining ordered quantity.
- Sales confirmation reserves all lines or none. Shipments consume reservations atomically.
- Cancellation preserves shipped history and releases the outstanding reservation.
- Customer returns restore stock but do not reopen fulfillment or create credit notes.
- Payments cannot exceed invoice balances or mix partners, directions or currencies.
- Plugin rollback restores extension state as a new revision; it does not undo ERP transactions.

Organization locks are intentionally retained to serialize commands and protect
idempotency under PostgreSQL. Narrower locks require measured contention and
concurrency regression coverage, not just a faster single-request benchmark.

## Performance choices

Feature screens use lazy imports. Translation lookup uses a precomputed map.
Finance summaries aggregate invoices, payments and expenses in three queries.
Purchase input resolves product lines in one tenant-scoped query. Plugin resolution
queries only the requested approved release; bundled manifests are cached and
returned as copies. Dependency traversal remembers visited nodes.

Anomaly detection caches only numeric demand results, bounded to 128 entries.
Margins and other request-specific values are evaluated freshly. This cache holds
no user identifiers or invoice rows and is not a shared application result cache.

Notification polling is shared only for a verified subject, organization and role.
It still rechecks membership through Django, adapts idle polling up to 30 seconds,
and retains per-connection expiry checks. Different users are not authorized
through one another's membership.

## Compatibility

Historical migration filenames/dependencies must not be renamed: existing
installations record those identities in the database. Deterministic demo UUID
namespaces also remain stable to avoid duplicating earlier demo records.
Descriptive seed commands are `seed_demo`, `seed_purchasing_demo`,
`seed_sales_demo` and `seed_finance_demo`.
