#!/usr/bin/env python3
"""
safe_io.py

Cross-platform helpers for:
  - cross-process file locking
  - collision-free, atomic JSON writes (os.replace)
  - race-free read→modify→write operations

Goal:
  - Readers see either the old complete file or the new complete file (never partial).
  - Multiple writers serialize via a lock file to avoid "last writer wins with stale data".
  - Read→modify→write operations are atomic (no lost updates).
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Optional


class FileLockTimeoutError(RuntimeError):
    """Raised when lock acquisition times out."""

    pass


@contextmanager
def file_lock(lock_path: Path, timeout_s: float = 10.0, poll_s: float = 0.1) -> Iterator[None]:
    """
    Cross-platform advisory lock using a dedicated lock file.

    - Unix: fcntl.flock (exclusive lock)
    - Windows: msvcrt.locking on 1 byte

    Usage:
        with file_lock(Path("registry.json.lock")):
            # ... read, modify, write registry.json ...
    """
    # Use os.makedirs instead of Path.mkdir so tests can patch Path.stat()
    # without breaking directory existence checks inside pathlib.
    os.makedirs(lock_path.parent, exist_ok=True)

    fh = open(lock_path, "a+", encoding="utf-8", errors="replace")
    start = time.monotonic()

    def _try_lock() -> None:
        if os.name == "nt":  # pragma: win32-only
            import msvcrt

            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:  # pragma: posix-only
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock() -> None:
        try:
            if os.name == "nt":  # pragma: win32-only
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:  # pragma: posix-only
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass

    try:
        while True:
            try:
                _try_lock()
                break
            except OSError:
                if (time.monotonic() - start) >= timeout_s:
                    raise FileLockTimeoutError(f"Timed out waiting for lock: {lock_path}")
                time.sleep(poll_s)

        yield
    finally:
        _unlock()
        try:
            fh.close()
        except Exception:
            pass


def _fsync_dir_if_possible(directory: Path) -> None:
    """
    On Unix, fsync the directory after os.replace to reduce the chance of
    missing directory entry updates after a crash.
    On Windows, this is typically unnecessary / unsupported in the same way.
    """
    if os.name == "nt":  # pragma: win32-only
        return

    # POSIX-only (directory fsync)
    if os.name != "nt":  # pragma: posix-only
        try:
            fd = os.open(str(directory), os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except Exception:
            # Best effort only
            pass


def safe_load_json(path: Path, default: Any = None) -> Any:
    """
    Safely load JSON from a file.

    Returns default if file doesn't exist or is corrupt.
    Attempts to recover from backup if main file is corrupt.

    Note: No lock is acquired because with os.replace() writers,
    readers always see either the complete old file or complete new file,
    never a partial write.
    """
    return _safe_load_json_unlocked(path, default=default, allow_backup_recovery=True)


def _safe_load_json_unlocked(
    path: Path,
    default: Any = None,
    *,
    allow_backup_recovery: bool = False,
) -> Any:
    """
    Load JSON without acquiring lock (for use inside locked sections).

    INTERNAL USE ONLY - call this only when you already hold the lock.

    Args:
        path: Path to JSON file
        default: Value to return if file doesn't exist or is corrupt
        allow_backup_recovery: If True, attempt to recover from .bak file
                               when main file is corrupt. Should be True
                               for safe_update_json() to avoid "resetting"
                               state when main file is corrupt but .bak exists.
    """
    if not path.exists():
        return default

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except json.JSONDecodeError:
        # Main file is corrupt
        if allow_backup_recovery:
            backup_path = path.with_suffix(path.suffix + ".bak")
            if backup_path.exists():
                try:
                    with open(backup_path, "r", encoding="utf-8", errors="replace") as f:
                        return json.load(f)
                except (json.JSONDecodeError, OSError):
                    pass
        return default
    except OSError:
        return default


def _is_valid_json_file(path: Path) -> bool:
    """
    Return True iff `path` exists and contains valid JSON.

    IMPORTANT: Used to avoid overwriting a previously-good `.bak` with corrupt
    bytes from a corrupted main file during recovery flows.
    """
    try:
        if not path.exists():
            return False
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            json.load(f)
        return True
    except (OSError, json.JSONDecodeError):
        return False


def _safe_write_json_unlocked(
    path: Path,
    data: Any,
    *,
    indent: int = 2,
    ensure_ascii: bool = False,
    create_backup: bool = True,
) -> bool:
    """
    Write JSON without acquiring lock (for use inside locked sections).

    INTERNAL USE ONLY - call this only when you already hold the lock.
    """
    os.makedirs(path.parent, exist_ok=True)

    # Create UNIQUE temp file in the same directory
    tmp_path: Optional[Path] = None

    try:
        tmp_fd, tmp_name = tempfile.mkstemp(
            prefix=path.name + ".",
            suffix=".tmp",
            dir=str(path.parent),
        )
        tmp_path = Path(tmp_name)

        # Write to temp file with fsync
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="\n", errors="replace") as f:
            json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)
            f.flush()
            os.fsync(f.fileno())

        # Create backup BEFORE replacing (while we hold the lock)
        if create_backup and os.path.exists(path):
            backup_path = path.with_suffix(path.suffix + ".bak")
            try:
                if _is_valid_json_file(path):
                    # Main file is valid - safe to use as new backup
                    shutil.copy2(path, backup_path)
            except Exception:
                pass  # Best-effort backup

        # Atomic replace - works on both Unix and Windows
        os.replace(tmp_path, path)

        # Fsync directory on Unix for crash safety
        _fsync_dir_if_possible(path.parent)

        return True
    except Exception as e:
        print(f"Error writing {path}: {e}")
        try:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        return False


def safe_write_json(
    path: Path,
    data: Any,
    *,
    indent: int = 2,
    ensure_ascii: bool = False,
    timeout_s: float = 10.0,
    create_backup: bool = True,
) -> bool:
    """
    Safely write JSON to `path` with locking and backups.
    Returns True on success, False on failure.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    lock_path = path.with_suffix(path.suffix + ".lock")

    try:
        with file_lock(lock_path, timeout_s=timeout_s):
            return _safe_write_json_unlocked(
                path,
                data,
                indent=indent,
                ensure_ascii=ensure_ascii,
                create_backup=create_backup,
            )
    except FileLockTimeoutError:
        return False


