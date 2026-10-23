"""Windows Start launcher; hold a run lock through setup and uploader exit."""
from __future__ import annotations

import os
import subprocess
import sys

from .control import ROOT, StopRequested, check_stop, start_run


def main(argv: list[str] | None = None) -> int:
    try:
        with start_run():
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
                                    *(sys.argv[1:] if argv is None else argv)])
    except (StopRequested, KeyboardInterrupt):
        print("Đã hủy khởi động theo yêu cầu Stop.", file=sys.stderr)
        return 130
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Chưa chạy được: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
