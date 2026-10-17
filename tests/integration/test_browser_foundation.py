"""
Phase 4 Integration Test: Browser Automation Foundation
Verifies BrowserContextManager, LocatorResolver uniqueness checks,
screenshot captures, and Playwright trace.zip generation.
"""
import threading
import time
import pytest
import uvicorn
from pathlib import Path

from demo_app.main import app
from app.browser.context import BrowserContextManager
from app.browser.evidence import EvidenceManager
from app.browser.locators import ElementNotFoundError, AmbiguousLocatorError


class UvicornServerThread(threading.Thread):
    def __init__(self, host="127.0.0.1", port=8001):
        super().__init__(daemon=True)
        config = uvicorn.Config(app, host=host, port=port, log_level="warning")
        self.server = uvicorn.Server(config)

    def run(self):
        self.server.run()

    def stop(self):
        self.server.should_exit = True


@pytest.fixture(scope="module")
def sap_server():
    server = UvicornServerThread(port=8001)
    server.start()
    time.sleep(0.5)
    yield "http://127.0.0.1:8001"
    server.stop()


def test_browser_context_lifecycle_and_evidence(sap_server, tmp_path):
    """Verify clean startup, accessible locator resolution, screenshot and trace generation."""
    evidence = EvidenceManager(run_id="test_run_phase4")
    # Clean any prior artifacts for this test id
    evidence.cleanup_run()

    with BrowserContextManager(headless=True, evidence_manager=evidence, enable_tracing=True) as bcm:
        page = bcm.page
        page.goto(f"{sap_server}/")

        # 1. Resolve unique accessible elements
        btn = bcm.locators.resolve_unique("role", "Submit Sales Order", role_type="button")
        assert btn.is_visible()

        input_field = bcm.locators.resolve_unique("test_id", "customer-id-input")
        assert input_field.is_visible()

        # 2. Capture screenshot
        screenshot_path = bcm.capture_screenshot("TC_SAP_01")
        assert screenshot_path.exists()
        assert screenshot_path.stat().st_size > 0

    # 3. Post-exit checks: trace.zip must be successfully generated
    trace_path = evidence.trace_file_path
    assert trace_path.exists(), f"Trace file {trace_path} was not generated."
    assert trace_path.stat().st_size > 0, "Trace file is empty."

    # Cleanup test run
    evidence.cleanup_run()


def test_locator_ambiguity_detection(sap_server):
    """Verify that LocatorResolver raises AmbiguousLocatorError when a selector matches multiple elements."""
    with BrowserContextManager(headless=True, enable_tracing=False) as bcm:
        bcm.page.goto(f"{sap_server}/")
        
        # 'input' matches multiple form fields on the SAP screen
        with pytest.raises(AmbiguousLocatorError) as exc_info:
            bcm.locators.resolve_unique("css", "input")
        
        assert "Ambiguous locator" in str(exc_info.value)


def test_locator_not_found_detection(sap_server):
    """Verify that LocatorResolver raises ElementNotFoundError when an element doesn't exist."""
    with BrowserContextManager(headless=True, enable_tracing=False) as bcm:
        bcm.page.goto(f"{sap_server}/")
        
        with pytest.raises(ElementNotFoundError) as exc_info:
            bcm.locators.resolve_unique("test_id", "non-existent-sap-element", timeout_ms=500)
        
        assert "Element not found" in str(exc_info.value)

