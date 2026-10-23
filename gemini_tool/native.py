"""Open Gemini in installed Chrome/Edge with a dedicated local profile."""
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

def find_system_browser() -> tuple[str, Path]:
    """Use an installed, supported browser."""
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
    raise ValueError("Cần Google Chrome hoặc Microsoft Edge bản cập nhật trên máy để mở Gemini.")

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

def start_native_browser(url: str, profile_root: Path) -> tuple[int, Path]:
    name, executable = find_system_browser()
    profile = (profile_root / name).resolve()
    profile.mkdir(parents=True, exist_ok=True)
    session_file = profile / "gemini-export-session.json"
    # Reuse only the exact browser instance previously started by this tool.
    try:
        saved = json.loads(session_file.read_text(encoding="utf-8"))
        info = debug_endpoint(saved["port"])
        if info["webSocketDebuggerUrl"] == saved["websocket"]:
            subprocess.Popen([
                str(executable), f"--user-data-dir={profile}", "--new-window", url,
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return saved["port"], session_file
    except (OSError, ValueError, KeyError, TypeError):
        pass
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
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            info = debug_endpoint(port)
            session_file.write_text(json.dumps({
                "port": port, "websocket": info["webSocketDebuggerUrl"],
            }), encoding="utf-8")
            print(f"Đã mở {name.title()} trên máy.", flush=True)
            return port, session_file
        except (OSError, ValueError, KeyError):
            if process.poll() is not None:
                break
            time.sleep(0.2)
    raise ValueError(
        "Không kết nối được cửa sổ Chrome/Edge của script. Đóng cửa sổ này rồi chạy lại BAT. "
        "Nếu máy có chính sách công ty chặn kết nối trình duyệt, cần quản trị viên cho phép."
    )

def close_native_browser(browser, session_file: Path) -> None:
    # Close only our dedicated browser, allowing it to flush its saved login.
    try:
        session = browser.new_browser_cdp_session()
        session.send("Browser.close")
    except Exception:
        pass
    finally:
        try:
            browser.close()
        except Exception:
            pass
        try:
            session_file.unlink(missing_ok=True)
        except OSError:
            pass
