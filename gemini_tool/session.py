"""Sign in using installed Chrome/Edge before connecting browser automation."""
from __future__ import annotations

import http.client
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.parse import urlsplit

GEMINI_URL = "https://gemini.google.com/app?hl=en"


class BrowserSessionError(RuntimeError):
    pass


def find_browser(choice: str, explicit: Path | None = None) -> Path:
    if explicit:
        if explicit.is_file():
            return explicit.resolve()
        raise BrowserSessionError(f"Không tìm thấy trình duyệt: {explicit}")
    choices = ("chrome", "msedge") if choice == "auto" else (choice,)
    for name in choices:
        candidates = []
        if sys.platform == "win32":
            relative = ("Google/Chrome/Application/chrome.exe" if name == "chrome"
                        else "Microsoft/Edge/Application/msedge.exe")
            for variable in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
                if os.environ.get(variable):
                    candidates.append(Path(os.environ[variable]) / relative)
        elif sys.platform == "darwin":
            application = "Google Chrome" if name == "chrome" else "Microsoft Edge"
            candidates.append(Path(f"/Applications/{application}.app/Contents/MacOS/{application}"))
        commands = (("google-chrome", "google-chrome-stable", "chrome") if name == "chrome"
                    else ("microsoft-edge", "microsoft-edge-stable", "msedge"))
        candidates.extend(Path(path) for command in commands if (path := shutil.which(command)))
        for candidate in candidates:
            if candidate.is_file():
                return candidate
    raise BrowserSessionError("Cần cài Google Chrome/Microsoft Edge, hoặc chỉ định --browser-path.")


def active_endpoint(profile: Path) -> str | None:
    """Use only this profile's loopback port and its matching browser ID."""
    try:
        lines = (profile / "DevToolsActivePort").read_text(encoding="utf-8").splitlines()
        port = int(lines[0])
        if not 1 <= port <= 65535 or not lines[1].startswith("/devtools/browser/"):
            return None
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
        try:
            connection.request("GET", "/json/version")
            response = connection.getresponse()
            if response.status != 200:
                return None
            data = json.loads(response.read(65536))
        finally:
            connection.close()
        websocket = urlsplit(data.get("webSocketDebuggerUrl", ""))
        if (websocket.hostname in {"127.0.0.1", "localhost", "::1"}
                and websocket.port == port and websocket.path == lines[1]):
            return f"http://127.0.0.1:{port}"
    except (OSError, ValueError, IndexError, http.client.HTTPException):
        pass
    return None


def start_process(command: list[str]):
    # No shell, automation flags, certificate exceptions or sandbox changes.
    return subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def prepare_session(profile: Path, choice: str, explicit: Path | None = None,
                    *, login: bool = False) -> str:
    profile = profile.resolve()
    profile.mkdir(parents=True, exist_ok=True)
    marker = profile / ".gemini-login-ready"
    endpoint = active_endpoint(profile)
    if endpoint:
        if login:
            raise BrowserSessionError("Đóng Chrome/Edge dùng cho Gemini rồi chạy lại --login.")
        return endpoint
    executable = find_browser(choice, explicit)
    base = [str(executable), f"--user-data-dir={profile}"]
    if login or not marker.exists():
        process = start_process([*base, "--new-window", GEMINI_URL])
        print("Đã mở trình duyệt cài trên máy, chưa kết nối điều khiển.")
        print("Đăng nhập Google và mở được Gemini. Sau đó đóng toàn bộ cửa sổ của phiên Gemini này.")
        try:
            input("Khi đã đăng nhập và đóng cửa sổ, nhấn Enter tại đây để tiếp tục: ")
        except EOFError as exc:
            raise BrowserSessionError("Cần chạy trong terminal để hoàn tất lần đăng nhập đầu tiên.") from exc
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired as exc:
            raise BrowserSessionError("Trình duyệt đăng nhập vẫn đang mở. Hãy đóng rồi chạy lại.") from exc
        marker.touch()
    # Old port files are metadata, not cookies. Do not attach to a stale port.
    (profile / "DevToolsActivePort").unlink(missing_ok=True)
    process = start_process([
        *base, "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=0",
        "--new-window", GEMINI_URL,
    ])
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        endpoint = active_endpoint(profile)
        if endpoint:
            return endpoint
        if process.poll() is not None:
            break
        time.sleep(0.2)
    raise BrowserSessionError(
        "Chưa kết nối được Chrome/Edge. Đóng các cửa sổ dùng cùng profile rồi thử lại. "
        "Có thể chọn --browser msedge hoặc --login để đăng nhập lại."
    )
