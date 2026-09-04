"""Persistent runtime status so a run can be observed and judged from outside.

The workflow state file records *where* the workflow is. This records whether
anything is actually still working on it: which process, which stage, which
command, and how long ago it last said anything. A status file that stops being
updated is the signal that a run died rather than finished.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from .config import OrchestratorConfig

#: Relative to the .ai directory.
RUNTIME_DIRNAME: Final = "runtime"
STATUS_FILENAME: Final = "current_status.json"

#: A heartbeat older than this is treated as stale. Generous, because a single
#: verification command can legitimately run for minutes without a beat.
STALE_AFTER_SECONDS: Final = 900.0


def heartbeat_path(config: OrchestratorConfig) -> Path:
    return config.ai_dir / RUNTIME_DIRNAME / STATUS_FILENAME


def new_workflow_id() -> str:
    return uuid.uuid4().hex[:12]


if sys.platform == "win32":  # pragma: no cover - platform specific

    def process_alive(pid: int | None) -> bool:
        """Whether a PID is still running.

        ``os.kill(pid, 0)`` must never be used here: on Windows ``os.kill``
        calls ``TerminateProcess`` for any signal other than the console control
        events, so the "harmless liveness probe" idiom from POSIX would actually
        kill the process it was asked about.
        """

        import ctypes

        if pid is None or pid <= 0:
            return False
        if pid == os.getpid():
            return True
        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(
            process_query_limited_information, False, int(pid)
        )
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return int(code.value) == still_active
            return True
        finally:
            kernel32.CloseHandle(handle)

else:

    def process_alive(pid: int | None) -> bool:
        if pid is None or pid <= 0:
            return False
        if pid == os.getpid():
            return True
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            # Exists, owned by someone else.
            return True
        except OSError:
            return False
        return True


@dataclass(slots=True)
class HeartbeatRecord:
    """Everything `status --verbose` needs to describe a live or dead run."""

    workflow_id: str
    pid: int
    started_at: float
    last_heartbeat: float
    package: str | None = None
    stage: str | None = None
    workflow_status: str | None = None
    builder: str | None = None
    reviewer: str | None = None
    current_command: str | None = None
    verification_gate: str | None = None
    correction_count: int = 0
    max_corrections: int | None = None
    audit_debt: int = 0
    science_firewall: str = "UNKNOWN"
    next_action: str | None = None
    finished: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "pid": self.pid,
            "started_at": self.started_at,
            "last_heartbeat": self.last_heartbeat,
            "package": self.package,
            "stage": self.stage,
            "workflow_status": self.workflow_status,
            "builder": self.builder,
            "reviewer": self.reviewer,
            "current_command": self.current_command,
            "verification_gate": self.verification_gate,
            "correction_count": self.correction_count,
            "max_corrections": self.max_corrections,
            "audit_debt": self.audit_debt,
            "science_firewall": self.science_firewall,
            "next_action": self.next_action,
            "finished": self.finished,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> HeartbeatRecord:
        known = set(cls.__dataclass_fields__)
        payload = {key: value for key, value in raw.items() if key in known}
        payload.setdefault("workflow_id", "unknown")
        payload.setdefault("pid", 0)
        payload.setdefault("started_at", 0.0)
        payload.setdefault("last_heartbeat", 0.0)
        return cls(**payload)

    # ------------------------------------------------------------- derived

    def elapsed_seconds(self, *, now: float | None = None) -> float:
        return max(0.0, (now if now is not None else time.time()) - self.started_at)

    def age_seconds(self, *, now: float | None = None) -> float:
        return max(0.0, (now if now is not None else time.time()) - self.last_heartbeat)

    def is_stale(
        self, *, now: float | None = None, stale_after: float = STALE_AFTER_SECONDS
    ) -> bool:
        return self.age_seconds(now=now) > stale_after

    def is_running(
        self, *, now: float | None = None, stale_after: float = STALE_AFTER_SECONDS
    ) -> bool:
        """A run counts as live only if it is unfinished, fresh, and its process
        still exists. Any one of those failing means nothing is working on it."""

        if self.finished:
            return False
        if self.is_stale(now=now, stale_after=stale_after):
            return False
        return process_alive(self.pid)


def format_duration(seconds: float) -> str:
    total = int(max(0.0, seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def write_heartbeat(config: OrchestratorConfig, record: HeartbeatRecord) -> Path:
    """Persist atomically so a reader never sees a half-written status."""

    path = heartbeat_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(record.to_dict(), indent=2) + "\n"
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return path


def read_heartbeat(config: OrchestratorConfig) -> HeartbeatRecord | None:
    """Return the last recorded status, or None when there is none to read.

    A corrupt file is treated as absent rather than fatal: the heartbeat is
    observability, and losing it must never block the workflow it describes.
    """

    path = heartbeat_path(config)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(raw, dict):
        return None
    return HeartbeatRecord.from_dict(raw)


class Heartbeat:
    """Owns one run's status file and keeps it current."""

    def __init__(
        self,
        config: OrchestratorConfig,
        *,
        workflow_id: str | None = None,
        clock: Any = time.time,
    ) -> None:
        self.config = config
        self._clock = clock
        now = float(clock())
        self.record = HeartbeatRecord(
            workflow_id=workflow_id or new_workflow_id(),
            pid=os.getpid(),
            started_at=now,
            last_heartbeat=now,
        )

    def beat(self, **updates: Any) -> HeartbeatRecord:
        """Update fields and stamp the time. Unknown keys go to ``extra``."""

        for key, value in updates.items():
            if hasattr(self.record, key):
                setattr(self.record, key, value)
            else:
                self.record.extra[key] = value
        self.record.last_heartbeat = float(self._clock())
        write_heartbeat(self.config, self.record)
        return self.record

    def finish(self, **updates: Any) -> HeartbeatRecord:
        """Mark the run finished so a later reader does not call it live."""

        updates.setdefault("finished", True)
        return self.beat(**updates)

    def __enter__(self) -> Heartbeat:
        self.beat()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.finish(next_action=None if exc_type is None else "run ended with an error")
