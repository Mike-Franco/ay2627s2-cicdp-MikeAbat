# Tory v1.2.0 build brief (for Claude Code)

Source of truth: the approved mockup in `docs/ui-reference/v1.2/mockup/*.dc.html`.
Those files are design references, not templates: they use `<x-dc>`, `<dc-import>` and `{{…}}` placeholders from the design tool. Copy the **CSS tokens, layout, wording and behaviour** into the real Django templates; don't copy the design-tool markup.
Logo: `docs/ui-reference/v1.2/logo/` (light and dark SVG/PNG, transparent).

Jira: TORY-62 … TORY-67. One branch + PR per ticket off `develop`, in the order below. Move each ticket In Progress → Review/Test → Done as you go.

## Ground rules (unchanged)
- Never commit `.env`, keys, `.tory-*` folders or `scripts/repair_local_stockout_schema.py`.
- Do **not** merge Dependabot PRs #86–#90. Leave PR #76 open.
- Before every PR: `ruff check .`, full test suite, coverage ≥ 90%, `makemigrations --check`, `check --deploy`.
- Before merging each PR, trial-merge it onto the latest `develop` and diff it against `develop`: no unrelated files may be deleted or reverted (this is how the TORY-54 / #98 incident happened).
- Keep all existing permission checks (`protected_view`, `inventory_access/authorization.py`). New views use the same scope helpers.
- Release to `main` (v1.2.0 tag) only after Mike says go.

---

## 1. TORY-62: UI foundation
Branch `feature/TORY-62-ui-foundation`
1. `static/tory/tokens.css`: copy the `.t` / `.t.dark` variable block from any mockup file into `:root` and `[data-theme="dark"]`. Add `@media (prefers-color-scheme: dark)` as the default when the user hasn't chosen a theme. Add a theme toggle in the sidebar profile menu, stored in localStorage (wrapped in try/catch), and apply it before first paint with a tiny inline script in `<head>` to avoid a flash.
   - Logo variables: `--mk-t/--mk-l/--mk-r` (light `#5B5BD6/#3B3B9E/#8E8FF5`, dark `#8E8FF5/#5B5BD6/#B9BAFB`).
   - Self-host Inter and JetBrains Mono via the existing static pipeline (no Google Fonts call, to keep the CSP strict), or fall back to the system-ui stack if that's simpler. Don't loosen the CSP.
2. Replace Bootstrap colours and spacing in `app.css` / `pages.css` with the tokens: 13px base, 1.45 line height, normal `letter-spacing`/`word-spacing` (remove any custom word-spacing), 6px radius on buttons and inputs, 8px on cards, 34px table header, 38px rows, `font-variant-numeric: tabular-nums` and right alignment on numeric columns.
3. Logo: inline the cube mark (copy the `<svg viewBox="0 0 37.04 35.80">` from `mockup/Sidebar.dc.html`) into `includes/sidebar.html` and `accounts/login.html`. Generate a favicon from `logo/tory-mark-light.svg` (keep the SVG favicon plus a 32px PNG).
4. New `templates/includes/page_header.html`: a title row with an actions slot, and a breadcrumb `<nav aria-label="Breadcrumb">` **under** the title, as in the mockup. Use it on every authenticated page. Breadcrumbs come from the view context as a list of (label, url) pairs.
5. Upgrade `includes/pagination.html` into a single component: "Showing **26–50** of 142", a rows-per-page `<select>` (10/25/50/100, plus 5 where noted) that submits `?per_page=` and keeps the other query parameters, and ‹ 1 2 3 … › buttons with `aria-current`. Clamp `per_page` server-side to the allowed set. Per-table defaults:
   | Table | Default |
   |---|---|
   | Catalogue, Inventory products, Staff, Invitations, Product history | 25 |
   | Activity log | 50 |
   | Insights tables | 5 (ranking), 10 (others) |
   | Dashboard panels | 5–10 plus a "View all" link |
   Every table in the app must use it, including the ones that don't page today.
6. Colour rule, used everywhere: **indigo = a task or action for the user**, amber/red/green = stock state only.
7. Mobile: 44px touch targets under 700px, tables scroll horizontally inside their card.
Tests: pagination (per_page clamp, query parameters preserved, out-of-range page), and the breadcrumb context on 2–3 views.

## 2. TORY-63: Manage follows the selected inventory, plus the "Do this first" banner
Branch `fix/TORY-63-scoped-manage`
- **Bug:** Catalogue (and Activity log) ignore the selected inventory. Default both to the current inventory (the same session/selection the sidebar switcher uses). Show the scope chip "Showing [icon] Grocery · Show all inventories (N)". `?scope=all` widens to all inventories **the user may see**. Staff can never widen past their assigned inventories.
- Dashboard: when there are unverified demand days, show the `.todo` banner from `mockup/Main.dc.html` (indigo border, 4px left bar, "DO THIS FIRST" tag, "Verify N demand days in <inventory> (dates)", primary button "Verify N days"). Show it only to managers. The header "Verify demand" button gets a count badge. Remove the old amber note.
Tests: default scope, scope=all, staff scope cap, banner shown or hidden by count and role.

## 3. TORY-64: Insights
Branch `feature/TORY-64-insights-v12`
- `includes/help_tip.html`: a `?` button with `aria-label` that opens a popover on hover, focus or tap (CSS `:hover`/`:focus-within`, plus a few lines of JS for tap-to-toggle and Esc to close). Copy the exact wording from `mockup/Insights.dc.html` for each KPI and chart.
- KPI strip: Stock value (vs previous period), Turnover, Median days of supply, **Forecast accuracy**.
  - New: MAPE of the 7-day forecast made a week ago vs verified demand. Skip unverified days. Skip days with zero actual demand, or use the WAPE fallback (Σ|err| / Σactual), and document the choice in the help tip. Show "Not enough verified data" when there are fewer than 3 points.
- Charts (existing Chart.js): stock vs reorder point (bar below reorder shown red), intake vs outtake weekly, value breakdown donut with a Category/Status toggle, daily demand plus a dashed 7-day forecast (unverified days as hollow amber points).
- Tables: days-of-supply ranking (paginated, default 5) and expiring stock by week with value at risk (default 10).
- Range control 7d/30d/90d (`?range=`), and Export CSV of the tables.
Tests: MAPE/WAPE maths (including zero demand and no data), range parameter validation, pagination.

## 4. TORY-65: Inventory edit, staff access and deactivation
Branch `feature/TORY-65-inventory-staff-access`
- On the edit page add a "Who can use this inventory" section. List the business's active memberships with avatar initials, email and role.
  - Managers: checkbox checked and disabled, pill "Manager · always".
  - Staff: a checkbox per person, backed by `InventoryAssignment`. Toggle `is_active` and never delete rows. Bulk-sync in one transaction.
  - Include a "Select all staff" link and an "Invite someone" link.
- Write an audit event per change, so it shows up in the Activity log ("Gave Aisha Rahman access").
- Deactivate goes into a danger section with a confirm step where the user types the inventory name. Check it server-side, case-sensitive and trimmed. Wording as in the mockup.
- Keep the existing icon, colour and picture fields, laid out as in the mockup (icon grid, colour swatches, live preview).
Tests: manager only, a membership from another business is rejected, audit rows created, wrong confirm name rejected, staff lose access immediately.

## 5. TORY-66: Product page
Branch `feature/TORY-66-product-page`
- Header: title, SKU, status pill. Actions: **Receive** (primary), Issue, Adjust, and a ⋯ menu (Edit product, Transfer, Quarantine a batch, Print label, Deactivate). Show only the actions the user is allowed to do.
- Tabs: Overview / Batches (n) / History / Forecast. Reuse `includes/product_tabs.html`, restyled as an underline tab bar.
- Overview summary strip: Available (with the reorder point), Quarantined, Avg demand/day, Days of supply plus the run-out date, **Suggested order**, Price plus value on hand.
- **Suggested order** = `ceil(avg_daily × (14 + lead_time_days) + safety_stock − available)`, minimum 0. Put the calculation in `catalogue/reorder.py` next to the reorder point. If the inputs are missing, show "—" with the reason (same as the reorder point does today). Make the 14-day cover a constant.
- New optional field `Product.supplier_name` (CharField, 120, blank). Add the migration, the form field and the CSV import column (optional). Show it with the lead time.
- A 7-day projected stock line with a dashed reorder line, and the callout "Order N today. Lead time X days…".
- FEFO batches table and recent history (paginated, default 25 on the History tab, 4 on Overview with "Open in Activity log").
Tests: suggested-order edge cases (no forecast, no lead time, already above target), the supplier field, CSV import with and without the column.

## 6. TORY-67: Activity log for staff
Branch `feature/TORY-67-staff-activity`
- `activity_log` currently requires `manager_memberships`. Allow staff memberships too:
  - Staff rows are restricted to their **active assigned** inventories and the movement kinds (received, issued, adjusted, quarantined, imported).
  - Settings and access rows are hidden from staff.
  - The CSV export returns 403 for staff.
  - Staff can't filter by person outside their own scope.
- Show Activity log in the sidebar for staff.
- Restyle to the mockup: day separators, relative times with exact time in `title`, coloured action pills, signed quantities, "Showing 1–50 of N".
Tests: staff scope, CSV 403, an unassigned inventory never leaks, a manager sees everything.

## 7. Release v1.2.0 (after Mike says go)
- Update CHANGELOG, open a PR develop → main, tag `v1.2.0`, and confirm CD deploys green. Smoke-test the live site in light and dark mode on desktop and on a phone-sized viewport.
- Take screenshots of each page (light and dark) into `docs/evidence/v1.2/` for the report.
- Then **feature freeze**: from here on, only bug fixes until submission on Fri 27 Nov.

When each PR is merged, report back: PR number, test count, coverage, and anything you had to decide.
