#!/usr/bin/env python3
"""
redaction.py

Secret redaction utilities for agentic content conversion.
Removes common credential patterns from converted content.

Part of Agentic Discovery & Conversion
"""

import re
from typing import List, Tuple

# Regex patterns for common secrets
# Format: (pattern, replacement, description)
SECRET_PATTERNS: List[Tuple[str, str, str]] = [
    # OpenAI API keys
    (r"sk-[a-zA-Z0-9]{40,}", "[REDACTED-OPENAI-KEY]", "OpenAI API key"),
    # GitHub tokens
    (r"ghp_[a-zA-Z0-9]{36,}", "[REDACTED-GITHUB-PAT]", "GitHub Personal Access Token"),
    (r"gho_[a-zA-Z0-9]{36,}", "[REDACTED-GITHUB-OAUTH]", "GitHub OAuth Token"),
    (r"ghu_[a-zA-Z0-9]{36,}", "[REDACTED-GITHUB-USER]", "GitHub User Token"),
    (r"ghs_[a-zA-Z0-9]{36,}", "[REDACTED-GITHUB-SERVER]", "GitHub Server Token"),
    (r"ghr_[a-zA-Z0-9]{36,}", "[REDACTED-GITHUB-REFRESH]", "GitHub Refresh Token"),
    # Google API keys
    (r"AIza[a-zA-Z0-9_-]{35}", "[REDACTED-GOOGLE-API-KEY]", "Google API key"),
    # AWS keys
    (r"AKIA[A-Z0-9]{16}", "[REDACTED-AWS-ACCESS-KEY]", "AWS Access Key ID"),
    # AWS Secret Key - handles: key=value, key: value, "key": "value", and JSON format
    (
        r'(["\']?(?:aws[_-]?secret[_-]?access[_-]?key|secret[_-]?key)["\']?\s*[:=]\s*["\']?)([a-zA-Z0-9/+=]{40})(["\']?)',
        r"\1[REDACTED-AWS-SECRET]\3",
        "AWS Secret Key",
    ),
    # Anthropic keys
    (r"sk-ant-[a-zA-Z0-9-]{80,}", "[REDACTED-ANTHROPIC-KEY]", "Anthropic API key"),
    # Azure keys - contextual patterns (require Azure-specific keywords to avoid over-redaction)
    (
        r'(azure[_-]?(?:storage[_-]?)?(?:account[_-]?)?key|subscription[_-]?key|cognitive[_-]?services[_-]?key|client[_-]?secret|azure[_-]?api[_-]?key)(\s*[:=]\s*["\']?)([a-zA-Z0-9+/]{32,})(["\']?)',
        r"\1\2[REDACTED-AZURE-KEY]\4",
        "Azure API key",
    ),
    # Azure Storage connection strings
    (
        r"(DefaultEndpointsProtocol=https?;AccountName=)([^;]+)(;AccountKey=)([a-zA-Z0-9+/=]{86,88})(;)",
        r"\1[REDACTED]\3[REDACTED-AZURE-STORAGE-KEY]\5",
        "Azure Storage connection string",
    ),
    # Private keys (PEM format)
    (
        r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----[\s\S]*?-----END\s+(?:RSA\s+)?PRIVATE\s+KEY-----",
        "[REDACTED-PRIVATE-KEY]",
        "Private key",
    ),
    (
        r"-----BEGIN\s+EC\s+PRIVATE\s+KEY-----[\s\S]*?-----END\s+EC\s+PRIVATE\s+KEY-----",
        "[REDACTED-EC-PRIVATE-KEY]",
        "EC Private key",
    ),
    (
        r"-----BEGIN\s+OPENSSH\s+PRIVATE\s+KEY-----[\s\S]*?-----END\s+OPENSSH\s+PRIVATE\s+KEY-----",
        "[REDACTED-SSH-PRIVATE-KEY]",
        "SSH Private key",
    ),
    # Generic patterns (processed last due to potential false positives)
    (
        r'(api[_-]?key|apikey|api_secret|secret_key|access_token|auth_token|bearer_token)\s*[:=]\s*["\']?([a-zA-Z0-9_-]{16,})["\']?',
        r"\1: [REDACTED]",
        "Generic API key",
    ),
    (r'(password|passwd|pwd)\s*[:=]\s*["\']?([^\s"\']{8,})["\']?', r"\1: [REDACTED]", "Password"),
    (r'(token)\s*[:=]\s*["\']?([a-zA-Z0-9_-]{20,})["\']?', r"\1: [REDACTED]", "Generic token"),
    # Bearer tokens in headers
    (
        r'(Authorization|Bearer)\s*[:=]?\s*["\']?Bearer\s+([a-zA-Z0-9._-]+)["\']?',
        r"\1: Bearer [REDACTED]",
        "Bearer token",
    ),
    # Connection strings
    (
        r'(mongodb|postgres|mysql|redis|amqp)://[^\s<>"\']+:[^\s<>"\']+@[^\s<>"\']+',
        r"\1://[REDACTED-CONNECTION-STRING]",
        "Connection string",
    ),
    # Slack tokens
    (r"xox[baprs]-[a-zA-Z0-9-]+", "[REDACTED-SLACK-TOKEN]", "Slack token"),
    # Stripe keys
    (r"sk_live_[a-zA-Z0-9]{24,}", "[REDACTED-STRIPE-SECRET]", "Stripe secret key"),
    (r"pk_live_[a-zA-Z0-9]{24,}", "[REDACTED-STRIPE-PUBLIC]", "Stripe public key"),
    (r"rk_live_[a-zA-Z0-9]{24,}", "[REDACTED-STRIPE-RESTRICTED]", "Stripe restricted key"),
    # SendGrid
    (r"SG\.[a-zA-Z0-9_-]{22}\.[a-zA-Z0-9_-]{43}", "[REDACTED-SENDGRID-KEY]", "SendGrid API key"),
    # Twilio
    (r"SK[a-zA-Z0-9]{32}", "[REDACTED-TWILIO-KEY]", "Twilio API key"),
    # npm tokens
    (r"npm_[a-zA-Z0-9]{36}", "[REDACTED-NPM-TOKEN]", "npm token"),
    # Discord tokens
    (r"[MN][a-zA-Z0-9]{23,}\.[a-zA-Z0-9_-]{6}\.[a-zA-Z0-9_-]{27}", "[REDACTED-DISCORD-TOKEN]", "Discord token"),
]


class SecretRedactor:
    """Redacts secrets from content."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.redaction_count = 0
        self.redaction_types: List[str] = []

    def redact(self, content: str) -> str:
        """
        Redact secrets from content.

        Args:
            content: The content to redact

        Returns:
            Content with secrets replaced by redaction markers
        """
        result = content
        self.redaction_count = 0
        self.redaction_types = []

        for pattern, replacement, description in SECRET_PATTERNS:
            try:
                matches = re.findall(pattern, result, flags=re.IGNORECASE | re.MULTILINE)
                if matches:
                    result = re.sub(pattern, replacement, result, flags=re.IGNORECASE | re.MULTILINE)
                    count = len(matches) if isinstance(matches, list) else 1
                    self.redaction_count += count
                    self.redaction_types.append(description)

                    if self.verbose:
                        print(f"[REDACT] Found {count} {description}", file=__import__("sys").stderr)
            except re.error as e:
                if self.verbose:
                    print(f"[REDACT] Regex error for {description}: {e}", file=__import__("sys").stderr)
                continue

        return result

    def get_stats(self) -> dict:
        """Get redaction statistics from the last redact() call."""
        return {
            "redaction_count": self.redaction_count,
            "redaction_types": list(set(self.redaction_types)),
        }


def redact_secrets(content: str, verbose: bool = False) -> str:
    """
    Convenience function to redact secrets from content.

    Args:
        content: The content to redact
        verbose: Enable verbose logging

    Returns:
        Content with secrets redacted
    """
    redactor = SecretRedactor(verbose=verbose)
    return redactor.redact(content)


def contains_secrets(content: str) -> bool:
    """
    Check if content appears to contain secrets.

    Args:
        content: The content to check

    Returns:
        True if secrets are detected
    """
    for pattern, _, _ in SECRET_PATTERNS:
        try:
            if re.search(pattern, content, flags=re.IGNORECASE | re.MULTILINE):
                return True
        except re.error:
            continue
    return False
