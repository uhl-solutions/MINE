"""
test_transaction.py - Tests for transactional rollback behavior

Tests that the UpdateTransaction class properly tracks changes and rolls back
all modifications on failure, as required by SECURITY.md.
"""

import pytest
from pathlib import Path

from transaction import UpdateTransaction, TransactionError


class TestRollback:
    """Test transaction rollback behavior."""

    def test_rollback_restores_copied_file(self, tmp_path):
        """Rollback restores file to original content after copy."""
        src = tmp_path / "source.txt"
        src.write_text("source content")

        dest = tmp_path / "dest.txt"
        dest.write_text("original content")

        tx = UpdateTransaction()
        tx.copy_file(src, dest)

        # Dest should now have source content
        assert dest.read_text() == "source content"

        # Rollback
        tx.rollback()

        assert dest.read_text() == "original content"

    def test_rollback_removes_new_file(self, tmp_path):
        """Rollback removes files that didn't exist before copy."""
        src = tmp_path / "source.txt"
        src.write_text("new content")

        new_dest = tmp_path / "new_file.txt"
        assert not new_dest.exists()

        tx = UpdateTransaction()
        tx.copy_file(src, new_dest)

        assert new_dest.exists()

        # Rollback
        tx.rollback()

        assert not new_dest.exists()

    def test_rollback_restores_deleted_file(self, tmp_path):
        """Rollback restores deleted files."""
        target = tmp_path / "to_delete.txt"
        target.write_text("important content")

        tx = UpdateTransaction()
        tx.delete_file(target)

        assert not target.exists()

        # Rollback
        tx.rollback()

        assert target.exists()
        assert target.read_text() == "important content"

    def test_partial_failure_full_rollback(self, tmp_path):
        """Multiple operations should all rollback."""
        src = tmp_path / "source.txt"
        src.write_text("source")

        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"

        file1.write_text("original1")
        file2.write_text("original2")

        tx = UpdateTransaction()
        tx.copy_file(src, file1)
        tx.copy_file(src, file2)

        # Simulate failure and rollback
        tx.rollback()

        assert file1.read_text() == "original1"
        assert file2.read_text() == "original2"

    def test_commit_prevents_rollback(self, tmp_path):
        """After commit, rollback has no effect."""
        src = tmp_path / "source.txt"
        src.write_text("new content")

        dest = tmp_path / "dest.txt"
        dest.write_text("original content")

        tx = UpdateTransaction()
        tx.copy_file(src, dest)

        # Commit
        tx.commit()

        # Rollback should do nothing after commit
        tx.rollback()

        assert dest.read_text() == "new content"

    def test_context_manager_commits_on_success(self, tmp_path):
        """Transaction context manager commits on successful exit."""
        src = tmp_path / "source.txt"
        src.write_text("context manager content")

        dest = tmp_path / "dest.txt"
        dest.write_text("original")

        with UpdateTransaction() as tx:
            tx.copy_file(src, dest)
            tx.commit()

        # Should be committed (not rolled back)
        assert dest.read_text() == "context manager content"

    def test_context_manager_rolls_back_on_exception(self, tmp_path):
        """Transaction context manager rolls back on exception."""
        src = tmp_path / "source.txt"
        src.write_text("attempted change")

        dest = tmp_path / "dest.txt"
        dest.write_text("original")

        try:
            with UpdateTransaction() as tx:
                tx.copy_file(src, dest)
                raise ValueError("Simulated failure")
        except ValueError:
            pass

        # Should be rolled back
        assert dest.read_text() == "original"


class TestTransactionEdgeCases:
    """Test edge cases in transaction handling."""

    def test_empty_transaction_rollback(self, tmp_path):
        """Rollback on empty transaction does nothing."""
        tx = UpdateTransaction()
        # Should not raise
        tx.rollback()

    def test_double_rollback_is_safe(self, tmp_path):
        """Calling rollback twice is safe."""
        src = tmp_path / "source.txt"
        src.write_text("new")

        dest = tmp_path / "dest.txt"
        dest.write_text("original")

        tx = UpdateTransaction()
        tx.copy_file(src, dest)

        tx.rollback()
        tx.rollback()  # Should not raise

        assert dest.read_text() == "original"

    def test_delete_nonexistent_file(self, tmp_path):
        """Deleting nonexistent file is a no-op."""
        missing = tmp_path / "missing.txt"

        tx = UpdateTransaction()
        # Should not raise
        tx.delete_file(missing)

    def test_multiple_operations_mixed(self, tmp_path):
        """Tracks mix of copy and delete operations."""
        src = tmp_path / "source.txt"
        src.write_text("source")

        existing = tmp_path / "existing.txt"
        existing.write_text("original")

        to_delete = tmp_path / "to_delete.txt"
        to_delete.write_text("will be deleted")

        tx = UpdateTransaction()
        tx.copy_file(src, existing)
        tx.delete_file(to_delete)

        tx.rollback()

        assert existing.read_text() == "original"
        assert to_delete.exists()
        assert to_delete.read_text() == "will be deleted"


class TestTransactionCopyIntoNewDirectory:
    """Test transaction handling when creating new directories."""

    def test_copy_creates_parent_directories(self, tmp_path):
        """Copy operation creates parent directories as needed."""
        src = tmp_path / "source.txt"
        src.write_text("content")

        dest = tmp_path / "deep" / "nested" / "dir" / "file.txt"

        tx = UpdateTransaction()
        tx.copy_file(src, dest)

        assert dest.exists()
        assert dest.read_text() == "content"

        # Rollback should remove the file
        tx.rollback()

        assert not dest.exists()
