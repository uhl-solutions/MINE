"""
Registry management for integration discovery.

Provides functions for loading, saving, and managing the integration
registry file.
"""

import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

# Try to import shared modules
try:
    import _init_shared
except ImportError:
    # Add shared module path manually
    _shared_path = Path(__file__).parent.parent.parent.parent / "_shared"
    if str(_shared_path) not in sys.path:
        sys.path.insert(0, str(_shared_path))

from safe_io import safe_load_json, safe_write_json


# Default registry structure
DEFAULT_REGISTRY_STRUCTURE = {
    "version": "1.0",
    "config": {
        "search_roots": [],
        "auto_track": True,
        "ask_confirmation": True,
    },
    "integrations": {},
}


def load_registry(
    registry_path: Path,
    log_fn: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    Load the integration registry from disk.

    Uses safe_load_json which handles corruption and backup recovery.

    Args:
        registry_path: Path to the registry JSON file
        log_fn: Optional logging function

    Returns:
        Registry dictionary (default structure if file doesn't exist or is corrupt)
    """
    default = DEFAULT_REGISTRY_STRUCTURE.copy()
    default["config"] = DEFAULT_REGISTRY_STRUCTURE["config"].copy()
    default["integrations"] = {}

    registry = safe_load_json(registry_path, default=default)

    if registry == default and registry_path.exists():
        if log_fn:
            log_fn("Failed to load registry (corrupt or unreadable), using default")

    return registry


def save_registry(
    registry_path: Path,
    registry: Dict[str, Any],
    log_fn: Optional[Callable[[str], None]] = None,
) -> bool:
    """
    Save the integration registry to disk.

    Uses atomic write with backup and URL sanitization.

    Args:
        registry_path: Path to the registry JSON file
        registry: Registry dictionary to save
        log_fn: Optional logging function

    Returns:
        True if save was successful

    Raises:
        RuntimeError: If save fails
    """
    # Import URL sanitization utility
    try:
        from url_utils import sanitize_json_urls
    except ImportError:

        def sanitize_json_urls(x):
            return x

    # Ensure parent directory exists
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    # Sanitize URL credentials before writing to disk
    sanitized_registry = sanitize_json_urls(registry)

    # Use safe_write_json for atomic write with backup and locking
    ok = safe_write_json(registry_path, sanitized_registry, indent=2)

    if not ok:
        raise RuntimeError(f"Failed to save registry to {registry_path}")

    if log_fn:
        log_fn(f"Registry saved to {registry_path}")

    return True


def get_integration(
    registry: Dict[str, Any],
    integration_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Get an integration by ID from the registry.

    Args:
        registry: Registry dictionary
        integration_id: ID of the integration to retrieve

    Returns:
        Integration dictionary or None if not found
    """
    return registry.get("integrations", {}).get(integration_id)


def add_integration(
    registry: Dict[str, Any],
    integration_id: str,
    integration: Dict[str, Any],
) -> None:
    """
    Add or update an integration in the registry.

    Args:
        registry: Registry dictionary (modified in place)
        integration_id: ID for the integration
        integration: Integration data dictionary
    """
    if "integrations" not in registry:
        registry["integrations"] = {}

    registry["integrations"][integration_id] = integration


def remove_integration(
    registry: Dict[str, Any],
    integration_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Remove an integration from the registry.

    Args:
        registry: Registry dictionary (modified in place)
        integration_id: ID of the integration to remove

    Returns:
        The removed integration or None if not found
    """
    integrations = registry.get("integrations", {})
    return integrations.pop(integration_id, None)


def list_integrations(
    registry: Dict[str, Any],
    scope: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    List integrations from the registry, optionally filtered by scope.

    Args:
        registry: Registry dictionary
        scope: Filter by scope ("user" or "project"), None for all

    Returns:
        Dictionary of integration_id -> integration
    """
    integrations = registry.get("integrations", {})

    if scope:
        return {k: v for k, v in integrations.items() if v.get("target_scope") == scope}

    return integrations


def generate_integration_id(
    registry: Dict[str, Any],
    scope: str,
    repo_name: str,
) -> str:
    """
    Generate a unique integration ID.

    Args:
        registry: Registry dictionary
        scope: Target scope ("user" or "project")
        repo_name: Repository name to base ID on

    Returns:
        Unique integration ID
    """
    base_id = f"{scope}-{repo_name}"
    integration_id = base_id
    counter = 1

    integrations = registry.get("integrations", {})
    while integration_id in integrations:
        integration_id = f"{base_id}-{counter}"
        counter += 1

    return integration_id


def get_config(
    registry: Dict[str, Any],
    key: str,
    default: Any = None,
) -> Any:
    """
    Get a configuration value from the registry.

    Args:
        registry: Registry dictionary
        key: Configuration key
        default: Default value if key not found

    Returns:
        Configuration value or default
    """
    return registry.get("config", {}).get(key, default)


def set_config(
    registry: Dict[str, Any],
    key: str,
    value: Any,
) -> None:
    """
    Set a configuration value in the registry.

    Args:
        registry: Registry dictionary (modified in place)
        key: Configuration key
        value: Value to set
    """
    if "config" not in registry:
        registry["config"] = {}

    registry["config"][key] = value
