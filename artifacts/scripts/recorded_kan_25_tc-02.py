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
    page.locator("iframe[name=\"__container20-iframe\"]").content_frame.locator("iframe[name=\"thDialogIframe_1\"]").content_frame.locator("iframe[name=\"WorkAreaFrame1popup\"]").content_frame.get_by_text("CE-Direct Sales").click()
    page.locator("iframe[name=\"__container20-iframe\"]").content_frame.get_by_role("textbox", name="Description:").fill("RAR")
    page.locator("iframe[name=\"__container20-iframe\"]").content_frame.get_by_role("textbox", name="Description:").press("Tab")
    page.locator("iframe[name=\"__container20-iframe\"]").content_frame.get_by_role("textbox", name="Sold-To Party:").fill("101")
    page.locator("iframe[name=\"__container20-iframe\"]").content_frame.get_by_role("textbox", name="Sold-To Party:").press("Enter")
    page.locator("iframe[name=\"__container20-iframe\"]").content_frame.get_by_role("textbox", name="Ms. RAR01 FL").click()
    page.locator("iframe[name=\"__container20-iframe\"]").content_frame.get_by_role("option", name="Dates").click()
    page.locator("iframe[name=\"__container20-iframe\"]").content_frame.locator("#C16_W64_V65_DatesTable_bottom_div tr").filter(has_text="Term of Quotation").get_by_role("textbox").click()
    page.locator("iframe[name=\"__container20-iframe\"]").content_frame.locator("#C16_W64_V65_DatesTable_bottom_div tr").filter(has_text="Term of Quotation").get_by_role("textbox").fill("12")
    page.locator("iframe[name=\"__container20-iframe\"]").content_frame.get_by_role("option", name="Items").click()
    page.locator("iframe[name=\"__container20-iframe\"]").content_frame.locator("[id=\"C13_W49_V50_V54_btadmini_table\\[1\\]\\.ordered_prod\"]").click()
    page.locator("iframe[name=\"__container20-iframe\"]").content_frame.locator("[id=\"C13_W49_V50_V54_btadmini_table\\[1\\]\\.ordered_prod\"]").fill("45157510101")
    page.locator("iframe[name=\"__container20-iframe\"]").content_frame.locator("[id=\"C13_W49_V50_V54_btadmini_table\\[1\\]\\.ordered_prod\"]").press("Enter")
    page.locator("iframe[name=\"__container20-iframe\"]").content_frame.get_by_text("VELLYS SATELLITE STATION SKU1").click()
    page.locator("iframe[name=\"__container20-iframe\"]").content_frame.get_by_role("textbox", name="Quantity:", exact=True).click()
    page.locator("iframe[name=\"__container20-iframe\"]").content_frame.get_by_role("textbox", name="Quantity:", exact=True).fill("2")
    page.locator("iframe[name=\"__container20-iframe\"]").content_frame.get_by_role("textbox", name="ATP Plant:").click()
    page.locator("iframe[name=\"__container20-iframe\"]").content_frame.get_by_role("textbox", name="ATP Plant:").fill("BEV8")
    page.locator("iframe[name=\"__container20-iframe\"]").content_frame.get_by_role("textbox", name="ATP Plant:").press("Enter")
    page.locator("iframe[name=\"__container20-iframe\"]").content_frame.get_by_role("button", name="Back").click()
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
