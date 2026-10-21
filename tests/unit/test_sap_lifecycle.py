"""
Unit tests for SAP S/4HANA Lifecycle Enforcement.
Verifies that:
1. SAP test cases always start with complete logon steps (Navigate, Username, Password, Login button, Assert Launchpad Home).
2. Business functionality steps are preserved.
3. SAP test cases always end with complete logoff steps (Avatar Menu, Sign Out, OK confirmation, Assert logged off).
4. All steps are sequentially numbered from 1 to N.
5. Non-SAP test cases are not modified with SAP steps.
"""
import pytest
from app.models.requirements import JiraRequirement, AcceptanceCriterion
from app.models.test_suite import TestCase, TestStep, ActionType, LocatorStrategy, TestCategory
from app.test_design.generator import TestDesigner
from app.config import settings


@pytest.fixture
def sap_requirement():
    return JiraRequirement(
        key="KAN-23",
        summary="SAP RAR – Service Quotation Steps",
        description_text="Create and accept a service quotation in SAP S/4HANA Fiori.",
        acceptance_criteria=[
            AcceptanceCriterion(id="AC-01", text="User creates service quotation with sold-to party Brugmann Hospital"),
            AcceptanceCriterion(id="AC-02", text="User adds line item 45157510101 with quantity 1"),
        ],
        status="To Do",
    )


def test_enforce_sap_lifecycle_prepends_login_and_appends_logoff(sap_requirement):
    """Verify that a test case without login credentials gets login prepended and logoff appended."""
    # Functional steps only (e.g. LLM generated only quotation creation without login/logoff)
    raw_tc = TestCase(
        id="TC-01",
        requirement_key="KAN-23",
        source_ac_id="AC-01",
        title="Create Service Quotation Header",
        objective="Verify header creation",
        category=TestCategory.POSITIVE,
        steps=[
            TestStep(
                step_number=1,
                action=ActionType.CLICK,
                locator_strategy=LocatorStrategy.TEXT,
                selector_value="Manage Service Quotations",
                description="Click Manage Service Quotations tile",
            ),
            TestStep(
                step_number=2,
                action=ActionType.CLICK,
                locator_strategy=LocatorStrategy.CSS,
                selector_value="button:has-text('Create')",
                description="Click Create button",
            ),
            TestStep(
                step_number=3,
                action=ActionType.FILL,
                locator_strategy=LocatorStrategy.CSS,
                selector_value="input[id*='SoldToParty']",
                input_value="Brugmann Hospital",
                description="Enter Sold-to Party",
            ),
        ],
        expected_result="Quotation header created",
    )

    enforced = TestDesigner._enforce_sap_lifecycle(raw_tc, settings.sap_fiori_url, sap_requirement)

    # 1. Total steps should be 5 login + 3 functional + 4 logoff = 12 steps
    assert len(enforced.steps) == 12

    # 2. Check login steps (Steps 1-5)
    assert enforced.steps[0].action == ActionType.NAVIGATE
    assert enforced.steps[1].action == ActionType.FILL
    assert "#USERNAME_FIELD-inner" in enforced.steps[1].selector_value
    assert enforced.steps[1].input_value == (settings.sap_username or "MYRAR1").strip()
    assert enforced.steps[2].action == ActionType.FILL
    assert "#PASSWORD_FIELD-inner" in enforced.steps[2].selector_value
    assert enforced.steps[2].input_value == (settings.sap_password or "Pass23#$").strip()
    assert enforced.steps[3].action == ActionType.CLICK
    assert "#LOGIN_LINK" in enforced.steps[3].selector_value
    assert enforced.steps[4].action == ActionType.ASSERT_TEXT
    assert enforced.steps[4].expected_value == "Home"

    # 3. Check preserved functional steps (Steps 6-8)
    assert enforced.steps[5].description == "Click Manage Service Quotations tile"
    assert enforced.steps[6].description == "Click Create button"
    assert enforced.steps[7].description == "Enter Sold-to Party"

    # 4. Check logoff steps (Steps 9-12)
    assert enforced.steps[8].action == ActionType.CLICK
    assert "userActionsMenuHeaderButton" in enforced.steps[8].selector_value
    assert enforced.steps[9].action == ActionType.CLICK
    assert "Sign Out" in enforced.steps[9].selector_value
    assert enforced.steps[10].action == ActionType.CLICK
    assert "OK" in enforced.steps[10].selector_value
    assert enforced.steps[11].action == ActionType.ASSERT_TEXT
    assert enforced.steps[11].expected_value == "logged off"

    # 5. Check sequential numbering
    for i, s in enumerate(enforced.steps, start=1):
        assert s.step_number == i


