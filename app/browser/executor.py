"""
Playwright Test Execution Engine
Executes approved TestSuite models against target web application with deterministic assertions,
duration metrics, evidence capture (traces/screenshots), and failure classification.
"""
import logging
import time
from typing import Optional, List
from uuid import uuid4
from datetime import datetime, timezone

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app.config import settings
from app.browser.context import BrowserContextManager
from app.browser.evidence import EvidenceManager
from app.browser.locators import ElementNotFoundError, AmbiguousLocatorError
from app.models.test_suite import TestSuite, TestCase, TestStep, ActionType, TestCategory
from app.models.execution import (
    ExecutionRun,
    TestCaseResult,
    TestStepResult,
    TestOutcome,
    FailureClassification,
)

try:
    from langfuse import observe
except ImportError:
    def observe(*args, **kwargs):
        def decorator(f):
            return f
        return decorator

logger = logging.getLogger(__name__)


class TestExecutionError(Exception):
    """Base exception for test execution failures."""
    pass


class TestExecutor:
    """
    Executes declarative Pydantic test suites using Playwright.
    Supports both headed (visual on-screen) and headless (background) execution modes.
    """
    __test__ = False

    def __init__(
        self,
        headless: Optional[bool] = None,
        slow_mo_ms: Optional[int] = None,
        evidence_manager: Optional[EvidenceManager] = None,
        capture_all_screenshots: bool = True,
        cdp_url: Optional[str] = None,
    ):
        self.headless = settings.browser_headless if headless is None else headless
        self.slow_mo_ms = slow_mo_ms
        self.evidence_manager = evidence_manager or EvidenceManager()
        self.capture_all_screenshots = capture_all_screenshots
        self.cdp_url = cdp_url or settings.cdp_endpoint_url

    @observe(name="TestExecutor.execute_suite")
    def execute_suite(
        self,
        suite: TestSuite,
        target_url: Optional[str] = None,
        step_callback=None,
    ) -> ExecutionRun:
        """
        Executes all test cases in the test suite sequentially.
        
        Args:
            suite: Cryptographically approved TestSuite model.
            target_url: Target application base URL.
            step_callback: Optional callback(test_case, step, step_result_or_none) for live UI reporting.
            
        Returns:
            ExecutionRun model with detailed step results, outcomes, and evidence paths.
        """
        app_url = target_url or settings.target_base_url
        run_id = f"RUN-{uuid4().hex[:8].upper()}"

        run = ExecutionRun(
            run_id=run_id,
            suite_id=suite.suite_id,
            target_url=app_url,
            total_tests=len(suite.test_cases),
            started_at=datetime.now(timezone.utc),
        )

        with BrowserContextManager(
            headless=self.headless,
            slow_mo_ms=self.slow_mo_ms,
            evidence_manager=self.evidence_manager,
            enable_tracing=True,
            cdp_url=self.cdp_url,
        ) as browser_ctx:
            page = browser_ctx.page
            locators = browser_ctx.locators

            for tc in suite.test_cases:
                tc_result = self._execute_test_case(tc, page, locators, browser_ctx, step_callback=step_callback)
                run.results.append(tc_result)

        # Finalize execution statistics
        run.passed_tests = sum(1 for r in run.results if r.outcome == TestOutcome.PASS)
        run.failed_tests = sum(1 for r in run.results if r.outcome == TestOutcome.FAIL)
        run.blocked_tests = sum(1 for r in run.results if r.outcome == TestOutcome.BLOCKED)
        run.error_tests = sum(1 for r in run.results if r.outcome == TestOutcome.ERROR)
        run.finished_at = datetime.now(timezone.utc)
        run.trace_path = str(self.evidence_manager.trace_file_path)

        return run

    def _execute_test_case(
        self,
        tc: TestCase,
        page,
        locators,
        browser_ctx: BrowserContextManager,
        step_callback=None,
    ) -> TestCaseResult:
        """Executes a single TestCase step-by-step."""
        start_time = time.perf_counter()
        step_results: List[TestStepResult] = []
        failure_msg: Optional[str] = None
        screenshot_path: Optional[str] = None
        outcome = TestOutcome.PASS
        classification = FailureClassification.NONE

        for step in tc.steps:
            if step_callback:
                try:
                    step_callback(tc, step, None)
                except Exception:
                    pass

            t0 = time.perf_counter()
            step_res = None
            try:
                self._dispatch_step(step, page, locators, test_case=tc)
                duration_ms = (time.perf_counter() - t0) * 1000

                # Capture step evidence screenshot
                step_shot = None
                if self.capture_all_screenshots:
                    try:
                        shot = browser_ctx.capture_screenshot(tc.id, step.step_number)
                        step_shot = str(shot.resolve())
                    except Exception as shot_err:
                        logger.warning("Could not capture step screenshot: %s", shot_err)

                step_res = TestStepResult(
                    step_number=step.step_number,
                    action=step.action,
                    duration_ms=round(duration_ms, 2),
                    passed=True,
                    screenshot_path=step_shot,
                )
                step_results.append(step_res)
                if step_callback:
                    try:
                        step_callback(tc, step, step_res)
                    except Exception:
                        pass
            except Exception as exc:
                duration_ms = (time.perf_counter() - t0) * 1000
                failure_msg = f"Step {step.step_number} ({step.action.value}) failed: {exc}"
                logger.error("Test case %s failed at step %d: %s", tc.id, step.step_number, exc)

                # Capture failure evidence screenshot
                try:
                    shot = browser_ctx.capture_screenshot(tc.id, step.step_number)
                    screenshot_path = str(shot.resolve())
                except Exception as shot_err:
                    logger.warning("Could not capture screenshot for %s: %s", tc.id, shot_err)

                # Classify the failure
                if isinstance(exc, (ElementNotFoundError, AmbiguousLocatorError)):
                    classification = FailureClassification.LOCATOR_ERROR
                    outcome = TestOutcome.FAIL
                elif isinstance(exc, PlaywrightTimeoutError):
                    classification = FailureClassification.TIMEOUT_ERROR
                    outcome = TestOutcome.FAIL
                elif isinstance(exc, AssertionError):
                    classification = FailureClassification.APPLICATION_DEFECT
                    outcome = TestOutcome.FAIL
                else:
                    classification = FailureClassification.APPLICATION_DEFECT
                    outcome = TestOutcome.FAIL

                step_res = TestStepResult(
                    step_number=step.step_number,
                    action=step.action,
                    duration_ms=round(duration_ms, 2),
                    passed=False,
                    error_message=str(exc),
                    screenshot_path=screenshot_path,
                )
                step_results.append(step_res)
                if step_callback:
                    try:
                        step_callback(tc, step, step_res)
                    except Exception:
                        pass
                break  # Stop execution of remaining steps in this test case

        duration_seconds = round(time.perf_counter() - start_time, 2)
        # If no explicit failure screenshot was captured, use the last step screenshot if available
        if not screenshot_path and step_results and step_results[-1].screenshot_path:
            screenshot_path = step_results[-1].screenshot_path

        return TestCaseResult(
            test_case_id=tc.id,
            outcome=outcome,
            classification=classification,
            duration_seconds=duration_seconds,
            step_results=step_results,
            failure_message=failure_msg,
            screenshot_path=screenshot_path,
        )

    def _dispatch_step(self, step: TestStep, page, locators, test_case: Optional[TestCase] = None) -> None:
        """Dispatches a single declarative TestStep to Playwright."""
        strategy = step.locator_strategy.value if step.locator_strategy else "test_id"
        selector = step.selector_value or ""
        role_type = step.role_name

        # Guard: In positive scenarios, verify that an application error banner is not displayed
        if test_case and test_case.category == TestCategory.POSITIVE and step.action in (ActionType.ASSERT_TEXT, ActionType.ASSERT_ELEMENT_STATE, ActionType.WAIT_FOR):
            try:
                err_banner = page.locator("[data-testid='error-banner'], #error-banner, .sap-banner-error")
                if err_banner.count() > 0 and err_banner.first.is_visible():
                    err_text = err_banner.first.inner_text().strip()
                    raise AssertionError(f"Unexpected application error banner displayed during positive test '{test_case.id}': '{err_text}'")
            except AssertionError:
                raise
            except Exception:
                pass

        if step.action == ActionType.NAVIGATE:
            url = step.input_value or settings.target_base_url
            page.goto(url, wait_until="networkidle")

            # Automated SAP S/4HANA Fiori Logon Handler
            try:
                sap_user_loc = page.locator("#USERNAME_FIELD-inner")
                if sap_user_loc.count() > 0 and sap_user_loc.first.is_visible():
                    sap_user = getattr(settings, "sap_username", "") or ""
                    sap_pwd = getattr(settings, "sap_password", "") or ""
                    if sap_user and sap_pwd:
                        logger.info("SAP Fiori Logon screen detected; automatically submitting SAP credentials...")
                        sap_user_loc.first.fill(sap_user)
                        sap_pwd_loc = page.locator("#PASSWORD_FIELD-inner")
                        if sap_pwd_loc.count() > 0:
                            sap_pwd_loc.first.fill(sap_pwd)
                        sap_login_btn = page.locator("#LOGIN_LINK")
                        if sap_login_btn.count() > 0:
                            sap_login_btn.first.click()
                            page.wait_for_load_state("networkidle", timeout=15000)
            except Exception as auto_login_err:
                logger.warning("Automated SAP logon encountered: %s", auto_login_err)

        elif step.action == ActionType.CLICK:
            elem = locators.resolve(strategy=strategy, value=selector, role_type=role_type)
            elem.click()

            # Wait for network / DOM update after click
            try:
                page.wait_for_load_state("networkidle", timeout=2000)
            except Exception:
                pass

            # If clicking submitted a form in a positive flow, check if an error banner was immediately returned
            if test_case and test_case.category == TestCategory.POSITIVE:
                try:
                    err_banner = page.locator("[data-testid='error-banner'], #error-banner, .sap-banner-error")
                    if err_banner.count() > 0 and err_banner.first.is_visible():
                        err_text = err_banner.first.inner_text().strip()
                        raise AssertionError(f"Form submission failed with application error banner: '{err_text}'")
                except AssertionError:
                    raise
                except Exception:
                    pass

            # If clicking submitted a form in a negative flow, check if form unexpectedly succeeded
            if test_case and test_case.category == TestCategory.NEGATIVE and "submit" in selector.lower():
                try:
                    succ_banner = page.locator("[data-testid='success-banner'], #success-banner, .sap-banner-success")
                    if succ_banner.count() > 0 and succ_banner.first.is_visible():
                        succ_text = succ_banner.first.inner_text().strip()
                        raise AssertionError(f"Negative test failed: form unexpectedly succeeded ('{succ_text}') instead of displaying validation error.")
                except AssertionError:
                    raise
                except Exception:
                    pass

        elif step.action == ActionType.FILL:
            elem = locators.resolve(strategy=strategy, value=selector, role_type=role_type)
            elem.fill(step.input_value or "")

        elif step.action == ActionType.SELECT_OPTION:
            elem = locators.resolve(strategy=strategy, value=selector, role_type=role_type)
            val = (step.input_value or "").strip()
            # 1. Try direct value match
            try:
                elem.select_option(value=val, timeout=2000)
            except Exception:
                # 2. Try direct label match
                try:
                    elem.select_option(label=val, timeout=2000)
                except Exception:
                    # 3. Substring / case-insensitive fuzzy match across available options
                    matched = False
                    try:
                        options = elem.locator("option").all()
                        for opt in options:
                            opt_text = opt.inner_text().strip().lower()
                            opt_val = (opt.get_attribute("value") or "").strip().lower()
                            if val.lower() in opt_text or val.lower() in opt_val:
                                opt_val_actual = opt.get_attribute("value")
                                elem.select_option(value=opt_val_actual)
                                matched = True
                                break
                    except Exception:
                        pass
                    if not matched:
                        # Fallback to standard Playwright exception
                        elem.select_option(label=val)

        elif step.action == ActionType.WAIT_FOR:
            elem = locators.resolve(strategy=strategy, value=selector, role_type=role_type)
            elem.first.wait_for(state="visible", timeout=settings.browser_step_timeout_ms)

        elif step.action == ActionType.ASSERT_TEXT:
            if test_case and test_case.category == TestCategory.NEGATIVE and "error" in selector.lower():
                try:
                    succ_banner = page.locator("[data-testid='success-banner'], #success-banner, .sap-banner-success")
                    if succ_banner.count() > 0 and succ_banner.first.is_visible():
                        succ_text = succ_banner.first.inner_text().strip()
                        raise AssertionError(f"Negative scenario failed: Form unexpectedly succeeded ('{succ_text}') instead of displaying error banner.")
                except AssertionError:
                    raise
                except Exception:
                    pass

            elem = locators.resolve(strategy=strategy, value=selector, role_type=role_type)
            expected = (step.expected_value or "").strip()
            # Bounded wait for element to become visible if it is an alert or banner
            try:
                elem.first.wait_for(state="visible", timeout=3000)
            except Exception:
                pass

            # Handle multiple matching elements (e.g. repeated table cells) without throwing strict mode violation
            count = elem.count()
            if count > 1:
                texts = [elem.nth(i).inner_text().strip() for i in range(count)]
                if not any(expected.lower() in t.lower() for t in texts):
                    raise AssertionError(
                        f"Text assertion failed on '{selector}' (matched {count} elements). "
                        f"Expected '{expected}' not found in any matching element: {texts}"
                    )
            else:
                actual_text = elem.inner_text().strip()
                if expected.lower() not in actual_text.lower():
                    raise AssertionError(
                        f"Text assertion failed on '{selector}'. Expected '{expected}' to be contained in '{actual_text}'."
                    )

        elif step.action == ActionType.ASSERT_URL:
            expected = step.expected_value or ""
            actual_url = page.url
            if expected not in actual_url:
                raise AssertionError(
                    f"URL assertion failed. Expected URL to contain '{expected}', but was '{actual_url}'."
                )

        elif step.action == ActionType.ASSERT_ELEMENT_STATE:
            elem = locators.resolve(strategy=strategy, value=selector, role_type=role_type)
            if not elem.first.is_visible():
                raise AssertionError(f"Element state assertion failed: '{selector}' is not visible.")

        else:
            raise ValueError(f"Unsupported action type: {step.action}")

