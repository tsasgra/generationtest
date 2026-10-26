"""Cooperative cancellation shared by the uploader and Windows Stop launcher."""
from __future__ import annotations

from pathlib import Path
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
import os
from threading import Event
import time

ROOT = Path(__file__).resolve().parent.parent
STOP_FILE = ROOT / ".gemini-stop-request"
RUNTIME = ROOT / ".gemini-runtime"
_CANCELLATION: ContextVar[Event | None] = ContextVar("gemini_cancellation", default=None)


class AlreadyRunning(ValueError):
    """Another uploader or Stop owns the requested operation."""


@contextmanager
def exclusive_lock(path: Path, timeout: float = 0):
    """Kernel-owned lock: a killed process cannot leave a stale busy flag."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if not stream.tell():
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        deadline = time.monotonic() + timeout
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise AlreadyRunning(
                        "Công cụ đang chạy hoặc Stop đang dọn dữ liệu. "
                        "Chờ Stop hoàn tất rồi mở lại start.bat gemini."
                    ) from exc
                time.sleep(0.05)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


@contextmanager
def upload_run(cleanup=None):
    # Start cannot enter while Stop is resetting a profile. Keep the uploader
    # lock through browser shutdown and temporary-file removal.
    with ExitStack() as stack:
        with exclusive_lock(ROOT / ".gemini-reset.lock"):
            stack.enter_context(exclusive_lock(ROOT / ".gemini-upload.lock"))
        try:
            check_stop()
            yield
        finally:
            if cleanup is not None:
                with exclusive_lock(ROOT / ".gemini-reset.lock", timeout=2):
                    cleanup()


@contextmanager
def start_run(before_start=None, after_run=None, *, replace_existing: bool = False):
    with ExitStack() as stack:
        with exclusive_lock(ROOT / ".gemini-reset.lock", timeout=2):
            if replace_existing and before_start is not None:
                before_start()
            stack.enter_context(exclusive_lock(ROOT / ".gemini-launch.lock"))
            # An older uploader must finish unwinding before cancellation is
            # cleared. Hold the launch lock through setup and the child run.
            with exclusive_lock(ROOT / ".gemini-upload.lock"):
                if not replace_existing and before_start is not None:
                    before_start()
                STOP_FILE.unlink(missing_ok=True)
        try:
            yield
        finally:
            if after_run is not None:
                with exclusive_lock(ROOT / ".gemini-reset.lock", timeout=2):
                    after_run()


class StopRequested(KeyboardInterrupt):
    """Unwind browser/temp-file contexts without entering the error tab loop."""


def check_stop() -> None:
    cancellation = _CANCELLATION.get()
    if STOP_FILE.exists() or (cancellation is not None and cancellation.is_set()):
        raise StopRequested("Đã nhận yêu cầu Stop.")


@contextmanager
def cancellation_scope(cancellation: Event):
    """Let existing UI/file waits react to cancellation in this worker only."""
    token = _CANCELLATION.set(cancellation)
    try:
        yield
    finally:
        _CANCELLATION.reset(token)


def sleep(seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while True:
        check_stop()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.1, remaining))
