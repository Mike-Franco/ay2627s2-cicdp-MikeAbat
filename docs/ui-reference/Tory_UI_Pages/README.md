# Tory HTML pages

Open `index.html` after extracting this folder. Keep the `assets` folder beside the HTML files. The pages use plain HTML, CSS and JavaScript and can also be served from a static web server.

Use **Sample workspace** in the top bar to preview Alex Tan as Manager or Jamie Lim as Staff. Alex is assigned to Pharmacy and Grocery. Jamie is assigned to Pharmacy. The sidebar displays the selected sample account’s name and role.

| HTML file | Screen |
| --- | --- |
| `index.html` | Products and inventory overview |
| `inventories.html` | Assigned inventory chooser |
| `product.html` | Product stock and batch balances |
| `history.html` | Product stock history |
| `forecast.html` | Seven-day demand and observation coverage |
| `receive.html` | Receive stock form |
| `issue.html` | Issue stock form |
| `adjust.html` | Manager batch count adjustment |
| `dispose.html` | Manager disposal form |
| `import.html` | Manager CSV file selection and review |
| `catalogue.html` | Product definitions for the selected inventory |
| `reorder-settings.html` | Manager lead time and safety stock form |
| `product-status.html` | Manager product lifecycle eligibility view |
| `login.html` | Sample sign-in layout |
| `reset-password.html` | Password reset request layout |

Stock and demand are illustrative fixtures for 11 November 2026. Form submissions show confirmation previews. CSV handling previews file selection. Browser preferences store the selected theme, inventory and sample account. Stock operations, authentication and email delivery require the existing Django backend.

The Team destination remains tracked under TORY-11. Add that navigation link when its authorised page is ready.

`assets/app.css` defines the light and dark palettes, sidebar, tables, forms and responsive layouts. `assets/app.js` renders the shared interface and handles preview interactions. `assets/data.js` contains the sample fixtures. `DESIGN.md` records the design direction.

For Django integration, use the signed-in user and effective role from the authenticated server context. Resolve inventory assignments and permissions on the server, connect links to named routes, and send forms to the existing CSRF-protected views. Use Tory’s existing stock, expiry, forecast, audit and idempotency services.
