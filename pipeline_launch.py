"""Bootstrap Windows launchers without deleting the completed run's results."""
from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys

from gemini_tool.control import StopRequested, exclusive_lock

ROOT = Path(__file__).resolve().parent


def _python_with_dependencies() -> Path:
    python = ROOT / ".venv-gemini" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    with exclusive_lock(ROOT / ".pipeline-setup.lock"):
        if not python.is_file():
            subprocess.run([sys.executable, "-m", "venv", str(ROOT / ".venv-gemini")], check=True)
        check = subprocess.run([str(python), "-c",
            "import playwright.sync_api, websocket, PIL, pillow_heif, resvg_py, rawpy"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if check.returncode:
            print("Đang cài thư viện còn thiếu vào .venv-gemini...", flush=True)
            subprocess.run([str(python), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")], check=True)
    return python


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    action = arguments.pop(0) if arguments else "run"
    if action not in ("run", "check", "resume", "stop"):
        print("Dùng start.bat, start_check.bat, start_resume.bat hoặc stop.bat.", file=sys.stderr)
        return 2
    try:
        if action == "stop":
            from gemini_tool.stop import main as stop
            return stop(arguments)
        if action == "resume":
            # No reset here: the user's intent is to resume the exact Polygon
            # problems saved by the last run. This path only needs stdlib.
            command = [sys.executable, "-u", str(ROOT / "polygon_batch.py"), "resume",
                       "--input", str(ROOT / "problem"),
                       "--state-dir", str(ROOT / ".pipeline-state" / "polygon"),
                       "--output-dir", str(ROOT / "polygon_results"),
                       "--report", str(ROOT / "report.txt"), *arguments]
            # The batch CLI clears a previous Stop sentinel while holding its
            # own lifecycle locks; the bootstrap must not race that operation.
        else:
            python = _python_with_dependencies()
            command = [str(python), "-u", str(ROOT / "pipeline.py"), action, *arguments]
        return subprocess.call(command, cwd=ROOT)
    except (StopRequested, KeyboardInterrupt):
        print("Đã dừng khởi động.", file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Chưa chạy được: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
