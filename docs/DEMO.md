# Week 12 demonstration plan

Use only the seeded demo organization when recording or presenting.

1. Sign in, select the organization and show products/warehouses.
2. Show inventory balances, purchase receipt and sales shipment behavior.
3. Show finance and AI review screens; AI suggestions require human review.
4. Open Plugins and install stock-alerts 1.0.0.
5. Change its threshold; show tenant-specific output.
6. Update to 1.1.0; explain that organization settings stay intact.
7. Roll back to revision 1 and show the new history entry.
8. Explain administrator-only lifecycle and preserved ERP transactions.

Screenshots and video were NOT produced in the build environment: Chromium was
blocked from opening a required socket (Operation not permitted). The supplied
script will generate `screenshots/` and `plugin-walkthrough.webm` locally with
synthetic demo data. It uses isolated Django development authentication
to demonstrate plugin UI behavior. It does not demonstrate Spring or Docker.
The separate OIDC integration script tests the identity transport chain.

To generate the demo, install Playwright in your development tooling and Chromium,
then run `node scripts/record_demo.cjs` after backend/frontend dependencies are installed.
The script creates a disposable SQLite database and captures only that demo.
