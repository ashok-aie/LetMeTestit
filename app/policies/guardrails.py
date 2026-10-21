"""
Security Policy & Guardrails Engine
Enforces URL allowlists, prevents malicious URL schemes, and blocks unauthorized actions.
"""
from typing import List, Optional
from urllib.parse import urlparse

from app.config import settings


class SecurityPolicyViolation(Exception):
    """Raised when an action or navigation breaches configured security guardrails."""
    pass


class PolicyEngine:
    """Enforces execution boundaries, domain allowlists, and action constraints."""

    ALLOWED_SCHEMES = ("http", "https")
    DEFAULT_ALLOWED_ACTIONS = (
        "navigate",
        "click",
        "fill",
        "select_option",
        "wait_for",
        "assert_text",
        "assert_url",
        "assert_element_state",
    )

    def __init__(self, allowed_domains: Optional[List[str]] = None):
        self.allowed_domains = allowed_domains if allowed_domains is not None else settings.allowed_domains

    def validate_navigation_url(self, target_url: str) -> str:
        """
        Validates that a URL is strictly within allowlisted domains and safe schemes.
        
        Args:
            target_url: The URL string proposed for browser navigation.
            
        Returns:
            The validated URL string if safe.
            
        Raises:
            SecurityPolicyViolation: If the URL uses a dangerous scheme or unallowlisted domain.
        """
        if not target_url or not isinstance(target_url, str):
            raise SecurityPolicyViolation("Navigation URL must be a non-empty string.")

        clean_url = target_url.strip()
        parsed = urlparse(clean_url)

        # 1. Scheme Validation
        if parsed.scheme.lower() not in self.ALLOWED_SCHEMES:
            raise SecurityPolicyViolation(
                f"Security Guardrail: Forbidden URL scheme '{parsed.scheme}'. "
                f"Only {self.ALLOWED_SCHEMES} are permitted."
            )

        # 2. Hostname Validation
        hostname = (parsed.hostname or "").lower()
        if not hostname:
            raise SecurityPolicyViolation(f"Security Guardrail: Invalid URL without hostname: '{clean_url}'")

        # Check localhost and allowlisted domains
        is_local = hostname in ("localhost", "127.0.0.1")
        is_allowlisted = any(
            hostname == domain.lower() or hostname.endswith(f".{domain.lower()}")
            for domain in self.allowed_domains
        )

        if not (is_local or is_allowlisted):
            raise SecurityPolicyViolation(
                f"Security Guardrail Block: Navigation to domain '{hostname}' is not permitted. "
                f"Approved domains: {self.allowed_domains}"
            )

        return clean_url

    def validate_action(self, action_type: str) -> None:
        """Ensures that only allowlisted, safe browser action types can be performed."""
        if action_type.lower() not in self.DEFAULT_ALLOWED_ACTIONS:
            raise SecurityPolicyViolation(
                f"Security Guardrail Block: Action '{action_type}' is not an approved browser operation. "
                f"Allowed operations: {self.DEFAULT_ALLOWED_ACTIONS}"
            )


def is_credential_step(
    selector: Optional[str] = None,
    description: Optional[str] = None,
    input_value: Optional[str] = None,
) -> bool:
    """Detects whether a test step enters or handles credentials (username or password)."""
    sel_lower = (selector or "").lower()
    desc_lower = (description or "").lower()
    val_str = str(input_value or "").strip()

    is_user = any(k in sel_lower or k in desc_lower for k in ["username", "user_field", "sap-user"]) or (
        settings.sap_username and val_str == settings.sap_username
    ) or val_str.upper() in ("MYRAR1", "<CONFIGURED_USERNAME>", "[CONFIGURED_USERNAME]")

    is_pwd = any(k in sel_lower or k in desc_lower for k in ["password", "pwd", "pass_field"]) or (
        settings.sap_password and val_str == settings.sap_password
    ) or val_str in ("Pass23#$", "Welcome@123", "<CONFIGURED_PASSWORD>", "[CONFIGURED_PASSWORD]")

    return bool(is_user or is_pwd)


def mask_step_credential_display(
    action: str,
    selector: Optional[str] = None,
    value: Optional[str] = None,
    description: Optional[str] = None,
) -> tuple[str, str]:
    """
    Returns (safe_value, safe_description) with usernames and passwords securely masked
    for presentation in UI tables, logs, defect drafts, and test reports.
    """
    sel_lower = (selector or "").lower()
    desc_lower = (description or "").lower()
    val_str = str(value or "")

    is_pwd = any(k in sel_lower or k in desc_lower for k in ["password", "pwd", "pass_field"]) or (
        settings.sap_password and val_str == settings.sap_password
    ) or val_str in ("Pass23#$", "Welcome@123", "<CONFIGURED_PASSWORD>", "[CONFIGURED_PASSWORD]")

    is_user = any(k in sel_lower or k in desc_lower for k in ["username", "user_field", "sap-user"]) or (
        settings.sap_username and val_str == settings.sap_username
    ) or val_str.upper() in ("MYRAR1", "<CONFIGURED_USERNAME>", "[CONFIGURED_USERNAME]")

    if is_pwd:
        safe_val = "••••••••"
        safe_desc = description or "Enter SAP password"
        for leaked in [settings.sap_password, "Pass23#$", "Welcome@123"]:
            if leaked and leaked in safe_desc:
                safe_desc = safe_desc.replace(leaked, "••••••••")
        if any(w in safe_desc.lower() for w in ["pass23#$", "welcome@123"]):
            safe_desc = "Enter SAP password"
        return safe_val, safe_desc

    if is_user:
        safe_val = "••••••••"
        safe_desc = description or "Enter SAP username"
        for leaked in [settings.sap_username, "MYRAR1", "myrar1"]:
            if leaked and leaked in safe_desc:
                safe_desc = safe_desc.replace(leaked, "••••••••")
        if "myrar1" in safe_desc.lower():
            safe_desc = "Enter SAP username"
        return safe_val, safe_desc

    return val_str, (description or "")

