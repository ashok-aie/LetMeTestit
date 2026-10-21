import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()
    page.goto("https://s4srv25.nodomain.com:44325/sap/bc/ui2/flp?sap-client=100&sap-language=EN#Launchpad-openFLPPage?pageId=SAP_CRM_PG_SERVICE_PROCESSING&spaceId=SAP_CRM_SP_SERVICE")
    page.get_by_role("textbox", name="User").fill("MYRAR1")
    page.get_by_role("textbox", name="User").press("Tab")
    page.get_by_role("textbox", name="Password").fill("Pass23#$")
    page.get_by_role("button", name="Log On").click()
    page.get_by_role("button", name="Open Search").click()
    page.get_by_role("searchbox", name="Search").fill("Manage Revenue Contracts")
    page.get_by_role("searchbox", name="Search").press("Enter")
    page.get_by_label("Manage Revenue Contracts Tile").click()
    page.locator("[id=\"fin\\.rar\\.manage\\.contract\\:\\:sap\\.suite\\.ui\\.generic\\.template\\.ListReport\\.view\\.ListReport\\:\\:C_RAContrWithPostedBalanceTP--listReportFilter-filterItemControl_BASIC-RevenueAccountingContract-vhi\"]").click()
    page.get_by_role("textbox", name="Operational Document:").click()
    page.get_by_role("textbox", name="Operational Document:").fill("962")
    page.get_by_role("textbox", name="Operational Document:").press("Enter")
    page.get_by_label("Selection column").click()
    page.get_by_role("dialog", name="Revenue Contract").get_by_label("Go").click()
    page.get_by_role("button", name="OK").click()
    page.get_by_role("button", name="Go").click()
    page.locator("[id=\"__identifier0-__clone165\"] div").first.click()
    page.get_by_role("button", name="Avatar").click()
    page.get_by_role("button", name="Sign Out").click()
    page.get_by_role("button", name="OK").click()
    page.close()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
