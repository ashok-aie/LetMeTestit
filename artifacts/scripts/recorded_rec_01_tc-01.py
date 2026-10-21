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
    page.get_by_role("link", name="Manage Service Quotations Tile").click()
    page.locator("iframe[name=\"__container20-iframe\"]").content_frame.get_by_role("button", name="New Create (Ctrl+Enter)").click()
    page.locator("iframe[name=\"__container20-iframe\"]").content_frame.locator("iframe[name=\"thDialogIframe_1\"]").content_frame.locator("iframe[name=\"WorkAreaFrame1popup\"]").content_frame.get_by_text("ZQDS").click()
    page.locator("iframe[name=\"__container20-iframe\"]").content_frame.get_by_role("textbox", name="Description:").fill("RAR Test")
    page.locator("iframe[name=\"__container20-iframe\"]").content_frame.get_by_role("textbox", name="Sold-To Party:").click()
    page.locator("iframe[name=\"__container20-iframe\"]").content_frame.get_by_role("textbox", name="Sold-To Party:").fill("Brugmann Hospital")
    page.locator("iframe[name=\"__container20-iframe\"]").content_frame.get_by_role("textbox", name="Sold-To Party:").press("Enter")
    page.locator("iframe[name=\"__container20-iframe\"]").content_frame.get_by_role("button", name="Save (Ctrl+S)").click()
    page.get_by_role("button", name="Avatar").click()
    page.get_by_role("button", name="Sign Out").click()
    page.get_by_role("button", name="OK").click()
    page.close()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
