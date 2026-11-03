"""Stop the previous Windows session, clear its data, and start a new problem."""
from __future__ import annotations

import json
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess
import sys

from .cleanup import reset_workspace
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
    rf'(?P<script>{_ARG})\s+(?:start|run|resume|init)(?=\s|$)', re.IGNORECASE)

_PROCESS_QUERY = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Get-CimInstance Win32_Process |
    Select-Object ProcessId, ParentProcessId, Name, CommandLine,
        @{Name='Created'; Expression={if ($null -ne $_.CreationDate) {$_.CreationDate.ToUniversalTime().ToString('o')} else {''}}} |
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
    processes = list_processes()
    parents = {row['ProcessId']: row.get('ParentProcessId') for row in processes}
    # py -3 can remain alive as our parent. Killing its process tree would also
    # kill this new Start before cleanup. Protect the whole current ancestry.
    protected = {os.getpid()}
    parent = os.getppid()
    while parent and parent not in protected:
        protected.add(parent)
        parent = parents.get(parent)
    targets = [row for row in processes
               if row.get('ProcessId') not in protected and is_uploader(row)]
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


def start_fresh(run_cli, directory: Path = REPOSITORY_DIR) -> int:
    if os.name != 'nt':
        print('Luồng Start tự dừng tiến trình chỉ dùng trên Windows.', file=sys.stderr)
        return 1
    directory = directory.resolve()
    try:
        stopped, failed = stop_uploads()
        if failed:
            raise WorkflowError('Chưa dừng được các tiến trình PID: ' + ', '.join(map(str, failed)))
        print(f'Đã dừng {stopped} tiến trình uploader cũ cùng các tiến trình con.')
        with state_lock(directory / '.polygon-start'):
            reset_workspace(directory)
            print('Đã xóa checkpoint và dữ liệu chạy cũ. Nội dung trong problem/ và resource/ được giữ nguyên.')
            print(f'Đang upload bài từ {directory / "problem"}...')
            return run_cli(['run', '--input', str(directory / 'problem'),
                            '--state', str(directory / 'run_state.json'),
                            '--output-dir', str(directory)])
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(f'Không thể bắt đầu phiên mới: {exc}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('\nĐã dừng. Mở lại start.bat sẽ dọn checkpoint/kết quả cũ, giữ nguyên problem/.')
        return 130
