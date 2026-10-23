"""
Jira Cloud REST API Client Module
Handles authentication, issue retrieval, rate-limit backoff, and error taxonomy.
"""
import re
import time
from typing import Optional, Dict, Any
import httpx

from app.config import settings
from app.jira.normalizer import ADFNormalizer
from app.models.requirements import JiraRequirement


class JiraClientError(Exception):
    """Base exception for Jira client operations."""
    pass


class JiraAuthenticationError(JiraClientError):
    """Raised when authentication credentials are invalid (HTTP 401/403)."""
    pass


class JiraIssueNotFoundError(JiraClientError):
    """Raised when the requested issue key does not exist (HTTP 404)."""
    pass


class JiraRateLimitError(JiraClientError):
    """Raised when Jira Cloud API rate limits are exceeded (HTTP 429)."""
    pass


class JiraConnectionError(JiraClientError):
    """Raised on network connection failures."""
    pass


class JiraClient:
    """Client for querying Jira Cloud REST API v3."""

    ISSUE_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9]+-[0-9]+$")

    def __init__(
        self,
        base_url: Optional[str] = None,
        user_email: Optional[str] = None,
        api_token: Optional[str] = None,
        timeout: float = 25.0,
    ):
        self.base_url = (base_url or settings.jira_base_url).rstrip("/")
        self.user_email = user_email or settings.jira_user_email
        self.api_token = api_token or settings.jira_api_token
        self.timeout = timeout

    @property
    def auth(self) -> httpx.BasicAuth:
        return httpx.BasicAuth(username=self.user_email, password=self.api_token)

    def is_connected(self) -> bool:
        """Verifies authentication and connectivity against Jira Cloud /rest/api/3/myself."""
        if not self.api_token or not self.user_email:
            return False

        try:
            with httpx.Client(auth=self.auth, timeout=self.timeout) as client:
                res = client.get(f"{self.base_url}/rest/api/3/myself")
                return res.status_code == 200
        except Exception:
            return False

    def get_issue(self, issue_key: str, max_retries: int = 3) -> JiraRequirement:
        """
        Retrieves a Jira issue by key and normalizes its rich-text ADF description.
        
        Args:
            issue_key: Jira issue key, e.g. 'PROJ-101'
            max_retries: Number of retry attempts on HTTP 429 rate limits.
            
        Returns:
            JiraRequirement model with clean summary, markdown description, and metadata.
        """
        clean_key = issue_key.strip().upper()
        if not self.ISSUE_KEY_PATTERN.match(clean_key):
            raise ValueError(f"Invalid Jira issue key format: '{issue_key}'. Expected format like 'PROJ-101'.")

        url = f"{self.base_url}/rest/api/3/issue/{clean_key}"
        params = {"fields": "summary,description,status,labels,issuetype"}

        retry_count = 0
        while True:
            try:
                with httpx.Client(auth=self.auth, timeout=self.timeout) as client:
                    res = client.get(url, params=params)

                if res.status_code == 200:
                    data = res.json()
                    fields = data.get("fields", {})

                    summary = fields.get("summary", "")
                    description_raw = fields.get("description")
                    description_md = ADFNormalizer.to_markdown(description_raw)

                    status_name = fields.get("status", {}).get("name", "To Do")
                    issue_type = fields.get("issuetype", {}).get("name", "Story")
                    labels = fields.get("labels", [])

                    return JiraRequirement(
                        key=clean_key,
                        summary=summary,
                        description_text=description_md,
                        status=status_name,
                        issue_type=issue_type,
                        labels=labels,
                    )

                elif res.status_code in (401, 403):
                    raise JiraAuthenticationError(
                        f"Authentication failed for user '{self.user_email}'. Verify Jira API Token and permissions."
                    )

                elif res.status_code == 404:
                    raise JiraIssueNotFoundError(f"Jira issue '{clean_key}' was not found in project.")

                elif res.status_code == 429:
                    retry_after = int(res.headers.get("Retry-After", 2))
                    if retry_count < max_retries:
                        retry_count += 1
                        time.sleep(retry_after)
                        continue
                    raise JiraRateLimitError(f"Jira API rate limit exceeded after {max_retries} retries.")

                else:
                    raise JiraClientError(f"Unexpected Jira API error (HTTP {res.status_code}): {res.text}")

            except httpx.ConnectError as exc:
                raise JiraConnectionError(f"Failed to connect to Jira server at {self.base_url}: {exc}") from exc
            except httpx.TimeoutException as exc:
                raise JiraConnectionError(f"Jira API request timed out after {self.timeout}s.") from exc

    def attach_file(self, issue_key: str, file_path: str, filename: Optional[str] = None) -> bool:
        """
        Attaches a file (e.g. execution report or screenshot) to a Jira issue.
        """
        from pathlib import Path
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File to attach not found: {file_path}")

        upload_name = filename or path.name
        url = f"{self.base_url}/rest/api/3/issue/{issue_key.strip().upper()}/attachments"
        headers = {"X-Atlassian-Token": "no-check"}

        with open(path, "rb") as f:
            file_bytes = f.read()

        with httpx.Client(auth=self.auth, timeout=self.timeout) as client:
            res = client.post(url, headers=headers, files={"file": (upload_name, file_bytes)})
            if res.status_code in (200, 201):
                return True
            raise JiraClientError(f"Failed to attach file to {issue_key} (HTTP {res.status_code}): {res.text}")

    def add_comment(self, issue_key: str, comment_text: str) -> bool:
        """
        Adds a comment to a Jira issue with ADF formatting.
        """
        url = f"{self.base_url}/rest/api/3/issue/{issue_key.strip().upper()}/comment"
        payload = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": comment_text}],
                    }
                ],
            }
        }
        with httpx.Client(auth=self.auth, timeout=self.timeout) as client:
            res = client.post(url, json=payload)
            if res.status_code in (200, 201):
                return True
            raise JiraClientError(f"Failed to add comment to {issue_key} (HTTP {res.status_code}): {res.text}")

    def create_defect(
        self,
        project_key: str,
        summary: str,
        description_text: str,
        parent_issue_key: Optional[str] = None,
        screenshot_path: Optional[str] = None,
    ) -> str:
        """
        Creates a defect issue in Jira Cloud, attaches evidence, and links to parent story.
        """
        from pathlib import Path
        url = f"{self.base_url}/rest/api/3/issue"

        # Determine available issue type (Bug or Task fallback)
        issue_type = "Task"
        try:
            with httpx.Client(auth=self.auth, timeout=self.timeout) as client:
                res = client.get(f"{self.base_url}/rest/api/3/project/{project_key}")
                if res.status_code == 200:
                    types = [t.get("name") for t in res.json().get("issueTypes", [])]
                    if "Bug" in types:
                        issue_type = "Bug"
        except Exception:
            pass

        paragraphs = []
        for line in description_text.splitlines():
            if line.strip():
                paragraphs.append({
                    "type": "paragraph",
                    "content": [{"type": "text", "text": line}],
                })

        # Jira Cloud strictly enforces summary <= 255 chars and single-line
        clean_summary = " ".join(summary.replace("\r", " ").replace("\n", " ").split()).strip()
        if len(clean_summary) > 250:
            clean_summary = clean_summary[:247] + "..."
        if not clean_summary:
            clean_summary = f"[Defect] Automated test failure in {project_key}"

        payload = {
            "fields": {
                "project": {"key": project_key},
                "summary": clean_summary,
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": paragraphs if paragraphs else [{"type": "paragraph", "content": [{"type": "text", "text": description_text}]}],
                },
                "issuetype": {"name": issue_type},
                "labels": ["defect", "automation-failure", "letmetestit"],
            }
        }

        with httpx.Client(auth=self.auth, timeout=self.timeout) as client:
            res = client.post(url, json=payload)
            if res.status_code not in (200, 201):
                raise JiraClientError(f"Failed to create defect in Jira (HTTP {res.status_code}): {res.text}")
            created_key = res.json().get("key")

        # Attach failure screenshot if available
        if screenshot_path and created_key and Path(screenshot_path).exists():
            try:
                self.attach_file(created_key, screenshot_path)
            except Exception:
                pass

        # Link back to parent requirement
        if parent_issue_key and created_key:
            try:
                link_url = f"{self.base_url}/rest/api/3/issueLink"
                link_payload = {
                    "type": {"name": "Relates"},
                    "inwardIssue": {"key": created_key},
                    "outwardIssue": {"key": parent_issue_key},
                }
                with httpx.Client(auth=self.auth, timeout=self.timeout) as client:
                    client.post(link_url, json=link_payload)
            except Exception:
                pass

        return created_key