def safe_update_json(
    path: Path,
    update_fn: Callable[[Any], Any],
    *,
    default: Any = None,
    indent: int = 2,
    ensure_ascii: bool = False,
    timeout_s: float = 10.0,
    create_backup: bool = True,
) -> bool:
    """
    Atomically read→modify→write JSON with the lock held throughout.

    Args:
        path: Path to JSON file
        update_fn: Function that takes current data and returns new data.
        default: Value to pass to update_fn if file doesn't exist.

    Returns True on success, False on failure.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    lock_path = path.with_suffix(path.suffix + ".lock")

    try:
        with file_lock(lock_path, timeout_s=timeout_s):
            # Read INSIDE the lock
            current_data = _safe_load_json_unlocked(
                path,
                default=default,
                allow_backup_recovery=True,
            )

            # Apply the update function
            try:
                new_data = update_fn(current_data)
            except Exception as e:
                print(f"Error in update function for {path}: {e}")
                return False

            # Write INSIDE the lock
            return _safe_write_json_unlocked(
                path,
                new_data,
                indent=indent,
                ensure_ascii=ensure_ascii,
                create_backup=create_backup,
            )
    except FileLockTimeoutError:
        return False


def safe_write_text(
    path: Path,
    content: str,
    *,
    encoding: str = "utf-8",
    timeout_s: float = 10.0,
    create_backup: bool = True,
    preserve_mode: bool = False,  # Set True for executable scripts
) -> bool:
    """
    Safely write text content to `path` with:
      - Cross-process locking via `path.<suffix>.lock`
      - Backup creation (*.bak) before replacing
      - Unique temp file (no collisions between concurrent writers)
      - flush + fsync for durability
      - os.replace() for atomic replace semantics (Unix + Windows)
      - Optional mode preservation (for executable files)

    Returns True on success, False on failure (including lock timeout).

    NOTE: If preserve_mode=True and the file exists, the original file's
    permission bits are restored after the atomic replace. This is important
    for executable scripts where os.replace() would reset to umask defaults.
    """
    os.makedirs(path.parent, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")

    # Capture original permission bits if we need to preserve them
    # Use stat.S_IMODE() to extract only permission bits (0o777 mask)
    # This avoids any ambiguity around file-type bits
    original_mode = None
    if preserve_mode and os.path.exists(path):
        try:
            import stat as stat_module

            original_mode = stat_module.S_IMODE(path.stat().st_mode)
        except OSError:
            pass

    try:
        with file_lock(lock_path, timeout_s=timeout_s):
            # Create backup if file exists and is non-empty
            # Guard against stat() failures (e.g. permission denied)
            should_backup = False
            if create_backup and os.path.exists(path):
                try:
                    should_backup = path.stat().st_size > 0
                except OSError:
                    pass

            if should_backup:
                backup_path = path.with_suffix(path.suffix + ".bak")
                try:
                    shutil.copy2(path, backup_path)
                except Exception:
                    pass  # Best-effort backup

            # Create unique temp file in same directory
            tmp_path: Optional[Path] = None

            try:
                tmp_fd, tmp_name = tempfile.mkstemp(
                    prefix=path.name + ".",
                    suffix=".tmp",
                    dir=str(path.parent),
                )
                tmp_path = Path(tmp_name)

                with os.fdopen(tmp_fd, "w", encoding=encoding, newline="\n") as f:
                    f.write(content)
                    f.flush()
                    os.fsync(f.fileno())

                os.replace(tmp_path, path)
                _fsync_dir_if_possible(path.parent)

                # Restore original permissions if requested
                if original_mode is not None:
                    try:
                        os.chmod(path, original_mode)
                    except OSError:
                        pass  # Best-effort mode restoration

                return True

            except Exception:
                try:
                    if tmp_path and tmp_path.exists():
                        tmp_path.unlink()
                except Exception:
                    pass
                return False

    except FileLockTimeoutError:
        return False
