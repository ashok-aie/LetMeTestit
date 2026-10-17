"""
Pydantic Data Models for Requirements & Acceptance Criteria
"""
from typing import List, Optional
from enum import Enum
from pydantic import BaseModel, Field


class RequirementType(str, Enum):
    FUNCTIONAL = "functional"
    UI_VALIDATION = "ui_validation"
    BOUNDARY = "boundary"
    AUTHORIZATION = "authorization"


class AcceptanceCriterion(BaseModel):
    id: str = Field(description="Unique AC identifier, e.g. AC-01")
    text: str = Field(description="Normalized acceptance condition statement")
    type: RequirementType = RequirementType.FUNCTIONAL
    is_explicit: bool = True


class JiraRequirement(BaseModel):
    key: str = Field(description="Jira issue key, e.g. PROJ-101")
    summary: str
    description_text: str
    status: str = "To Do"
    issue_type: str = "Story"
    labels: List[str] = Field(default_factory=list)
    acceptance_criteria: List[AcceptanceCriterion] = Field(default_factory=list)
    quality_score: int = Field(ge=0, le=100, default=100)
    ambiguity_notes: List[str] = Field(default_factory=list)

