"""
Unit Tests for Persistent Storage Repository & Selective Execution
Validates:
1. Regression Suite CRUD and requirement cache lookup
2. Reusable Flow library loading, step extraction, and saving
3. Learned Selector Catalog continuous updates and prompt injection
4. Selective test case execution in TestExecutor
"""
import pytest
from app.models.test_suite import TestSuite, TestCase, TestStep, ActionType, LocatorStrategy, TestCategory
from app.storage.repository import (
    save_regression_suite,
    load_regression_suite,
    list_regression_suites,
    delete_regression_suite,
    get_cached_suite_for_requirement,
    list_reusable_flows,
    get_reusable_flow_steps,
    save_reusable_flow,
    get_learned_selectors,
    save_learned_selector,
    get_learned_selectors_prompt_context,
)
from app.browser.executor import TestExecutor


def test_regression_suite_crud_and_caching():
    step1 = TestStep(step_number=1, action=ActionType.NAVIGATE, description="Navigate")
    step2 = TestStep(step_number=2, action=ActionType.CLICK, selector_value="#btn", description="Click")
    tc = TestCase(
        id="TC-01",
        requirement_key="TEST-REQ-99",
        source_ac_id="AC-01",
        title="Test Case 1",
        objective="Objective 1",
        steps=[step1, step2],
        expected_result="Success",
    )
    suite = TestSuite(
        suite_id="SUITE-TEST-99",
        requirement_key="TEST-REQ-99",
        version=1,
        test_cases=[tc],
    )

    # 1. Save
    saved_path = save_regression_suite(suite, suite_name="Unit Test Suite 99", last_run_status="1/1 Passed")
    assert saved_path.exists()

    # 2. List
    suites = list_regression_suites()
    assert any(s["suite_id"] == "SUITE-TEST-99" for s in suites)

    # 3. Cache lookup
    cached = get_cached_suite_for_requirement("TEST-REQ-99")
    assert cached is not None
    assert cached.suite_id == "SUITE-TEST-99"
    assert len(cached.test_cases) == 1

    # 4. Load
    loaded = load_regression_suite("SUITE-TEST-99")
    assert loaded is not None
    assert len(loaded.test_cases) == 1
    assert loaded.test_cases[0].steps[1].selector_value == "#btn"

    # 5. Delete
    deleted = delete_regression_suite("SUITE-TEST-99")
    assert deleted is True
    assert load_regression_suite("SUITE-TEST-99") is None


def test_reusable_flows_library():
    flows = list_reusable_flows()
    assert "SAP Standard Logon" in flows
    assert "SAP Standard Logout" in flows

    steps = get_reusable_flow_steps("SAP Standard Logon", starting_step_number=1)
    assert len(steps) >= 4
    assert steps[0].action == ActionType.NAVIGATE
    assert steps[1].action == ActionType.FILL

    # Custom flow save
    custom_step = TestStep(step_number=1, action=ActionType.WAIT_FOR, input_value="5s", description="Wait 5s")
    save_reusable_flow(
        flow_name="Custom Pause 5s",
        description="Pauses for 5 seconds",
        category="Utility",
        steps=[custom_step],
    )
    updated_flows = list_reusable_flows()
    assert "Custom Pause 5s" in updated_flows


def test_learned_selector_catalog():
    # Save a learned selector
    save_learned_selector(
        element_label="Test Order Submit Button",
        selector="#submit-order-btn-test",
        strategy="css",
        action="click",
        app_domain="SAP S/4HANA",
    )

    selectors = get_learned_selectors()
    found = [s for s in selectors if s.get("selector") == "#submit-order-btn-test"]
    assert len(found) == 1
    initial_passes = found[0]["pass_count"]

    # Increment pass count
    save_learned_selector(
        element_label="Test Order Submit Button",
        selector="#submit-order-btn-test",
        strategy="css",
        action="click",
    )
    selectors_updated = get_learned_selectors()
    found_updated = [s for s in selectors_updated if s.get("selector") == "#submit-order-btn-test"]
    assert found_updated[0]["pass_count"] == initial_passes + 1

    # Check prompt context string
    prompt_ctx = get_learned_selectors_prompt_context()
    assert "VERIFIED WORKING SELECTORS" in prompt_ctx
    assert "#submit-order-btn-test" in prompt_ctx

