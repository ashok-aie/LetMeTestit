from unittest.mock import MagicMock
import pytest
from app.test_design.generator import TestDesigner
from app.models.requirements import JiraRequirement, AcceptanceCriterion
from app.graph.nodes import WorkflowNodes

def test_kan25_multi_ac_split_and_parameterization():
    raw_text = """Validate the SAP Fiori Solution Quotation bundle from creation and acceptance through sales order, fulfillment, billing, SAP RAR contract/obligation processing, revenue recognition, accounting validation, and safe reprocessing.

Preconditions / Notes: Create the quotation in SAP Fiori Service Quotations; transaction type ZQDS; sold-to Brugmann Hospital; main product 45157510101; quantity 1; 

In Service Quotation application, start new Quotation.
Select Transaction Type ZQDV — CE-Direct Sales
Give Description as 'RAR test'  and Sold-to Party as Brugmann Hospital
In the ‘Dates’ tab, In ‘Term of Quotation’ and give its Duration as 24 and Time Unit as Months

In Items tab, 
Product ID is 45157510101 and Quantity is 1 
Product ID 45157510707 (Sales Material); quantity 1; 
Product ID 45157022301 (Equipment Item - RUI) ; quantity 1;
Product ID 45157022302 (Equipment Item - SUI)  ; quantity 1;
Product ID 45157022900 (Digital Subscription - DS)  ; quantity 1;

Click on the Product Name, the product's item details will appear
In the Price details tab, click on Add button, then select a pricing element ZTAF 
Click on back to return to the quotation and Save the Quotation.
Click on Edit to Change status to Released and save
Then Accept the quotation.
Capture the Quotation number and status changes are recorded as evidence.
Copy Transaction id from Transaction History to use in “Manage Revenue Contracts”
Navigate to ‘Manage Revenue Contracts’ 
Then Navigate to Revenue contract popup, enter the Transaction id in Operational Document and click enter
Select all the Items with same Operational Document then click ok
Then click Go in the Manage Revenue Contract 
Click on Revenue Contract to view details

AC-01 (Multi-Item Service Quotation with Downstream RAR Contract Creation):
Verify that a Service Quotation of transaction type ZQDS can be created with Sold-to Party Brugmann Hospital, Term of 24 Months, containing 5 line items,  Product ID is 45157510101 and its  Quantity is 1, Product ID 45157510707 (Sales Material) and its quantity 1, Product ID 45157022301 (Equipment Item - RUI) and its quantity 1, Product ID 45157022302 (Equipment Item - SUI)   and its quantity 2, Product ID 45157022900 (Digital Subscription - DS)  and its quantity 1, price condition ZTAF added to Item 1, released, accepted,

AC-02 The resulting Operational Document successfully appears in Manage Revenue Contracts.. Also, can you update the knowledge base for Solution Qutoation flow and Manage Revenue contracts flow so that they can be help full in writing test case acurately and execution accurately.
"""

    nodes = WorkflowNodes()
    state = {"raw_requirement_text": raw_text, "issue_key": "TEST-25"}
    state.update(nodes.fetch_requirement(state))
    state.update(nodes.normalize_requirement(state))
    state.update(nodes.assess_completeness(state))
    req = state["jira_requirement"]

    # Verify both ACs extracted
    assert len(req.acceptance_criteria) == 2
    assert req.acceptance_criteria[0].id == "AC-01"
    assert "45157022302" in req.acceptance_criteria[0].text
    assert req.acceptance_criteria[1].id == "AC-02"
    assert "Manage Revenue Contracts" in req.acceptance_criteria[1].text

    mock_llm = MagicMock()
    mock_llm.generate.side_effect = Exception("LLM fallback trigger")
    designer = TestDesigner(llm_client=mock_llm)
    suite = designer.generate_suite(
        requirement=req,
        target_base_url="https://s4srv25.nodomain.com:44325/sap/bc/ui2/flp",
    )

    # 1. Verify two distinct test cases generated
    assert len(suite.test_cases) == 2
    tc1, tc2 = suite.test_cases[0], suite.test_cases[1]
    assert tc1.id == "TC-01"
    assert tc2.id == "TC-02"

    # 2. Verify TC-01: Parameterized Transaction Type ZQDS
    ttype_step = next(s for s in tc1.steps if "Transaction Type" in (s.description or ""))
    assert ttype_step.selector_value == "ZQDS"

    # 3. Verify TC-01: Multi-product line items with row-specific indexing and quantities
    p1 = next(s for s in tc1.steps if s.input_value == "45157510101")
    p4 = next(s for s in tc1.steps if s.input_value == "45157022302")
    q4 = next(s for s in tc1.steps if s.input_value == "2" and "item 4" in (s.description or "").lower())
    assert "table[1]" in p1.selector_value
    assert "table[4]" in p4.selector_value
    assert "table[4]" in q4.selector_value

    # 4. Verify TC-01 terminates at Transaction History capture + logoff (does NOT include Manage Revenue Contracts)
    assert any("Transaction History" in (s.description or "") for s in tc1.steps)
    assert not any("Manage Revenue Contracts" in (s.description or "") for s in tc1.steps)

    # 5. Verify TC-02: Manage Revenue Contracts with ${OPERATIONAL_DOCUMENT}
    assert any("Manage Revenue Contracts" in (s.description or "") for s in tc2.steps)
    op_step = next(s for s in tc2.steps if s.input_value == "${OPERATIONAL_DOCUMENT}")
    assert op_step.selector_value == "Operational Document:"
    assert any("Go" in (s.description or "") for s in tc2.steps)
    assert any("Revenue Contract" in (s.expected_value or "") for s in tc2.steps)
