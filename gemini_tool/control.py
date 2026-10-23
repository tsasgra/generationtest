"""Cooperative cancellation shared by the uploader and Windows Stop launcher."""
from __future__ import annotations

from pathlib import Path
import time

STOP_FILE = Path(__file__).resolve().parent.parent / ".gemini-stop-request"


class StopRequested(KeyboardInterrupt):
    """Unwind browser/temp-file contexts without entering the error tab loop."""


def check_stop() -> None:
    if STOP_FILE.exists():
        raise StopRequested("Đã nhận yêu cầu Stop.")


def sleep(seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while True:
        check_stop()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.1, remaining))
