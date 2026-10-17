"""
Typed State Contract for the LangGraph Quality Engineering Engine.
Defines the shared state dictionary flowing through all workflow nodes and interruption gates.
"""
from typing import TypedDict, Optional, List, Dict, Any
from app.models.requirements import JiraRequirement, AcceptanceCriterion
from app.models.test_suite import TestSuite
from app.models.execution import ApprovalRecord, ExecutionRun
from app.models.defects import DefectDraft


class AgentState(TypedDict, total=False):
    """
    Primary state graph payload passed between LangGraph nodes.
    Supports partial state updates across acyclic and cyclic execution stages.
    """
    # Ingestion inputs
    issue_key: Optional[str]
    raw_requirement_text: Optional[str]
    target_url: Optional[str]
    headless: Optional[bool]
    slow_mo_ms: Optional[int]

    # Ingested & Analyzed Requirement
    jira_requirement: Optional[JiraRequirement]
    acceptance_criteria: List[AcceptanceCriterion]

    # Test Suite Synthesis & Self-Correction
    test_suite: Optional[TestSuite]
    retry_count: int
    generation_feedback: Optional[str]

    # Human-in-the-Loop Governance & Approvals
    approval_record: Optional[ApprovalRecord]

    # Browser Execution & Evidence Collection
    execution_run: Optional[ExecutionRun]

    # Defect Remediation
    defect_drafts: List[DefectDraft]
    approved_defect_ids: List[str]
    created_defects: List[Dict[str, Any]]

    # Workflow Lifecycle State & Diagnostic Error Tracking
    status: str
    error: Optional[str]

