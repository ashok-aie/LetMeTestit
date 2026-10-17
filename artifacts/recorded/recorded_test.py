import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("http://127.0.0.1:8000/")
    page.get_by_test_id("customer-id-input").click()
    page.get_by_test_id("customer-id-input").fill("abcd-200")
    page.get_by_test_id("customer-name-input").click()
    page.get_by_test_id("customer-name-input").fill("adfas")
    page.get_by_test_id("material-select").select_option("MAT-2002")
    page.get_by_test_id("quantity-input").click()
    page.get_by_test_id("quantity-input").fill("5")
    page.get_by_test_id("priority-select").select_option("Urgent")
    page.get_by_test_id("submit-order-button").click()
    page.close()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
