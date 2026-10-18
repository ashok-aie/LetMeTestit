import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv(override=True)

# Ensure artifacts directory exists
ARTIFACTS_DIR = Path("artifacts")
ARTIFACTS_DIR.mkdir(exist_ok=True)

SAP_URL = os.environ.get(
    "SAP_URL",
    (
        "https://s4srv25.nodomain.com:44325/sap/bc/ui2/flp"
        "?sap-client=100&sap-language=EN#Launchpad-openFLPPage"
        "?pageId=SAP_CRM_PG_SERVICE_PROCESSING&spaceId=SAP_CRM_SP_SERVICE"
    )
)

SAP_USERNAME = os.environ.get("SAP_USERNAME", "")
SAP_PASSWORD = os.environ.get("SAP_PASSWORD", "")

def connect_to_sap(keep_open_seconds: int = 25):
    print("=" * 65)
    print("  SAP S/4HANA Fiori Automation (Real Google Chrome)")
    print("=" * 65)
    print(f"Target URL: {SAP_URL}")
    print(f"Username:   {SAP_USERNAME}")

    with sync_playwright() as p:
        # Launch real Google Chrome with foreground focus
        print("\n[Step 1] Launching Google Chrome (channel='chrome', headless=False)...")
        browser = p.chromium.launch(
            channel="chrome",
            headless=False,
            slow_mo=800,
            args=[
                "--ignore-certificate-errors",
                "--start-maximized",
                "--no-default-browser-check",
                "--no-first-run",
            ]
        )
        context = browser.new_context(
            ignore_https_errors=True,
            no_viewport=True
        )
        page = context.new_page()

        # Bring window to foreground
        page.bring_to_front()

        # Step 2: Navigate to SAP logon page
        print("[Step 2] Navigating to SAP Logon page...")
        page.goto(SAP_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("#USERNAME_FIELD-inner", timeout=30000)
        time.sleep(2)

        # Screenshot 1: Login page
        screenshot_1 = ARTIFACTS_DIR / "sap_01_login_page.png"
        page.screenshot(path=str(screenshot_1))
        print(f"  [Screenshot] Saved: {screenshot_1}")

        # Step 3: Enter Credentials
        print(f"[Step 3] Typing Username '{SAP_USERNAME}'...")
        user_field = page.locator("#USERNAME_FIELD-inner")
        user_field.click()
        user_field.fill("")
        user_field.press_sequentially(SAP_USERNAME, delay=100)
        time.sleep(1)

        print("[Step 4] Typing Password...")
        pwd_field = page.locator("#PASSWORD_FIELD-inner")
        pwd_field.click()
        pwd_field.fill("")
        pwd_field.press_sequentially(SAP_PASSWORD, delay=100)
        time.sleep(1)

        # Screenshot 2: Credentials typed
        screenshot_2 = ARTIFACTS_DIR / "sap_02_credentials_typed.png"
        page.screenshot(path=str(screenshot_2))
        print(f"  [Screenshot] Saved: {screenshot_2}")

        # Step 5: Click Log On
        print("[Step 5] Clicking 'Log On' button (#LOGIN_LINK)...")
        page.click("#LOGIN_LINK")

        print("  Authenticating and waiting for Fiori Launchpad to load...")
        time.sleep(6)

        # Check for multiple logon confirmation dialog if present
        multi_logon_continue = page.query_selector("button:has-text('Continue'), input[value*='Continue'], #LOGON_CONTINUE_BUTTON")
        if multi_logon_continue and multi_logon_continue.is_visible():
            print("  Detected multiple logon warning dialog. Acknowledging...")
            multi_logon_continue.click()
            time.sleep(4)

        try:
            page.wait_for_load_state("domcontentloaded", timeout=25000)
        except Exception:
            pass

        # Screenshot 3: Logged in dashboard
        screenshot_3 = ARTIFACTS_DIR / "sap_03_logged_in_dashboard.png"
        page.screenshot(path=str(screenshot_3))
        print(f"  [Screenshot] Saved: {screenshot_3}")

        print(f"\n[Status] Successfully reached post-login screen!")
        print(f"  Page Title: '{page.title()}'")
        print(f"  Page URL:   '{page.url}'")
        print(f"\nBrowser window will remain open for {keep_open_seconds} seconds...")
        time.sleep(keep_open_seconds)

        browser.close()
        print("Browser session ended.")

if __name__ == "__main__":
    connect_to_sap()
