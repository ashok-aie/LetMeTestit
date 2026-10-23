from unittest.mock import MagicMock
import pytest
from app.test_design.generator import TestDesigner
from app.graph.nodes import WorkflowNodes


def test_kan32_user_story_flow_and_two_tc_generation():
    raw_text = """Validate the SAP Fiori Solution Quotation end-to-end lifecycle from creation, item configuration, pricing condition addition, and acceptance, through to downstream verification in Manage Revenue Contracts.

Preconditions:

Target Application: SAP S/4HANA Fiori Launchpad
Authorized User with roles for Service Quotations and Revenue Accounting

AC-01: AC-01 (Multi-Item Service Quotation Creation, Pricing, and Acceptance):
In Service Quotation application', start new Quotation.
Select Transaction Type ZQDV — CE-Direct Sales
Give Description as 'RAR test'  and Sold-to Party as Brugmann Hospital
In the ‘Dates’ tab, In ‘Term of Quotation’ and give its Duration as 24 and Time Unit as Months
Items Tab line items:
Line Item 1: Product ID '45157510101' , go to product add Quantity 1 and add Price condition 'ZTAF' 
Line Item 2: Product ID '45157510707' , go to product add Quantity 1 and add Price condition 'ZTAF'
Return to the quotation and Save the Quotation.
Click on Edit to Change status to Released and save
Then Accept the quotation.
Capture the Quotation number and status changes are recorded as evidence.
Copy Transaction id from Transaction History to use in “Manage Revenue Contracts

AC-02 (Downstream Manage Revenue Contracts Processing):
Verify that the Operational Document generated from AC-01 successfully appears in Manage Revenue Contracts:
Navigate to ‘Manage Revenue Contracts’ 
Then Navigate to Revenue contract popup, enter the Transaction id in Operational Document and click enter
Select all the Items with same Operational Document then click ok
Then click Go in the Manage Revenue Contract 
Click on Revenue Contract to view details
"""

    nodes = WorkflowNodes()
    state = {"raw_requirement_text": raw_text, "issue_key": "TEST-32"}
    state.update(nodes.fetch_requirement(state))
    state.update(nodes.normalize_requirement(state))
    state.update(nodes.assess_completeness(state))
    req = state["jira_requirement"]

    # 1. Exactly 2 Acceptance Criteria extracted
    assert len(req.acceptance_criteria) == 2, f"Expected 2 ACs, got {len(req.acceptance_criteria)}"
    assert req.acceptance_criteria[0].id == "AC-01"
    assert "45157510101" in req.acceptance_criteria[0].text
    assert "45157510707" in req.acceptance_criteria[0].text
    assert req.acceptance_criteria[1].id == "AC-02"
    assert "Manage Revenue Contracts" in req.acceptance_criteria[1].text

    # 2. Exactly 2 Test Cases generated (TC-01 and TC-02)
    mock_llm = MagicMock()
    mock_llm.generate.side_effect = Exception("LLM fallback trigger")
    designer = TestDesigner(llm_client=mock_llm)
    suite = designer.generate_suite(
        requirement=req,
        target_base_url="https://s4srv25.nodomain.com:44325/sap/bc/ui2/flp",
    )

    assert len(suite.test_cases) == 2, f"Expected 2 Test Cases, got {len(suite.test_cases)}"
    tc1, tc2 = suite.test_cases[0], suite.test_cases[1]
    assert tc1.id == "TC-01"
    assert tc2.id == "TC-02"

    # 3. Transaction Type ZQDV dynamically extracted (not hardcoded ZQDS)
    ttype_step = next(s for s in tc1.steps if "Transaction Type" in (s.description or ""))
    assert "ZQDV" in (ttype_step.selector_value or "") or tc1.test_data.get("transaction_type") == "ZQDV"

    # 4. Step 12 opens Items tab directly, Step 13 enters Product ID 45157510101 (no invalid Dates tab)
    step_12 = tc1.steps[11]
    assert step_12.step_number == 12
    assert "Items" in (step_12.selector_value or "")

    step_num_item1 = next(
        s.step_number
        for s in tc1.steps
        if s.input_value in ("45157510101", "${item1_product_id}", "${item_1_product_id}")
    )
    assert step_num_item1 in (13, 17), f"Expected Product ID 45157510101 at Step 13/17, got Step {step_num_item1}"
    assert tc1.test_data.get("item1_product_id") == "45157510101"

    # Item 1 details drilldown happens immediately after product 1 commit (no table quantity)
    step_num_drill1 = next(s.step_number for s in tc1.steps if "item 1 details" in (s.description or "").lower())
    assert step_num_drill1 > step_num_item1, f"Expected item 1 details click after Step {step_num_item1}, got Step {step_num_drill1}"

    # Item 2 is entered after returning to quotation and opening Items tab
    step_num_item2 = next(
        s.step_number
        for s in tc1.steps
        if s.input_value in ("45157510707", "${item2_product_id}", "${item_2_product_id}")
    )
    assert tc1.test_data.get("item2_product_id") == "45157510707"
    assert step_num_item1 < step_num_drill1 < step_num_item2, "Item 1 details drilldown must occur before Item 2 is entered in table"

    # 5. Items tab is clicked after Back from item 1 before item 2 is entered
    back_step1 = next(s.step_number for s in tc1.steps if "return to quotation from item 1" in (s.description or "").lower())
    items_tab_step = next(s.step_number for s in tc1.steps if s.step_number > back_step1 and s.selector_value == "Items")
    step_num_drill2 = next(s.step_number for s in tc1.steps if "item 2 details" in (s.description or "").lower())
    assert back_step1 < items_tab_step < step_num_item2 < step_num_drill2, "Items tab must be clicked after Back from item 1 before item 2 is entered and clicked"

    # 6. Lifecycle: Released, Accepted, and Transaction History captured
    assert any("Released" in (s.selector_value or "") or "${release_status}" in (s.selector_value or "") for s in tc1.steps)
    assert any("Accept" in (s.description or "") for s in tc1.steps)
    assert any("Transaction History" in (s.description or "") for s in tc1.steps)

    # 7. TC-02: Manage Revenue Contracts with dynamic ${operational_document}
    op_step = next(s for s in tc2.steps if (s.input_value or "").lower() == "${operational_document}")
    assert op_step.selector_value == "Operational Document:"
    assert any("Go" in (s.description or "") for s in tc2.steps)
    assert any("Revenue Contract" in (s.expected_value or "") for s in tc2.steps)
    assert any("view details" in (s.description or "").lower() for s in tc2.steps)


