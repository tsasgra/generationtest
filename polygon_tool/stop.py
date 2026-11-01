"""Stop Windows uploader process trees and reset the launcher's local run."""
from __future__ import annotations

import json
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess
import sys

from .workflow import WorkflowError, state_lock


REPOSITORY_DIR = Path(__file__).resolve().parent.parent


_PYTHON_NAME = re.compile(r'(?:py|pythonw?|python\d+(?:\.\d+)*)\.exe', re.IGNORECASE)
_ARG = r'(?:"[^"\r\n]+"|[^\s"]+)'
# Match an actual script invocation, not a filename appearing in another
# program's arguments or inside python -c. Includes commands used by start.bat.
_UPLOADER_COMMAND = re.compile(
    rf'^\s*{_ARG}\s+'
    rf'(?:(?:-[23](?:\.\d+)?(?:-(?:32|64))?|-[uBEIsSOqv]+|'
    rf'-[WX]\s+{_ARG})\s+)*'
    rf'(?P<script>{_ARG})\s+(?:run|resume|init)(?=\s|$)', re.IGNORECASE)

_PROCESS_QUERY = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Get-CimInstance Win32_Process |
    Where-Object { $_.Name -match '^(py|pythonw?|python\d+(\.\d+)*)\.exe$' } |
    Select-Object ProcessId, Name, CommandLine,
        @{Name='Created'; Expression={$_.CreationDate.ToUniversalTime().ToString('o')}} |
    ConvertTo-Json -Compress
'''


def is_uploader(process: dict) -> bool:
    if not _PYTHON_NAME.fullmatch(process.get('Name') or ''):
        return False
    match = _UPLOADER_COMMAND.match(process.get('CommandLine') or '')
    return bool(match and PureWindowsPath(match['script'].strip('"')).name.casefold() == 'polygon_upload.py')


def list_processes() -> list[dict]:
    result = subprocess.run(
        ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', _PROCESS_QUERY],
        capture_output=True, encoding='utf-8-sig', timeout=30, check=False)
    if result.returncode:
        raise RuntimeError('Không đọc được danh sách tiến trình Windows.')
    rows = json.loads(result.stdout) if result.stdout.strip() else []
    return [rows] if isinstance(rows, dict) else rows


def same_process(expected: dict, current: dict) -> bool:
    # A stale PID alone must never authorize termination after Windows reuses it.
    pid = expected.get('ProcessId')
    return (type(pid) is int and pid > 0 and pid != os.getpid()
            and bool(expected.get('Created'))
            and current.get('ProcessId') == pid
            and current.get('Created') == expected['Created']
            and is_uploader(current))


def stop_uploads() -> tuple[int, list[int]]:
    targets = [row for row in list_processes() if is_uploader(row)]
    stopped, failed = 0, []
    for target in targets:
        # Recheck identity just before taskkill. Parent termination may already
        # have stopped a child Python process from the original snapshot.
        if not any(same_process(target, row) for row in list_processes()):
            continue
        pid = target['ProcessId']
        result = subprocess.run(['taskkill.exe', '/PID', str(pid), '/T', '/F'],
                                capture_output=True, timeout=30, check=False)
        still_running = any(same_process(target, row) for row in list_processes())
        if still_running:
            failed.append(pid)
        elif result.returncode == 0:
            stopped += 1
    return stopped, failed


def reset_checkpoint(directory: Path) -> None:
    """Clear only this repository's default launcher state and output files."""
    state = directory / 'run_state.json'
    # Even an idle/failed run needs resetting. Do not parse its JSON: a damaged
    # checkpoint must also be removable. The lock prevents deleting active state.
    with state_lock(state):
        for name in ('run_state.json.tmp', 'result.json.tmp', 'problem_url.txt.tmp',
                     'result.json', 'problem_url.txt', 'run_state.json'):
            (directory / name).unlink(missing_ok=True)
    # Windows requires the lock handle to be closed before deleting its file.
    state.with_name(state.name + '.lock').unlink(missing_ok=True)


def main() -> int:
    if os.name != 'nt':
        print('stop.bat chỉ dùng trên Windows.', file=sys.stderr)
        return 1
    try:
        stopped, failed = stop_uploads()
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
        print('Không thể hoàn tất việc dừng. Kiểm tra quyền truy cập tiến trình trên Windows.',
              file=sys.stderr)
        return 1
    if failed:
        print('Chưa dừng được các tiến trình PID: ' + ', '.join(map(str, failed)), file=sys.stderr)
        return 1
    if stopped:
        print(f'Đã dừng {stopped} tiến trình uploader cùng các tiến trình con.')
    else:
        print('Không còn tiến trình uploader phù hợp đang chạy.')
    try:
        reset_checkpoint(REPOSITORY_DIR)
    except (OSError, WorkflowError) as exc:
        print(f'Chưa xóa hết checkpoint/kết quả cũ: {exc}', file=sys.stderr)
        print('Đóng uploader rồi bấm stop.bat lại trước khi chạy bài mới.', file=sys.stderr)
        return 1
    print('Đã xóa checkpoint và kết quả cục bộ của lần chạy trước.')
    print('Sửa nội dung trong problem, rồi bấm start.bat để bắt đầu bài mới.')
    print('Dùng tên định danh mới trong problem/name problem.txt nếu tên cũ đã có trên Polygon.')
    print('Bài đã tải và tác vụ Polygon đã nhận vẫn ở trên máy chủ.')
    return 0


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    raise SystemExit(main())
