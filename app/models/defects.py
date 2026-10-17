"""
Pydantic Data Contracts for Jira Defect Drafts
"""
from typing import List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field, field_validator


class DefectDraft(BaseModel):
    draft_id: str
    parent_issue_key: str
    test_case_id: str
    summary: str
    steps_to_reproduce: List[str] = Field(default_factory=list)

    @field_validator("summary", mode="before")
    @classmethod
    def sanitize_and_truncate_summary(cls, v: str) -> str:
        if isinstance(v, str):
            clean = " ".join(v.replace("\r", " ").replace("\n", " ").split()).strip()
            if len(clean) > 250:
                return clean[:247] + "..."
            return clean
        return v
    expected_result: str
    actual_result: str
    environment: str = "local"
    evidence_paths: List[str] = Field(default_factory=list)
    jira_defect_key: Optional[str] = None
    created_in_jira: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_markdown_description(self) -> str:
        """Formats the defect draft into a professional Jira bug ticket markdown description."""
        repro_steps_md = "\n".join(f"{i}. {step}" for i, step in enumerate(self.steps_to_reproduce, start=1))
        evidence_md = "\n".join(f"- `{p}`" for p in self.evidence_paths) if self.evidence_paths else "No attachments."

        return f"""h2. Bug Summary
{self.summary}

h3. Environment
* Target Environment: {self.environment}
* Parent Requirement: {self.parent_issue_key}
* Associated Test Case: {self.test_case_id}

h3. Steps to Reproduce
{repro_steps_md}

h3. Expected Result
{self.expected_result}

h3. Actual Result
{self.actual_result}

h3. Execution Evidence & Artifacts
{evidence_md}

----
_Logged automatically by [Let me TEST it....!|https://github.com/LetMeTestIt] after explicit Human QA approval._
"""

