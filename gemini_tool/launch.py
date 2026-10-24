"""Windows Start launcher; hold a run lock through setup and uploader exit."""
from __future__ import annotations

import os
import argparse
from pathlib import Path
import subprocess
import sys

from .control import ROOT, StopRequested, check_stop, start_run
from .stop import main as stop_main, reset_run


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == ["--stop"]:
        return stop_main(arguments[1:])
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--profile", type=Path, default=ROOT / ".gemini-browser-native")
    parser.add_argument("--input", type=Path, default=ROOT / "img")
    selected, _ = parser.parse_known_args(arguments)
    diagnostic = any(value in arguments for value in ("--browser-info", "--help", "-h"))

    def reset(message):
        print(message, flush=True)
        reset_run(ROOT, [selected.profile])
        print("Đã dọn trạng thái cục bộ; giữ đăng nhập Google và ảnh gốc còn lại.", flush=True)

    try:
        for path in (selected.profile, selected.input):
            if path.resolve().is_relative_to((ROOT / ".gemini-runtime").resolve()):
                raise ValueError("Không đặt ảnh gốc hoặc profile đăng nhập trong .gemini-runtime (thư mục tạm).")
        with start_run(
            before_start=None if diagnostic else lambda: reset("Đang dừng và dọn phiên cũ trước khi chạy..."),
            after_run=None if diagnostic else lambda: reset("Đang dọn sau lần chạy, kể cả khi có lỗi..."),
            replace_existing=sys.platform == "win32",
        ):
            python = ROOT / ".venv-gemini" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            if not python.is_file():
                check_stop()
                subprocess.run([sys.executable, "-m", "venv", str(ROOT / ".venv-gemini")], check=True)
            check_stop()
            check = subprocess.run([str(python), "-c",
                "import playwright.sync_api, websocket, PIL, pillow_heif, resvg_py, rawpy"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if check.returncode:
                check_stop()
                print("Đang cài thư viện cho Gemini...", flush=True)
                subprocess.run([str(python), "-m", "pip", "install", "-r",
                                str(ROOT / "requirements-gemini.txt")], check=True)
            check_stop()
            return subprocess.call([str(python), "-u", str(ROOT / "gemini_upload.py"),
                                    *arguments])
    except (StopRequested, KeyboardInterrupt):
        print("Đã hủy khởi động theo yêu cầu Stop.", file=sys.stderr)
        return 130
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Chưa chạy được: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
