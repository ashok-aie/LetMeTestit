from unittest.mock import MagicMock
import pytest
from app.test_design.generator import TestDesigner
from app.models.requirements import JiraRequirement, AcceptanceCriterion
from app.graph.nodes import WorkflowNodes


def test_kan31_two_ac_split_and_two_tc_generation():
    raw_text = """Validate the SAP Fiori Solution Quotation end-to-end lifecycle from creation, item configuration, pricing condition addition, and acceptance, through to downstream verification in Manage Revenue Contracts.

Preconditions:

Target Application: SAP S/4HANA Fiori Launchpad
Authorized User with roles for Service Quotations and Revenue Accounting

AC-01 (Multi-Item Service Quotation Creation, Pricing, and Acceptance):
Verify that a Service Quotation of Transaction Type 'ZQDS' can be successfully created with:

Description: 'RAR testing'
Sold-to Party: 'Brugmann Hospital'
Term of Quotation Duration: 24 (Time Unit: Months)
Items Tab line items:
Line Item 1: Product ID '45157510101' , go to product add Quantity 1 and add Price condition 'ZTAF' 
Line Item 2: Product ID '45157510707' , go to product add Quantity 1 and add Price condition 'ZTAF' 
Save the Quotation,  lifecycle status updated to 'Released', saved, and accepted
Transaction ID copied from the 'Transaction History' tab as test evidence for downstream verification.

AC-02 (Downstream Manage Revenue Contracts Processing):
Verify that the Operational Document generated from AC-01 successfully appears in Manage Revenue Contracts:

Navigate to 'Manage Revenue Contracts'
In the Revenue Contract filter / Value Help popup, enter the Transaction ID captured from AC-01 into 'Operational Document:' and press Enter
Select the matching contract from the list and click OK
Click Go and verify that the Revenue Contract details and accounting obligations load successfully.
"""

    nodes = WorkflowNodes()
    state = {"raw_requirement_text": raw_text, "issue_key": "TEST-31"}
    state.update(nodes.fetch_requirement(state))
    state.update(nodes.normalize_requirement(state))
    state.update(nodes.assess_completeness(state))
    req = state["jira_requirement"]

    # 1. Verify exactly 2 ACs are extracted (NOT 12)
    assert len(req.acceptance_criteria) == 2, f"Expected 2 ACs, got {len(req.acceptance_criteria)}"
    assert req.acceptance_criteria[0].id == "AC-01"
    assert "45157510101" in req.acceptance_criteria[0].text
    assert "45157510707" in req.acceptance_criteria[0].text
    assert req.acceptance_criteria[1].id == "AC-02"
    assert "Manage Revenue Contracts" in req.acceptance_criteria[1].text

    # 2. Verify exactly 2 Test Cases are generated (TC-01 and TC-02)
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

    # 3. Verify TC-01: Contains inputs for both items and pricing drilldowns for both items
    assert any(s.input_value == "45157510101" for s in tc1.steps)
    assert any(s.input_value == "45157510707" for s in tc1.steps)

    # Item 1 pricing steps
    assert any("item 1 details" in (s.description or "").lower() for s in tc1.steps)
    assert any("Price Details tab for item 1" in (s.description or "") for s in tc1.steps)
    assert any("ZTAF from popup for item 1" in (s.description or "") for s in tc1.steps)

    # Item 2 pricing steps
    assert any("item 2 details" in (s.description or "").lower() for s in tc1.steps)
    assert any("Price Details tab for item 2" in (s.description or "") for s in tc1.steps)
    assert any("ZTAF from popup for item 2" in (s.description or "") for s in tc1.steps)

    # Released, Accepted, and Transaction History
    assert any("Released" in (s.selector_value or "") for s in tc1.steps)
    assert any("Accept" in (s.description or "") for s in tc1.steps)
    assert any("Transaction History" in (s.description or "") for s in tc1.steps)

    # 4. Verify TC-02: Manage Revenue Contracts with ${OPERATIONAL_DOCUMENT}
    op_step = next(s for s in tc2.steps if s.input_value == "${OPERATIONAL_DOCUMENT}")
    assert op_step.selector_value == "Operational Document:"
    assert any("Go" in (s.description or "") for s in tc2.steps)
    assert any("Revenue Contract" in (s.expected_value or "") for s in tc2.steps)

