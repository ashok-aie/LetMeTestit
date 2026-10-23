from unittest.mock import MagicMock
import pytest
from app.test_design.generator import TestDesigner
from app.models.requirements import JiraRequirement, AcceptanceCriterion
from app.graph.nodes import WorkflowNodes
from app.flows.sap_flows import extract_sap_quotation_parameters, build_service_quotation_steps


def test_multi_item_pricing_extraction_and_step_generation():
    raw_text = """Validate the SAP Fiori Solution Quotation bundle from creation and acceptance, and make sure its operational document successfully appears in Manage Revenue Contracts.

AC-01: Create new service quotation of transaction type ZQDS, can be created with description as 'RAR testing', Sold-to Party as 'Brugmann Hospital', Term of Quotation is 2 Years, give below product id's in Items tab:
Product id is 45157510101, go into product enter quantity is 1 and price condition ZTAF.
Product id is 45157510707, go into product enter quantity 1 and price condition ZTAF.
Then, release, accept, and go to transaction history to copy transaction id.

AC-02: The resulting Operational Document using the transaction id successfully appears in Manage Revenue Contracts.
"""

    nodes = WorkflowNodes()
    state = {"raw_requirement_text": raw_text, "issue_key": "TEST-28"}
    state.update(nodes.fetch_requirement(state))
    state.update(nodes.normalize_requirement(state))
    state.update(nodes.assess_completeness(state))
    req = state["jira_requirement"]

    assert len(req.acceptance_criteria) == 2

    # Verify parameter extraction
    params = extract_sap_quotation_parameters(req, req.acceptance_criteria[0])
    assert params["desc_val"] == "RAR testing"
    assert params["soldto_val"] == "Brugmann Hospital"
    assert params["duration_val"] == "2"
    assert params["time_unit_val"] == "Year"
    assert params["ttype_val"] == "ZQDS"
    assert params["pricing_val"] == "ZTAF"
    assert params["price_all_items"] is True
    assert len(params["extracted_items"]) == 2
    assert params["extracted_items"][0] == ("45157510101", "1")
    assert params["extracted_items"][1] == ("45157510707", "1")

    # Generate suite using TestDesigner with resilient fallback
    mock_llm = MagicMock()
    mock_llm.generate.side_effect = Exception("LLM fallback trigger")
    designer = TestDesigner(llm_client=mock_llm)
    suite = designer.generate_suite(
        requirement=req,
        target_base_url="https://s4srv25.nodomain.com:44325/sap/bc/ui2/flp",
    )

    assert len(suite.test_cases) == 2
    tc1, tc2 = suite.test_cases[0], suite.test_cases[1]
    assert tc1.id == "TC-01"
    assert tc2.id == "TC-02"

    # TC-01: Must include table entry for both items
    assert any(s.input_value == "45157510101" for s in tc1.steps)
    assert any(s.input_value == "45157510707" for s in tc1.steps)

    # TC-01: Must include pricing drilldown for item 1
    assert any("item 1 details" in (s.description or "").lower() for s in tc1.steps)
    assert any("Price Details tab for item 1" in (s.description or "") for s in tc1.steps)
    assert any("pricing element button for item 1" in (s.description or "").lower() for s in tc1.steps)
    assert any("ZTAF from popup for item 1" in (s.description or "") for s in tc1.steps)
    assert any("Back to return to quotation from item 1" in (s.description or "") for s in tc1.steps)

    # TC-01: Must include pricing drilldown for item 2
    assert any("item 2 details" in (s.description or "").lower() for s in tc1.steps)
    assert any("Price Details tab for item 2" in (s.description or "") for s in tc1.steps)
    assert any("pricing element button for item 2" in (s.description or "").lower() for s in tc1.steps)
    assert any("ZTAF from popup for item 2" in (s.description or "") for s in tc1.steps)
    assert any("Back to return to quotation from item 2" in (s.description or "") for s in tc1.steps)

    # TC-01: Releases and accepts
    assert any("Released" in (s.selector_value or "") for s in tc1.steps)
    assert any("Accept" in (s.description or "") for s in tc1.steps)
    assert any("Transaction History" in (s.description or "") for s in tc1.steps)

    # TC-02: Receives ${OPERATIONAL_DOCUMENT} and validates Manage Revenue Contracts
    op_step = next(s for s in tc2.steps if s.input_value == "${OPERATIONAL_DOCUMENT}")
    assert op_step.selector_value == "Operational Document:"
    assert any("Go" in (s.description or "") for s in tc2.steps)
    assert any("Revenue Contract" in (s.expected_value or "") for s in tc2.steps)
