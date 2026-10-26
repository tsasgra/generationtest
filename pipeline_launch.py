"""Bootstrap Windows launchers without deleting the completed run's results."""
from __future__ import annotations

import argparse
from pathlib import Path
import os
import subprocess
import sys

from gemini_tool.control import StopRequested, check_stop, exclusive_lock, start_run

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


def _run_gemini(arguments: list[str]) -> int:
    """Keep the standalone uploader's reset/lock lifecycle in one bootstrap."""
    from gemini_tool.stop import reset_run

    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--profile", type=Path, default=ROOT / ".gemini-browser-native")
    parser.add_argument("--input", type=Path)
    selected, _ = parser.parse_known_args(arguments)
    diagnostic = any(value in arguments for value in ("--browser-info", "--help", "-h"))
    # The child always runs from ROOT, even if this launcher was invoked from
    # another working directory. Resolve cleanup targets the same way.
    selected.profile = (ROOT / selected.profile).resolve()
    if selected.input is not None:
        selected.input = (ROOT / selected.input).resolve()
    for path in (selected.profile, selected.input):
        if path is not None and path.resolve().is_relative_to((ROOT / ".gemini-runtime").resolve()):
            raise ValueError("Không đặt ảnh gốc hoặc profile đăng nhập trong .gemini-runtime (thư mục tạm).")

    def reset(message: str) -> None:
        print(message, flush=True)
        reset_run(ROOT, [selected.profile], stop_processes=False)
        print("Đã dọn trạng thái Gemini; giữ thư viện, đăng nhập, ảnh và kết quả Polygon.", flush=True)

    if diagnostic:
        python = _python_with_dependencies()
        return subprocess.call([str(python), "-u", str(ROOT / "gemini_upload.py"), *arguments], cwd=ROOT)

    # Share the batch lifecycle lock as well as Gemini's locks: a standalone
    # click must not reset an active Polygon-only batch or its input files.
    with exclusive_lock(ROOT / ".pipeline-run.lock"), start_run(
        before_start=lambda: reset("Đang dọn phiên Gemini cũ trước khi chạy..."),
        after_run=lambda: reset("Đang dọn dữ liệu Gemini tạm sau lần chạy..."),
    ):
        check_stop()
        python = _python_with_dependencies()
        check_stop()
        return subprocess.call([str(python), "-u", str(ROOT / "gemini_upload.py"), *arguments], cwd=ROOT)


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    # Preserve start.bat --workers ... while also accepting an explicit mode.
    action = arguments.pop(0) if arguments and not arguments[0].startswith("-") else "run"
    if action not in ("run", "check", "resume", "stop", "init", "gemini", "polygon"):
        print("Dùng start.bat [run|check|resume|stop|init|gemini|polygon].", file=sys.stderr)
        return 2
    try:
        if action == "stop" or (action == "gemini" and arguments[:1] == ["--stop"]):
            from gemini_tool.stop import main as stop
            return stop(arguments[1:] if action == "gemini" else arguments)
        if action == "gemini":
            return _run_gemini(arguments)
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
        elif action == "init":
            command = [sys.executable, "-u", str(ROOT / "pipeline.py"), "init", *arguments]
        elif action == "polygon":
            command = [sys.executable, "-u", str(ROOT / "polygon_upload.py"), *arguments]
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
