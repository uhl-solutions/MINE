"""
Error classes for integration discovery.

Provides structured exception types for expected discovery failures.
"""


class DiscoveryError(Exception):
    """Base class for expected discovery failures."""

    pass


class InvalidRootError(DiscoveryError):
    """Raised when the scan root is invalid or inaccessible."""

    pass


class InvalidConfigError(DiscoveryError):
    """Raised when the configuration is invalid."""

    pass


class OutputError(DiscoveryError):
    """Raised when output writing fails."""

    pass


class RegistryError(DiscoveryError):
    """Raised when registry operations fail."""

    pass


class SafetyError(DiscoveryError):
    """Raised when a safety policy is violated (e.g., path traversal)."""

    pass
