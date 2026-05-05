"""Fetch AmOne invoice data from QMP Exchange portal via Playwright."""

import os
from playwright.sync_api import sync_playwright


def main():
    os.makedirs("/home/ubuntu/recon-dashboard/screenshots", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Step 1: Login
        print("[qmp] Loading login page...")
        page.goto("https://exchange.qmp.ai/", timeout=30000)
        page.wait_for_load_state("networkidle")

        page.locator('input[name="username"]').fill("rushit.virani@brightmoney.co")
        page.locator('input[name="password"]').fill("Bright@2025")

        page.locator('button:has-text("Login"), button[type="submit"]').first.click()
        print("[qmp] Login submitted...")
        page.wait_for_load_state("networkidle", timeout=30000)
        page.wait_for_timeout(3000)

        page.screenshot(path="/home/ubuntu/recon-dashboard/screenshots/02_after_login.png")
        print(f"[qmp] Post-login URL: {page.url}")

        # List navigation items
        print("[qmp] Available navigation:")
        nav_items = page.locator("a, button, [role='tab'], [role='menuitem'], nav a, .nav-link, li a").all()
        seen = set()
        for item in nav_items[:50]:
            txt = item.text_content().strip().replace('\n', ' ')
            href = item.get_attribute('href') or ''
            if txt and txt not in seen and len(txt) < 80:
                seen.add(txt)
                print(f"  - [{txt}] href={href[:80]}")

        # Click Accounting
        print("\n[qmp] Looking for Accounting...")
        acct = page.locator('text=Accounting').first
        if acct.is_visible():
            acct.click()
            print("[qmp] Clicked Accounting")
            page.wait_for_load_state("networkidle", timeout=30000)
            page.wait_for_timeout(3000)
        else:
            print("[qmp] 'Accounting' not found on page")

        page.screenshot(path="/home/ubuntu/recon-dashboard/screenshots/04_accounting.png", full_page=True)
        print(f"[qmp] URL: {page.url}")

        # Dump page text
        page_text = page.inner_text("body")
        with open("/home/ubuntu/recon-dashboard/screenshots/page_text.txt", "w") as f:
            f.write(page_text)
        print(f"\n[qmp] Page text preview:\n{page_text[:3000]}")

        browser.close()


if __name__ == "__main__":
    main()
