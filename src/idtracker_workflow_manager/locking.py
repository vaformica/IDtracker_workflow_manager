"""Process-safe serialization for Firebird-side registry access."""

from __future__ import annotations

import fcntl
from pathlib import Path
import time
from types import TracebackType


class RegistryLockTimeout(TimeoutError):
    """Raised when the backend cannot obtain the registry lock in time."""


class RegistryFileLock:
    """Advisory exclusive lock used by every backend database operation."""

    def __init__(
        self,
        lock_path: str | Path,
        *,
        timeout_seconds: float = 30.0,
        poll_seconds: float = 0.05,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive")
        self.lock_path = Path(lock_path)
        self.timeout_seconds = timeout_seconds
        self.poll_seconds = poll_seconds
        self._file: object | None = None

    def __enter__(self) -> "RegistryFileLock":
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = self.lock_path.open("a+", encoding="utf-8")
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._file = lock_file
                return self
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    lock_file.close()
                    raise RegistryLockTimeout(
                        f"timed out waiting for registry lock: {self.lock_path}"
                    )
                time.sleep(self.poll_seconds)

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._file is None:
            return
        lock_file = self._file
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()
        self._file = None
