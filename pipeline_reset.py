"""Reset only this pipeline's owned state before a fresh ten-problem run."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from pathlib import Path

from gemini_tool.control import exclusive_lock
from gemini_tool.state import ordinary_directory, remove_state
from gemini_tool.stop import profile_roots, reset_run
from polygon_tool.workflow import state_lock


def _ordinary_path(path: Path, *, directory: bool = True) -> None:
    for parent in (path, *path.parents) if directory else path.parents:
        if parent.is_symlink() or (parent.exists() and not ordinary_directory(parent)):
            raise ValueError(f"Đường dẫn không được qua liên kết hoặc file: {parent}")
    if not directory and path.is_symlink():
        raise ValueError(f"File trạng thái không được là liên kết: {path}")


def _overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _validate(root: Path, problem_dirs: list[Path], profile: Path) -> None:
    _ordinary_path(root)
    expected = [root / "problem" / f"problem{i}" for i in range(1, 11)]
    if problem_dirs != expected:
        raise ValueError("Chỉ dọn đúng problem/problem1 đến problem/problem10 của repository này.")
    for path in (root / "img", root / "problem", *problem_dirs,
                 root / ".pipeline-state", root / "batch_state",
                 root / "polygon_results", root / ".gemini-runtime"):
        _ordinary_path(path)
    _ordinary_path(profile)
    for reserved in (root / "img", root / "problem", root / ".pipeline-state",
                     root / "batch_state", root / "polygon_results", root / ".gemini-runtime",
                     root / ".venv-gemini", root / ".venv", root / "polygon_tool", root / "gemini_tool",
                     *(root / name for name in ("report.txt", "report.txt.tmp", "result.json", "result.json.tmp",
                       "problem_url.txt", "problem_url.txt.tmp", ".env", ".pipeline-run.lock",
                       ".gemini-launch.lock", ".gemini-upload.lock", ".gemini-reset.lock", ".gemini-stop-request"))):
        if _overlap(profile, reserved):
            raise ValueError("Profile trình duyệt phải tách khỏi ảnh, problem, mã nguồn và dữ liệu chạy.")
    # A custom profile at an ancestor of this repository would expose unrelated
    # folders to browser cleanup and is not an isolated tool profile.
    if profile == root or profile in root.parents:
        raise ValueError("Dùng một thư mục profile riêng, không dùng thư mục repository hoặc thư mục cha.")
    for name in (".pipeline-run.lock", ".gemini-launch.lock", ".gemini-upload.lock",
                 ".gemini-reset.lock", ".gemini-stop-request", "report.txt", "report.txt.tmp"):
        _ordinary_path(root / name, directory=False)


def _legacy_states(root: Path) -> list[Path]:
    states = {root / "run_state.json"}
    for path in root.glob("run_state*.json*"):
        name = path.name
        if name.endswith(".lock") or name.endswith(".tmp"):
            name = name.rsplit(".", 1)[0]
        if name.endswith(".json"):
            states.add(root / name)
    for path in states:
        for candidate in (path, path.with_name(path.name + ".tmp"), path.with_name(path.name + ".lock")):
            _ordinary_path(candidate, directory=False)
            if candidate.exists() and not candidate.is_file():
                raise ValueError(f"Checkpoint phải là file: {candidate}")
    return sorted(states)


def _check_owned_locks(root: Path) -> None:
    # Batch CLIs share .pipeline-run.lock. Also refuse a directly invoked
    # library workflow still using an owned checkpoint.
    with ExitStack() as locks:
        for directory in (root / ".pipeline-state", root / "batch_state"):
            if not directory.exists():
                continue
            for path in sorted(directory.rglob("*.lock")):
                _ordinary_path(path, directory=False)
                locks.enter_context(exclusive_lock(path))


def _clear_outputs(root: Path, problem_dirs: list[Path], legacy: list[Path]) -> None:
    problem_root = root / "problem"
    if problem_root.exists():
        # Start owns this entire generated-output tree, including archived
        # images and remnants of an interrupted export. Never follow links.
        for path in problem_root.iterdir():
            remove_state(path)
    for directory in problem_dirs:
        directory.mkdir(parents=True, exist_ok=True)
    for path in legacy:
        path.unlink(missing_ok=True)
        path.with_name(path.name + ".tmp").unlink(missing_ok=True)
    for name in (".pipeline-state", "batch_state", "polygon_results",
                 "report.txt", "report.txt.tmp", "result.json", "result.json.tmp",
                 "problem_url.txt", "problem_url.txt.tmp"):
        remove_state(root / name)


@contextmanager
def fresh_run(root: Path, problem_dirs: list[Path], profile: Path):
    """Hold the run locks while resetting and processing a fresh batch.

    Reset is performed once, before yielding. Completion/failure never erases
    the new report/checkpoints. Lock files are synchronization, not progress;
    an in-use legacy lock is deliberately never unlinked.
    """
    root = Path(root).absolute()
    problem_dirs = [Path(path).absolute() for path in problem_dirs]
    profile = Path(profile).absolute()
    _validate(root, problem_dirs, profile)
    legacy = _legacy_states(root)
    profiles = profile_roots(root, [], [profile])
    for candidate in profiles:
        _validate(root, problem_dirs, candidate)
        _ordinary_path(candidate / ".gemini-profile.lock", directory=False)
        if any(_overlap(candidate, state) for state in legacy):
            raise ValueError("Profile trình duyệt phải tách khỏi checkpoint.")
    with ExitStack() as held:
        held.enter_context(exclusive_lock(root / ".pipeline-run.lock"))
        with exclusive_lock(root / ".gemini-reset.lock", timeout=2):
            held.enter_context(exclusive_lock(root / ".gemini-launch.lock"))
            held.enter_context(exclusive_lock(root / ".gemini-upload.lock"))
            for path in legacy:
                held.enter_context(state_lock(path))
            _check_owned_locks(root)
            with ExitStack() as profile_locks:
                for candidate in sorted(profiles):
                    profile_locks.enter_context(exclusive_lock(candidate / ".gemini-profile.lock"))
                print("Đang xóa checkpoint, kết quả cũ và toàn bộ dữ liệu trong problem, kể cả img...", flush=True)
                # Only orphan connections can remain: active uploaders own the
                # launch/upload locks above. Preserve the native login profile.
                reset_run(root, [profile], stop_processes=False)
                _clear_outputs(root, problem_dirs, legacy)
            (root / ".gemini-stop-request").unlink(missing_ok=True)
        print("Đã dọn problem và checkpoint; bắt đầu lượt mới. Ảnh đầu vào trong img/ và đăng nhập được giữ lại.", flush=True)
        yield
