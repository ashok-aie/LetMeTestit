"""
LangGraph Workflow Definition for Let me TEST it....!
Builds and compiles the Quality Engineering StateGraph with cyclic self-correction,
cryptographic verification, and human-in-the-loop interruption gates.
"""
from typing import Optional, List, Literal
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.graph.state import AgentState
from app.graph.nodes import WorkflowNodes
from app.persistence.checkpointer import get_memory_checkpointer


def route_after_validation(
    state: AgentState,
) -> Literal["human_review", "generate_test_cases", "handle_failure"]:
    """Routes after schema validation: proceed to review, retry generation, or fail."""
    status = state.get("status")
    retry_count = state.get("retry_count", 0)

    if status == "TESTS_VALIDATED":
        return "human_review"
    if retry_count < 2:
        return "generate_test_cases"
    return "handle_failure"


def route_after_review(
    state: AgentState,
) -> Literal["validate_approval", "finalize_run", "human_review"]:
    """Routes based on human review decision: approve, reject, or wait."""
    status = state.get("status")
    if status == "REVIEW_APPROVED":
        return "validate_approval"
    if status == "REVIEW_REJECTED":
        return "finalize_run"
    return "human_review"


def route_after_approval_validation(
    state: AgentState,
) -> Literal["execute_test_suite", "handle_failure"]:
    """Routes based on cryptographic hash and security policy validation."""
    if state.get("status") == "APPROVAL_VALIDATED":
        return "execute_test_suite"
    return "handle_failure"


def route_after_report(
    state: AgentState,
) -> Literal["prepare_defect_drafts", "finalize_run"]:
    """Routes based on test outcomes: prepare defects if failures exist, else finalize."""
    run = state.get("execution_run")
    if run and run.failed_tests > 0:
        return "prepare_defect_drafts"
    return "finalize_run"


def route_after_defect_review(
    state: AgentState,
) -> Literal["create_jira_defect", "finalize_run"]:
    """Routes based on defect approval: create in Jira or finalize."""
    if state.get("approved_defect_ids"):
        return "create_jira_defect"
    return "finalize_run"


def build_testpilot_graph(
    nodes: Optional[WorkflowNodes] = None,
    checkpointer: Optional[BaseCheckpointSaver] = None,
    interrupt_nodes: Optional[List[str]] = None,
):
    """
    Constructs and compiles the complete LangGraph StateGraph for TestPilot AI.

    Args:
        nodes: Optional WorkflowNodes instance with injected dependencies.
        checkpointer: State checkpointer (SQLite or MemorySaver).
        interrupt_nodes: List of node names to pause before for human approval.
                         Defaults to ['human_review', 'human_approve_defect'].

    Returns:
        Compiled LangGraph application.
    """
    workflow_nodes = nodes or WorkflowNodes()
    builder = StateGraph(AgentState)

    # 1. Register all nodes
    builder.add_node("fetch_requirement", workflow_nodes.fetch_requirement)
    builder.add_node("normalize_requirement", workflow_nodes.normalize_requirement)
    builder.add_node("assess_completeness", workflow_nodes.assess_completeness)
    builder.add_node("generate_test_cases", workflow_nodes.generate_test_cases)
    builder.add_node("validate_test_cases", workflow_nodes.validate_test_cases)
    builder.add_node("human_review", workflow_nodes.human_review)
    builder.add_node("validate_approval", workflow_nodes.validate_approval)
    builder.add_node("execute_test_suite", workflow_nodes.execute_test_suite)
    builder.add_node("classify_results", workflow_nodes.classify_results)
    builder.add_node("generate_report", workflow_nodes.generate_report)
    builder.add_node("prepare_defect_drafts", workflow_nodes.prepare_defect_drafts)
    builder.add_node("human_approve_defect", workflow_nodes.human_approve_defect)
    builder.add_node("create_jira_defect", workflow_nodes.create_jira_defect)
    builder.add_node("finalize_run", workflow_nodes.finalize_run)
    builder.add_node("handle_failure", workflow_nodes.handle_failure)

    # 2. Add sequential flow edges
    builder.add_edge(START, "fetch_requirement")
    builder.add_edge("fetch_requirement", "normalize_requirement")
    builder.add_edge("normalize_requirement", "assess_completeness")
    builder.add_edge("assess_completeness", "generate_test_cases")
    builder.add_edge("generate_test_cases", "validate_test_cases")

    # 3. Add conditional self-correction edge
    builder.add_conditional_edges(
        "validate_test_cases",
        route_after_validation,
        {
            "human_review": "human_review",
            "generate_test_cases": "generate_test_cases",
            "handle_failure": "handle_failure",
        },
    )

    # 4. Add human-in-the-loop review decision edge
    builder.add_conditional_edges(
        "human_review",
        route_after_review,
        {
            "validate_approval": "validate_approval",
            "finalize_run": "finalize_run",
            "human_review": "human_review",
        },
    )

    # 5. Add security & checksum gate edge
    builder.add_conditional_edges(
        "validate_approval",
        route_after_approval_validation,
        {
            "execute_test_suite": "execute_test_suite",
            "handle_failure": "handle_failure",
        },
    )

    # 6. Add execution to results & reporting
    builder.add_edge("execute_test_suite", "classify_results")
    builder.add_edge("classify_results", "generate_report")

    # 7. Add defect routing edge
    builder.add_conditional_edges(
        "generate_report",
        route_after_report,
        {
            "prepare_defect_drafts": "prepare_defect_drafts",
            "finalize_run": "finalize_run",
        },
    )

    builder.add_edge("prepare_defect_drafts", "human_approve_defect")

    # 8. Add defect approval routing edge
    builder.add_conditional_edges(
        "human_approve_defect",
        route_after_defect_review,
        {
            "create_jira_defect": "create_jira_defect",
            "finalize_run": "finalize_run",
        },
    )

    builder.add_edge("create_jira_defect", "finalize_run")
    builder.add_edge("finalize_run", END)
    builder.add_edge("handle_failure", END)

    # 9. Configure checkpointer & interruption gates
    effective_checkpointer = checkpointer or get_memory_checkpointer()
    default_interrupts = ["human_review", "human_approve_defect"]
    actual_interrupts = default_interrupts if interrupt_nodes is None else interrupt_nodes

    return builder.compile(
        checkpointer=effective_checkpointer,
        interrupt_before=actual_interrupts if actual_interrupts else None,
    )

