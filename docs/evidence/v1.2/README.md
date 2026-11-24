# v1.2 UI evidence screenshots

Captured on 24 Nov 2026 from the live staging site (https://104-208-96-230.sslip.io) running **v1.2.2**
(image `sha-e3c44ae`), straight after a demo reset (`flush` + `seed_demo`). Browser: Microsoft Edge via Playwright.

- Desktop: 1440 px wide, light and dark theme, each page captured to its full height. Pages `01`–`21` are signed in
  as the demo Manager (Grocery inventory, product Oat Milk); `22`–`23` are signed in as the demo Staff user.
- Phone: 390 px wide, dashboard and product overview, light and dark (`mobile-390-*`).
- No passwords are shown: the sign-in and change-password fields are empty, and the capture script
  checked that neither generated demo password appeared anywhere in a page's HTML.

At capture time Insights showed a forecast accuracy (MAPE) of 14% for Grocery and 15% for Pharmacy, and the Manager
dashboard showed the "Do this first" banner (2 unverified demand days in Grocery). Staff don't see the banner
because only Managers can verify demand (TORY-63).
