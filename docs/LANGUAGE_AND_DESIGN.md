# Languages and optional design editing

The application keeps the Weeks 1–14 interface and its original default theme.
New navigation entries open Marketplace and Design; they do not redesign existing pages.

## English / Français / العربية

Use the language selector on the login page or in the dashboard toolbar. The choice is
stored in this browser and changes immediately. Arabic sets `lang="ar"` and `dir="rtl"`
on the document; the MUI direction and Emotion RTL styling change together.
French and English use left-to-right layout. MUI component messages use their locales.

- `apps/web/src/i18n/messages.json`: English key → French and Arabic text.
- `i18n/index.ts`: selection, fallback, normalized status labels and interpolation.
- `i18n/LanguageSelect.tsx`: language control.
- `design/DesignProvider.tsx`: theme direction, MUI locale and RTL cache.
- `api/client.ts`: sends `Accept-Language`; Express forwards it to Django.
- Django `LocaleMiddleware`: translates supported built-in validation responses.

Example: `t("Products")` produces Products / Produits / المنتجات. Add one dictionary
entry when introducing another UI label, then reuse the same key throughout the app.
API field names, enums, UUIDs, decimals and stored customer data do not change language.
Product names, notes and publisher descriptions remain as entered. Some legacy dynamic
success messages and custom server business errors still use English. The separate
Spring Identity login page is not translated by this React language selector.

## Design settings

Open **Design** as an organization administrator. You can prepare primary/secondary
colors, background, corner radius, font size, light/dark mode and table density.

1. Edit the fields. This alone changes no shared design.
2. Select **Preview** to see the draft locally.
3. **Cancel preview** restores the saved theme. Leaving Design also cancels preview.
4. **Save design** persists the settings for the selected organization.
5. **Restore defaults** fills the form with the original values; Save applies them.

Other roles can view settings but cannot save them. Preview never calls the write API.
Each save checks `expected_revision`; a stale edit returns HTTP 409 rather than overwriting
another administrator's changes. Saves create audit events. Organizations have separate settings.

Code entry points:

| Layer | Files | Responsibility |
|---|---|---|
| Theme contract | `apps/web/src/design/context.ts` | Original defaults and token types |
| Editor | `apps/web/src/design/DesignEditor.tsx` | Draft, preview, cancel and save |
| Theme application | `apps/web/src/design/DesignProvider.tsx` | Validated settings → MUI theme |
| API | `services/erp-core/apps/extensions/appearance.py` | Membership, admin permission, validation and revision check |
| Storage | `extensions/models.py`, migration `0002` | Per-organization settings and revision |

This is a design-token editor, not a drag-and-drop page builder. To change layout in code,
start with `dashboard/Dashboard.tsx` and the relevant feature component. Add a reviewed
token to both the TypeScript contract and Django serializer for new configurable options;
do not accept arbitrary CSS, HTML or scripts through the settings API.
