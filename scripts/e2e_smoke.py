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
        expect(page.get_by_role("heading", name="Dashboard", exact=True)).to_be_visible()
        # TORY-62: one page header with the breadcrumb under the title.
        expect(page.get_by_role("navigation", name="Breadcrumb")).to_be_visible()
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
        expect(page.get_by_role("heading", name="Insights", exact=True)).to_be_visible()
        # TORY-59: six explained chart cards; seeded demo data always fills these four
        # (the value and days-of-supply cards may legitimately show their empty state).
        expect(page.locator("section.insight-card")).to_have_count(6)
        charts = ("stock-chart", "traffic-chart", "demand-chart", "expiry-chart")
        for chart in charts:
            expect(page.locator(f"canvas#{chart}")).to_be_visible()
        page.wait_for_function(
            "ids => window.Chart && ids.every(id => Chart.getChart(document.getElementById(id)))", arg=list(charts))
        snap("3-insights")

        page.goto(base + forecast_href)
        # TORY-62: the product name is the page title; the underline tab shows the forecast.
        expect(page.locator(".product-tabs a[aria-current='page']")).to_have_text("Forecast")
        expect(page.locator(".summary-card")).to_have_count(3)
        snap("4-forecast")

        # TORY-62: Sign out (and the theme toggle) live in the sidebar profile menu.
        page.locator(".profile-menu summary").click()
        page.get_by_role("button", name="Sign out").click()
        expect(page).to_have_url(f"{base}/login/")
        # TORY-60: "/" is the public landing page; the dashboard needs sign-in again.
        page.goto(f"{base}/")
        expect(page.get_by_role("link", name="Sign in").first).to_be_visible()
        page.goto(f"{base}/dashboard/")
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
