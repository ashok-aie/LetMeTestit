"""
Phase 3 Browser Integration Test: Playwright on SAP Fiori Demo App
Verifies real browser automation against the local SAP Material Order screen:
- Filling form using accessible test IDs
- Selecting material from dropdown
- Verifying order appears in the table with correct calculated amount
- Verifying validation error banner appears when form is invalid
"""
import threading
import time
import pytest
import uvicorn
from playwright.sync_api import sync_playwright, expect
from demo_app.main import app


class UvicornServerThread(threading.Thread):
    def __init__(self, host="127.0.0.1", port=8000):
        super().__init__(daemon=True)
        config = uvicorn.Config(app, host=host, port=port, log_level="warning")
        self.server = uvicorn.Server(config)

    def run(self):
        self.server.run()

    def stop(self):
        self.server.should_exit = True


@pytest.fixture(scope="module")
def live_server():
    """Starts local FastAPI SAP Demo server on 127.0.0.1:8000 in background if not already active."""
    import urllib.request
    already_active = False
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/", timeout=1) as resp:
            if resp.status == 200:
                already_active = True
    except Exception:
        pass

    if already_active:
        yield "http://127.0.0.1:8000"
        return

    server_thread = UvicornServerThread(port=8000)
    server_thread.start()
    time.sleep(0.5)  # Allow server to bind
    yield "http://127.0.0.1:8000"
    server_thread.stop()


@pytest.mark.browser
def test_sap_create_order_via_playwright(live_server):
    """Automates end-to-end order creation in Chromium and verifies table DOM update."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        page = context.new_page()

        # 1. Navigate to SAP Fiori screen
        page.goto(f"{live_server}/")
        expect(page).to_have_title("SAP S/4HANA — Manage Sales & Material Orders")

        # 2. Reset database to clean seed
        page.get_by_test_id("reset-db-button").click()
        expect(page.get_by_test_id("success-banner")).to_be_visible()

        # 3. Fill Sales Order Form using accessible test IDs
        page.get_by_test_id("customer-id-input").fill("CUST-5555")
        page.get_by_test_id("customer-name-input").fill("Apex Machining Solutions")
        page.get_by_test_id("material-select").select_option("MAT-1001")
        page.get_by_test_id("quantity-input").fill("3")
        page.get_by_test_id("priority-select").select_option("Urgent")

        # 4. Submit Order
        page.get_by_test_id("submit-order-button").click()

        # 5. Deterministic Assertions
        # Success banner should be visible
        success_banner = page.get_by_test_id("success-banner")
        expect(success_banner).to_be_visible()
        expect(success_banner).to_contain_text("created successfully for CUST-5555")

        # Orders table should contain new order with calculated total (3 * 450 = 1350.00)
        orders_table = page.get_by_test_id("orders-table")
        expect(orders_table).to_contain_text("CUST-5555")
        expect(orders_table).to_contain_text("Apex Machining Solutions")
        expect(orders_table).to_contain_text("$1350.00")
        expect(orders_table).to_contain_text("Submitted")

        context.close()
        browser.close()


@pytest.mark.browser
def test_sap_validation_error_via_playwright(live_server):
    """Verifies that submitting with missing customer triggers SAP error banner."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(f"{live_server}/")

        # Submit without customer ID (bypass HTML5 required attribute to test server validation)
        page.evaluate("document.getElementById('customer_id').removeAttribute('required')")
        page.get_by_test_id("material-select").select_option("MAT-1001")
        page.get_by_test_id("quantity-input").fill("2")
        page.get_by_test_id("submit-order-button").click()

        # Assert Error Banner displays
        error_banner = page.get_by_test_id("error-banner")
        expect(error_banner).to_be_visible()
        expect(error_banner).to_contain_text("Customer ID (Sold-to Party) is mandatory")

        browser.close()

