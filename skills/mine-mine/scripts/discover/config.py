"""
Configuration dataclass and defaults for integration discovery.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


# Default registry path
DEFAULT_REGISTRY_PATH = Path.home() / ".claude" / "mine" / "registry.json"


@dataclass
class DiscoverConfig:
    """
    Configuration for integration discovery operations.

    Attributes:
        registry_path: Path to the registry JSON file
        verbose: Enable verbose logging
        search_roots: List of directories to search for integrations
        auto_track: Automatically track discovered integrations
        ask_confirmation: Ask for confirmation before adding to registry
        target_repo: Specific repository to scan (project scope)
        skip_dirs: Directories to skip during scanning
        dry_run: Preview changes without writing (default: False for API)
    """

    registry_path: Path = field(default_factory=lambda: DEFAULT_REGISTRY_PATH)
    verbose: bool = False
    search_roots: List[str] = field(default_factory=list)
    auto_track: bool = True
    ask_confirmation: bool = True
    target_repo: Optional[Path] = None
    skip_dirs: List[str] = field(default_factory=lambda: ["node_modules", "venv", "__pycache__", ".git"])
    dry_run: bool = False

    def __post_init__(self):
        """Normalize paths after initialization."""
        if isinstance(self.registry_path, str):
            self.registry_path = Path(self.registry_path).expanduser()
        if isinstance(self.target_repo, str):
            self.target_repo = Path(self.target_repo).expanduser()

    @classmethod
    def from_args(cls, args) -> "DiscoverConfig":
        """
        Create a DiscoverConfig from parsed command-line arguments.

        Args:
            args: Namespace from argparse.parse_args()

        Returns:
            DiscoverConfig instance
        """
        search_roots = []
        if hasattr(args, "search_roots") and args.search_roots:
            search_roots = [r.strip() for r in args.search_roots.split(",")]

        target_repo = None
        if hasattr(args, "target_repo") and args.target_repo:
            target_repo = Path(args.target_repo).expanduser()

        registry_path = DEFAULT_REGISTRY_PATH
        if hasattr(args, "registry") and args.registry:
            registry_path = Path(args.registry).expanduser()

        return cls(
            registry_path=registry_path,
            verbose=getattr(args, "verbose", False),
            search_roots=search_roots,
            target_repo=target_repo,
            ask_confirmation=not getattr(args, "no_confirm", False),
        )

    def get_search_locations(self) -> List[tuple]:
        """
        Determine search locations based on configuration.

        Returns:
            List of (scope, path) tuples to scan
        """
        locations = []

        # Add current directory if it has a .claude folder (unless target_repo is set)
        if not self.target_repo:
            cwd = Path.cwd()
            if (cwd / ".claude").exists():
                locations.append(("project", cwd))

        # Add target repository if specified
        if self.target_repo:
            locations.append(("project", self.target_repo))

        # Add search roots
        for root in self.search_roots:
            root_path = Path(root).expanduser()
            if root_path.exists():
                locations.append(("root", root_path))

        # Always check user scope
        locations.append(("user", Path.home() / ".claude"))

        return locations
