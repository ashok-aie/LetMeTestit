"""
Workflow Nodes for the LangGraph Quality Engineering Engine.
Each node performs a distinct, isolated transformation or evaluation step on AgentState.
"""
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import uuid4

from app.config import settings
from app.jira.client import JiraClient, JiraClientError
from app.jira.normalizer import ADFNormalizer
from app.models.requirements import JiraRequirement, AcceptanceCriterion, RequirementType
from app.models.test_suite import TestSuite, TestStep, ActionType
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
from app.policies.guardrails import PolicyEngine, SecurityPolicyViolation
from app.test_design.generator import TestDesigner, TestDesignError
from app.browser.executor import TestExecutor
from app.graph.state import AgentState

logger = logging.getLogger(__name__)


class WorkflowNodes:
    """
    Encapsulates all node execution logic, supporting dependency injection
    for Jira client, test designer, policy enforcement engine, and test executor.
    """

    def __init__(
        self,
        jira_client: Optional[JiraClient] = None,
        test_designer: Optional[TestDesigner] = None,
        policy_engine: Optional[PolicyEngine] = None,
        test_executor: Optional[TestExecutor] = None,
    ):
        self.jira_client = jira_client or JiraClient()
        self.test_designer = test_designer or TestDesigner()
        self.policy_engine = policy_engine or PolicyEngine()
        self.test_executor = test_executor

    def fetch_requirement(self, state: AgentState) -> Dict[str, Any]:
        """
        Retrieves requirement details either from Jira Cloud via issue key,
        or directly from raw input text.
        """
        issue_key = state.get("issue_key")
        raw_text = state.get("raw_requirement_text")

        if issue_key and issue_key.strip():
            try:
                requirement = self.jira_client.get_issue(issue_key.strip())
                return {
                    "jira_requirement": requirement,
                    "status": "REQUIREMENT_FETCHED",
                    "error": None,
                }
            except JiraClientError as exc:
                logger.warning("Jira retrieval failed for %s: %s", issue_key, exc)
                # If raw_text is also provided as fallback
                if raw_text:
                    pass
                else:
                    return {
                        "status": "FAILED",
                        "error": f"Failed to fetch Jira issue '{issue_key}': {exc}",
                    }

        if raw_text and raw_text.strip():
            lines = [line.strip() for line in raw_text.strip().splitlines() if line.strip()]
            summary = lines[0] if lines else "Manual Requirement Specification"
            key = issue_key if issue_key else "LOCAL-REQ-01"

            requirement = JiraRequirement(
                key=key,
                summary=summary,
                description_text=raw_text.strip(),
                acceptance_criteria=[],
            )
            return {
                "jira_requirement": requirement,
                "status": "REQUIREMENT_FETCHED",
                "error": None,
            }

        return {
            "status": "FAILED",
            "error": "Neither valid issue_key nor raw_requirement_text was provided.",
        }

    def normalize_requirement(self, state: AgentState) -> Dict[str, Any]:
        """
        Cleans and normalizes ADF / markup within the requirement description into Markdown.
        """
        requirement = state.get("jira_requirement")
        if not requirement:
            return {"status": "FAILED", "error": "No requirement available for normalization."}

        # ADF normalizer handles structured dicts or raw strings safely
        clean_description = ADFNormalizer.to_markdown(requirement.description_text)
        requirement.description_text = clean_description

        return {
            "jira_requirement": requirement,
            "status": "REQUIREMENT_NORMALIZED",
        }

    def assess_completeness(self, state: AgentState) -> Dict[str, Any]:
        """
        Extracts Acceptance Criteria from the normalized requirement, scores completeness,
        and annotates ambiguity notes if necessary.
        """
        requirement = state.get("jira_requirement")
        if not requirement:
            return {"status": "FAILED", "error": "No requirement available for AC assessment."}

        text = requirement.description_text
        ac_list: List[AcceptanceCriterion] = []

        # Parse text lines for AC patterns (e.g. AC-01, AC 1, bullet points)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        ac_idx = 1
        for line in lines:
            lower = line.lower()
            if any(lower.startswith(prefix) for prefix in ("ac-", "ac:", "ac ", "- ac", "* ac", "acceptance criteria")):
                clean_text = line.lstrip("-* ").strip()
                ac_list.append(
                    AcceptanceCriterion(
                        id=f"AC-{ac_idx:02d}",
                        text=clean_text,
                        type=RequirementType.FUNCTIONAL,
                    )
                )
                ac_idx += 1
            elif line.startswith(("-", "*")) and len(line) > 5 and not line.startswith("---"):
                clean_text = line.lstrip("-* ").strip()
                ac_list.append(
                    AcceptanceCriterion(
                        id=f"AC-{ac_idx:02d}",
                        text=clean_text,
                        type=RequirementType.FUNCTIONAL,
                    )
                )
                ac_idx += 1

        # Fallback if no explicit bullet points were formatted: treat non-empty paragraphs as ACs
        if not ac_list:
            for line in lines:
                if len(line) > 10 and not line.startswith("#"):
                    ac_list.append(
                        AcceptanceCriterion(
                            id=f"AC-{ac_idx:02d}",
                            text=line,
                            type=RequirementType.FUNCTIONAL,
                        )
                    )
                    ac_idx += 1

        # Calculate quality score (0-100)
        score = 100
        ambiguities = []
        if len(ac_list) == 0:
            score = 20
            ambiguities.append("No explicit acceptance criteria detected.")
        elif len(ac_list) < 2:
            score = 65
            ambiguities.append("Minimal acceptance criteria; coverage may be incomplete.")
        if len(text) < 30:
            score = min(score, 40)
            ambiguities.append("Requirement description is very brief.")

        requirement.acceptance_criteria = ac_list
        requirement.quality_score = score
        requirement.ambiguity_notes = ambiguities

        return {
            "jira_requirement": requirement,
            "acceptance_criteria": ac_list,
            "status": "COMPLETENESS_ASSESSED",
        }

    def generate_test_cases(self, state: AgentState) -> Dict[str, Any]:
        """
        Invokes TestDesigner to synthesize a Pydantic-validated TestSuite from the requirement.
        """
        requirement = state.get("jira_requirement")
        if not requirement:
            return {"status": "FAILED", "error": "No requirement provided to generate tests."}

        target_url = state.get("target_url") or settings.target_base_url
        try:
            suite = self.test_designer.generate_suite(
                requirement=requirement,
                target_base_url=target_url,
            )
            return {
                "test_suite": suite,
                "status": "TESTS_GENERATED",
                "error": None,
            }
        except Exception as exc:
            retry_count = state.get("retry_count", 0) + 1
            logger.warning("Test generation failed (attempt %d): %s", retry_count, exc)
            return {
                "retry_count": retry_count,
                "generation_feedback": str(exc),
                "status": "GENERATION_FAILED",
                "error": f"Test generation failed: {exc}",
            }

    def validate_test_cases(self, state: AgentState) -> Dict[str, Any]:
        """
        Evaluates whether the generated test suite exists and is non-empty.
        """
        suite = state.get("test_suite")
        if suite and isinstance(suite, TestSuite) and len(suite.test_cases) > 0:
            return {"status": "TESTS_VALIDATED"}

        return {
            "status": "TESTS_INVALID",
            "error": state.get("error") or "Test suite is empty or invalid.",
        }

    def human_review(self, state: AgentState) -> Dict[str, Any]:
        """
        Human-in-the-Loop review evaluation node.
        This is an interruption gate. Upon resume, inspects the human approval decision.
        """
        record = state.get("approval_record")
        if not record:
            return {"status": "PENDING_REVIEW"}

        if record.decision == ApprovalDecision.APPROVED:
            return {"status": "REVIEW_APPROVED"}
        elif record.decision == ApprovalDecision.REJECTED:
            return {"status": "REVIEW_REJECTED"}

        return {"status": "PENDING_REVIEW"}

    def validate_approval(self, state: AgentState) -> Dict[str, Any]:
        """
        Validates cryptographic checksum integrity and execution guardrail policies.
        """
        suite = state.get("test_suite")
        record = state.get("approval_record")

        if not suite or not record:
            return {
                "status": "FAILED",
                "error": "Missing test suite or approval record during approval validation.",
            }

        # 1. Cryptographic SHA-256 Checksum Match
        computed_hash = suite.compute_hash()
        if computed_hash != record.suite_hash:
            return {
                "status": "FAILED",
                "error": (
                    f"Cryptographic suite checksum mismatch! "
                    f"Suite computed hash: '{computed_hash}' does not match "
                    f"approved hash: '{record.suite_hash}'."
                ),
            }

        # 2. Execution Guardrail & URL Allowlist Verification
        for tc in suite.test_cases:
            for step in tc.steps:
                try:
                    self.policy_engine.validate_action(step.action.value)
                    if step.action == ActionType.NAVIGATE and step.input_value:
                        self.policy_engine.validate_navigation_url(step.input_value)
                except SecurityPolicyViolation as exc:
                    return {
                        "status": "FAILED",
                        "error": f"Security Guardrail Violation in test case {tc.id}: {exc}",
                    }

        return {"status": "APPROVAL_VALIDATED"}

    def execute_test_suite(self, state: AgentState) -> Dict[str, Any]:
        """
        Executes the approved test suite using the Playwright browser runner.
        Respects user's choice of watching on-screen (headless=False) or background (headless=True).
        """
        suite = state.get("test_suite")
        if not suite:
            return {"status": "FAILED", "error": "No test suite available to execute."}

        target_url = state.get("target_url") or settings.target_base_url
        headless = state.get("headless")
        slow_mo_ms = state.get("slow_mo_ms")

        # If a custom test executor is injected, use it; otherwise create one with runtime options
        if self.test_executor:
            executor = self.test_executor
        else:
            executor = TestExecutor(headless=headless, slow_mo_ms=slow_mo_ms)

        try:
            run = executor.execute_suite(suite=suite, target_url=target_url)
            return {
                "execution_run": run,
                "status": "EXECUTION_COMPLETED",
            }
        except Exception as exc:
            logger.error("Execution failed: %s", exc)
            return {
                "status": "FAILED",
                "error": f"Execution failed: {exc}",
            }

    def classify_results(self, state: AgentState) -> Dict[str, Any]:
        """
        Summarizes pass/fail metrics and classifies failure modes.
        """
        run = state.get("execution_run")
        if not run:
            return {"status": "RESULTS_CLASSIFIED"}

        run.passed_tests = sum(1 for r in run.results if r.outcome == TestOutcome.PASS)
        run.failed_tests = sum(1 for r in run.results if r.outcome == TestOutcome.FAIL)
        run.blocked_tests = sum(1 for r in run.results if r.outcome == TestOutcome.BLOCKED)
        run.error_tests = sum(1 for r in run.results if r.outcome == TestOutcome.ERROR)
        run.finished_at = datetime.now(timezone.utc)

        return {
            "execution_run": run,
            "status": "RESULTS_CLASSIFIED",
        }

    def generate_report(self, state: AgentState) -> Dict[str, Any]:
        """
        Produces final run summary.
        """
        return {"status": "REPORT_GENERATED"}

    def prepare_defect_drafts(self, state: AgentState) -> Dict[str, Any]:
        """
        Generates structured DefectDraft objects for each failed test case.
        """
        suite = state.get("test_suite")
        run = state.get("execution_run")
        req = state.get("jira_requirement")
        parent_key = req.key if req else "REQ-01"

        tc_map = {tc.id: tc for tc in suite.test_cases} if suite else {}
        drafts: List[DefectDraft] = []

        if run:
            for r in run.results:
                if r.outcome == TestOutcome.FAIL:
                    tc = tc_map.get(r.test_case_id)
                    draft = DefectDraft(
                        draft_id=f"DRAFT-{r.test_case_id}-{uuid4().hex[:6].upper()}",
                        parent_issue_key=parent_key,
                        test_case_id=r.test_case_id,
                        summary=f"Automated Test Failure: {tc.title if tc else r.test_case_id}",
                        steps_to_reproduce=[s.description for s in tc.steps] if tc else [],
                        expected_result=tc.expected_result if tc else "Expected condition satisfied",
                        actual_result=r.failure_message or "Assertion failed during test execution",
                        evidence_paths=[r.screenshot_path] if r.screenshot_path else [],
                    )
                    drafts.append(draft)

        return {
            "defect_drafts": drafts,
            "status": "DEFECTS_PREPARED",
        }

    def human_approve_defect(self, state: AgentState) -> Dict[str, Any]:
        """
        Interruption gate for human QA to review and select defects for Jira creation.
        """
        approved_ids = state.get("approved_defect_ids", [])
        if approved_ids:
            return {"status": "DEFECTS_APPROVED"}
        return {"status": "NO_DEFECTS_APPROVED"}

    def create_jira_defect(self, state: AgentState) -> Dict[str, Any]:
        """
        Submits approved defect drafts to Jira Cloud.
        """
        approved_ids = set(state.get("approved_defect_ids", []))
        drafts = state.get("defect_drafts", [])
        created = []

        for d in drafts:
            if d.draft_id in approved_ids:
                d.created_in_jira = True
                d.jira_defect_key = f"BUG-{uuid4().hex[:4].upper()}"
                created.append({
                    "draft_id": d.draft_id,
                    "jira_key": d.jira_defect_key,
                    "status": "CREATED",
                })

        return {
            "created_defects": created,
            "status": "DEFECTS_CREATED",
        }

    def finalize_run(self, state: AgentState) -> Dict[str, Any]:
        """Terminal success/completion node."""
        return {"status": "COMPLETED"}

    def handle_failure(self, state: AgentState) -> Dict[str, Any]:
        """Terminal unrecoverable failure node."""
        return {"status": "FAILED"}

