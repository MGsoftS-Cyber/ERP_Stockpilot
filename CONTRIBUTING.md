# Contributing

Use the setup and checks in README.md. Keep changes focused and explain the
business behavior, affected permissions and verification in each pull request.

## Requirements

- Filter reads and related-object resolution by the authorized organization.
- Validate actor permissions at public service boundaries before replay or writes.
- Keep business commands atomic; preserve stock/payment and immutable-history invariants.
- Reuse an idempotency key only for unchanged command input.
- Store prices, quantities and financial values as exact decimals, not floats.
- Add French/Arabic translations for new static UI labels and verify RTL.
- Keep SDK validation aligned with the server manifest contract.
- Add regression tests for new command, permission, replay or concurrency behavior.
- Preserve historical migration identifiers and persistent data.

Do not commit environments, private uploads, identity exports, signing keys,
database backups or generated dependency/build directories. Do not claim
performance improvements without a measurable query count, benchmark or workload.

Run `make check` when all toolchains are installed. Run strict typing separately:
`cd services/erp-core && uv run mypy apps config`. The existing typing debt is
tracked in the verification report and must not be hidden by disabling strict mode.
