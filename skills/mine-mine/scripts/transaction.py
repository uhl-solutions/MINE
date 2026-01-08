"""
transaction.py - Transaction management for file operations.

Provides atomicity and rollback capabilities for file updates.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Callable, List

import platform_utils


class TransactionError(Exception):
    """Raised when a transaction fails."""

    pass


class UpdateTransaction:
    """
    Manages a sequence of file operations with rollback capability.

    If any operation fails, or if rollback() is called, all changes
    are reverted to their original state.
    """

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._rollbacks: List[Callable[[], None]] = []
        self._temp_dir = tempfile.mkdtemp(prefix="claude-txn-")
        self._committed = False
        self._active = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            # Exception occurred, rollback
            self.rollback()
        elif not self._committed:
            # No exception but commit() wasn't called (e.g. return)
            # Should we rollback? Usually yes for safety in a txn block.
            # But let's assume explicit commit is required.
            if self._active:
                self.rollback()

        # Cleanup temp dir
        if os.path.exists(self._temp_dir):
            try:
                shutil.rmtree(self._temp_dir)
            except Exception as e:
                if self.verbose:
                    print(f"Warning: Failed to cleanup temp dir {self._temp_dir}: {e}", file=sys.stderr)

    def _log(self, msg: str):
        if self.verbose:
            print(f"[TXN] {msg}", file=sys.stderr)

    def copy_file(self, src: Path, dest: Path):
        """
        Copy src to dest.
        If dest exists, it is backed up for rollback.
        If dest doesn't exist, rollback will delete it.
        """
        if not self._active:
            raise TransactionError("Transaction is not active")

        dest = Path(dest).resolve()
        src = Path(src).resolve()

        if dest.exists():
            # Backup existing file
            backup_name = str(len(self._rollbacks)) + "_" + dest.name
            backup_path = Path(self._temp_dir) / backup_name
            shutil.copy2(platform_utils.get_long_path(dest), platform_utils.get_long_path(backup_path))

            def restore_existing():
                if backup_path.exists():
                    shutil.copy2(platform_utils.get_long_path(backup_path), platform_utils.get_long_path(dest))

            self._rollbacks.append(restore_existing)
        else:
            # Dest doesn't exist, rollback means delete it
            def delete_created():
                if dest.exists():
                    dest.unlink()

            self._rollbacks.append(delete_created)

        # Perform operation
        try:
            os.makedirs(platform_utils.get_long_path(dest.parent), exist_ok=True)
            shutil.copy2(platform_utils.get_long_path(src), platform_utils.get_long_path(dest))
        except Exception as e:
            raise TransactionError(f"Failed to copy {src} to {dest}: {e}")

    def delete_file(self, target: Path):
        """
        Delete target file.
        Target is moved to temp for rollback.
        """
        if not self._active:
            raise TransactionError("Transaction is not active")

        target = Path(target).resolve()

        if not target.exists():
            return  # Nothing to delete

        # Backup for rollback
        backup_name = str(len(self._rollbacks)) + "_del_" + target.name
        backup_path = Path(self._temp_dir) / backup_name
        shutil.copy2(platform_utils.get_long_path(target), platform_utils.get_long_path(backup_path))

        def restore_deleted():
            os.makedirs(platform_utils.get_long_path(target.parent), exist_ok=True)
            shutil.copy2(platform_utils.get_long_path(backup_path), platform_utils.get_long_path(target))

        self._rollbacks.append(restore_deleted)

        # Perform operation
        try:
            os.unlink(platform_utils.get_long_path(target))
        except Exception as e:
            raise TransactionError(f"Failed to delete {target}: {e}")

    def commit(self):
        """Commit the transaction. Clears rollback history."""
        self._committed = True
        self._active = False
        self._rollbacks.clear()
        self._log("Transaction committed.")

    def rollback(self):
        """Revert all changes in reverse order."""
        if not self._active:
            return

        self._log("Rolling back transaction...")
        for rollback_func in reversed(self._rollbacks):
            try:
                rollback_func()
            except Exception as e:
                print(f"Error during rollback: {e}", file=sys.stderr)

        self._active = False
        self._log("Rollback complete.")
