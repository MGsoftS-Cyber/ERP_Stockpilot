# Demonstrating StockPilot

Use a disposable seeded environment with fictional data. Verify each scenario
before recording; do not show private identity exports, secrets or real documents.

1. Show products, a warehouse and initial stock.
2. Create a purchase, submit/approve it, receive goods and show the increased balance.
3. Create/confirm a sale, ship it and show reservation/on-hand changes.
4. Create/post an invoice, allocate payment and inspect remaining balance.
5. Upload a sample invoice, review OCR fields and create a supplier draft.
6. Show a forecast and record a human decision without automatically placing an order.
7. Switch English, French and Arabic and demonstrate right-to-left layout.
8. Preview/cancel/save organization appearance as an administrator.
9. Install/configure/update/rollback stock-alerts and inspect immutable history.
10. Sign in as a viewer to demonstrate denied writes and organization boundaries.

For a portfolio, prepare a 90-second workflow video and readable screenshots of
inventory, purchasing, sales, finance and Arabic layout. Describe your actual
contribution and verification; do not invent customers, savings or deployments.

`scripts/record_demo.cjs` records a synthetic local plugin walkthrough with
Playwright. It uses local Django authentication and does not validate the full
Spring/Docker stack. Install Playwright/Chromium before running it.
