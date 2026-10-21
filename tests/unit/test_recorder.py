"""
Unit tests for Playwright Codegen recorder and parser
"""
import pytest
from app.models.test_suite import ActionType, LocatorStrategy
from app.browser.recorder import parse_recorded_script, create_test_case_from_recording


def test_parse_recorded_script_standard_flow():
    sample_script = """
import re
from playwright.sync_api import Playwright, sync_playwright, expect

def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("http://127.0.0.1:8000/")
    page.get_by_test_id("customer-id-input").click()
    page.get_by_test_id("customer-id-input").fill("CUST-999")
    page.get_by_test_id("material-select").select_option("MAT-1001")
    page.get_by_test_id("quantity-input").fill("15")
    page.get_by_test_id("submit-order-button").click()
    expect(page.get_by_test_id("success-banner")).to_contain_text("created successfully")
    context.close()
    browser.close()
"""
    steps = parse_recorded_script(sample_script)
    assert len(steps) >= 5

    # Step 1: Navigate
    assert steps[0].action == ActionType.NAVIGATE
    assert steps[0].input_value == "http://127.0.0.1:8000/"
    assert steps[0].step_number == 1

    # Step 2: Redundant click before fill was removed! Next is fill customer-id-input
    assert steps[1].action == ActionType.FILL
    assert steps[1].locator_strategy == LocatorStrategy.TEST_ID
    assert steps[1].selector_value == "customer-id-input"
    assert steps[1].input_value == "CUST-999"

    # Step 3: Select option
    assert steps[2].action == ActionType.SELECT_OPTION
    assert steps[2].selector_value == "material-select"
    assert steps[2].input_value == "MAT-1001"

    # Step 4: Fill quantity
    assert steps[3].action == ActionType.FILL
    assert steps[3].selector_value == "quantity-input"
    assert steps[3].input_value == "15"

    # Step 5: Click submit
    assert steps[4].action == ActionType.CLICK
    assert steps[4].selector_value == "submit-order-button"

    # Step 6: Assertion
    assert steps[5].action == ActionType.ASSERT_TEXT
    assert steps[5].selector_value == "success-banner"
    assert steps[5].expected_value == "created successfully"

    # Test Case creation
    tc = create_test_case_from_recording(
        title="Recorded E2E Order Flow",
        steps=steps,
        requirement_key="KAN-4",
        tc_id="TC-05",
    )
    assert tc.id == "TC-05"
    assert len(tc.steps) == len(steps)
    assert tc.requirement_key == "KAN-4"


def test_parse_recorded_script_missing_initial_goto():
    sample_script = """
    page.locator("#my-btn").click()
"""
    steps = parse_recorded_script(sample_script, default_url="http://127.0.0.1:8000")
    assert len(steps) == 2
    assert steps[0].action == ActionType.NAVIGATE
    assert steps[0].input_value == "http://127.0.0.1:8000/"
    assert steps[1].action == ActionType.CLICK
    assert steps[1].selector_value == "#my-btn"


def test_record_playwright_session_command_construction(monkeypatch, tmp_path):
    from unittest.mock import MagicMock
    import subprocess
    import sys
    from app.browser.recorder import record_playwright_session
    from app.automation.recorder import SessionRecorder

    dummy_out = tmp_path / "test_out.py"

    def side_effect(cmd, **kwargs):
        dummy_out.write_text("page.goto('https://example.com')\n", encoding="utf-8")
        return 0

    mock_run = MagicMock(side_effect=side_effect)
    monkeypatch.setattr("app.browser.recorder.run_process_on_interactive_desktop", mock_run)

    result = record_playwright_session(
        target_url="https://sap-server:44300/ui?a=1&b=2",
        output_file=dummy_out,
    )

    assert result == "page.goto('https://example.com')\n"
    assert mock_run.called
    call_args, call_kwargs = mock_run.call_args
    cmd = call_args[0]
    # Asserts that sys.executable is used directly instead of npx
    assert cmd[0] == sys.executable
    assert cmd[1:4] == ["-m", "playwright", "codegen"]
    assert "--ignore-https-errors" in cmd
    assert cmd[-1] == "https://sap-server:44300/ui?a=1&b=2"

    # Test SessionRecorder wrapper
    steps = SessionRecorder.parse("page.locator('#btn').click()")
    assert len(steps) >= 1


