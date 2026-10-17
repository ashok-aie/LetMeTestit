"""
Unit & Integration Tests for LangGraph Workflow Orchestration (Phase 9).
Tests compile integrity, Human-in-the-Loop interruption gates, cryptographic checksums,
security guardrails, defect drafting, and SQLite persistence.
"""
from typing import List, Optional
import pytest
from uuid import uuid4

from app.graph.state import AgentState
from app.graph.nodes import WorkflowNodes
from app.graph.workflow import build_testpilot_graph
from app.models.requirements import JiraRequirement, AcceptanceCriterion
from app.models.test_suite import TestSuite, TestCase, TestStep, ActionType, LocatorStrategy, TestCategory
from app.models.execution import (
    ApprovalRecord,
    ApprovalDecision,
    ExecutionRun,
    TestCaseResult,
    TestStepResult,
    TestOutcome,
)
from app.persistence.checkpointer import get_memory_checkpointer, get_sqlite_checkpointer
from app.policies.guardrails import PolicyEngine


class MockTestDesigner:
    """Deterministic TestDesigner for fast unit testing of workflow state transitions."""
    __test__ = False

    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.call_count = 0

    def generate_suite(
        self,
        requirement: JiraRequirement,
        target_base_url: Optional[str] = None,
    ) -> TestSuite:
        self.call_count += 1
        if self.should_fail:
            raise ValueError("Simulated schema generation error")

        steps = [
            TestStep(
                step_number=1,
                action=ActionType.NAVIGATE,
                input_value=target_base_url or "http://127.0.0.1:8000",
                description="Navigate to SAP Order Portal",
            ),
            TestStep(
                step_number=2,
                action=ActionType.ASSERT_TEXT,
                locator_strategy=LocatorStrategy.TEST_ID,
                selector_value="page-title",
                expected_value="Sales Order Overview",
                description="Verify Fiori dashboard header",
            ),
        ]

        test_case = TestCase(
            id="TC-01",
            requirement_key=requirement.key,
            source_ac_id="AC-01",
            title="Verify Fiori dashboard loads correctly",
            objective="Ensure material sales order page is accessible",
            category=TestCategory.POSITIVE,
            steps=steps,
            expected_result="Page loaded with title Sales Order Overview",
        )

        return TestSuite(
            suite_id=f"SUITE-{requirement.key}-V1",
            requirement_key=requirement.key,
            test_cases=[test_case],
        )


class MockTestExecutor:
    """Deterministic MockTestExecutor for fast unit testing of workflow state transitions."""
    __test__ = False

    def execute_suite(self, suite: TestSuite, target_url: Optional[str] = None) -> ExecutionRun:
        run = ExecutionRun(
            run_id="RUN-MOCK-01",
            suite_id=suite.suite_id,
            target_url=target_url or "http://127.0.0.1:8000",
            total_tests=len(suite.test_cases),
        )
        for tc in suite.test_cases:
            run.results.append(
                TestCaseResult(
                    test_case_id=tc.id,
                    outcome=TestOutcome.PASS,
                    duration_seconds=0.05,
                    step_results=[
                        TestStepResult(
                            step_number=s.step_number,
                            action=s.action,
                            duration_ms=10.0,
                            passed=True,
                        )
                        for s in tc.steps
                    ],
                )
            )
        return run


@pytest.fixture
def mock_nodes():
    return WorkflowNodes(
        test_designer=MockTestDesigner(),
        policy_engine=PolicyEngine(allowed_domains=["127.0.0.1", "localhost"]),
        test_executor=MockTestExecutor(),
    )


def test_graph_compilation_with_checkpointers(tmp_path):
    """Verifies that the LangGraph StateGraph compiles with both Memory and SQLite savers."""
    memory_saver = get_memory_checkpointer()
    graph_mem = build_testpilot_graph(checkpointer=memory_saver)
    assert graph_mem is not None

    sqlite_db = tmp_path / "checkpoints.db"
    sqlite_saver = get_sqlite_checkpointer(str(sqlite_db))
    graph_sqlite = build_testpilot_graph(checkpointer=sqlite_saver)
    assert graph_sqlite is not None


def test_linear_flow_to_human_review_interrupt(mock_nodes):
    """
    Tests that a new requirement flows through ingestion, normalization,
    AC assessment, and test generation, then halts BEFORE human_review.
    """
    graph = build_testpilot_graph(nodes=mock_nodes)
    config = {"configurable": {"thread_id": "test-session-01"}}

    raw_req = """As a Sales Rep, I need to create standard sales orders.
    AC-01: User can navigate to the order creation screen.
    AC-02: User can select a valid customer and material.
    """

    # Initial invoke
    graph.invoke({"raw_requirement_text": raw_req, "issue_key": "SAP-101"}, config)

    # Inspect paused state
    state = graph.get_state(config)
    assert state.next == ("human_review",)
    assert state.values["status"] == "TESTS_VALIDATED"
    assert state.values["jira_requirement"] is not None
    assert len(state.values["acceptance_criteria"]) >= 2
    assert state.values["test_suite"] is not None
    assert len(state.values["test_suite"].test_cases) == 1


