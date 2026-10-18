"""
Pydantic Data Contracts for Test Cases & Test Suites
Defines strongly typed, declarative browser action steps, locator strategies,
and cryptographic SHA-256 suite hashing for human approval governance.
"""
import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


class ActionType(str, Enum):
    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    SELECT_OPTION = "select_option"
    WAIT_FOR = "wait_for"
    ASSERT_TEXT = "assert_text"
    ASSERT_URL = "assert_url"
    ASSERT_ELEMENT_STATE = "assert_element_state"


class LocatorStrategy(str, Enum):
    ROLE = "role"             # Accessible ARIA role (e.g. button, textbox)
    TEXT = "text"             # Exact or substring text
    TEST_ID = "test_id"       # data-testid attribute
    CSS = "css"               # Fallback CSS selector


class TestCategory(str, Enum):
    __test__ = False
    POSITIVE = "positive"
    NEGATIVE = "negative"
    BOUNDARY = "boundary"
    VALIDATION = "validation"


class TestStep(BaseModel):
    __test__ = False
    step_number: int = Field(ge=1, description="Sequential step number (1-indexed)")
    action: ActionType
    locator_strategy: Optional[LocatorStrategy] = None
    selector_value: Optional[str] = Field(default=None, description="Selector string or accessible name")
    role_name: Optional[str] = Field(default=None, description="ARIA role type when strategy is role (e.g. button)")
    input_value: Optional[str] = Field(default=None, description="Value to type or select")
    expected_value: Optional[str] = Field(default=None, description="Expected text or condition for assertions")
    description: str = Field(description="Human-readable explanation of this action")


class TestCase(BaseModel):
    __test__ = False
    id: str = Field(description="Unique Test ID, e.g. TC-01")
    requirement_key: str = Field(description="Parent Jira requirement key, e.g. ERP-205")
    source_ac_id: str = Field(description="Mapped Acceptance Criteria ID, e.g. AC-01")
    title: str = Field(description="Descriptive title of the test scenario")
    objective: str = Field(description="Clear business objective being validated")
    category: TestCategory = TestCategory.POSITIVE
    preconditions: List[str] = Field(default_factory=list)
    test_data: Dict[str, Any] = Field(default_factory=dict)
    steps: List[TestStep] = Field(min_length=1, description="Ordered action steps")
    expected_result: str = Field(description="Final expected outcome of the test case")
    priority: Literal["High", "Medium", "Low"] = "Medium"
    group: Optional[str] = Field(default="General", description="Logical group or functional module name, e.g. Authentication, Quotations")
    tags: List[str] = Field(default_factory=list, description="Categorization tags, e.g. ['smoke', 'regression']")


class TestSuite(BaseModel):
    __test__ = False
    suite_id: str = Field(description="Unique suite identifier, e.g. SUITE-ERP-205-V1")
    requirement_key: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = Field(default=1, ge=1)
    test_cases: List[TestCase] = Field(min_length=1)

    def compute_hash(self) -> str:
        """
        Calculates a canonical SHA-256 checksum of the test suite structure.
        This hash is signed in the ApprovalRecord to cryptographically prevent
        unauthorized alterations after human sign-off.
        """
        # Exclude dynamic timestamp to ensure deterministic hashing of content
        content_dict = {
            "suite_id": self.suite_id,
            "requirement_key": self.requirement_key,
            "version": self.version,
            "test_cases": [tc.model_dump(mode="json") for tc in self.test_cases],
        }
        canonical_json = json.dumps(content_dict, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
