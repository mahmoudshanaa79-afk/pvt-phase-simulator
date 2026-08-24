"""Single-orchestrator process lock with safe stale-lock recovery."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType


class LockHeld(RuntimeError):
    """Raised when another live orchestrator already holds the lock."""


def _process_alive(pid: int) -> bool:
    """Best-effort liveness check that works on Windows and POSIX."""

    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)) == 0:
                return False
            return code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@dataclass(slots=True)
class OrchestratorLock:
    """Context manager that refuses a second concurrent RUN."""

    path: Path
    acquired: bool = False

    def _read(self) -> dict[str, object] | None:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def inspect(self) -> tuple[bool, str]:
        """Return (held_by_live_process, description) without acquiring."""

        payload = self._read()
        if payload is None:
            return False, "no lock"
        pid = int(payload.get("pid", -1))  # type: ignore[arg-type]
        if _process_alive(pid):
            return True, f"held by live pid {pid}"
        return False, f"stale lock from dead pid {pid}"

    def acquire(self) -> None:
        held, description = self.inspect()
        if held:
            raise LockHeld(f"another orchestrator is running ({description})")
        if self.path.exists():
            # Recover the stale lock rather than forcing manual cleanup.
            self.path.unlink(missing_ok=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"pid": os.getpid(), "started": time.time()}, indent=2),
            encoding="utf-8",
        )
        self.acquired = True

    def release(self) -> None:
        if self.acquired:
            self.path.unlink(missing_ok=True)
            self.acquired = False

    def __enter__(self) -> OrchestratorLock:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()
