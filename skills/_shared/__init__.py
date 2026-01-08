"""
MINE Shared Utilities Library
"""

from .artifact_types import (
    ArtifactType,
    Scope,
    ImportMode,
    FrameworkType,
    get_destination,
    sanitize_repo_id,
    is_importable_artifact,
    is_convertible_artifact,
    MAX_ARTIFACTS,
    MAX_SCAN_TIME,
    SKILL_PATTERNS,
    COMMAND_PATTERNS,
    AGENT_PATTERNS,
    HOOK_PATTERNS,
    MCP_PATTERNS,
    DOC_PATTERNS,
    BUILD_PATTERNS,
)
from .hash_helpers import hash_file, hash_string
from .path_safety import PathSafetyError, is_safe_path, validate_path
from .platform_utils import get_long_path, is_windows_path, is_wsl
from .redaction import SecretRedactor, redact_secrets
from .safe_io import safe_load_json, safe_update_json, safe_write_json, safe_write_text
from .url_utils import clone_with_auth_fallback, redact_url_credentials, sanitize_json_urls
from .cli_helpers import (
    add_dry_run_argument,
    add_apply_argument,
    resolve_dry_run,
    get_dry_run_prefix,
    print_dry_run_notice,
    DryRunAction,
    NoDryRunAction,
)
from .logging_utils import (
    setup_logging,
    get_logger,
    add_logging_arguments,
    log_action,
    log_skip,
)
from .skill_creator_bridge import (
    is_skill_creator_available,
    get_skill_creator_path,
    should_handoff,
    generate_handoff_context,
    format_handoff_message,
    get_skill_creator_instructions,
    DEFAULT_HANDOFF_THRESHOLD,
)

__all__ = [
    # Artifact types
    "ArtifactType",
    "Scope",
    "ImportMode",
    "FrameworkType",
    "get_destination",
    "sanitize_repo_id",
    "is_importable_artifact",
    "is_convertible_artifact",
    "MAX_ARTIFACTS",
    "MAX_SCAN_TIME",
    "SKILL_PATTERNS",
    "COMMAND_PATTERNS",
    "AGENT_PATTERNS",
    "HOOK_PATTERNS",
    "MCP_PATTERNS",
    "DOC_PATTERNS",
    "BUILD_PATTERNS",
    # Safe I/O
    "safe_write_text",
    "safe_write_json",
    "safe_update_json",
    "safe_load_json",
    # Path safety
    "validate_path",
    "is_safe_path",
    "PathSafetyError",
    # Platform utils
    "is_wsl",
    "is_windows_path",
    "get_long_path",
    # Redaction
    "redact_secrets",
    "SecretRedactor",
    # URL utils
    "redact_url_credentials",
    "sanitize_json_urls",
    "clone_with_auth_fallback",
    # Hash helpers
    "hash_file",
    "hash_string",
    # CLI helpers
    "add_dry_run_argument",
    "add_apply_argument",
    "resolve_dry_run",
    "get_dry_run_prefix",
    "print_dry_run_notice",
    "DryRunAction",
    "NoDryRunAction",
    # Logging utils
    "setup_logging",
    "get_logger",
    "add_logging_arguments",
    "log_action",
    "log_skip",
    # Skill-creator bridge
    "is_skill_creator_available",
    "get_skill_creator_path",
    "should_handoff",
    "generate_handoff_context",
    "format_handoff_message",
    "get_skill_creator_instructions",
    "DEFAULT_HANDOFF_THRESHOLD",
]