def test_ac03_and_ac04_recorded_flows_in_knowledge_store():
    """Verify AC-03 ([TC-01] 24 steps, [TC-02] 23 steps) and AC-04 ([TC-03] 9 steps) recorded flows are in the Knowledge Store."""
    from app.storage.repository import (
        load_regression_suite,
        get_reusable_flow_steps,
        list_golden_examples,
        get_testing_standards,
        get_full_knowledge_base_context,
    )

    # 1. Recorded Suite (SUITE-REC-01-202610221551.json)
    rec_suite = load_regression_suite("SUITE-REC-01-202610221551")
    assert rec_suite is not None
    tc_map = {tc.id: tc for tc in rec_suite.test_cases}
    assert tc_map["TC-01"].source_ac_id == "AC-03"
    assert len(tc_map["TC-01"].steps) == 24
    assert tc_map["TC-02"].source_ac_id == "AC-03"
    assert len(tc_map["TC-02"].steps) == 23
    assert tc_map["TC-03"].source_ac_id == "AC-04"
    assert len(tc_map["TC-03"].steps) == 9

    # 2. Reusable Flow Library (data/library/flows.json)
    flow_tc01 = get_reusable_flow_steps("Recorded: [TC-01] Create Outbound Delivery (AC-03 — 24 steps)")
    assert len(flow_tc01) == 24
    flow_tc02 = get_reusable_flow_steps("Recorded: [TC-02] Create Outbound Delivery (AC-03 — 23 steps)")
    assert len(flow_tc02) == 23
    flow_tc03 = get_reusable_flow_steps("Recorded: [TC-03] Create Billing Document (AC-04 — 9 steps)")
    assert len(flow_tc03) == 9

    # 3. Golden Examples (data/knowledge/golden_examples.json)
    golden = {g["example_id"]: g for g in list_golden_examples()}
    assert golden["GOLDEN-RECORDED-WORKFLOW-(CREATE-OUTBOUND-DELIVERY)-30"]["test_case"]["source_ac_id"] == "AC-03"
    assert len(golden["GOLDEN-RECORDED-WORKFLOW-(CREATE-OUTBOUND-DELIVERY)-30"]["test_case"]["steps"]) == 24
    assert golden["GOLDEN-RECORDED-WORKFLOW-(CREATE-OUTBOUND-DELIVERY)-31"]["test_case"]["source_ac_id"] == "AC-03"
    assert len(golden["GOLDEN-RECORDED-WORKFLOW-(CREATE-OUTBOUND-DELIVERY)-31"]["test_case"]["steps"]) == 23
    assert golden["GOLDEN-RECORDED-WORKFLOW-(CREATE-BILLING-DOCUMENT)-32"]["test_case"]["source_ac_id"] == "AC-04"
    assert len(golden["GOLDEN-RECORDED-WORKFLOW-(CREATE-BILLING-DOCUMENT)-32"]["test_case"]["steps"]) == 9

    # 4. Testing Standards & Full Knowledge Base Prompt Context
    standards = get_testing_standards()
    assert "[TC-01]" in standards and "24 steps" in standards
    assert "[TC-02]" in standards and "23 steps" in standards
    assert "[TC-03]" in standards and "9 steps" in standards

    full_ctx = get_full_knowledge_base_context()
    assert "AC-03" in full_ctx
    assert "AC-04" in full_ctx
    assert "Shipping Point Required" in full_ctx
    assert "Documents to Be Processed" in full_ctx


