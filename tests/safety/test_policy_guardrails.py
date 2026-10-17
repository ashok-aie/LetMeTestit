"""
Phase 5 Security & Safety Test Suite
Verifies URL allowlist enforcement, dangerous scheme blocking,
unauthorized action rejection, and secret redaction.
"""
import pytest
from app.policies.guardrails import PolicyEngine, SecurityPolicyViolation
from app.policies.redaction import SecretRedactor


@pytest.fixture
def policy():
    return PolicyEngine(allowed_domains=["localhost", "127.0.0.1", "qa-internal.net"])


@pytest.fixture
def redactor():
    return SecretRedactor(additional_secrets=["MySuperSecretToken987", "VeryPrivatePassword!"])


# ------------------------------------------------------------------------------
# URL & Domain Security Guardrails Tests
# ------------------------------------------------------------------------------

def test_allowlisted_urls_pass(policy: PolicyEngine):
    """Verify that localhost, 127.0.0.1, and approved internal domains are allowed."""
    assert policy.validate_navigation_url("http://localhost:8000/orders") == "http://localhost:8000/orders"
    assert policy.validate_navigation_url("http://127.0.0.1:8000/") == "http://127.0.0.1:8000/"
    assert policy.validate_navigation_url("https://qa-internal.net/sap") == "https://qa-internal.net/sap"
    assert policy.validate_navigation_url("https://sub.qa-internal.net/portal") == "https://sub.qa-internal.net/portal"


def test_forbidden_external_domains_blocked(policy: PolicyEngine):
    """Verify that navigation to external domains is strictly rejected."""
    unapproved_urls = [
        "https://google.com",
        "https://evil-attacker.org/exfiltrate",
        "https://production-erp.sap.corp",
        "http://attacker.com",
    ]
    for url in unapproved_urls:
        with pytest.raises(SecurityPolicyViolation) as exc_info:
            policy.validate_navigation_url(url)
        assert "Navigation to domain" in str(exc_info.value) or "Security Guardrail Block" in str(exc_info.value)


def test_dangerous_schemes_blocked(policy: PolicyEngine):
    """Verify that file://, javascript:, and data: schemes are blocked."""
    dangerous_urls = [
        "file:///etc/passwd",
        "javascript:alert(document.cookie)",
        "data:text/html,<script>alert(1)</script>",
    ]
    for url in dangerous_urls:
        with pytest.raises(SecurityPolicyViolation) as exc_info:
            policy.validate_navigation_url(url)
        assert "Forbidden URL scheme" in str(exc_info.value)


def test_unapproved_actions_blocked(policy: PolicyEngine):
    """Verify that arbitrary or unsafe browser actions are rejected."""
    # Approved actions pass
    policy.validate_action("click")
    policy.validate_action("fill")
    policy.validate_action("assert_text")

    # Unapproved actions raise violation
    unsafe_actions = [
        "execute_system_command",
        "run_shell_script",
        "download_all_data",
        "arbitrary_eval",
    ]
    for action in unsafe_actions:
        with pytest.raises(SecurityPolicyViolation) as exc_info:
            policy.validate_action(action)
        assert "is not an approved browser operation" in str(exc_info.value)


# ------------------------------------------------------------------------------
# Secret Redaction Tests
# ------------------------------------------------------------------------------

def test_exact_secret_redaction(redactor: SecretRedactor):
    """Verify exact token scrubbing in error logs and strings."""
    raw_log = "Failed authenticating with token MySuperSecretToken987 for user alex."
    cleaned = redactor.redact(raw_log)
    assert "MySuperSecretToken987" not in cleaned
    assert "Failed authenticating with token ***REDACTED*** for user alex." in cleaned


def test_pattern_and_basic_auth_redaction(redactor: SecretRedactor):
    """Verify regex scrubbing for passwords and embedded URL credentials."""
    # Embedded basic auth
    url_with_creds = "https://admin:my_secret_password_123@atlassian.net/rest/api/3/issue"
    cleaned_url = redactor.redact(url_with_creds)
    assert "my_secret_password_123" not in cleaned_url
    assert "https://admin:***REDACTED***@atlassian.net/rest/api/3/issue" == cleaned_url

    # Regex key-value pattern
    json_str = '{"error": "Invalid auth", "api_token": "sk-live-999988887777"}'
    cleaned_json = redactor.redact(json_str)
    assert "sk-live-999988887777" not in cleaned_json
    assert "***REDACTED***" in cleaned_json


def test_recursive_data_redaction(redactor: SecretRedactor):
    """Verify deep dictionary and list scrubbing."""
    payload = {
        "user": "tester",
        "auth": {
            "password": "VeryPrivatePassword!",
            "token": "MySuperSecretToken987",
        },
        "endpoints": [
            "https://user:VeryPrivatePassword!@qa.corp/login",
            "http://localhost:8000",
        ],
    }
    scrubbed = redactor.redact_data(payload)
    assert scrubbed["auth"]["password"] == "***REDACTED***"
    assert scrubbed["auth"]["token"] == "***REDACTED***"
    assert "VeryPrivatePassword!" not in scrubbed["endpoints"][0]
    assert scrubbed["endpoints"][1] == "http://localhost:8000"

