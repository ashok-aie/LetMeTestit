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

