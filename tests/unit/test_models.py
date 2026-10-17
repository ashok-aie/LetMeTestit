"""
Phase 7 Unit Tests: Pydantic Data Contracts & Schemas
Verifies TestSuite validation, SHA-256 cryptographic hashing, ApprovalRecords,
ExecutionRun models, and DefectDraft markdown formatting.
"""
import pytest
from app.models.test_suite import (
    TestSuite,
    TestCase,
    TestStep,
    ActionType,
    LocatorStrategy,
    TestCategory,
)
from app.models.execution import (
    ApprovalRecord,
    ApprovalDecision,
    ExecutionRun,
    TestCaseResult,
    TestStepResult,
    TestOutcome,
    FailureClassification,
)
from app.models.defects import DefectDraft


def test_test_suite_validation_and_hash():
    """Verify TestSuite validation and cryptographic SHA-256 checksum generation."""
    suite = TestSuite(
        suite_id="SUITE-ERP-205",
        requirement_key="ERP-205",
        version=1,
        test_cases=[
            TestCase(
                id="TC-01",
                requirement_key="ERP-205",
                source_ac_id="AC-01",
                title="Create valid SAP Sales Order",
                objective="Verify user can order material MAT-1001 with quantity 4",
                category=TestCategory.POSITIVE,
                steps=[
                    TestStep(
                        step_number=1,
                        action=ActionType.NAVIGATE,
                        input_value="http://localhost:8000/",
                        description="Navigate to SAP Order screen",
                    ),
                    TestStep(
                        step_number=2,
                        action=ActionType.FILL,
                        locator_strategy=LocatorStrategy.TEST_ID,
                        selector_value="customer-id-input",
                        input_value="CUST-1001",
                        description="Enter Sold-to Party",
                    ),
                    TestStep(
                        step_number=3,
                        action=ActionType.CLICK,
                        locator_strategy=LocatorStrategy.ROLE,
                        role_name="button",
                        selector_value="Submit Sales Order",
                        description="Submit order",
                    ),
                ],
                expected_result="Order created and visible in ERP ledger",
            )
        ],
    )

    # 1. Assert validation passed
    assert suite.suite_id == "SUITE-ERP-205"
    assert len(suite.test_cases) == 1
    assert len(suite.test_cases[0].steps) == 3

    # 2. Check SHA-256 hash
    hash1 = suite.compute_hash()
    assert len(hash1) == 64
    assert hash1 == suite.compute_hash(), "Hash must be deterministic for identical content"

    # 3. Cryptographic integrity: altering a step alters the hash
    suite.test_cases[0].steps[1].input_value = "CUST-DIFFERENT"
    hash2 = suite.compute_hash()
    assert hash1 != hash2, "Modifying suite content must change the SHA-256 hash"


def test_approval_record_validation():
    """Verify ApprovalRecord with decision and checksum."""
    approval = ApprovalRecord(
        approval_id="APP-001",
        suite_id="SUITE-ERP-205",
        suite_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        reviewer="alex.qa@company.com",
        decision=ApprovalDecision.APPROVED,
        comments="All 4 acceptance criteria covered.",
    )
    assert approval.decision == ApprovalDecision.APPROVED
    assert approval.reviewer == "alex.qa@company.com"
    assert approval.suite_hash is not None


def test_execution_run_and_failure_classification():
    """Verify ExecutionRun structure and failure categorization."""
    run = ExecutionRun(
        run_id="RUN-1001",
        suite_id="SUITE-ERP-205",
        environment="local",
        target_url="http://localhost:8000/",
        total_tests=1,
        failed_tests=1,
        results=[
            TestCaseResult(
                test_case_id="TC-01",
                outcome=TestOutcome.FAIL,
                classification=FailureClassification.APPLICATION_DEFECT,
                duration_seconds=1.45,
                step_results=[
                    TestStepResult(
                        step_number=1,
                        action=ActionType.NAVIGATE,
                        duration_ms=250.0,
                        passed=True,
                    ),
                    TestStepResult(
                        step_number=2,
                        action=ActionType.ASSERT_TEXT,
                        duration_ms=120.0,
                        passed=False,
                        actual_value="Error 500 Internal Server",
                        error_message="Expected 'Order Created' but found 'Error 500'",
                    ),
                ],
                failure_message="Assertion failed on step 2",
                screenshot_path="artifacts/runs/RUN-1001/screenshots/TC-01_failure.png",
            )
        ],
    )
    assert run.results[0].outcome == TestOutcome.FAIL
    assert run.results[0].classification == FailureClassification.APPLICATION_DEFECT
    assert len(run.results[0].step_results) == 2


def test_defect_draft_markdown_formatting():
    """Verify DefectDraft generates structured Jira markdown for ticket submission."""
    draft = DefectDraft(
        draft_id="DRAFT-01",
        parent_issue_key="ERP-205",
        test_case_id="TC-01",
        summary="Order total mismatch on Industrial Steel Coil",
        steps_to_reproduce=[
            "Navigate to http://localhost:8000/",
            "Select MAT-1001 and enter quantity 4",
            "Click Submit Sales Order",
        ],
        expected_result="Order net value equals $1800.00",
        actual_result="Order net value displayed $0.00",
        evidence_paths=["artifacts/runs/RUN-1001/screenshots/TC-01.png"],
    )

    md = draft.to_markdown_description()
    assert "h2. Bug Summary" in md
    assert "1. Navigate to http://localhost:8000/" in md
    assert "Expected Result" in md
    assert "Order net value displayed $0.00" in md
    assert "artifacts/runs/RUN-1001/screenshots/TC-01.png" in md


def test_defect_draft_summary_truncation():
    """Verify DefectDraft automatically sanitizes newlines and bounds summary to <= 250 chars."""
    long_msg = "A" * 300 + "\nSecond line with error details"
    draft = DefectDraft(
        draft_id="DRAFT-02",
        parent_issue_key="KAN-4",
        test_case_id="TC-02",
        summary=f"[Defect] Automated failure: {long_msg}",
        expected_result="Pass",
        actual_result="Fail",
    )
    assert len(draft.summary) <= 250
    assert "\n" not in draft.summary
    assert draft.summary.endswith("...")


