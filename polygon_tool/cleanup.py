"""Remove uploader-owned local data before preparing a blank single problem."""
from __future__ import annotations

from contextlib import ExitStack
import json
from pathlib import Path
import stat

from .input import init_directory
from .workflow import WorkflowError, state_lock


_PROTECTED = {'.git', '.venv', 'venv', 'node_modules', 'work'}
_RESULTS = {'result.json', 'result.json.tmp', 'problem_url.txt', 'problem_url.txt.tmp'}


def _linked(path: Path) -> bool:
    """Include Windows junctions on Python 3.10, which lacks Path.is_junction."""
    attributes = path.lstat()
    return path.is_symlink() or bool(getattr(attributes, 'st_file_attributes', 0)
                                    & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _checkpoint(path: Path) -> bool:
    if path.name.startswith('run_state') and path.name.endswith(('.json', '.json.tmp', '.json.lock')):
        return True
    if path.name.endswith(('.json', '.json.tmp')):
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return False
        return (isinstance(value, dict) and value.get('version') == 1
                and isinstance(value.get('options'), dict)
                and 'input_path' in value['options']
                and ('input_digest' in value or value.get('kind') == 'batch'))
    return False


def _state_path(path: Path) -> Path:
    return path.with_suffix('') if path.suffix in ('.tmp', '.lock') else path


def _remove(path: Path, locked: set[Path]) -> None:
    if path in locked or not path.exists():
        return
    if _linked(path):
        raise WorkflowError(f'Không dọn dữ liệu qua liên kết: {path.name}')
    if path.is_dir():
        for child in list(path.iterdir()):
            _remove(child, locked)
        if not any(path.iterdir()):
            path.rmdir()
    else:
        path.unlink()


def reset_workspace(directory: Path) -> None:
    """Clear known run data inside this repository, preserving code and .env.

    No paths from checkpoint contents are followed. Damaged default checkpoints
    and leftover batch checkpoints are removable without valid JSON.
    """
    directory = directory.resolve()
    files, trees, states = set(), set(), {directory / 'run_state.json'}
    for name in ('problem', 'results', '.polygon-browser'):
        path = directory / name
        if path.exists() or path.is_symlink():
            trees.add(path)

    def scan(folder: Path, owned=False, batch_states=False):
        for path in folder.iterdir():
            if path.name == '.env' and folder == directory:
                continue
            if not owned and path.name in _PROTECTED:
                continue
            # Refuse linked cleanup targets before deleting ANY old input.
            if _linked(path):
                if owned or path in trees or path.name in _RESULTS or path.name.startswith('run_state'):
                    raise WorkflowError(f'Không dọn dữ liệu qua liên kết: {path.name}')
                continue
            if path.is_dir():
                is_batch = path.name.endswith('.problems')
                if path.name == '__pycache__' or is_batch:
                    trees.add(path)
                scan(path, owned or path in trees, batch_states or is_batch)
            elif _checkpoint(path) or (batch_states and path.name.endswith(('.json', '.json.tmp', '.json.lock'))):
                states.add(_state_path(path))
            elif path.name in _RESULTS or (folder == directory and path.suffix == '.log'):
                files.add(path)

    scan(directory)
    for state in states:
        for suffix in ('', '.tmp', '.lock'):
            path = state.with_name(state.name + suffix)
            if (path.exists() or path.is_symlink()) and _linked(path):
                raise WorkflowError(f'Không dọn checkpoint qua liên kết: {path.name}')
            files.add(path)
    locks = {state.with_name(state.name + '.lock') for state in states}
    # Lock every discovered checkpoint before deleting any data. Windows cannot
    # unlink open lock files, so remove those only after releasing all handles.
    with ExitStack() as stack:
        for state in sorted(states):
            stack.enter_context(state_lock(state))
        for path in sorted(files):
            _remove(path, locks)
        for path in sorted(trees, key=lambda p: len(p.parts), reverse=True):
            _remove(path, locks)
    for lock in locks:
        lock.unlink(missing_ok=True)
    for path in sorted(trees, key=lambda p: len(p.parts), reverse=True):
        _remove(path, set())
    init_directory(directory / 'problem')
