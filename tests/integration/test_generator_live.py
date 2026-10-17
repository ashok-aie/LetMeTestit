"""
Phase 8 Live Integration Test: TestDesigner with Local Ollama qwen2.5:7b
Verifies real end-to-end synthesis of an SAP Material Order TestSuite using the local LLM.
"""
import pytest
from app.models.requirements import JiraRequirement
from app.models.test_suite import TestSuite
from app.test_design.generator import TestDesigner
from app.agents.llm_client import OllamaClient


@pytest.mark.integration
def test_live_ollama_generate_sap_test_suite():
    """Verify that qwen2.5:7b generates a valid, executable SAP TestSuite from a requirement."""
    client = OllamaClient()
    assert client.is_healthy(), "Ollama daemon must be running"

    sap_requirement = JiraRequirement(
        key="SAP-301",
        summary="Create Material Sales Order with Customer ID and Material Validation in SAP",
        description_text="""## User Story
As a Sales & Logistics Clerk, I want to create a Material Sales Order in SAP S/4HANA for customer CUST-1001 with 3 units of MAT-1001.

## Acceptance Criteria
- AC-01: User navigates to the SAP order page.
- AC-02: User fills Sold-to Party with CUST-1001 and selects material MAT-1001.
- AC-03: User clicks Submit Sales Order and verifies the success banner is visible.
- AC-04: If customer ID is omitted, system must display an error banner stating Sold-to Party is mandatory.
""",
        status="To Do",
        labels=["SAP", "SalesOrder"],
    )

    designer = TestDesigner(llm_client=client, max_retries=2)
    suite: TestSuite = designer.generate_suite(sap_requirement, target_base_url="http://localhost:8000")

    # Assertions on generated suite
    assert isinstance(suite, TestSuite)
    assert suite.requirement_key == "SAP-301"
    assert len(suite.test_cases) >= 2, f"Expected at least 2 test cases, got {len(suite.test_cases)}"

    # Check for both positive and negative/validation coverage
    categories = {tc.category.value for tc in suite.test_cases}
    assert "positive" in categories, f"Expected positive test case in {categories}"
    assert any(c in categories for c in ("negative", "validation")), f"Expected negative or validation test in {categories}"

    # Verify steps are well-formed
    for tc in suite.test_cases:
        assert len(tc.steps) > 0
        assert tc.steps[0].action.value == "navigate"

    # Verify SHA-256 hash is generated
    suite_hash = suite.compute_hash()
    assert len(suite_hash) == 64

