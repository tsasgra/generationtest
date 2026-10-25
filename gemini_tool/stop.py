"""Stop this Windows tool and clear connection state without removing images/login."""
from __future__ import annotations

import argparse
import json
import ntpath
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess
import sys
import tempfile

from .control import exclusive_lock
from .state import ordinary_directory, remove_state, reset_browser_state, saved_profiles

ROOT = Path(__file__).resolve().parent.parent
PYTHON_NAME = re.compile(r"(?:py|pythonw?|python\d+(?:\.\d+)*)\.exe", re.I)
PROCESS_QUERY = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Get-CimInstance Win32_Process |
    Where-Object { $_.Name -match '^(py|pythonw?|python\d+(\.\d+)*|chrome|msedge)\.exe$' } |
    Select-Object ProcessId, ParentProcessId, Name, CommandLine,
        @{Name='Created'; Expression={$_.CreationDate.ToUniversalTime().ToString('o')}} |
    ConvertTo-Json -Compress
"""


def windows_args(command: str) -> list[str]:
    """Parse Windows quoting, including backslashes before quotes."""
    result = []
    index = 0
    while index < len(command):
        while index < len(command) and command[index] in " \t":
            index += 1
        if index == len(command):
            break
        value = []
        quoted = False
        while index < len(command) and (quoted or command[index] not in " \t"):
            slashes = 0
            while index < len(command) and command[index] == "\\":
                slashes += 1
                index += 1
            if index < len(command) and command[index] == '"':
                value.append("\\" * (slashes // 2))
                if slashes % 2:
                    value.append('"')
                elif quoted and index + 1 < len(command) and command[index + 1] == '"':
                    value.append('"')
                    index += 1
                else:
                    quoted = not quoted
                index += 1
            else:
                value.append("\\" * slashes)
                if index < len(command) and (quoted or command[index] not in " \t"):
                    value.append(command[index])
                    index += 1
        result.append("".join(value))
    return result


def python_arguments(process: dict) -> list[str]:
    if not PYTHON_NAME.fullmatch(process.get("Name") or ""):
        return []
    arguments = windows_args(process.get("CommandLine") or "")[1:]
    index = 0
    while index < len(arguments):
        value = arguments[index]
        if value == "--":
            rest = arguments[index + 1:]
            return rest if rest and not rest[0].startswith("-") else []
        if value == "-m" or not value.startswith("-"):
            return arguments[index:]
        if value in {"-W", "-X"}:
            index += 1
        elif not (value.startswith(("-W", "-X"))
                  or re.fullmatch(r"-[uBEIsSOqvPbdR]+|-[23](?:\.\d+)?(?:-(?:32|64))?", value)):
            # Never mistake code passed via -c/-uc or a module name for a
            # script filename merely appearing in that program's arguments.
            return []
        index += 1
    return []


def option(arguments: list[str], name: str) -> str | None:
    for index, value in enumerate(arguments):
        if value == name and index + 1 < len(arguments):
            return arguments[index + 1]
        if value.startswith(name + "="):
            return value[len(name) + 1:]
    return None


def path_key(value) -> str:
    return ntpath.normcase(ntpath.normpath(str(value)))


def is_uploader(process: dict) -> bool:
    arguments = python_arguments(process)
    return bool(arguments and PureWindowsPath(arguments[0]).name.casefold()
                in {"gemini_upload.py", "pipeline.py"})


def is_tool_process(process: dict, directory: Path) -> bool:
    if is_uploader(process):
        return True
    arguments = python_arguments(process)
    if arguments and PureWindowsPath(arguments[0]).name.casefold() in {"polygon_batch.py", "polygon_upload.py", "pipeline_launch.py"}:
        return True
    if arguments[:2] in (["-m", "gemini_tool.launch"], ["-m", "pipeline_launch"]):
        return True
    if arguments[:2] == ["-m", "venv"]:
        return len(arguments) == 3 and path_key(arguments[2]) == path_key(directory / ".venv-gemini")
    if arguments[:3] == ["-m", "pip", "install"]:
        requirement = option(arguments[3:], "-r") or option(arguments[3:], "--requirement")
        return requirement is not None and path_key(requirement) in {
            path_key(directory / "requirements-gemini.txt"), path_key(directory / "requirements.txt")}
    return False


def profile_roots(directory: Path, processes: list[dict], extra: list[Path]) -> set[Path]:
    roots = {directory / ".gemini-browser-native", *extra}
    roots.update(saved_profiles(directory / ".gemini-runtime"))
    roots.update(path for path in directory.glob(".gemini-browser*") if path.is_dir())
    for process in processes:
        if not is_uploader(process):
            continue
        arguments = python_arguments(process)
        script = arguments[0]
        base = Path(script).parent if ntpath.isabs(script) else directory
        profile = option(arguments[1:], "--profile")
        selected = Path(profile) if profile else base / ".gemini-browser-native"
        roots.add(selected if selected.is_absolute() else base / selected)
    return {path.absolute() for path in roots}


def is_tool_browser(process: dict, roots: set[Path]) -> bool:
    if (process.get("Name") or "").casefold() not in {"chrome.exe", "msedge.exe"}:
        return False
    profile = option(windows_args(process.get("CommandLine") or "")[1:], "--user-data-dir")
    return profile is not None and path_key(profile) in {
        path_key(root / name) for root in roots for name in ("chrome", "edge")
    }


def browser_targets(processes: list[dict], roots: set[Path]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for process in processes:
        if is_tool_browser(process, roots):
            arguments = windows_args(process.get("CommandLine") or "")[1:]
            groups.setdefault(path_key(option(arguments, "--user-data-dir")), []).append(process)
    targets = []
    for group in groups.values():
        parents = [row for row in group if option(
            windows_args(row.get("CommandLine") or "")[1:], "--type") is None]
        # taskkill /T on the browser parent also handles its renderer/helpers.
        # Only enumerate helpers separately when the browser parent has gone.
        targets.extend(parents or group)
    return targets


def list_processes() -> list[dict]:
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", PROCESS_QUERY],
        capture_output=True, encoding="utf-8-sig", timeout=30, check=False,
    )
    if result.returncode:
        raise RuntimeError("Không đọc được danh sách tiến trình Windows.")
    rows = json.loads(result.stdout) if result.stdout.strip() else []
    rows = [rows] if isinstance(rows, dict) else rows
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise RuntimeError("Danh sách tiến trình Windows không hợp lệ.")
    return rows


def same_process(expected: dict, current: dict) -> bool:
    pid = expected.get("ProcessId")
    return (type(pid) is int and pid > 0 and pid != os.getpid()
            and bool(expected.get("Created"))
            and all(current.get(key) == expected.get(key)
                    for key in ("ProcessId", "Created", "Name", "CommandLine")))


def terminate_tree(target: dict) -> bool:
    if not same_process(target, target):
        raise RuntimeError("Thiếu thông tin xác minh tiến trình; chưa dừng hoặc xóa trạng thái.")
    if not any(same_process(target, row) for row in list_processes()):
        return False
    pid = target["ProcessId"]
    subprocess.run(["taskkill.exe", "/PID", str(pid), "/T", "/F"],
                   capture_output=True, timeout=30, check=False)
    if any(same_process(target, row) for row in list_processes()):
        raise RuntimeError(f"Chưa dừng được PID {pid}; chưa xóa trạng thái. Kiểm tra quyền chạy tiến trình.")
    return True


def stop_all(directory: Path, extra: list[Path]) -> tuple[int, set[Path]]:
    roots = profile_roots(directory, [], extra)
    stopped = 0
    # Re-scan after terminating uploaders to catch detached/reused browser
    # processes and children that appeared during the first process snapshot.
    for _ in range(3):
        processes = list_processes()
        roots.update(profile_roots(directory, processes, extra))
        protected = caller_processes(processes)
        tools = [row for row in processes if row.get("ProcessId") not in protected
                 and is_tool_process(row, directory)]
        for target in tools:
            stopped += terminate_tree(target)
        if tools:
            # The uploader may already have closed Chrome during cooperative
            # cancellation, or taskkill /T may have removed the whole tree.
            processes = list_processes()
        browsers = [row for row in browser_targets(processes, roots)
                    if row.get("ProcessId") not in protected]
        for target in browsers:
            stopped += terminate_tree(target)
        if not tools and not browsers:
            return stopped, roots
    processes = list_processes()
    protected = caller_processes(processes)
    if any(row.get("ProcessId") not in protected
           and (is_tool_process(row, directory) or is_tool_browser(row, roots)) for row in processes):
        raise RuntimeError("Vẫn còn tiến trình của công cụ; chưa xóa trạng thái. Bấm Stop lại.")
    return stopped, roots


def caller_processes(processes: list[dict]) -> set[int]:
    """Automatic reset runs inside Start: never taskkill Start or its py.exe
    ancestors, since /T would also kill the reset which is currently running.
    """
    protected = {os.getpid(), os.getppid()}
    parents = {row.get("ProcessId"): row.get("ParentProcessId") for row in processes}
    pending = list(protected)
    while pending:
        parent = parents.get(pending.pop())
        if type(parent) is int and parent > 0 and parent not in protected:
            protected.add(parent)
            pending.append(parent)
    return protected


def reset_connections(roots: set[Path]) -> int:
    removed = 0
    for root in sorted(roots):
        if not ordinary_directory(root):
            continue
        for name in ("chrome", "edge"):
            browser = root / name
            removed += reset_browser_state(browser)
    return removed


def reset_temporary_files(directory: Path) -> int:
    removed = remove_state(directory / ".gemini-runtime")
    # Older releases prepared images in the Windows temp directory. A forced
    # termination could leave them behind; only accept the tool's file layout.
    for path in Path(tempfile.gettempdir()).glob("gemini-upload-*"):
        if ordinary_directory(path) and all(
            item.is_file() and not item.is_symlink()
            and re.fullmatch(r"(?:\d{4,}_.+\.png|\.source-\d{4,})", item.name)
            for item in path.iterdir()
        ):
            removed += remove_state(path)
    return removed


def reset_run(directory: Path, extra: list[Path], *, stop_processes: bool = True) -> int:
    """Shared Start/finally reset. Caller holds the reset lock throughout."""
    if stop_processes and sys.platform == "win32":
        request_stop(directory)
        _, roots = stop_all(directory, extra)
    else:
        from .native import close_unfinished_browsers

        roots = profile_roots(directory, [], extra)
        close_unfinished_browsers(roots)
    removed = reset_connections(roots)
    removed += reset_temporary_files(directory)
    (directory / ".gemini-stop-request").unlink(missing_ok=True)
    return removed


def request_stop(directory: Path) -> None:
    # Tell an in-flight BAT launcher not to advance from dependency checks into
    # installation/upload. The next explicit Start clears this cancellation.
    try:
        with (directory / ".gemini-stop-request").open("x", encoding="utf-8") as stream:
            stream.write("stop\n")
    except FileExistsError:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dừng luồng Gemini/Polygon, giữ checkpoint Polygon và đăng nhập Google.")
    parser.add_argument("--profile", type=Path, action="append", default=[],
                        help="Profile riêng bên ngoài repo cần dừng/dọn; có thể truyền nhiều lần.")
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        print("Chế độ --stop chỉ dùng trên Windows.", file=sys.stderr)
        return 1
    try:
        # Keep Start outside the entire reset, including the interval between
        # killing the old uploader and removing its browser/session state.
        with exclusive_lock(ROOT / ".gemini-reset.lock", timeout=2):
            request_stop(ROOT)
            print("Đã gửi yêu cầu Stop. Đang đóng uploader và trình duyệt của công cụ...", flush=True)
            stopped, roots = stop_all(ROOT, args.profile)
            removed = reset_connections(roots)
            removed += reset_temporary_files(ROOT)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Lỗi khi dừng/dọn trạng thái: {exc}", file=sys.stderr)
        return 1
    print(f"Đã hoàn tất Stop; không còn tiến trình của công cụ (dừng cưỡng bức {stopped} tiến trình gốc).")
    print(f"Đã dọn {removed} mục dữ liệu Gemini tạm: kết nối, tab khôi phục, bản nháp, cache và ảnh tạm.")
    print("Giữ ảnh gốc, đăng nhập, nội dung problem, checkpoint Polygon và report.txt.")
    print("Dùng start_resume.bat để tiếp tục Polygon; start.bat xóa trạng thái và nội dung cũ để chạy lượt mới.")
    print("Tin nhắn Gemini và tác vụ Polygon đã nhận vẫn tồn tại trên máy chủ.")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