def test_human_review_approval_and_execution_completion(mock_nodes):
    """
    Tests the complete happy path:
    1. Pauses at human_review
    2. QA engineer signs ApprovalRecord with matching SHA-256 hash
    3. Resumes graph
    4. Validates approval, runs tests, classifies results, completes.
    """
    graph = build_testpilot_graph(nodes=mock_nodes)
    config = {"configurable": {"thread_id": "test-session-02"}}

    raw_req = "AC-01: Order dashboard must render."
    graph.invoke({"raw_requirement_text": raw_req, "issue_key": "SAP-102"}, config)

    # Verify paused at human_review
    state_before = graph.get_state(config)
    assert state_before.next == ("human_review",)
    suite = state_before.values["test_suite"]

    # Human QA approves the suite
    approval = ApprovalRecord(
        approval_id="APP-001",
        suite_id=suite.suite_id,
        suite_hash=suite.compute_hash(),
        reviewer="qa.engineer@enterprise.com",
        decision=ApprovalDecision.APPROVED,
        comments="Looks good, ready to execute.",
    )

    # Update checkpointed state and resume
    graph.update_state(config, {"approval_record": approval})
    graph.invoke(None, config)

    # Verify final state
    state_after = graph.get_state(config)
    assert state_after.next == ()  # Reached END
    assert state_after.values["status"] == "COMPLETED"
    run = state_after.values["execution_run"]
    assert run is not None
    assert run.passed_tests == 1
    assert run.failed_tests == 0


def test_human_review_rejection_halts_without_execution(mock_nodes):
    """
    Tests that if a human rejects the suite, execution is skipped and run terminates.
    """
    graph = build_testpilot_graph(nodes=mock_nodes)
    config = {"configurable": {"thread_id": "test-session-03"}}

    graph.invoke({"raw_requirement_text": "AC-01: Order dashboard renders."}, config)
    suite = graph.get_state(config).values["test_suite"]

    # Reject
    rejection = ApprovalRecord(
        approval_id="APP-002",
        suite_id=suite.suite_id,
        suite_hash=suite.compute_hash(),
        reviewer="qa.lead@enterprise.com",
        decision=ApprovalDecision.REJECTED,
        comments="Missing boundary scenarios.",
    )

    graph.update_state(config, {"approval_record": rejection})
    graph.invoke(None, config)

    state_after = graph.get_state(config)
    assert state_after.next == ()
    assert state_after.values["status"] == "COMPLETED"
    assert state_after.values.get("execution_run") is None


def test_cryptographic_checksum_tampering_defense(mock_nodes):
    """
    Ensures that if the test suite is modified after human sign-off (hash mismatch),
    the workflow halts immediately with an error and refuses to execute.
    """
    graph = build_testpilot_graph(nodes=mock_nodes)
    config = {"configurable": {"thread_id": "test-session-04"}}

    graph.invoke({"raw_requirement_text": "AC-01: Order dashboard renders."}, config)
    suite = graph.get_state(config).values["test_suite"]

    # Invalid / forged hash
    tampered_approval = ApprovalRecord(
        approval_id="APP-003",
        suite_id=suite.suite_id,
        suite_hash="0000000000000000000000000000000000000000000000000000000000000000",
        reviewer="attacker@unauthorized.com",
        decision=ApprovalDecision.APPROVED,
    )

    graph.update_state(config, {"approval_record": tampered_approval})
    graph.invoke(None, config)

    state_after = graph.get_state(config)
    assert state_after.values["status"] == "FAILED"
    assert "Cryptographic suite checksum mismatch" in state_after.values["error"]
    assert state_after.values.get("execution_run") is None


def test_security_policy_guardrail_url_block(mock_nodes):
    """
    Ensures that if a test case attempts to navigate to an unauthorized domain,
    PolicyEngine blocks it during approval validation before execution.
    """
    graph = build_testpilot_graph(nodes=mock_nodes)
    config = {"configurable": {"thread_id": "test-session-05"}}

    graph.invoke({"raw_requirement_text": "AC-01: Order dashboard renders."}, config)
    suite = graph.get_state(config).values["test_suite"]

    # Modify step URL to forbidden external domain
    suite.test_cases[0].steps[0].input_value = "https://malicious-external-site.com"

    # Sign with new hash matching the modified suite so hash matches, but policy fails
    approval = ApprovalRecord(
        approval_id="APP-004",
        suite_id=suite.suite_id,
        suite_hash=suite.compute_hash(),
        reviewer="qa.engineer@enterprise.com",
        decision=ApprovalDecision.APPROVED,
    )

    graph.update_state(config, {"test_suite": suite, "approval_record": approval})
    graph.invoke(None, config)

    state_after = graph.get_state(config)
    assert state_after.values["status"] == "FAILED"
    assert "Security Guardrail Violation" in state_after.values["error"]
    assert state_after.values.get("execution_run") is None


