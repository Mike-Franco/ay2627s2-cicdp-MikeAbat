# Tory UI design

*Inventory made simple.*

**Navigation draft.** The sidebar links, product tabs and placement of Manager tools below are proposed defaults. Check the current Django routes before connecting the links.

The design covers the signed-in workspace. The first implementation slice is the selected inventory’s Products page, including the balance labels and reorder status. The shared sidebar, product tabs and theme preference can be delivered as a separate slice. [TORY-33](https://mikefrancoabat.atlassian.net/browse/TORY-33)

## Visual direction

Use Fixoria’s labelled sidebar, compact toolbar and product table as the layout reference. Use Finly’s theme control and keep the same layout in both modes. Use the dark dashboard reference for the separation between the canvas and panels. Tory’s accent is indigo, with quieter neutral surfaces and colour reserved for the active link, primary action and meaningful stock states.

| Region | Design |
| --- | --- |
| Left sidebar | About 232 px wide on desktop. Stack the Tory wordmark, inventory switcher and icon plus text links. Highlight the current section with a tinted background and a visible label. |
| Sidebar footer | Show the signed-in user’s display name with **Manager** or **Staff** on a second line. An initials avatar is optional. Put **Sign out** beside or below the account details. |
| Top bar | Use a breadcrumb such as **Inventory › Pharmacy › Products**. Place the **Light / Dark** control on the right. The selected inventory stays visible on stock forms and product pages. |
| Main content | Use one clear page heading, one row of relevant actions, then the table or form. Use 24–32 px page padding on desktop, 16 px on small screens and 10–12 px panel corners. |
| Small screens | Below 900 px, open the sidebar from a labelled **Menu** button. Keep the name, role and inventory switcher in the drawer. Let the product table scroll within its own panel. |

Use the system sans serif font. Set page titles to about 28 px, section titles to 16–18 px and navigation and table text to 14 px. Use tabular numerals for stock quantities. Choose a filled primary button for the main action and outlined or plain buttons for secondary actions.

## Navigation and destinations

The sidebar switches workspace areas. Product tabs switch the view for the same inventory and SKU. Stock actions open from the page that already shows the relevant inventory or product.

| Where | Label | Opens | Access and state |
| --- | --- | --- | --- |
| Sidebar | **Inventory** | The selected inventory’s **Products** list. If a selection is needed, open the existing assigned inventory chooser. | Manager and Staff with a valid assignment. |
| Sidebar switcher | **Inventory name** | The list of assigned inventories. Selecting another inventory opens its **Products** list. | Use the inventories returned by the server for the signed-in user. |
| Inventory header | **Import CSV** | The stock transaction upload form for the selected inventory. Show its name on the upload and result views. | Manager with import permission for that inventory. |
| Product name in list | **Product name** | The product’s stock view, with the proposed product tabs below its heading. | Manager and Staff with access to this inventory and product. |
| Product tabs | **Stock · Stock history · Demand forecast** | The stock view, history and forecast for the same inventory and product. Provide a **Back to products** link. | Use each destination’s existing access rules. Manager controls inside a tab use their own permission checks. |
| Product stock actions | **Receive stock · Issue stock** | The existing transaction forms, with the inventory and product shown above the fields. | Show each action when the server grants it for the current product and inventory. |
| Product stock actions | **Adjust batch count · Dispose stock** | The Manager forms with batch, quantity and reason where applicable. | Manager with the corresponding permission. |
| Manage group | **Catalogue** | The shared product catalogue if there is an existing authorised page. Keep inventory quantities on **Products**. | Render when the route and the required catalogue permission are available. |
| Manage group | **Team** | Staff invitations and access management when the page is ready. | Planned Manager destination. [TORY-11](https://mikefrancoabat.atlassian.net/browse/TORY-11) |
| Sidebar footer | **Sign out** | The existing sign-out action. | Signed-in users. |

Use a valid selection when reopening Inventory. If the user needs to choose a location, list their assigned inventories. If they have none, show **No assigned inventories** and guidance to contact their Manager. Render the **Manage** heading when it contains an available link.

**Route check.** Connect to existing named Django routes. If there is currently no standalone product stock route, keep **Stock history** and **Demand forecast** reachable from their product row while the shared product layout is being introduced. Use route links styled as tabs with `aria-current="page"` for the active view.

## Screen layouts

### Products

Start with the inventory name and **Products** heading. Place existing search or filters above the table when available. Put **Import CSV** in the header for an authorised Manager. The product name is the first link in each row. Give **Available** the strongest emphasis of the balance columns.

| Product | SKU | Physical | Quarantined | Available | Reorder status |
| --- | --- | ---: | ---: | ---: | --- |
| Adhesive bandages | PH-017 | 20 boxes | 4 boxes | **16 boxes** | At or below reorder point |
| Cotton pads | PH-024 | 52 packs | 0 packs | **52 packs** | Above reorder point |
| Alcohol wipes | PH-031 | 0 boxes | 0 boxes | **0 boxes** | Reorder point unavailable |

*Example rows for the layout.*

**Physical** is the quantity recorded on hand. **Quarantined** is stock held back from issue. **Available** is the quantity Tory currently allows users to issue. Use the existing expiry-aware balances and show each product’s base unit. Use Tory’s authoritative reorder state to label the row. If a valid threshold is unavailable, show **Reorder point unavailable** or the existing eligibility explanation. A recorded zero in Available is still shown as **0**.

### Product stock, history and forecast

| Screen | Main content |
| --- | --- |
| **Stock** | Put the SKU and inventory under the product name. Show physical, quarantined and available balances together. Follow with the existing batch and expiry information and permitted stock actions. |
| **Stock history** | Show event type, quantity, actor, reason where recorded and Singapore date and time. Keep effective and recorded times distinct where both apply. Use the existing pagination controls. |
| **Demand forecast** | Show the previous seven complete Singapore days and their observation states. Put the forecast and reorder recommendation above the day list when eligible. When the forecast is unavailable, show the reason Tory reports. Keep Manager verification and reorder settings close to the information they affect. |

### Forms and account screens

Keep receive, issue, adjustment and disposal forms compact. Show the inventory, product and unit before inputs. Place field errors beside their inputs and provide clear confirmation after submission. The CSV import view shows the inventory, file requirements and the result of the upload. Sign-in and existing account setup screens use the same wordmark, typography and theme as a simple form.

## Light and dark themes

Apply these semantic tokens to navigation, tables, forms and feedback. Use the same layout in both modes.

| Token | Light | Dark |
| --- | --- | --- |
| Canvas | `#F6F7FB` | `#111319` |
| Panel | `#FFFFFF` | `#1A1D27` |
| Subtle surface | `#F2F3F8` | `#222633` |
| Main text | `#1A2235` | `#F2F4FC` |
| Secondary text | `#526078` | `#AFBAD0` |
| Divider | `#DCE1EB` | `#373E51` |
| Control outline | `#7A8498` | `#748097` |
| Accent and focus | `#4D3BBF` | `#B5A9FF` |
| Text on filled accent | `#FFFFFF` | `#171130` |
| Active link background | `#EEEAFE` | `#2E284A` |
| Attention background / text | `#FFF3D6` / `#765018` | `#362B1A` / `#FFD28A` |
| Success background / text | `#E8F5EC` / `#1D6542` | `#18362A` / `#A2E8B6` |
| Error background / text | `#FEE9EA` / `#9E2635` | `#40262D` / `#FFB0B9` |

Start with the device preference. Persist an explicit Light or Dark choice on the current browser and apply it before the shared shell is drawn. Give the toggle an accessible label that identifies the mode it will switch to. Use text alongside status colour and keep keyboard focus visible on links, tabs, inputs and menu controls.

## Account and scope rules

- Render the user’s name and Tory role from the authenticated server context. If the role depends on the active inventory or business, use the role Django resolves for that context. Use the existing account label if a display name is unavailable.
- Filter inventories and stock data by the current assignment. Apply the existing permission checks to every page and action, including direct links and form submissions. The sidebar reflects those checks. [TORY-12](https://mikefrancoabat.atlassian.net/browse/TORY-12)
- Use available stock and the existing reorder rule for the attention label. Forecast eligibility and reorder recommendations come from Tory’s existing logic. [TORY-24](https://mikefrancoabat.atlassian.net/browse/TORY-24)
- Keep the inventory overview focused on product balances and reorder status. The first build uses existing stock, history and forecast data.

## Decisions to review

| Decision | Draft choice |
| --- | --- |
| Main sidebar links | One **Inventory** entry and an inventory switcher. The selected inventory opens **Products**. |
| Product navigation | **Stock**, **Stock history** and **Demand forecast** as contextual tabs. |
| Manager tools | **Import CSV** on the selected inventory. **Catalogue** and **Team** under **Manage** as their pages become available. |
