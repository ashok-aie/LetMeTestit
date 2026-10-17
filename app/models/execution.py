"""
Pydantic Data Contracts for Execution Runs, Approvals, and Results
"""
from typing import List, Optional
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field

from app.models.test_suite import ActionType


class ApprovalDecision(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ApprovalRecord(BaseModel):
    approval_id: str
    suite_id: str
    suite_hash: str = Field(description="SHA-256 checksum of the approved TestSuite")
    reviewer: str = Field(description="Username or email of the human approver")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    decision: ApprovalDecision
    comments: Optional[str] = None


class TestOutcome(str, Enum):
    __test__ = False
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


class FailureClassification(str, Enum):
    NONE = "none"
    APPLICATION_DEFECT = "application_defect"
    LOCATOR_ERROR = "locator_error"
    TIMEOUT_ERROR = "timeout_error"
    ENVIRONMENT_ISSUE = "environment_issue"


class TestStepResult(BaseModel):
    __test__ = False
    step_number: int
    action: ActionType
    duration_ms: float
    passed: bool
    actual_value: Optional[str] = None
    error_message: Optional[str] = None
    screenshot_path: Optional[str] = None


class TestCaseResult(BaseModel):
    __test__ = False
    test_case_id: str
    outcome: TestOutcome
    classification: FailureClassification = FailureClassification.NONE
    duration_seconds: float
    step_results: List[TestStepResult] = Field(default_factory=list)
    failure_message: Optional[str] = None
    screenshot_path: Optional[str] = None


class ExecutionRun(BaseModel):
    run_id: str
    suite_id: str
    environment: str = "local"
    target_url: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    blocked_tests: int = 0
    error_tests: int = 0
    trace_path: Optional[str] = None
    results: List[TestCaseResult] = Field(default_factory=list)
