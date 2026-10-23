from unittest.mock import MagicMock, patch
import pytest
from app.models.test_suite import TestSuite, TestCase, TestStep, ActionType
from app.models.execution import TestOutcome
from app.browser.executor import TestExecutor


def test_executor_runs_each_test_case_in_isolated_browser_context():
    tc1 = TestCase(
        id="TC-01",
        requirement_key="ISO-01",
        source_ac_id="AC-01",
        title="Quotation Creation",
        objective="Create quotation",
        steps=[
            TestStep(step_number=1, action=ActionType.NAVIGATE, input_value="http://test.local/login", description="Navigate to login"),
            TestStep(step_number=2, action=ActionType.ASSERT_TEXT, selector_value="body", expected_value="Transaction", description="Assert text"),
        ],
        expected_result="Quotation created",
    )
    tc2 = TestCase(
        id="TC-02",
        requirement_key="ISO-01",
        source_ac_id="AC-02",
        title="Manage Revenue Contracts",
        objective="Verify downstream contract",
        steps=[
            TestStep(step_number=1, action=ActionType.NAVIGATE, input_value="http://test.local/mrc", description="Navigate to MRC"),
            TestStep(step_number=2, action=ActionType.FILL, selector_value="Operational Document:", input_value="${OPERATIONAL_DOCUMENT}", description="Fill Operational Document"),
        ],
        expected_result="Contract verified",
    )
    suite = TestSuite(
        suite_id="SUITE-ISO-01",
        requirement_key="ISO-01",
        version=1,
        test_cases=[tc1, tc2],
    )

    executor = TestExecutor(headless=True)

    open_close_log: list = []

    class MockBrowserContextManager:
        def __init__(self, *args, **kwargs):
            # test_case_id is set as attribute after __enter__, not passed as kwarg anymore
            self.test_case_id = None
            self.page = MagicMock()
            self.locators = MagicMock()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            # By __exit__ the executor has set test_case_id on browser_ctx
            open_close_log.append(self.test_case_id)
            return False

        def capture_screenshot(self, *args, **kwargs):
            mock_path = MagicMock()
            mock_path.resolve.return_value = "screenshot.png"
            return mock_path

    captured_docs = []

    def mock_dispatch_step(step, page, locators, test_case=None):
        if test_case.id == "TC-01" and step.step_number == 2:
            executor.runtime_context["operational_document"] = "99887766"
        elif test_case.id == "TC-02" and step.step_number == 2:
            val = step.input_value
            if val == "${OPERATIONAL_DOCUMENT}":
                val = executor.runtime_context.get("operational_document")
            captured_docs.append(val)

    with patch("app.browser.executor.BrowserContextManager", MockBrowserContextManager), \
         patch.object(executor, "_dispatch_step", side_effect=mock_dispatch_step), \
         patch("app.storage.repository.save_execution_run_record", return_value=None):

        run = executor.execute_suite(suite=suite)

    # 1. Browser context was entered and exited twice (once per test case)
    assert len(open_close_log) == 2, "Expected 2 browser context close events (one per TC)"

    # test_case_id is set on browser_ctx after __enter__, captured on __exit__
    assert open_close_log == ["TC-01", "TC-02"], f"Expected TC-01 then TC-02, got {open_close_log}"

    # 2. Runtime context persisted from TC-01 into TC-02
    assert executor.runtime_context["operational_document"] == "99887766"
    assert captured_docs == ["99887766"]

    # 3. Both tests passed
    assert run.passed_tests == 2
    assert run.total_tests == 2
