"""
Playwright Browser Context Lifecycle Manager
Safely manages Chromium browser contexts, viewport settings, tracing, and clean teardown.
"""
from typing import Optional
from pathlib import Path
from playwright.sync_api import sync_playwright, Playwright, Browser, BrowserContext, Page

from app.config import settings
from app.browser.evidence import EvidenceManager
from app.browser.locators import LocatorResolver


class BrowserContextManager:
    """
    Context manager that guarantees clean startup, tracing, screenshot capture on failure,
    and deterministic shutdown of Playwright Chromium instances.
    """

    def __init__(
        self,
        headless: Optional[bool] = None,
        slow_mo_ms: Optional[int] = None,
        evidence_manager: Optional[EvidenceManager] = None,
        enable_tracing: bool = True,
        cdp_url: Optional[str] = None,
    ):
        self.headless = settings.browser_headless if headless is None else headless
        self.cdp_url = cdp_url or settings.cdp_endpoint_url
        if slow_mo_ms is not None:
            self.slow_mo_ms = slow_mo_ms
        elif not self.headless:
            self.slow_mo_ms = max(settings.browser_slow_mo_ms, 500)
        else:
            self.slow_mo_ms = settings.browser_slow_mo_ms

        self.evidence_manager = evidence_manager or EvidenceManager()
        self.enable_tracing = enable_tracing

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._locator_resolver: Optional[LocatorResolver] = None

    def __enter__(self) -> "BrowserContextManager":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            # Capture failure screenshot if an error occurred while page was active
            self.capture_failure_screenshot("error_state")
        self.stop()
        # Do not suppress the exception
        return False

    def start(self) -> None:
        """Launches Chromium or connects to a remote Chrome instance via CDP."""
        self._playwright = sync_playwright().start()

        if self.cdp_url:
            self._browser = self._playwright.chromium.connect_over_cdp(self.cdp_url)
            if self._browser.contexts:
                self._context = self._browser.contexts[0]
            else:
                self._context = self._browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    ignore_https_errors=True,
                )
            if self.enable_tracing:
                try:
                    self._context.tracing.start(screenshots=True, snapshots=True, sources=True)
                except Exception:
                    pass
            if self._context.pages:
                self._page = self._context.pages[0]
            else:
                self._page = self._context.new_page()
            self._page.set_default_timeout(settings.browser_step_timeout_ms)
            self._locator_resolver = LocatorResolver(self._page)
            return

        launch_args = [
            "--ignore-certificate-errors",
            f"--host-resolver-rules=MAP {settings.sap_host_domain} {settings.sap_host_ip}",
        ]
        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            slow_mo=self.slow_mo_ms,
            args=launch_args,
        )
        self._context = self._browser.new_context(
            viewport={"width": 1280, "height": 720},
            ignore_https_errors=True,
        )

        if self.enable_tracing:
            self._context.tracing.start(
                screenshots=True,
                snapshots=True,
                sources=True,
            )

        self._page = self._context.new_page()
        self._page.set_default_timeout(settings.browser_step_timeout_ms)
        self._locator_resolver = LocatorResolver(self._page)

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("BrowserContextManager has not been started.")
        return self._page

    @property
    def locators(self) -> LocatorResolver:
        if self._locator_resolver is None:
            raise RuntimeError("BrowserContextManager has not been started.")
        return self._locator_resolver

    def capture_screenshot(self, test_case_id: str, step_number: Optional[int] = None) -> Path:
        """Captures a full-page screenshot and saves it to the evidence directory."""
        if self._page is None:
            raise RuntimeError("Page is not active.")
        path = self.evidence_manager.get_screenshot_path(test_case_id, step_number)
        self._page.screenshot(path=str(path), full_page=True)
        return path

    def capture_failure_screenshot(self, test_case_id: str) -> Optional[Path]:
        """Safely captures a screenshot upon failure without raising secondary exceptions."""
        try:
            if self._page and not self._page.is_closed():
                return self.capture_screenshot(test_case_id)
        except Exception:
            pass
        return None

    def stop(self) -> None:
        """Stops tracing, exports trace archive, and closes the browser context."""
        try:
            if self._context and self.enable_tracing:
                trace_path = self.evidence_manager.trace_file_path
                self._context.tracing.stop(path=str(trace_path))
        except Exception:
            pass

        try:
            if self._context:
                self._context.close()
        except Exception:
            pass

        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass

        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass

