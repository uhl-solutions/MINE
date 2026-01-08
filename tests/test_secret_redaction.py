#!/usr/bin/env python3
"""
test_secret_redaction.py - Comprehensive tests for secret redaction

Tests the redaction.py module's secret detection and replacement.
Covers all supported secret patterns and validates no over-redaction.
"""

import pytest
import sys
from pathlib import Path

# Add shared modules to path
SHARED_DIR = Path(__file__).resolve().parent.parent / "skills" / "_shared"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from redaction import redact_secrets, contains_secrets, SecretRedactor

DOC_CLAIMS = ["secrets_redacted"]


class TestSecretRedaction:
    """Tests for positive secret redaction cases."""

    def test_openai_key_redacted(self):
        """OpenAI API keys (sk-...) are redacted."""
        # Pattern: sk-[a-zA-Z0-9]{40,} (40+ alphanumeric after sk-)
        content = 'OPENAI_API_KEY="sk-abcdefghijklmnopqrstuvwxyz0123456789ABCD"'
        result = redact_secrets(content)

        assert "sk-abcdefg" not in result
        assert "[REDACTED-OPENAI-KEY]" in result

    def test_anthropic_key_redacted(self):
        """Anthropic API keys (sk-ant-...) are redacted."""
        # Pattern: sk-ant-[a-zA-Z0-9-]{80,} (80+ chars after sk-ant-)
        key = "sk-ant-" + "a" * 85
        content = f'ANTHROPIC_API_KEY="{key}"'
        result = redact_secrets(content)

        assert "sk-ant-" not in result
        assert "[REDACTED-ANTHROPIC-KEY]" in result

    def test_github_pat_redacted(self):
        """GitHub Personal Access Tokens (ghp_...) are redacted."""
        # Pattern: ghp_[a-zA-Z0-9]{36,}
        content = 'GITHUB_TOKEN="ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh12"'
        result = redact_secrets(content)

        assert "ghp_ABCDEF" not in result
        assert "[REDACTED-GITHUB-PAT]" in result

    def test_github_oauth_redacted(self):
        """GitHub OAuth tokens (gho_...) are redacted."""
        content = 'token = "gho_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh12"'
        result = redact_secrets(content)

        assert "gho_ABCDEF" not in result
        assert "[REDACTED-GITHUB-OAUTH]" in result

    def test_github_user_token_redacted(self):
        """GitHub User tokens (ghu_...) are redacted."""
        content = "ghu_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij12"
        result = redact_secrets(content)

        assert "ghu_ABCDEF" not in result
        assert "[REDACTED-GITHUB-USER]" in result

    def test_aws_access_key_id_redacted(self):
        """AWS Access Key IDs (AKIA...) are redacted."""
        # Pattern: AKIA[A-Z0-9]{16}
        content = 'AWS_ACCESS_KEY_ID="AKIAIOSFODNN7EXAMPLE"'
        result = redact_secrets(content)

        assert "AKIAIOSFODNN7EXAMPLE" not in result
        assert "[REDACTED-AWS-ACCESS-KEY]" in result

    def test_aws_secret_key_redacted(self):
        """AWS Secret Access Keys (40 chars) are redacted with context."""
        content = 'aws_secret_access_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"'
        result = redact_secrets(content)

        assert "wJalrXUtnFEMI" not in result
        assert "[REDACTED-AWS-SECRET]" in result
        # Verify context is preserved
        assert "aws_secret_access_key" in result

    def test_aws_secret_key_json_format(self):
        """AWS Secret Key in JSON format is redacted."""
        content = '{"aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYzzzzzzzzzz"}'
        result = redact_secrets(content)

        assert "wJalrXUtnFEMI" not in result
        assert "[REDACTED-AWS-SECRET]" in result

    def test_aws_secret_key_no_quotes(self):
        """AWS Secret Key without quotes is redacted."""
        content = "secret_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYaaaaaaaaaaa"
        result = redact_secrets(content)

        assert "wJalrXUtnFEMI" not in result
        assert "[REDACTED-AWS-SECRET]" in result

    def test_google_api_key_redacted(self):
        """Google API keys (AIza...) are redacted."""
        # Pattern: AIza[a-zA-Z0-9_-]{35}
        content = 'GOOGLE_API_KEY="AIzaSyDaGmWKa4JsXZ-HjGw7ISLn_3namBGewQe"'
        result = redact_secrets(content)

        assert "AIzaSyDaGmWKa" not in result
        assert "[REDACTED-GOOGLE-API-KEY]" in result

    def test_rsa_private_key_redacted(self):
        """RSA private keys (PEM format) are redacted."""
        content = """-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEAklDrkjl4vQ7J8q3h
-----END RSA PRIVATE KEY-----"""
        result = redact_secrets(content)

        assert "MIIEowIBAAKCAQEA" not in result
        assert "[REDACTED-PRIVATE-KEY]" in result

    def test_ec_private_key_redacted(self):
        """EC private keys (PEM format) are redacted."""
        content = """-----BEGIN EC PRIVATE KEY-----
MHQCAQEEIMVyf4Q5
-----END EC PRIVATE KEY-----"""
        result = redact_secrets(content)

        assert "MHQCAQEEIMVyf4Q5" not in result
        assert "[REDACTED-EC-PRIVATE-KEY]" in result

    def test_ssh_private_key_redacted(self):
        """SSH private keys (OpenSSH format) are redacted."""
        content = """-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmU
-----END OPENSSH PRIVATE KEY-----"""
        result = redact_secrets(content)

        assert "b3BlbnNzaC1rZXktdjEAAAAABG5vbmU" not in result
        assert "[REDACTED-SSH-PRIVATE-KEY]" in result

    def test_slack_token_redacted(self):
        """Slack tokens (xox...) are redacted."""
        content = 'SLACK_TOKEN="xoxb-123456789012-1234567890123-abcdefghijklmnop"'
        result = redact_secrets(content)

        # Secret should be removed - pattern matches xox[baprs]-...
        assert "xoxb-123456789012" not in result
        assert "[REDACTED" in result  # Could be SLACK-TOKEN or generic

    def test_stripe_secret_key_redacted(self):
        """Stripe secret keys (sk_live_...) are redacted."""
        # Pattern: sk_live_[a-zA-Z0-9]{24,}
        content = 'STRIPE_KEY="sk_live_1234567890abcdefghijklmn"'
        result = redact_secrets(content)

        assert "sk_live_1234567890" not in result
        assert "[REDACTED-STRIPE-SECRET]" in result

    def test_sendgrid_key_redacted(self):
        """SendGrid API keys are redacted."""
        # Pattern: SG\.[a-zA-Z0-9_-]{22}\.[a-zA-Z0-9_-]{43}
        content = 'SENDGRID_API_KEY="SG.abcdefghijklmnopqrstuv.wxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abc"'
        result = redact_secrets(content)

        assert "SG.abcdefghij" not in result
        assert "[REDACTED-SENDGRID-KEY]" in result

    def test_npm_token_redacted(self):
        """npm tokens are redacted."""
        # Pattern: npm_[a-zA-Z0-9]{36}
        # Note: The token may be caught by generic pattern (token=...) or npm-specific
        content = 'NPM_TOKEN="npm_abcdefghijklmnopqrstuvwxyz0123456789"'
        result = redact_secrets(content)

        # The important thing is the secret value is removed
        assert "npm_abcdefghij" not in result
        assert "[REDACTED" in result  # Could match npm-specific or generic token pattern

    def test_generic_api_key_redacted(self):
        """Generic API keys with contextual hints are redacted."""
        content = 'api_key = "abcdefghijklmnop1234"'
        result = redact_secrets(content)

        assert "abcdefghijklmnop1234" not in result
        assert "[REDACTED]" in result

    def test_bearer_token_redacted(self):
        """Bearer tokens in Authorization headers are redacted."""
        content = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc"
        result = redact_secrets(content)

        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result
        assert "[REDACTED]" in result

    def test_connection_string_redacted(self):
        """Database connection strings with credentials are redacted."""
        content = 'DATABASE_URL="postgres://user:password123@localhost:5432/mydb"'
        result = redact_secrets(content)

        assert "password123@" not in result
        assert "[REDACTED-CONNECTION-STRING]" in result


class TestNoOverRedaction:
    """Tests to ensure we don't over-redact common non-secret patterns."""

    def test_no_overredaction_md5_hash(self):
        """MD5 hashes (32 hex chars) should not be redacted without context."""
        # This should NOT match because there's no "api_key" or similar context
        content = 'checksum = "d41d8cd98f00b204e9800998ecf8427e"'
        result = redact_secrets(content)

        # MD5 hash should remain intact (no contextual hints like api_key)
        assert "d41d8cd98f00b204e9800998ecf8427e" in result

    def test_no_overredaction_sha1_hash(self):
        """SHA-1 hashes (40 hex chars) should not be redacted without context."""
        content = 'commit = "2fd4e1c67a2d28fced849ee1bb76e7391b93eb12"'
        result = redact_secrets(content)

        # SHA-1 should remain intact unless it looks like a key
        assert "2fd4e1c67a2d28fced849ee1bb76e7391b93eb12" in result

    def test_no_overredaction_uuid(self):
        """UUIDs should not be redacted."""
        content = 'id = "550e8400-e29b-41d4-a716-446655440000"'
        result = redact_secrets(content)

        assert "550e8400-e29b-41d4-a716-446655440000" in result

    def test_no_overredaction_git_commit(self):
        """Git commit SHAs should not be redacted without secret context."""
        content = 'ref = "abc123def456789012345678901234567890abcd"'
        result = redact_secrets(content)

        # Should remain because 'ref' is not a secret context indicator
        assert "abc123def456789012345678901234567890abcd" in result

    def test_preserves_regular_text(self):
        """Regular text without secrets is preserved."""
        content = """
        This is a normal document.
        It has some technical terms like API and KEY.
        But no actual secrets here.
        """
        result = redact_secrets(content)

        assert "This is a normal document" in result
        assert "[REDACTED" not in result


class TestSecretRedactorClass:
    """Tests for the SecretRedactor class interface."""

    def test_redactor_stats(self):
        """SecretRedactor tracks redaction statistics."""
        redactor = SecretRedactor()
        # Use secrets that will definitely match the patterns
        content = 'key1="sk-abcdefghijklmnopqrstuvwxyz0123456789ABCD" key2="ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh12"'

        result = redactor.redact(content)
        stats = redactor.get_stats()

        # We should have at least 2 redactions (OpenAI and GitHub)
        assert stats["redaction_count"] >= 2
        assert len(stats["redaction_types"]) >= 2

    def test_verbose_mode(self):
        """Verbose mode doesn't crash (output goes to stderr)."""
        redactor = SecretRedactor(verbose=True)
        content = 'OPENAI_API_KEY="sk-abcdefghijklmnopqrstuvwxyz0123456789ABCD"'

        # Should not raise
        result = redactor.redact(content)
        assert "[REDACTED" in result


class TestContainsSecrets:
    """Tests for the contains_secrets helper function."""

    def test_detects_openai_key(self):
        """Detects OpenAI key presence."""
        content = 'key="sk-abcdefghijklmnopqrstuvwxyz0123456789ABCD"'
        assert contains_secrets(content) is True

    def test_no_secrets_in_clean_content(self):
        """Returns False for content without secrets."""
        content = "This is clean content with no secrets."
        assert contains_secrets(content) is False

    def test_detects_aws_access_key(self):
        """Detects AWS access key ID."""
        content = 'AWS_KEY="AKIAIOSFODNN7EXAMPLE"'
        assert contains_secrets(content) is True


class TestAzureContextualRedaction:
    """Tests for Azure-specific contextual redaction (prevents over-redaction)."""

    def test_azure_key_with_context_redacted(self):
        """Azure key with contextual hint is redacted."""
        content = 'azure_storage_key = "abcdefghijklmnopqrstuvwxyz123456"'
        result = redact_secrets(content)

        assert "abcdefghijklmnopqrstuvwxyz123456" not in result
        assert "[REDACTED-AZURE" in result

    def test_azure_subscription_key_redacted(self):
        """Azure subscription key is redacted."""
        content = 'subscription_key = "abcdefghijklmnopqrstuvwxyz123456"'
        result = redact_secrets(content)

        assert "abcdefghijklmnopqrstuvwxyz123456" not in result
        assert "[REDACTED-AZURE" in result

    def test_azure_client_secret_redacted(self):
        """Azure client secret is redacted."""
        content = 'client_secret: "abcd1234efgh5678ijkl9012mnop3456"'
        result = redact_secrets(content)

        assert "abcd1234efgh5678ijkl9012mnop3456" not in result
        assert "[REDACTED-AZURE" in result

    def test_azure_connection_string_redacted(self):
        """Azure Storage connection strings are redacted."""
        key = "a" * 88
        content = f"DefaultEndpointsProtocol=https;AccountName=myaccount;AccountKey={key};"
        result = redact_secrets(content)

        assert key not in result
        assert "[REDACTED" in result

    def test_no_overredaction_md5_hash(self):
        """MD5 hashes (32 hex chars) should NOT be redacted without context."""
        content = 'checksum = "d41d8cd98f00b204e9800998ecf8427e"'
        result = redact_secrets(content)

        # MD5 hash should remain intact (no Azure-specific context)
        assert "d41d8cd98f00b204e9800998ecf8427e" in result

    def test_no_overredaction_random_id(self):
        """Random 32-char IDs without Azure context should NOT be redacted."""
        content = 'request_id = "abc123def456abc123def456abc12345"'
        result = redact_secrets(content)

        # Should remain because 'request_id' is not an Azure context
        assert "abc123def456abc123def456abc12345" in result

    def test_no_overredaction_commit_hash(self):
        """Git commit hashes should NOT be redacted."""
        content = 'commit = "a1b2c3d4e5f6g7h8i9j0a1b2c3d4e5f6"'
        result = redact_secrets(content)

        assert "a1b2c3d4e5f6g7h8i9j0a1b2c3d4e5f6" in result

    def test_no_overredaction_uuid_without_dashes(self):
        """UUIDs without dashes should NOT be redacted."""
        content = 'id = "550e8400e29b41d4a716446655440000"'
        result = redact_secrets(content)

        assert "550e8400e29b41d4a716446655440000" in result
