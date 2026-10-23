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
    page.goto("https://s4srv25.nodomain.com:44325/sap/bc/ui2/flp?sap-client=100&sap-language=EN#OutboundDelivery-createInWebGUI?sap-ui-tech-hint=GUI")
    page.locator("iframe[name=\"__container36-iframe\"]").content_frame.get_by_role("textbox", name="Shipping Point Required").click()
    page.locator("iframe[name=\"__container36-iframe\"]").content_frame.get_by_role("textbox", name="Shipping Point Required").fill("BEV8")
    page.locator("iframe[name=\"__container36-iframe\"]").content_frame.get_by_role("textbox", name="Order Required").click()
    page.locator("iframe[name=\"__container36-iframe\"]").content_frame.get_by_role("textbox", name="Order Required").fill("1023")
    page.locator("iframe[name=\"__container36-iframe\"]").content_frame.get_by_role("textbox", name="Order Required").press("Enter")
    page.locator("iframe[name=\"__container36-iframe\"]").content_frame.get_by_role("textbox", name="Shipping Point Required").click()
    page.locator("iframe[name=\"__container36-iframe\"]").content_frame.get_by_role("textbox", name="Shipping Point Required").press("Enter")
    page.locator("iframe[name=\"__container36-iframe\"]").content_frame.get_by_role("gridcell", name="1023", exact=True).get_by_role("textbox").click()
    page.get_by_role("button", name="Back").click()
    page.get_by_role("button", name="Back").click()
    page.locator("iframe[name=\"__container36-iframe\"]").content_frame.get_by_role("textbox", name="Order Required").click()
    page.locator("iframe[name=\"__container36-iframe\"]").content_frame.get_by_role("textbox", name="Order Required").fill("1022")
    page.locator("iframe[name=\"__container36-iframe\"]").content_frame.get_by_role("textbox", name="Order Required").press("Enter")
    page.locator("iframe[name=\"__container36-iframe\"]").content_frame.get_by_role("tab", name="Picking").locator("span").click()
    page.locator("iframe[name=\"__container36-iframe\"]").content_frame.locator("[id=\"M0\\:46\\:2\\:3B257\\:2\\[1\\,4\\]_c\"]").click()
    page.locator("iframe[name=\"__container36-iframe\"]").content_frame.get_by_label("All Items").locator("tbody").filter(has_text="BEV81EAEAA22.10.202617:46:").locator("input[name=\"InputField\"]").fill("6020")
    page.locator("iframe[name=\"__container36-iframe\"]").content_frame.locator("[id=\"M0\\:46\\:2\\:3B257\\:2\\[1\\,8\\]_c\"]").click()
    page.locator("iframe[name=\"__container36-iframe\"]").content_frame.get_by_role("grid", name="All Items").locator("input[name=\"InputField\"]").nth(2).fill("1")
    page.locator("iframe[name=\"__container36-iframe\"]").content_frame.get_by_role("button", name="Post Goods Issue").click()
    page.locator("iframe[name=\"__container36-iframe\"]").content_frame.get_by_text("Outbound Delivery 80000542 saved, material document 4900000927 created", exact=True).click(button="right")
    page.locator("iframe[name=\"__container36-iframe\"]").content_frame.get_by_text("Outbound Delivery 80000542 saved, material document 4900000927 createdContinue").click()
    page.close()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