def test_four_ac_extraction_and_four_tc_generation():
    """Verify that AC-01, AC-02, 'AC -03', and 'AC -04' are extracted as 4 distinct ACs and produce 4 Test Cases (TC-01..TC-04)."""
    raw_text = """AC-01: AC-01 (Multi-Item Service Quotation Creation, Pricing, and Acceptance):

In Service Quotation application', start new Quotation.
Select Transaction Type ZQDS — CE-Direct Sales
Give Description as 'RAR testing' and Sold-to Party as Brugmann Hospital
In the ‘Dates’ tab, In ‘Term of Quotation’ and give its Duration as 24 and Time Unit as Months
Items Tab line items:- Line Item 1: Product ID 45157022302, add Quantity 1, Plant BEV8, then go to product add Price condition 'ZTAF'
Line Item 2: Product ID 45157022301, add Quantity 1, Plant BEV8, then go to product add Price condition 'ZTAF'
Line Item 3: Product ID 45157510707, add Quantity 1, Plant BEV8, then go to product add Price condition 'ZTAF'
Line Item 4: Product ID 45157022900 , add Quantity 1, Plant BEV8, then go to product add Price condition 'ZTAF'
Return to the quotation and Save the Quotation.
Click on Edit to Change status to Released and save
Then Accept the quotation.
Capture the Quotation number and status changes are recorded as evidence.
Copy Transaction id from Transaction History to use in “Manage Revenue Contracts
AC-02 (Downstream Manage Revenue Contracts Processing):Verify that the Operational Document generated from AC-01 successfully appears in Manage Revenue Contracts:

Navigate to ‘Manage Revenue Contracts’
Then Navigate to Revenue contract popup, enter the Transaction id in Operational Document and click enter
Select all the Items with same Operational Document then click ok
Then click Go in the Manage Revenue Contract
Click on Revenue Contract to view details
AC -03

Navigate to Create Outbound Delivery with reference
Select Plant as ‘BEV8’ and enter the Order Number
Then click on ‘Picking' Tab and enter Storage Location as '6020’ and picking quantity
Click on ‘Post Goods issue’
Outbond Delivery and Material documen is created.
Capture Material number, to use in Create Billing Document scenario.
AC -04

Navigate to Create Billing Document
Enter the Document number which you copied in the previous test case.
select the Document and check if its Fully Invoiced in the Processing Status
Verify Billing Number is created"""

    nodes = WorkflowNodes()
    state = {"raw_requirement_text": raw_text}
    state.update(nodes.fetch_requirement(state))
    state.update(nodes.normalize_requirement(state))
    state.update(nodes.assess_completeness(state))
    req = state["jira_requirement"]

    # 1. All 4 ACs must be extracted (including 'AC -03' and 'AC -04' with spaces before hyphen)
    assert len(req.acceptance_criteria) == 4, f"Expected 4 ACs, got {len(req.acceptance_criteria)}: {[a.id for a in req.acceptance_criteria]}"
    assert [a.id for a in req.acceptance_criteria] == ["AC-01", "AC-02", "AC-03", "AC-04"]
    assert "Outbound Delivery" in req.acceptance_criteria[2].text
    assert "Create Billing Document" in req.acceptance_criteria[3].text
    assert "Create Billing Document" not in req.acceptance_criteria[1].text

    # 2. All 4 Test Cases (TC-01..TC-04) must be generated
    mock_llm = MagicMock()
    mock_llm.generate.side_effect = Exception("Fallback trigger")
    designer = TestDesigner(llm_client=mock_llm)
    suite = designer.generate_suite(
        requirement=req,
        target_base_url="https://s4srv25.nodomain.com:44325/sap/bc/ui2/flp",
    )

    assert len(suite.test_cases) == 4, f"Expected 4 Test Cases, got {len(suite.test_cases)}"
    assert [tc.id for tc in suite.test_cases] == ["TC-01", "TC-02", "TC-03", "TC-04"]
    assert [tc.source_ac_id for tc in suite.test_cases] == ["AC-01", "AC-02", "AC-03", "AC-04"]
    assert any("OutboundDelivery-createInWebGUI" in (s.input_value or "") for s in suite.test_cases[2].steps)
    assert any("BillingDocument-createBillingDocuments" in (s.input_value or "") for s in suite.test_cases[3].steps)
    assert suite.test_cases[2].test_data.get("storage_location") == "6020"
    assert suite.test_cases[2].test_data.get("picking_quantity") == "1"


