"""
Browser Integration Test: TestExecutor Declarative Execution on SAP Demo App
Tests declarative step dispatch, deterministic assertions, failure classification,
and screenshot/trace evidence capture in Chromium.
"""
from pathlib import Path
import pytest
from app.models.test_suite import (
    TestSuite,
    TestCase,
    TestStep,
    ActionType,
    LocatorStrategy,
    TestCategory,
)
from app.models.execution import TestOutcome, FailureClassification
from app.browser.executor import TestExecutor
from tests.browser.test_demo_app_playwright import live_server


@pytest.mark.browser
def test_executor_runs_declarative_test_suite(live_server, tmp_path):
    """Executes a declarative test case through TestExecutor and verifies all steps pass."""
    steps = [
        TestStep(
            step_number=1,
            action=ActionType.NAVIGATE,
            input_value=f"{live_server}/",
            description="Open SAP Fiori Order Portal",
        ),
        TestStep(
            step_number=2,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.TEST_ID,
            selector_value="reset-db-button",
            description="Reset database to clean seed state",
        ),
        TestStep(
            step_number=3,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.TEST_ID,
            selector_value="customer-id-input",
            input_value="CUST-7777",
            description="Enter Sold-to Party Customer ID",
        ),
        TestStep(
            step_number=4,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.TEST_ID,
            selector_value="customer-name-input",
            input_value="Zephyr Industrial Turbines",
            description="Enter Customer Legal Name",
        ),
        TestStep(
            step_number=5,
            action=ActionType.SELECT_OPTION,
            locator_strategy=LocatorStrategy.TEST_ID,
            selector_value="material-select",
            input_value="MAT-2002",
            description="Select Aerospace Titanium Bolts",
        ),
        TestStep(
            step_number=6,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.TEST_ID,
            selector_value="quantity-input",
            input_value="2",
            description="Enter Order Quantity of 2",
        ),
        TestStep(
            step_number=7,
            action=ActionType.SELECT_OPTION,
            locator_strategy=LocatorStrategy.TEST_ID,
            selector_value="priority-select",
            input_value="Urgent",
            description="Select Priority Urgent",
        ),
        TestStep(
            step_number=8,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.TEST_ID,
            selector_value="submit-order-button",
            description="Click Create Sales Order button",
        ),
        TestStep(
            step_number=9,
            action=ActionType.ASSERT_TEXT,
            locator_strategy=LocatorStrategy.TEST_ID,
            selector_value="orders-table",
            expected_value="Zephyr Industrial Turbines",
            description="Verify new customer row rendered in SAP table",
        ),
    ]

    test_case = TestCase(
        id="TC-SAP-EXEC-01",
        requirement_key="SAP-200",
        source_ac_id="AC-01",
        title="Create Standard Sales Order via Declarative Engine",
        objective="Validate declarative step execution through Playwright executor",
        category=TestCategory.POSITIVE,
        steps=steps,
        expected_result="Order created and verified in SAP table",
    )

    suite = TestSuite(
        suite_id="SUITE-SAP-200-V1",
        requirement_key="SAP-200",
        test_cases=[test_case],
    )

    executor = TestExecutor(headless=True)
    run = executor.execute_suite(suite=suite, target_url=f"{live_server}/")

    assert run.total_tests == 1
    assert run.passed_tests == 1
    assert run.failed_tests == 0
    assert len(run.results) == 1

    tc_res = run.results[0]
    assert tc_res.outcome == TestOutcome.PASS
    assert len(tc_res.step_results) == 9
    assert all(s.passed for s in tc_res.step_results)
    assert Path(run.trace_path).exists()


@pytest.mark.browser
def test_executor_handles_assertion_failure_and_captures_screenshot(live_server):
    """Executes a failing assertion step, verifying failure classification and screenshot capture."""
    steps = [
        TestStep(
            step_number=1,
            action=ActionType.NAVIGATE,
            input_value=f"{live_server}/",
            description="Open SAP Fiori Order Portal",
        ),
        TestStep(
            step_number=2,
            action=ActionType.ASSERT_TEXT,
            locator_strategy=LocatorStrategy.TEST_ID,
            selector_value="orders-table",
            expected_value="NON_EXISTENT_GHOST_CUSTOMER_9999",
            description="Assert absent customer is present (intentional failure)",
        ),
    ]

    test_case = TestCase(
        id="TC-SAP-EXEC-FAIL-02",
        requirement_key="SAP-200",
        source_ac_id="AC-02",
        title="Negative Assertion Test",
        objective="Trigger assertion error and capture evidence",
        category=TestCategory.NEGATIVE,
        steps=steps,
        expected_result="Assertion failure recorded",
    )

    suite = TestSuite(
        suite_id="SUITE-SAP-200-FAIL",
        requirement_key="SAP-200",
        test_cases=[test_case],
    )

    executor = TestExecutor(headless=True)
    run = executor.execute_suite(suite=suite, target_url=f"{live_server}/")

    assert run.total_tests == 1
    assert run.failed_tests == 1
    assert run.passed_tests == 0

    tc_res = run.results[0]
    assert tc_res.outcome == TestOutcome.FAIL
    assert tc_res.classification == FailureClassification.APPLICATION_DEFECT
    assert tc_res.screenshot_path is not None
    assert Path(tc_res.screenshot_path).exists()


