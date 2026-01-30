"""
hana.lock — SKU-level locking for concurrency control.

Implements filesystem-based locking with timeout and orphan cleanup.
"""

import fcntl
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from hana.config import HanaConfig, LockStrategy
from hana.errors import ConcurrencyError
from hana.logger import get_logger


class FilesystemLock:
    """Filesystem-based lock for a specific SKU."""

    def __init__(
        self,
        sku: str,
        lock_dir: Path,
        timeout_seconds: int,
        cleanup_orphans: bool,
    ):
        self._sku = sku
        self._lock_dir = lock_dir
        self._timeout_seconds = timeout_seconds
        self._cleanup_orphans = cleanup_orphans
        self._lock_file: Path | None = None
        self._lock_fd: int | None = None

    @property
    def lock_path(self) -> Path:
        """Get the lock file path for this SKU."""
        safe_sku = self._sku.replace("/", "_").replace("\\", "_")
        return self._lock_dir / f"{safe_sku}.lock"

    def acquire(self) -> bool:
        """Attempt to acquire the lock."""
        self._lock_dir.mkdir(parents=True, exist_ok=True)

        if self._cleanup_orphans:
            self._cleanup_orphan_lock()

        self._lock_file = self.lock_path
        start_time = time.monotonic()

        while True:
            try:
                self._lock_fd = os.open(
                    str(self._lock_file),
                    os.O_CREAT | os.O_RDWR,
                )
                fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

                os.write(self._lock_fd, f"{os.getpid()}\n".encode())
                return True

            except (OSError, IOError):
                if self._lock_fd is not None:
                    os.close(self._lock_fd)
                    self._lock_fd = None

                elapsed = time.monotonic() - start_time
                if elapsed >= self._timeout_seconds:
                    raise ConcurrencyError(
                        sku=self._sku,
                        stage="lock_acquire",
                        message=f"Lock acquisition timeout after {self._timeout_seconds}s",
                        payload={"lock_path": str(self._lock_file)},
                    )

                time.sleep(0.1)

    def release(self) -> None:
        """Release the lock."""
        if self._lock_fd is not None:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                os.close(self._lock_fd)
            except (OSError, IOError):
                pass
            finally:
                self._lock_fd = None

            if self._lock_file and self._lock_file.exists():
                try:
                    self._lock_file.unlink()
                except (OSError, IOError):
                    pass

    def _cleanup_orphan_lock(self) -> None:
        """Clean up orphan lock if the holding process is dead."""
        if not self.lock_path.exists():
            return

        try:
            with open(self.lock_path, "r") as f:
                content = f.read().strip()
                if content:
                    pid = int(content)
                    if not self._is_process_alive(pid):
                        get_logger().warn(
                            f"Cleaning up orphan lock for SKU {self._sku}",
                            sku=self._sku,
                            stage="lock_cleanup",
                            orphan_pid=pid,
                        )
                        self.lock_path.unlink()
        except (OSError, IOError, ValueError):
            pass

    @staticmethod
    def _is_process_alive(pid: int) -> bool:
        """Check if a process is alive."""
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


class LockManager:
    """Manager for SKU-level locks."""

    def __init__(self, config: HanaConfig):
        self._config = config
        self._lock_dir = Path(config.ledger.path).parent / "locks"
        self._active_locks: dict[str, FilesystemLock] = {}

    @contextmanager
    def lock_sku(self, sku: str) -> Generator[None, None, None]:
        """Context manager for locking a SKU."""
        if self._config.lock.strategy != LockStrategy.FILESYSTEM:
            yield
            return

        lock = FilesystemLock(
            sku=sku,
            lock_dir=self._lock_dir,
            timeout_seconds=self._config.lock.timeout_seconds,
            cleanup_orphans=self._config.lock.cleanup_orphans,
        )

        try:
            lock.acquire()
            self._active_locks[sku] = lock
            yield
        finally:
            lock.release()
            self._active_locks.pop(sku, None)

    def release_all(self) -> None:
        """Release all active locks."""
        for lock in list(self._active_locks.values()):
            lock.release()
        self._active_locks.clear()
