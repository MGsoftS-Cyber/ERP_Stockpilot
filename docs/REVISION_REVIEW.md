# Correctness, performance and documentation review

Reviewed 11 October 2026. This revision preserves the existing application and
business workflows. Tests use synthetic records; no production database was accessed.

## Correctness changes

| Area | Problem | Result |
|---|---|---|
| Inventory authorization | Direct service callers could bypass API role checks | Adjustments, transfers, reservations and releases check an active tenant membership before accessing replayed commands |
| Inventory retries | A reused key could silently return a different previous request | Warehouse, reason, reference and normalized product/quantity/cost contents are compared; changed input returns HTTP 409 |
| Stock validation | Service entry points could accept invalid decimal or whole-unit quantities | Finite, bounded, nonzero quantities with up to four decimal places; units that disallow fractions require whole quantities |
| Purchasing | Inactive actors and fractional whole-unit order/receipt quantities needed stronger validation | Direct service calls enforce these rules as well as existing tenant and workflow checks |
| Notification load | Each socket independently polled the same history | Verified user/organization/role groups share polling, with independent token expiry and membership revocation handling |
| Demonstration records | User-facing order notes and invoice references carried tutorial labels | Descriptive values for new seeds; legacy order markers are renamed without duplicating drafts; existing invoice replay identities are preserved |

Inventory release callers now supply the actor explicitly. Existing callers in
API and sales workflows were updated. Historical migration identities and
stable demo UUID namespaces are retained for compatibility.

## Performance changes

| Operation | Change | Evidence or boundary |
|---|---|---|
| Finance summary | Three database aggregates replace repeated totals queries | Query-count regression checks the three-query contract; financial outcome tests still pass |
| Purchase inputs | Resolve all line products in one tenant-scoped query | Removes a query per input line; unit relationships are included |
| Plugin lookup | Cache immutable bundled manifests; query only the requested approved release | Caller mutation cannot alter the cache; selected community package integrity is still validated |
| Plugin dependencies | Remember already visited nodes | Avoids repeated traversal while retaining cycle detection |
| Translation lookup | Precompute normalized keys | Constant-time dictionary lookup replaces repeated key scans |
| Web bundle | Lazy-load feature screens and split vendor assets | Main index 347.85 kB / 113.84 kB gzip; UI vendor 299.57 kB / 92.78 kB gzip; feature chunks load separately |
| Notifications | Shared polling with idle backoff | Default activity interval 5 seconds; idle interval grows to 30 seconds; tests cover user isolation and revocation |
| Demand anomaly detection | Bounded cache of numeric statistical results | Maximum 128 entries; fresh margins are evaluated on every request |

These are structural improvements with regression coverage, not measured
production latency or throughput claims. The reported earlier monolithic bundle
was approximately 829 kB / 259 kB gzip; browser startup was not benchmarked.
Organization locks remain intentionally coarse to protect atomic workflows.

Forecasting still uses a seven-day moving average and Isolation Forest. This
revision improves repeated work, not forecast accuracy. No seasonal demand model
or replenishment optimization guarantee is claimed.

## Application text and GitHub presentation

The header, purchasing page and outdated billing message now describe actual
features. Seed commands and test module names are descriptive. Repeated tutorial
comments have been removed. README explains the product, architecture, setup,
features, extension development and boundaries. Architecture, security,
contribution and demonstration guides provide further context.

No GitHub repository was created or published. The archive contains source and
lockfiles, excludes local dependencies and credentials, and needs a license
choice before it is advertised as open source.

## Remaining work

Strict mypy still fails across the inherited backend. Its exact current count
and full output are in [verification](VERIFICATION.md) and [review/mypy.txt](review/mypy.txt).
The configuration has not been weakened to hide errors. A broad typing pass is
still necessary; this revision does not claim to have completed it.

PostgreSQL lock concurrency, Docker deployment, PostgreSQL backup/restore and
browser end-to-end behavior require their own environment verification. Live
Django-to-AI and Spring-to-gateway-to-Django integrations did pass. The complete
verification evidence distinguishes executed checks from pending ones.