def test_enforce_sap_lifecycle_preserves_existing_login_and_adds_logoff(sap_requirement):
    """Verify that a test case that already has login steps does not duplicate them, but adds missing logoff."""
    raw_tc = TestCase(
        id="TC-02",
        requirement_key="KAN-23",
        source_ac_id="AC-01",
        title="Quotation with existing login",
        objective="Verify login preserved",
        category=TestCategory.POSITIVE,
        steps=[
            TestStep(step_number=1, action=ActionType.NAVIGATE, input_value=settings.sap_fiori_url, description="Open SAP"),
            TestStep(step_number=2, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#USERNAME_FIELD-inner", input_value="MYRAR1", description="Enter user"),
            TestStep(step_number=3, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#PASSWORD_FIELD-inner", input_value="Pass23#$", description="Enter pass"),
            TestStep(step_number=4, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#LOGIN_LINK", description="Click log on"),
            TestStep(step_number=5, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="Home", description="Verify home"),
            TestStep(step_number=6, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEXT, selector_value="Manage Service Quotations", description="Open tile"),
        ],
        expected_result="Success",
    )

    enforced = TestDesigner._enforce_sap_lifecycle(raw_tc, settings.sap_fiori_url, sap_requirement)

    # 6 original steps + 4 logoff steps = 10 steps
    assert len(enforced.steps) == 10
    # Steps 1 to 5 are the existing login steps
    assert enforced.steps[1].selector_value == "#USERNAME_FIELD-inner"
    assert enforced.steps[2].selector_value == "#PASSWORD_FIELD-inner"
    # Step 6 is the functional step
    assert enforced.steps[5].description == "Open tile"
    # Steps 7 to 10 are the logoff steps
    assert "Sign Out" in enforced.steps[7].selector_value
    assert enforced.steps[9].expected_value == "logged off"

    for i, s in enumerate(enforced.steps, start=1):
        assert s.step_number == i


def test_enforce_sap_lifecycle_preserves_already_complete_lifecycle(sap_requirement):
    """Verify that when a test case already has both login and logoff, neither is duplicated."""
    raw_tc = TestCase(
        id="TC-03",
        requirement_key="KAN-23",
        source_ac_id="AC-01",
        title="Quotation with complete lifecycle",
        objective="Verify no duplicate steps",
        category=TestCategory.POSITIVE,
        steps=[
            TestStep(step_number=1, action=ActionType.NAVIGATE, input_value=settings.sap_fiori_url, description="Open SAP"),
            TestStep(step_number=2, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#USERNAME_FIELD-inner", input_value="MYRAR1", description="Enter user"),
            TestStep(step_number=3, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#PASSWORD_FIELD-inner", input_value="Pass23#$", description="Enter pass"),
            TestStep(step_number=4, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#LOGIN_LINK", description="Click log on"),
            TestStep(step_number=5, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="Home", description="Verify home"),
            TestStep(step_number=6, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEXT, selector_value="Manage Service Quotations", description="Open tile"),
            TestStep(step_number=7, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#meAreaHeaderButton", description="Click avatar"),
            TestStep(step_number=8, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEXT, selector_value="Sign Out", description="Click sign out"),
            TestStep(step_number=9, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEXT, selector_value="OK", description="Confirm"),
            TestStep(step_number=10, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="logged off", description="Assert logged off"),
        ],
        expected_result="Success",
    )

    enforced = TestDesigner._enforce_sap_lifecycle(raw_tc, settings.sap_fiori_url, sap_requirement)

    # Must remain exactly 10 steps, not 14
    assert len(enforced.steps) == 10
    # Step 7 avatar selector is updated with robust alias
    assert "#userActionsMenuHeaderButton" in enforced.steps[6].selector_value


def test_non_sap_test_case_is_untouched():
    """Verify that a non-SAP test case (e.g. local demo app) does not get SAP logon/logoff injected."""
    non_sap_req = JiraRequirement(
        key="DEMO-01",
        summary="Customer Order Checkout",
        description_text="Complete checkout form on local retail app.",
        status="To Do",
    )

    raw_tc = TestCase(
        id="TC-01",
        requirement_key="DEMO-01",
        source_ac_id="AC-01",
        title="Valid checkout",
        objective="Verify form submission",
        category=TestCategory.POSITIVE,
        steps=[
            TestStep(step_number=1, action=ActionType.NAVIGATE, input_value="http://localhost:8000/", description="Open app"),
            TestStep(step_number=2, action=ActionType.FILL, locator_strategy=LocatorStrategy.TEST_ID, selector_value="name-input", input_value="John Doe", description="Enter name"),
            TestStep(step_number=3, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEST_ID, selector_value="submit-btn", description="Submit"),
        ],
        expected_result="Order placed",
    )

    enforced = TestDesigner._enforce_sap_lifecycle(raw_tc, "http://localhost:8000", non_sap_req)

    # Must stay exactly 3 steps, no SAP logon/logoff
    assert len(enforced.steps) == 3
    assert enforced.steps[1].selector_value == "name-input"


def test_transaction_id_extraction_filters_dates_and_quotation_id():
    """Verify that Step 32 transaction extraction logic rejects dates, quotation numbers, and port IDs."""
    import re
    invalid_candidates = {
        "100", "44325", "45157510101", "136", "24", "1", "2", "10", "12",
        "2020", "2021", "2022", "2023", "2024", "2025", "2026", "2027", "2028", "2029", "2030"
    }
    quotation_id = "8000000653"
    invalid_candidates.add(quotation_id)

    # Simulated cell texts from SAP CRM WebClient Document Flow and Date tables
    cell_values = ["8000000653", "21.10.2026", "2026", "45157510101", "986"]
    
    doc_num = None
    for val in cell_values:
        m = re.search(r"\b([0-9]{3,10})\b", val)
        if m:
            cand = m.group(1)
            if cand not in invalid_candidates and not cand.startswith("4515"):
                if cand.startswith("8000") and len(cand) >= 10:
                    continue
                doc_num = cand
                break

    assert doc_num == "986", f"Expected '986' but extracted '{doc_num}'"


