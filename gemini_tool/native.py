"""Native browser login ported from copy_info_on_gemini's gemini_export.bat.

Chrome/Edge handles sign-in before the uploader attaches Playwright over CDP.
Only the dedicated local browser profile is used.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener

from .control import check_stop, sleep
from .state import reset_browser_state

_ACTIVE_BROWSERS: dict[Path, subprocess.Popen] = {}

def find_system_browser() -> tuple[str, Path]:
    """Use the installed, supported browser and its normal login UI."""
    for name, executable, relative in (
        ("chrome", "chrome.exe", "Google/Chrome/Application/chrome.exe"),
        ("edge", "msedge.exe", "Microsoft/Edge/Application/msedge.exe"),
    ):
        candidates = []
        if sys.platform == "win32":
            import winreg
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                    try:
                        with winreg.OpenKey(
                            hive, rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{executable}",
                            0, winreg.KEY_READ | view,
                        ) as key:
                            value = winreg.QueryValueEx(key, None)[0]
                            candidates.append(Path(os.path.expandvars(value.strip('"'))))
                    except OSError:
                        pass
        for variable in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"):
            base = os.environ.get(variable)
            if base:
                candidates.append(Path(base) / relative)
        on_path = shutil.which(executable)
        if on_path:
            candidates.append(Path(on_path))
        if sys.platform == "darwin":
            app = "Google Chrome" if name == "chrome" else "Microsoft Edge"
            for root in (Path("/Applications"), Path.home() / "Applications"):
                candidates.append(root / f"{app}.app/Contents/MacOS/{app}")
        elif sys.platform != "win32":
            commands = ("google-chrome", "google-chrome-stable") if name == "chrome" else (
                "microsoft-edge", "microsoft-edge-stable")
            for command in commands:
                installed = shutil.which(command)
                if installed:
                    candidates.append(Path(installed))
        for candidate in candidates:
            if candidate.is_file():
                return name, candidate.resolve()
    raise ValueError("Cần Google Chrome hoặc Microsoft Edge bản cập nhật trên máy để đăng nhập Gemini.")

def read_debug_json(port: int, route: str):
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("Cổng kết nối trình duyệt không hợp lệ.")
    if route not in ("/json/version", "/json/list"):
        raise ValueError("Chỉ đọc thông tin kết nối/tab của trình duyệt cục bộ.")
    # Only local discovery metadata is read here, never login fields/cookies.
    opener = build_opener(ProxyHandler({}))
    with opener.open(f"http://127.0.0.1:{port}{route}", timeout=1) as response:
        return json.loads(response.read(262144))

def debug_endpoint(port: int) -> dict:
    info = read_debug_json(port, "/json/version")
    websocket = urlsplit(info["webSocketDebuggerUrl"])
    if (websocket.scheme != "ws" or websocket.hostname != "127.0.0.1"
            or websocket.port != port or not websocket.path.startswith("/devtools/browser/")):
        raise ValueError("Kết nối trình duyệt không thuộc phiên cục bộ này.")
    return info

def start_native_browser(url: str, profile_root: Path) -> tuple[int, Path, set[str]]:
    check_stop()
    name, executable = find_system_browser()
    profile = (profile_root / name).resolve()
    profile.mkdir(parents=True, exist_ok=True)
    session_file = profile / "gemini-export-session.json"
    # A new run must never attach to an older run's browser. Its late cleanup
    # could close this run's tabs/context, producing TargetClosedError.
    running = False
    try:
        saved = json.loads(session_file.read_text(encoding="utf-8"))
        info = debug_endpoint(saved["port"])
        running = info["webSocketDebuggerUrl"] == saved["websocket"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    if running:
        raise ValueError("Trình duyệt của lần chạy trước vẫn mở. Chạy stop.bat rồi mở lại Start.")
    reset_browser_state(profile)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    # Start the installed browser directly. A dedicated profile is required by
    # current Chrome; default personal profiles are never read or copied.
    process = subprocess.Popen([
        str(executable), f"--user-data-dir={profile}",
        "--remote-debugging-address=127.0.0.1", f"--remote-debugging-port={port}",
        "--no-first-run", "--no-default-browser-check", "--new-window", url,
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _ACTIVE_BROWSERS[session_file] = process
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        check_stop()
        try:
            info = debug_endpoint(port)
            session_file.write_text(json.dumps({
                "port": port, "websocket": info["webSocketDebuggerUrl"],
            }), encoding="utf-8")
            print(f"Đã mở {name.title()} trên máy.", flush=True)
            return port, session_file, set()
        except (OSError, ValueError, KeyError):
            if process.poll() is not None:
                break
            sleep(0.2)
    raise ValueError(
        "Không kết nối được cửa sổ Chrome/Edge của script. Đóng cửa sổ này rồi chạy lại BAT. "
        "Nếu máy có chính sách công ty chặn kết nối trình duyệt, cần quản trị viên cho phép."
    )

def wait_for_manual_login(port: int, old_tabs: set[str], timeout: float = 600) -> None:
    """Wait for Google's redirect before attaching any browser automation."""
    print("Đăng nhập Google trong cửa sổ mới nếu được yêu cầu; script sẽ tự tiếp tục.", flush=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        check_stop()
        try:
            tabs = read_debug_json(port, "/json/list")
        except (OSError, ValueError) as exc:
            raise ValueError("Cửa sổ đăng nhập đã đóng hoặc mất kết nối. Chạy lại BAT để tiếp tục.") from exc
        pages = [tab for tab in tabs if tab.get("type") == "page" and tab.get("id") not in old_tabs]
        for tab in pages:
            parsed = urlsplit(tab.get("url", ""))
            if parsed.hostname == "accounts.google.com" and "/signin/rejected" in parsed.path:
                raise ValueError(
                    "Google đã từ chối đăng nhập trong Chrome/Edge. Chưa kết nối tự động, "
                    "chưa tải hoặc xóa ảnh. Giữ cửa sổ để bạn kiểm tra thông báo của Google."
                )
            if parsed.scheme == "https" and parsed.netloc == "gemini.google.com":
                return
        if not pages:
            # The initial tab may still be being created during browser startup.
            if not tabs:
                sleep(0.5)
                continue
        sleep(0.5)
    raise ValueError(f"Hết {timeout:g} giây chờ đăng nhập Google. Chạy lại BAT để tiếp tục.")

def request_browser_close(session_file: Path) -> None:
    """Send an owned local CDP close with a bounded transport, without waiting
    for an acknowledgement from a browser which is shutting down.
    """
    from websocket import create_connection

    saved = json.loads(session_file.read_text(encoding="utf-8"))
    info = debug_endpoint(saved["port"])
    if info["webSocketDebuggerUrl"] != saved["websocket"]:
        raise ValueError("Kết nối đã đổi; không đóng trình duyệt khác.")
    connection = create_connection(saved["websocket"], timeout=2, suppress_origin=True,
                                   http_no_proxy=["127.0.0.1", "localhost"])
    try:
        connection.send(json.dumps({"id": 1, "method": "Browser.close"}))
    finally:
        connection.shutdown()


def close_native_browser(_browser, session_file: Path) -> None:
    # A Playwright CDPSession.send(Browser.close) can hang indefinitely when
    # Chrome exits before acknowledging it. Never send it over the old driver.
    process = _ACTIVE_BROWSERS.get(session_file)
    if process is None:
        return
    if process.poll() is None:
        try:
            request_browser_close(session_file)
        except Exception:
            # A concurrent window close/Stop may have already ended Chrome.
            # Its exit, rather than a CDP acknowledgement, confirms shutdown.
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Chrome/Edge chưa đóng hoàn toàn. Chạy stop.bat trước khi Start lại.") from exc
    _ACTIVE_BROWSERS.pop(session_file, None)
    session_file.unlink(missing_ok=True)


def close_unfinished_browsers(roots: set[Path]) -> None:
    """Also close native windows left by login/startup errors before CDP attach.
    Only terminate Popen handles created by this Python process.
    """
    profiles = {(root / name).resolve() for root in roots for name in ("chrome", "edge")}
    for session_file, process in list(_ACTIVE_BROWSERS.items()):
        if session_file.parent not in profiles:
            continue
        if process.poll() is None:
            try:
                request_browser_close(session_file)
            except Exception:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
        _ACTIVE_BROWSERS.pop(session_file, None)
        session_file.unlink(missing_ok=True)
    for profile in profiles:
        session_file = profile / "gemini-export-session.json"
        try:
            saved = json.loads(session_file.read_text(encoding="utf-8"))
            info = debug_endpoint(saved["port"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if info["webSocketDebuggerUrl"] == saved.get("websocket"):
            raise ValueError("Phiên trình duyệt cũ vẫn mở. Đóng cửa sổ đó rồi chạy lại Start; chưa xóa dữ liệu đang dùng.")