@pytest.mark.browser
def test_executor_fails_positive_scenario_when_error_banner_present(live_server):
    """Verifies that if an error banner is displayed on screen, positive test cases fail deterministically."""
    steps = [
        TestStep(
            step_number=1,
            action=ActionType.NAVIGATE,
            # Navigate to URL with simulated error banner
            input_value=f"{live_server}/?error=Validation+Error:+Customer+ID+is+mandatory.",
            description="Open SAP Fiori Order Portal with error state",
        ),
        TestStep(
            step_number=2,
            action=ActionType.ASSERT_TEXT,
            locator_strategy=LocatorStrategy.TEST_ID,
            selector_value="orders-table",
            # This text exists in the seed table, but the error banner on screen must cause failure
            expected_value="Submitted",
            description="Assert text on orders-table in positive category",
        ),
    ]

    test_case = TestCase(
        id="TC-SAP-EXEC-ERR-BANNER",
        requirement_key="SAP-200",
        source_ac_id="AC-01",
        title="Positive Test with Error Banner on Screen",
        objective="Verify error banner triggers failure in positive scenario",
        category=TestCategory.POSITIVE,
        steps=steps,
        expected_result="Test must fail because of error banner on screen",
    )

    suite = TestSuite(
        suite_id="SUITE-SAP-200-ERR",
        requirement_key="SAP-200",
        test_cases=[test_case],
    )

    executor = TestExecutor(headless=True)
    run = executor.execute_suite(suite=suite, target_url=f"{live_server}/")

    assert run.total_tests == 1
    assert run.failed_tests == 1
    assert run.passed_tests == 0
    tc_res = run.results[0]
    assert tc_res.outcome == TestOutcome.FAIL
    assert Path(tc_res.screenshot_path).exists()


@pytest.mark.browser
def test_executor_runs_negative_validation_test_case_success(live_server):
    """Executes a negative test case expecting a validation error banner and verifies it passes."""
    steps = [
        TestStep(
            step_number=1,
            action=ActionType.NAVIGATE,
            input_value=f"{live_server}/",
            description="Open SAP Fiori Order Portal",
        ),
        TestStep(
            step_number=2,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.TEST_ID,
            selector_value="customer-id-input",
            input_value="",
            description="Leave Customer ID blank (mandatory field violation)",
        ),
        TestStep(
            step_number=3,
            action=ActionType.SELECT_OPTION,
            locator_strategy=LocatorStrategy.TEST_ID,
            selector_value="material-select",
            input_value="MAT-1001",
            description="Select Industrial Steel Coil",
        ),
        TestStep(
            step_number=4,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.TEST_ID,
            selector_value="quantity-input",
            input_value="5",
            description="Enter Quantity 5",
        ),
        TestStep(
            step_number=5,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.TEST_ID,
            selector_value="submit-order-button",
            description="Click submit button to trigger mandatory field validation",
        ),
        TestStep(
            step_number=6,
            action=ActionType.ASSERT_TEXT,
            locator_strategy=LocatorStrategy.TEST_ID,
            selector_value="error-banner",
            expected_value="Validation Error",
            description="Assert validation error banner is displayed",
        ),
    ]

    test_case = TestCase(
        id="TC-SAP-NEG-01",
        requirement_key="SAP-200",
        source_ac_id="AC-02",
        title="Negative: Mandatory Sold-to Party Validation",
        objective="Verify system rejects order submission and displays error when Customer ID is missing",
        category=TestCategory.NEGATIVE,
        steps=steps,
        expected_result="Validation error banner displayed and verified",
    )

    suite = TestSuite(
        suite_id="SUITE-SAP-200-NEG",
        requirement_key="SAP-200",
        test_cases=[test_case],
    )

    executor = TestExecutor(headless=True)
    run = executor.execute_suite(suite=suite, target_url=f"{live_server}/")

    assert run.total_tests == 1
    assert run.passed_tests == 1
    assert run.failed_tests == 0
    assert len(run.results) == 1

    tc_res = run.results[0]
    assert tc_res.outcome == TestOutcome.PASS
    assert len(tc_res.step_results) == 6
    assert all(s.passed for s in tc_res.step_results)
    assert tc_res.screenshot_path is not None
    assert Path(tc_res.screenshot_path).exists()


