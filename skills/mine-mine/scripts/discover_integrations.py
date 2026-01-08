#!/usr/bin/env python3
"""
discover_integrations.py - Thin CLI wrapper for integration discovery.

This script provides the CLI interface for discovering, listing, and
registering Claude Code repository integrations. It delegates to the
discover package for all orchestration logic.
"""

import argparse
import sys
from pathlib import Path

# Setup path for shared modules and discover package
try:
    import _init_shared
except ImportError:
    pass

# Add discover package to path
sys.path.insert(0, str(Path(__file__).parent))

from cli_helpers import add_apply_argument, add_dry_run_argument, resolve_dry_run
from discover import (
    DEFAULT_REGISTRY_PATH,
    DiscoverConfig,
    load_registry,
    print_discovery_result,
    print_list_result,
    print_register_result,
    run_discovery,
    run_list,
    run_register,
    run_unregister,
    save_registry,
)

try:
    from url_utils import sanitize_json_urls
except ImportError:
    sanitize_json_urls = lambda x: x


class IntegrationDiscovery:
    """
    Backward-compatible class for registry access.

    New code should use discover.load_registry / discover.save_registry directly.
    This class is provided for compatibility with update_integrations.py and
    import_assets.py.
    """

    def __init__(self, registry_path: Path, verbose: bool = False):
        self.registry_path = registry_path
        self.verbose = verbose
        self.registry = self._load_registry()

    def _log(self, message: str):
        if self.verbose:
            print(f"[DISCOVER] {message}", file=sys.stderr)

    def _load_registry(self):
        return load_registry(self.registry_path)

    def _save_registry(self):
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        sanitized_registry = sanitize_json_urls(self.registry)
        save_registry(self.registry_path, sanitized_registry)


def main() -> int:
    """CLI entrypoint - thin wrapper delegating to discover package."""
    parser = argparse.ArgumentParser(
        description="Discover and register integrated Claude Code repositories",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Commands
    parser.add_argument("--list", action="store_true", help="List all registered integrations")
    parser.add_argument("--discover", action="store_true", help="Discover integrations in target locations")
    parser.add_argument("--register", action="store_true", help="Manually register an integration")
    parser.add_argument("--unregister", metavar="ID", help="Unregister an integration by ID")

    # Register options
    parser.add_argument("--source", help="Source URL (for --register)")
    parser.add_argument("--scope", choices=["user", "project"], help="Target scope (for --register)")

    # Common options
    parser.add_argument("--target-repo", help="Target repository path (for project scope)")
    parser.add_argument("--search-roots", help="Comma-separated list of search roots (for --discover)")
    parser.add_argument("--no-confirm", action="store_true", help="Skip confirmation prompts")
    parser.add_argument(
        "--registry",
        default=str(DEFAULT_REGISTRY_PATH),
        help=f"Registry file path (default: {DEFAULT_REGISTRY_PATH})",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    # Unregister options
    parser.add_argument(
        "--delete-files", action="store_true", help="Also delete imported artifact files (with --unregister)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force delete even locally modified files (with --unregister --delete-files)",
    )

    # Standardized dry-run and apply arguments
    add_dry_run_argument(parser, help_text="Preview changes only (default: true)")
    add_apply_argument(parser)

    args = parser.parse_args()

    # Build config
    registry_path = Path(args.registry).expanduser()
    search_roots = []
    if args.search_roots:
        search_roots = [r.strip() for r in args.search_roots.split(",")]
    target_repo = None
    if args.target_repo:
        target_repo = Path(args.target_repo).expanduser()

    effective_dry_run = resolve_dry_run(args)

    cfg = DiscoverConfig(
        registry_path=registry_path,
        verbose=args.verbose,
        search_roots=search_roots,
        target_repo=target_repo,
        ask_confirmation=not args.no_confirm,
        dry_run=effective_dry_run,
    )

    # Handle commands
    if args.list:
        result = run_list(cfg, verbose=args.verbose)
        print_list_result(result, args.verbose)
        return result.exit_code

    elif args.discover:
        result = run_discovery(cfg)
        print_discovery_result(result, args.verbose)
        return result.exit_code

    elif args.register:
        if not args.source or not args.scope:
            print("Error: --register requires --source and --scope")
            return 1
        result = run_register(cfg, source_url=args.source, scope=args.scope, target_repo=args.target_repo)
        print_register_result(result)
        return result.exit_code

    elif args.unregister:
        result = run_unregister(
            cfg,
            integration_id=args.unregister,
            delete_files=args.delete_files,
            force=args.force,
        )
        return result.exit_code

    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
