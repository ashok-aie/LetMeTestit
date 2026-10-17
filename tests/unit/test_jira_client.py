"""
Phase 6 Unit Tests: Jira Cloud Integration & ADF Normalizer
Verifies rich ADF to markdown parsing, issue fetching, and HTTP error taxonomy.
"""
import pytest
import respx
import httpx

from app.jira.normalizer import ADFNormalizer
from app.jira.client import (
    JiraClient,
    JiraAuthenticationError,
    JiraIssueNotFoundError,
    JiraRateLimitError,
)


# ------------------------------------------------------------------------------
# ADF Normalizer Unit Tests
# ------------------------------------------------------------------------------

def test_adf_paragraph_with_marks():
    """Verify ADF text with bold, italic, and code marks converts to clean markdown."""
    sample_adf = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "This is "},
                    {"type": "text", "text": "bold", "marks": [{"type": "strong"}]},
                    {"type": "text", "text": " and "},
                    {"type": "text", "text": "code", "marks": [{"type": "code"}]},
                    {"type": "text", "text": "."},
                ],
            }
        ],
    }
    result = ADFNormalizer.to_markdown(sample_adf)
    assert result == "This is **bold** and `code`."


def test_adf_headings_and_bullet_lists():
    """Verify ADF headings and bulleted acceptance criteria convert to markdown."""
    sample_adf = {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": "Acceptance Criteria"}],
            },
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "Given valid user credentials"}],
                            }
                        ],
                    },
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "Then order is created"}],
                            }
                        ],
                    },
                ],
            },
        ],
    }
    result = ADFNormalizer.to_markdown(sample_adf)
    assert "## Acceptance Criteria" in result
    assert "- Given valid user credentials" in result
    assert "- Then order is created" in result


# ------------------------------------------------------------------------------
# Jira Client Mocked Unit Tests (via respx)
# ------------------------------------------------------------------------------

@pytest.fixture
def jira_client():
    return JiraClient(
        base_url="https://test-company.atlassian.net",
        user_email="qa@test-company.com",
        api_token="dummy_token_abc123",
    )


@respx.mock
def test_jira_client_get_issue_success(jira_client: JiraClient):
    """Verify successful retrieval and normalization of a Jira issue."""
    mock_adf = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "As a plant manager, I want to create a material order."}],
            }
        ],
    }
    mock_response = {
        "key": "ERP-205",
        "fields": {
            "summary": "Create Material Sales Order in SAP",
            "description": mock_adf,
            "status": {"name": "In Progress"},
            "issuetype": {"name": "Story"},
            "labels": ["SAP", "SalesOrder", "MVP"],
        },
    }

    respx.get("https://test-company.atlassian.net/rest/api/3/issue/ERP-205").mock(
        return_value=httpx.Response(200, json=mock_response)
    )

    issue = jira_client.get_issue("ERP-205")
    assert issue.key == "ERP-205"
    assert issue.summary == "Create Material Sales Order in SAP"
    assert issue.description_text == "As a plant manager, I want to create a material order."
    assert issue.status == "In Progress"
    assert "SAP" in issue.labels


@respx.mock
def test_jira_client_authentication_failure(jira_client: JiraClient):
    """Verify 401 Unauthorized raises JiraAuthenticationError."""
    respx.get("https://test-company.atlassian.net/rest/api/3/issue/ERP-205").mock(
        return_value=httpx.Response(401, json={"errorMessages": ["Unauthorized"]})
    )

    with pytest.raises(JiraAuthenticationError) as exc_info:
        jira_client.get_issue("ERP-205")
    assert "Authentication failed" in str(exc_info.value)


@respx.mock
def test_jira_client_issue_not_found(jira_client: JiraClient):
    """Verify 404 Not Found raises JiraIssueNotFoundError."""
    respx.get("https://test-company.atlassian.net/rest/api/3/issue/ERP-999").mock(
        return_value=httpx.Response(404, json={"errorMessages": ["Issue Does Not Exist"]})
    )

    with pytest.raises(JiraIssueNotFoundError) as exc_info:
        jira_client.get_issue("ERP-999")
    assert "was not found" in str(exc_info.value)


def test_jira_client_invalid_key_format(jira_client: JiraClient):
    """Verify malformed issue keys are rejected without network requests."""
    with pytest.raises(ValueError) as exc_info:
        jira_client.get_issue("invalid_key_without_dash")
    assert "Invalid Jira issue key format" in str(exc_info.value)


@respx.mock
def test_jira_client_attach_file(jira_client: JiraClient, tmp_path):
    """Verify attach_file uploads multipart file successfully."""
    dummy_file = tmp_path / "report.md"
    dummy_file.write_text("# Test Report")

    respx.post("https://test-company.atlassian.net/rest/api/3/issue/ERP-205/attachments").mock(
        return_value=httpx.Response(200, json=[{"id": "10001", "filename": "report.md"}])
    )

    success = jira_client.attach_file("ERP-205", str(dummy_file))
    assert success is True


@respx.mock
def test_jira_client_add_comment(jira_client: JiraClient):
    """Verify add_comment posts formatted comment to Jira."""
    respx.post("https://test-company.atlassian.net/rest/api/3/issue/ERP-205/comment").mock(
        return_value=httpx.Response(201, json={"id": "20001"})
    )

    success = jira_client.add_comment("ERP-205", "Test execution completed.")
    assert success is True


@respx.mock
def test_jira_client_create_defect(jira_client: JiraClient):
    """Verify create_defect submits issue and links to parent story."""
    respx.get("https://test-company.atlassian.net/rest/api/3/project/ERP").mock(
        return_value=httpx.Response(200, json={"issueTypes": [{"name": "Bug"}, {"name": "Task"}]})
    )
    respx.post("https://test-company.atlassian.net/rest/api/3/issue").mock(
        return_value=httpx.Response(201, json={"key": "ERP-301", "id": "30001"})
    )
    respx.post("https://test-company.atlassian.net/rest/api/3/issueLink").mock(
        return_value=httpx.Response(201)
    )

    created_key = jira_client.create_defect(
        project_key="ERP",
        summary="Automated Failure in TC-01",
        description_text="Details of failure...",
        parent_issue_key="ERP-205",
    )
    assert created_key == "ERP-301"


@respx.mock
def test_jira_client_create_defect_truncates_long_summary(jira_client: JiraClient):
    """Verify create_defect truncates summary exceeding 250 characters."""
    respx.get("https://test-company.atlassian.net/rest/api/3/project/ERP").mock(
        return_value=httpx.Response(200, json={"issueTypes": [{"name": "Bug"}]})
    )
    
    captured_summary = []
    def handle_create(request):
        import json
        data = json.loads(request.content)
        captured_summary.append(data["fields"]["summary"])
        return httpx.Response(201, json={"key": "ERP-302", "id": "30002"})

    respx.post("https://test-company.atlassian.net/rest/api/3/issue").mock(side_effect=handle_create)

    overly_long = "Very long error message " * 20
    created_key = jira_client.create_defect(
        project_key="ERP",
        summary=overly_long,
        description_text="Details...",
    )
    assert created_key == "ERP-302"
    assert len(captured_summary[0]) <= 250
    assert captured_summary[0].endswith("...")


