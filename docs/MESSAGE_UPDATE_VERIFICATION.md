# Explanatory messages and source comments - 3 October 2026

This update changes screen text, seed-command feedback, API documentation text and
developer comments. No database migration or dependency version changed.

## Changes

- Replaced the week-number overview/purchasing headings with business feature names.
- Replaced the outdated claim that billing was planned with the implemented workflow:
  purchase draft -> approval -> goods receipt -> supplier invoice in Finance.
- Added more explanatory purchase, finance, AI and plugin success messages.
- Localized sales success messages and new text in French and Arabic.
- Replaced seed-command week messages with the available data and next action.
- Added responsibility/relationship comments to 47 entry-point files across React,
  Django, FastAPI, Express, Spring and the Python SDK.
- Added `CODE_RESPONSIBILITIES.md` with the request path and library/pattern roles.

Historical filenames, migrations, cache identifiers and stored demo markers remain
stable. Existing business operations, authentication rules and database constraints
were not altered by this message edit.

## Checks run on this update

- Python source parses successfully.
- JSON configuration/message files are valid.
- Every literal translated JSX message has French and Arabic entries.
- No translated screen heading references development week numbers.
- Python domain statements match the preceding archive when documentation strings
  are excluded; seed output and the API description are intentional text changes.
- All migration files, dependency manifests and lockfiles are byte-identical.
- ZIP integrity checked before delivery.

Full Django/React checks could not be rerun: npm and Python dependency downloads were
denied by the current environment's network restrictions. The earlier test outputs in
`docs/review/` describe the preceding revision, not a new runtime test run. No new browser
rendering or Java build was performed for this text-only update.

After installing dependencies locally, run:

```bash
pnpm --filter @stockpilot/web test
pnpm --filter @stockpilot/web lint
pnpm --filter @stockpilot/web build
uv --project services/erp-core run ruff check services/erp-core
uv --project services/erp-core run pytest services/erp-core
```

Then verify the overview, purchasing information banner and success messages in English,
French and Arabic. Inspect the leading comments in each major module to follow its role
and connections through the application.
