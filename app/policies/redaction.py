"""
Secret Redaction Module
Sanitizes credentials, API tokens, and passwords from logs, error traces, and reporting data.
"""
import re
from typing import List, Optional, Set, Any, Dict

from app.config import settings


class SecretRedactor:
    """Scrubs secrets and sensitive credentials before logging or disk persistence."""

    def __init__(self, additional_secrets: Optional[List[str]] = None):
        self.sensitive_tokens: Set[str] = set()

        # Seed with configured credentials from settings
        if settings.jira_api_token:
            self.sensitive_tokens.add(settings.jira_api_token)

        if additional_secrets:
            for s in additional_secrets:
                if s and len(s) >= 4:
                    self.sensitive_tokens.add(s)

        # Regex patterns for credential patterns in strings, JSON, and URLs
        self.patterns = [
            # JSON or key-value pattern: "password": "...", password=..., "api_token": "..."
            (
                re.compile(
                    r"""(['"]?(?:api[_-]?token|password|secret|auth[_-]?token)['"]?\s*[:=]\s*['"]?)[a-zA-Z0-9_\-\.]{6,}(['"]?)""",
                    re.IGNORECASE,
                ),
                r"\g<1>***REDACTED***\g<2>",
            ),
            # Bearer token pattern: Bearer eyJ...
            (
                re.compile(r"""(bearer\s+)[a-zA-Z0-9_\-\.]{8,}""", re.IGNORECASE),
                r"\g<1>***REDACTED***",
            ),
            # Basic Auth embedded in URLs: https://user:pass@host
            (
                re.compile(r"://([^:]+):([^@]+)@"),
                r"://\1:***REDACTED***@",
            ),
        ]

    def add_secret(self, secret: str) -> None:
        """Dynamically registers a secret to be scrubbed."""
        if secret and len(secret) >= 4:
            self.sensitive_tokens.add(secret)

    def redact(self, text: str) -> str:
        """Replaces all registered secrets and credential patterns in text with ***REDACTED***."""
        if not text or not isinstance(text, str):
            return text

        scrubbed = text

        # 1. Regex pattern replacements
        for pattern, replacement in self.patterns:
            scrubbed = pattern.sub(replacement, scrubbed)

        # 2. Exact token replacements
        for token in self.sensitive_tokens:
            if token in scrubbed:
                scrubbed = scrubbed.replace(token, "***REDACTED***")

        return scrubbed

    def redact_data(self, data: Any) -> Any:
        """Recursively scrubs strings within dictionaries, lists, or primitive types."""
        if isinstance(data, str):
            return self.redact(data)
        elif isinstance(data, dict):
            return {k: self.redact_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.redact_data(item) for item in data]
        return data


# Global singleton redactor
redactor = SecretRedactor()
