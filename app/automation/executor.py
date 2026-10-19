"""
Playwright Test Execution Engine
Executes approved TestSuite models against target web application with deterministic assertions,
duration metrics, evidence capture (traces/screenshots), and failure classification.
"""
import logging
import re
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
        test_cases: Optional[List[TestCase]] = None,
    ) -> ExecutionRun:
        """
        Executes test cases in the test suite sequentially.
        
        Args:
            suite: Cryptographically approved TestSuite model.
            target_url: Target application base URL.
            step_callback: Optional callback(test_case, step, step_result_or_none) for live UI reporting.
            test_cases: Optional specific subset and order of TestCases to execute. If omitted, executes all suite.test_cases.
            
        Returns:
            ExecutionRun model with detailed step results, outcomes, and evidence paths.
        """
        app_url = target_url or settings.target_base_url
        run_id = f"RUN-{uuid4().hex[:8].upper()}"
        cases_to_run = test_cases if test_cases is not None else suite.test_cases

        run = ExecutionRun(
            run_id=run_id,
            suite_id=suite.suite_id,
            target_url=app_url,
            total_tests=len(cases_to_run),
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

            for tc in cases_to_run:
                tc_result = self._execute_test_case(tc, page, locators, browser_ctx, step_callback=step_callback)
                run.results.append(tc_result)

        # Finalize execution statistics
        run.passed_tests = sum(1 for r in run.results if r.outcome == TestOutcome.PASS)
        run.failed_tests = sum(1 for r in run.results if r.outcome == TestOutcome.FAIL)
        run.blocked_tests = sum(1 for r in run.results if r.outcome == TestOutcome.BLOCKED)
        run.error_tests = sum(1 for r in run.results if r.outcome == TestOutcome.ERROR)
        run.finished_at = datetime.now(timezone.utc)
        run.trace_path = str(self.evidence_manager.trace_file_path)

        # Persist execution run summary for regression trends & audit
        try:
            from app.storage.repository import save_execution_run_record
            save_execution_run_record(run)
        except Exception as e:
            logger.warning("Could not persist execution run record: %s", e)

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

                # Continuous Learning: Record verified selector into catalog upon step success
                if step.selector_value:
                    try:
                        from app.storage.repository import save_learned_selector
                        save_learned_selector(
                            element_label=step.description or step.selector_value,
                            selector=step.selector_value,
                            strategy=step.locator_strategy.value if step.locator_strategy else "css",
                            action=step.action.value,
                            role_type=step.role_name,
                            app_domain="SAP S/4HANA",
                        )
                    except Exception as learn_err:
                        logger.debug("Learning selector skipped: %s", learn_err)

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
            page.goto(url, wait_until="domcontentloaded")
            try:
                page.wait_for_selector("#USERNAME_FIELD-inner", timeout=15000)
                time.sleep(1)
            except Exception:
                try:
                    page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass

        elif step.action == ActionType.CLICK:
            elem = locators.resolve(strategy=strategy, value=selector, role_type=role_type)
            try:
                elem.first.click(timeout=4000)
            except Exception:
                fallback_elem = None
                if any(k in selector for k in ("meAreaHeaderButton", "userActionsMenuHeaderButton")):
                    fallback_elem = page.locator(
                        "#userActionsMenuHeaderButton, #meAreaHeaderButton, "
                        "[id*='userActionsMenuHeaderButton'], [id*='meAreaHeaderButton'], "
                        ".sapUshellShellHeadItm[title*='User'], button[aria-label*='User Settings'], "
                        "button[title*='User Actions'], [data-sap-ui*='userActions']"
                    )
                elif "sign out" in selector.lower() or "logout" in selector.lower():
                    fallback_elem = page.locator(
                        "button:has-text('Sign Out'), #logoutBtn, [id*='logout'], "
                        "div[role='button']:has-text('Sign Out'), span:has-text('Sign Out'), "
                        "[aria-label*='Sign Out'], text='Sign Out'"
                    )

                target_elem = fallback_elem if (fallback_elem and fallback_elem.count() > 0) else elem
                try:
                    target_elem.first.click(force=True, timeout=4000)
                except Exception:
                    target_elem.first.dispatch_event("click")

            # Wait for network / DOM update after click
            try:
                page.wait_for_load_state("networkidle", timeout=3000)
            except Exception:
                pass

            # Handle SAP multiple logon warning dialog if present
            if "#LOGIN_LINK" in selector or "log on" in selector.lower() or "login" in selector.lower():
                try:
                    multi_logon = page.locator("button:has-text('Continue'), input[value*='Continue'], #LOGON_CONTINUE_BUTTON")
                    if multi_logon.count() > 0 and multi_logon.first.is_visible():
                        logger.info("Detected SAP multiple logon dialog; acknowledging...")
                        multi_logon.first.click()
                        page.wait_for_load_state("networkidle", timeout=5000)
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
            val = (step.input_value or "")
            if any(k in selector.lower() for k in ["username", "password", "user", "pwd"]):
                val = val.strip()
            elem.click()
            elem.fill("")
            if any(k in selector.lower() for k in ["username", "password", "user", "pwd"]):
                elem.press_sequentially(val, delay=100)
                time.sleep(0.5)
            else:
                elem.fill(val)

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
            # Check for duration-based wait (e.g. "20s", "20 sec", "20", "20000")
            wait_target = (step.input_value or step.selector_value or "").strip()
            match = re.search(r"^(\d+(?:\.\d+)?)\s*(s|sec|seconds|ms)?$", wait_target, re.IGNORECASE)
            if match:
                val, unit = match.groups()
                val_float = float(val)
                wait_ms = val_float if (unit and unit.lower() == "ms") or val_float >= 1000 else val_float * 1000
                logger.info("Executing timed wait_for: %0.1f ms", wait_ms)
                page.wait_for_timeout(wait_ms)
            elif selector:
                elem = locators.resolve(strategy=strategy, value=selector, role_type=role_type)
                elem.first.wait_for(state="visible", timeout=settings.browser_step_timeout_ms)
            else:
                page.wait_for_timeout(5000)

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

            timeout_sec = max(settings.browser_step_timeout_ms / 1000.0, 10.0)
            poll_start = time.perf_counter()
            matched = False
            last_text = ""

            while time.perf_counter() - poll_start < timeout_sec:
                try:
                    count = elem.count()
                    if count > 1:
                        texts = [elem.nth(i).inner_text().strip() for i in range(count)]
                        if any(expected.lower() in t.lower() for t in texts):
                            matched = True
                            break
                        if expected.lower() in ("logged off", "signed out", "log off"):
                            if any(any(k in t.lower() for k in ["logged off", "signed out", "log off", "goodbye"]) for t in texts):
                                matched = True
                                break
                        last_text = str(texts)
                    elif count == 1:
                        last_text = elem.first.inner_text().strip()
                        if expected.lower() in last_text.lower():
                            matched = True
                            break
                        if expected.lower() in ("logged off", "signed out", "log off"):
                            if any(k in last_text.lower() for k in ["logged off", "signed out", "log off", "goodbye"]):
                                matched = True
                                break
                except Exception:
                    pass
                time.sleep(0.5)

            if not matched:
                try:
                    if elem.count() > 0:
                        last_text = elem.first.inner_text().strip()
                except Exception:
                    pass
                raise AssertionError(
                    f"Text assertion failed on '{selector}'. Expected '{expected}' to be contained in '{last_text}'."
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