def test_defect_draft_generation_on_test_failure(mock_nodes):
    """
    Tests defect workflow:
    1. Simulates a test failure in execution run.
    2. Workflow creates DefectDraft and pauses at human_approve_defect.
    3. QA approves the defect draft.
    4. Workflow submits defect and completes.
    """
    # Custom node with simulated execution failure
    class FailingExecutionNodes(WorkflowNodes):
        def execute_test_suite(self, state: AgentState):
            suite = state["test_suite"]
            run = ExecutionRun(
                run_id="RUN-FAIL-01",
                suite_id=suite.suite_id,
                target_url="http://127.0.0.1:8000",
                total_tests=1,
            )
            run.results = [
                TestCaseResult(
                    test_case_id="TC-01",
                    outcome=TestOutcome.FAIL,
                    duration_seconds=0.1,
                    failure_message="Expected 'Sales Order Overview' but found '500 Internal Error'",
                    screenshot_path="artifacts/runs/RUN-FAIL-01/screenshot_TC-01.png",
                )
            ]
            return {"execution_run": run, "status": "EXECUTION_COMPLETED"}

    failing_nodes = FailingExecutionNodes(
        test_designer=mock_nodes.test_designer,
        policy_engine=mock_nodes.policy_engine,
    )

    graph = build_testpilot_graph(nodes=failing_nodes)
    config = {"configurable": {"thread_id": "test-session-06"}}

    graph.invoke({"raw_requirement_text": "AC-01: Order dashboard renders."}, config)
    suite = graph.get_state(config).values["test_suite"]

    # Approve test suite
    approval = ApprovalRecord(
        approval_id="APP-005",
        suite_id=suite.suite_id,
        suite_hash=suite.compute_hash(),
        reviewer="qa.engineer@enterprise.com",
        decision=ApprovalDecision.APPROVED,
    )
    graph.update_state(config, {"approval_record": approval})
    graph.invoke(None, config)

    # Verify pause at defect gate
    state_defect_gate = graph.get_state(config)
    assert state_defect_gate.next == ("human_approve_defect",)
    drafts = state_defect_gate.values["defect_drafts"]
    assert len(drafts) == 1
    assert drafts[0].test_case_id == "TC-01"
    assert "500 Internal Error" in drafts[0].actual_result

    # Human QA approves filing the defect
    graph.update_state(config, {"approved_defect_ids": [drafts[0].draft_id]})
    graph.invoke(None, config)

    # Verify final defect creation
    final_state = graph.get_state(config)
    assert final_state.next == ()
    assert final_state.values["status"] == "COMPLETED"
    assert len(final_state.values["created_defects"]) == 1
    assert final_state.values["created_defects"][0]["draft_id"] == drafts[0].draft_id


def test_sqlite_checkpointer_cross_instance_recovery(tmp_path, mock_nodes):
    """
    Tests that workflow checkpoints are fully durable in SQLite and can be
    recovered and resumed by a completely separate graph instance.
    """
    db_file = str(tmp_path / "persistent_testpilot.db")
    saver1 = get_sqlite_checkpointer(db_file)
    graph1 = build_testpilot_graph(nodes=mock_nodes, checkpointer=saver1)

    thread_id = "durable-session-07"
    config = {"configurable": {"thread_id": thread_id}}

    # Instance 1: runs to pause
    graph1.invoke({"raw_requirement_text": "AC-01: Durable persistence test."}, config)
    state1 = graph1.get_state(config)
    assert state1.next == ("human_review",)
    suite = state1.values["test_suite"]

    # Instance 2: brand new saver & graph instance pointing to same SQLite DB
    saver2 = get_sqlite_checkpointer(db_file)
    graph2 = build_testpilot_graph(nodes=mock_nodes, checkpointer=saver2)

    # Verify Instance 2 sees the exact paused checkpoint
    state2 = graph2.get_state(config)
    assert state2.next == ("human_review",)
    assert state2.values["test_suite"].suite_id == suite.suite_id

    # Instance 2 updates state and completes
    approval = ApprovalRecord(
        approval_id="APP-007",
        suite_id=suite.suite_id,
        suite_hash=suite.compute_hash(),
        reviewer="qa.persistent@enterprise.com",
        decision=ApprovalDecision.APPROVED,
    )
    graph2.update_state(config, {"approval_record": approval})
    graph2.invoke(None, config)

    final_state2 = graph2.get_state(config)
    assert final_state2.next == ()
    assert final_state2.values["status"] == "COMPLETED"

