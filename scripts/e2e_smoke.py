"""Browser smoke test against a running Tory stack seeded with seed_demo.

Usage: python scripts/e2e_smoke.py --base-url http://localhost:8000 \
           --email manager@tory-demo.test --password ... --screenshots e2e-screenshots

Signs in as the demo Manager, then checks the dashboard, a products list, the
Insights page (all three charts render on their canvases), a forecast page,
and signs out. Screenshots of each step are saved; any failure exits non-zero.
"""

import argparse
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--screenshots", type=Path, default=Path("e2e-screenshots"))
    parser.add_argument("--channel", default=None, help="browser channel, for example msedge (default: bundled Chromium)")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    args.screenshots.mkdir(parents=True, exist_ok=True)
    errors = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=args.channel)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.set_default_timeout(15000)
        page.on("pageerror", lambda error: errors.append(f"{page.url}: {error}"))

        def snap(name):
            page.screenshot(path=str(args.screenshots / f"{name}.png"), full_page=True)
            print(f"ok  {name:<10} {page.url}")

        page.goto(f"{base}/login/")
        page.fill("#id_email", args.email)
        page.fill("#id_password", args.password)
        page.get_by_role("button", name="Sign in").click()
        expect(page.get_by_role("heading", name="Inventory dashboard")).to_be_visible()
        expect(page.locator(".stat-tile")).not_to_have_count(0)
        snap("1-dashboard")

        page.goto(f"{base}/inventories/")
        page.locator(".inventory-card :is(h2, h3) a").first.click()
        expect(page.get_by_role("heading", name="Products", exact=True)).to_be_visible()
        expect(page.locator("a.product-name")).not_to_have_count(0)
        snap("2-products")
        inventory_id = page.url.rstrip("/").split("/")[-2]
        forecast_href = page.locator("a[href$='/forecast/']").first.get_attribute("href")

        page.goto(f"{base}/inventories/{inventory_id}/insights/")
        expect(page.get_by_role("heading", name="Inventory insights")).to_be_visible()
        for chart in ("demand-chart", "reorder-chart", "expiry-chart"):
            expect(page.locator(f"canvas#{chart}")).to_be_visible()
        page.wait_for_function(
            "() => window.Chart && ['demand-chart', 'reorder-chart', 'expiry-chart']"
            ".every(id => Chart.getChart(document.getElementById(id)))")
        snap("3-insights")

        page.goto(base + forecast_href)
        expect(page.get_by_role("heading", name="Demand forecast for", exact=False)).to_be_visible()
        expect(page.locator(".summary-card")).to_have_count(3)
        snap("4-forecast")

        page.get_by_role("button", name="Sign out").click()
        expect(page).to_have_url(f"{base}/login/")
        page.goto(f"{base}/")
        expect(page).to_have_url(f"{base}/login/")
        snap("5-signed-out")
        browser.close()

    if errors:
        print("JavaScript errors:", *errors, sep="\n  ")
        return 1
    print("E2E smoke test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