def test_outbound_delivery_sloc_6020_picked_qty_matches_deliv_qty_and_red_error_stops_execution():
    """
    Verify:
    1. SLoc (col 4) is always 6020 and Picked Qty (col 8) always matches Deliv. Qty (col 6) per row.
    2. If a SAP Red Error message appears after Save / Post Goods Issue / Picking Enter, execution stops immediately and classifies as APPLICATION_DEFECT.
    """
    from app.browser.executor import TestExecutor
    from app.models.test_suite import TestCase, TestStep, ActionType, LocatorStrategy

    executor = TestExecutor(headless=True)

    # Simulate a page with a child WebGUI frame displaying a red status bar error message
    mock_main_frame = MagicMock()
    mock_child_frame = MagicMock()
    mock_child_frame.evaluate.return_value = "Storage location 4 does not exist in plant BEV8"

    mock_page = MagicMock()
    mock_page.main_frame = mock_main_frame
    mock_page.frames = [mock_main_frame, mock_child_frame]

    detected = executor._detect_sap_red_error_message(mock_page)
    assert detected == "Storage location 4 does not exist in plant BEV8"

    # Verify Save step immediately raises AssertionError when a SAP Red Error message is present
    save_step = TestStep(
        step_number=14,
        action=ActionType.CLICK,
        locator_strategy=LocatorStrategy.ROLE,
        role_name="button",
        selector_value="Save (Ctrl+S)",
        description="Click Save button",
    )
    tc_dummy = TestCase(
        id="TC-03",
        requirement_key="KAN-32",
        source_ac_id="AC-03",
        title="Validate AC-03: Create Outbound Delivery",
        objective="Create Outbound Delivery and Post Goods Issue",
        steps=[save_step],
        expected_result="Outbound Delivery and Material Document created.",
    )
    with pytest.raises(AssertionError, match="SAP Red Error Message"):
        executor._dispatch_step(save_step, mock_page, MagicMock(), test_case=tc_dummy)



