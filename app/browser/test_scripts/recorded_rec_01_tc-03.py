import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()
    page.goto("https://s4srv25.nodomain.com:44325/sap/bc/ui2/flp?sap-client=100&sap-language=EN#Launchpad-openFLPPage?pageId=SAP_CRM_PG_SERVICE_PROCESSING&spaceId=SAP_CRM_SP_SERVICE")
    page.get_by_role("textbox", name="User").fill("MYRAR1")
    page.get_by_role("textbox", name="Password").click()
    page.get_by_role("textbox", name="Password").fill("Pass23#$")
    page.get_by_role("button", name="Log On").click()
    page.goto("https://s4srv25.nodomain.com:44325/sap/bc/ui2/flp?sap-client=100&sap-language=EN#BillingDocument-createBillingDocuments?sap-ui-tech-hint=GUI")
    page.locator("iframe[name=\"__container36-iframe\"]").content_frame.get_by_role("grid", name="Documents to Be Processed").locator("input[name=\"InputField\"]").fill("80000542")
    page.locator("iframe[name=\"__container36-iframe\"]").content_frame.get_by_role("grid", name="Documents to Be Processed").locator("input[name=\"InputField\"]").press("Enter")
    page.get_by_role("button", name="Back").click()
    page.locator("iframe[name=\"__container36-iframe\"]").content_frame.get_by_role("button", name="Save  Emphasized").click()
    page.close()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
