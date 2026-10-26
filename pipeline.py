#!/usr/bin/env python3
"""One entry point for imgN → Gemini → problemN → Polygon → report.txt."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from gemini_tool.browser import UploadTask, upload_tasks
from gemini_tool.control import StopRequested, check_stop, exclusive_lock, start_run
from gemini_tool.images import ImageInputError, collect_images, prepare_images
from gemini_tool.parts import DEFAULT_PROMPT, validate_output
from gemini_tool.state import ordinary_directory, remember_profile
from gemini_tool.cli import numbered_folders
from polygon_tool.credentials import load_credentials
from polygon_tool.input import MAX_PROBLEMS
from polygon_tool.cli import positive as positive_number, validate_options

ROOT = Path(__file__).resolve().parent
PROBLEM_COUNT = MAX_PROBLEMS


def directories(root: Path) -> tuple[list[Path], list[Path]]:
    return (numbered_folders(root),
            [root / "problem" / f"problem{i}" for i in range(1, PROBLEM_COUNT + 1)])


def initialize(root: Path) -> None:
    """Create only empty local folders; inputs/results are never distributed."""
    images, problems = directories(root)
    for path in (root / "img", root / "problem", *images, *problems):
        path.mkdir(parents=True, exist_ok=True)
        if not ordinary_directory(path):
            raise ValueError(f"Cần thư mục thật, không phải liên kết: {path}")


def prepare_tasks(root: Path, temporary: Path, max_file_mb: float) -> list[UploadTask]:
    image_dirs, problem_dirs = directories(root)
    tasks = []
    for number, (source, output) in enumerate(zip(image_dirs, problem_dirs), 1):
        check_stop()
        if not ordinary_directory(source):
            raise ImageInputError(f"Thiếu thư mục ảnh thật: {source}")
        files = collect_images(source, allow_empty=True)
        if not files:
            print(f"{source.name}: thư mục trống, bỏ qua.", flush=True)
            continue
        if not 1 <= len(files) <= 10:
            raise ImageInputError(f"img{number} cần từ 1 đến 10 ảnh của một bài; hiện có {len(files)} file.")
        # A missing/invalid page must fail the entire preflight, not silently
        # turn a multi-page problem into a different statement.
        images = prepare_images(files, temporary / f"img{number}", max_file_mb, skip_invalid=False)
        if any(not image.complete for image in images):
            raise ImageInputError(f"img{number}: hãy tách file nhiều trang/khung thành từng ảnh trước khi chạy.")
        validate_output(output)
        tasks.append(UploadTask(images, output, f"problem{number}"))
        print(f"img/{source.name}: {len(images)} ảnh → problem/problem{number}", flush=True)
    if not tasks:
        raise ImageInputError("Chưa có ảnh. Đặt ảnh vào img/img1…img10 rồi chạy lại start.bat.")
    return tasks


def execute(args, *, root: Path = ROOT) -> int:
    from pipeline_reset import fresh_run
    from polygon_tool.batch import preflight, upload_batch

    _, problem_dirs = directories(root)
    if args.command == "init":
        initialize(root)
        print("Đã tạo img/img1…img10 và problem/problem1…problem10.")
        return 0
    if args.command == "check":
        # This command never resets a previous run or opens a remote service.
        with tempfile.TemporaryDirectory(prefix="pipeline-check-") as temporary:
            tasks = prepare_tasks(root, Path(temporary), args.max_file_mb)
        print(f"Đã kiểm tra {len(tasks)} bài hợp lệ. Chưa gọi Gemini hoặc Polygon.")
        return 0

    validate_options({"timeLimit": args.time_limit, "memoryLimit": args.memory_limit,
                      "source_type": args.source_type})
    with ExitStack() as held:
        runtime = root / ".gemini-runtime"
        tasks = []

        def prepare():
            # Missing credentials/images must not erase the previous results.
            load_credentials(root / ".env")
            runtime.mkdir(parents=True, exist_ok=True)
            temporary = held.enter_context(tempfile.TemporaryDirectory(prefix="upload-", dir=runtime))
            tasks.extend(prepare_tasks(root, Path(temporary), args.max_file_mb))

        held.enter_context(fresh_run(root, problem_dirs, args.profile, before_reset=prepare))
        initialize(root)
        remember_profile(runtime, args.profile)
        print(f"Bước 1/3: gửi {len(tasks)} bài lên Gemini, tối đa {args.workers} tab song song.", flush=True)
        upload_tasks(tasks, profile=args.profile, login_timeout=args.login_timeout,
                     upload_timeout=args.upload_timeout, response_timeout=args.response_timeout,
                     prompt=args.prompt, keep_images=False, workers=args.workers)
        check_stop()
        # Only this run's full set may enter the Polygon stage. Start already
        # removed all old problem data, so stale output cannot leak in.
        selected = [task.output for task in tasks]
        preflight(selected)
        print(f"Bước 2/3: đã lưu và kiểm tra đủ 10 phần cho {len(tasks)} bài trong problem/.", flush=True)
        print(f"Bước 3/3: tải {len(tasks)} bài lên Polygon, tối đa {args.polygon_workers} bài song song.", flush=True)
        results = upload_batch(
            selected, state_dir=root / ".pipeline-state" / "polygon",
            output_dir=root / "polygon_results", report_path=root / "report.txt",
            options={"timeLimit": args.time_limit, "memoryLimit": args.memory_limit,
                     "source_type": args.source_type, "request_interval": args.request_interval,
                     "poll_timeout": args.poll_timeout},
            workers=args.polygon_workers, resume=False,
        )
        print(f"Hoàn tất {len(results)}/{len(tasks)} bài. Tổng hợp link: {root / 'report.txt'}", flush=True)
    return 0


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("command", choices=("run", "check", "init"), nargs="?", default="run",
                     help="run: xóa checkpoint và toàn bộ dữ liệu problem rồi chạy mới; check: kiểm tra ảnh offline.")
    cli.add_argument("--profile", type=Path, default=ROOT / ".gemini-browser-native")
    cli.add_argument("--workers", type=int, choices=range(1, 11), default=10)
    cli.add_argument("--polygon-workers", type=int, choices=range(1, 11), default=10)
    cli.add_argument("--login-timeout", type=positive_number, default=600)
    cli.add_argument("--upload-timeout", type=positive_number, default=180)
    cli.add_argument("--response-timeout", type=positive_number, default=600)
    cli.add_argument("--max-file-mb", type=positive_number, default=20)
    cli.add_argument("--prompt", default=DEFAULT_PROMPT)
    cli.add_argument("--time-limit", type=int)
    cli.add_argument("--memory-limit", type=int)
    cli.add_argument("--source-type", default="cpp.g++17")
    cli.add_argument("--request-interval", type=positive_number, default=1.0)
    cli.add_argument("--poll-timeout", type=positive_number, default=900)
    return cli


def run_pipeline(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not args.prompt.strip():
        parser().error("--prompt không được rỗng.")
    try:
        return execute(args)
    except (StopRequested, KeyboardInterrupt):
        print("Đã dừng. Start tạo lượt mới; start.bat resume tiếp tục giai đoạn Polygon.", file=sys.stderr)
        return 130
    except ImportError as exc:
        print(f"Thiếu thư viện {exc.name}. Chạy start.bat để cài thư viện.", file=sys.stderr)
        return 1
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Chưa hoàn tất: {exc}", file=sys.stderr)
        return 1


def _python_with_dependencies() -> Path:
    python = ROOT / ".venv-gemini" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    with exclusive_lock(ROOT / ".pipeline-setup.lock"):
        if not python.is_file():
            subprocess.run([sys.executable, "-m", "venv", str(ROOT / ".venv-gemini")], check=True)
        check = subprocess.run([str(python), "-c",
            "import playwright.sync_api, websocket, PIL, pillow_heif, resvg_py, rawpy"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if check.returncode:
            print("Đang cài thư viện còn thiếu vào .venv-gemini...", flush=True)
            subprocess.run([str(python), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")], check=True)
    return python


def _run_gemini(arguments: list[str]) -> int:
    """Keep the standalone uploader's reset/lock lifecycle in one bootstrap."""
    from gemini_tool.stop import reset_run

    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--profile", type=Path, default=ROOT / ".gemini-browser-native")
    parser.add_argument("--input", type=Path)
    selected, _ = parser.parse_known_args(arguments)
    diagnostic = any(value in arguments for value in ("--browser-info", "--help", "-h"))
    # The child always runs from ROOT, even if this launcher was invoked from
    # another working directory. Resolve cleanup targets the same way.
    selected.profile = (ROOT / selected.profile).resolve()
    if selected.input is not None:
        selected.input = (ROOT / selected.input).resolve()
    for path in (selected.profile, selected.input):
        if path is not None and path.resolve().is_relative_to((ROOT / ".gemini-runtime").resolve()):
            raise ValueError("Không đặt ảnh gốc hoặc profile đăng nhập trong .gemini-runtime (thư mục tạm).")

    def reset(message: str) -> None:
        print(message, flush=True)
        reset_run(ROOT, [selected.profile], stop_processes=False)
        print("Đã dọn trạng thái Gemini; giữ thư viện, đăng nhập, ảnh và kết quả Polygon.", flush=True)

    if diagnostic:
        return subprocess.call([sys.executable, "-u", "-m", "gemini_tool.cli", *arguments], cwd=ROOT)

    # Share the batch lifecycle lock as well as Gemini's locks: a standalone
    # click must not reset an active Polygon-only batch or its input files.
    with exclusive_lock(ROOT / ".pipeline-run.lock"), start_run(
        before_start=lambda: reset("Đang dọn phiên Gemini cũ trước khi chạy..."),
        after_run=lambda: reset("Đang dọn dữ liệu Gemini tạm sau lần chạy..."),
    ):
        check_stop()
        python = _python_with_dependencies()
        check_stop()
        return subprocess.call([str(python), "-u", "-m", "gemini_tool.cli", *arguments], cwd=ROOT)


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] in (["--help"], ["-h"]):
        print("Dùng: python pipeline.py [run|check|init|resume|gemini|polygon|polygon-one|stop] [tùy chọn]\n"
              "  run          ảnh → Gemini → problem → Polygon (mặc định)\n"
              "  check        kiểm tra ảnh offline\n"
              "  init         tạo thư mục img/img1…img10 và problem/problem1…problem10\n"
              "  resume       tiếp tục lô Polygon theo checkpoint\n"
              "  gemini       chỉ gửi ảnh và lấy 10 phần về problem\n"
              "  polygon      tải lô problem đã có (run/resume)\n"
              "  polygon-one  xử lý hoặc khôi phục một bài Polygon (run/resume)\n"
              "  stop         dừng và giữ checkpoint\n"
              "Xem tùy chọn: python pipeline.py run --help hoặc <chế độ> --help.")
        return 0
    action = arguments.pop(0) if arguments and not arguments[0].startswith("-") else "run"
    if action not in ("run", "check", "init", "resume", "gemini", "polygon", "polygon-one", "stop"):
        print("Chế độ không hợp lệ. Chạy python pipeline.py --help.", file=sys.stderr)
        return 2
    try:
        if action == "stop" or (action == "gemini" and arguments[:1] == ["--stop"]):
            from gemini_tool.stop import main as stop
            return stop(arguments[1:] if action == "gemini" else arguments)
        if action == "gemini":
            return _run_gemini(arguments)
        if action in ("resume", "polygon", "polygon-one"):
            if action == "polygon-one":
                from polygon_tool.cli import main as polygon
            else:
                from polygon_tool.batch import main as polygon
                if action == "resume":
                    arguments.insert(0, "resume")
                elif not arguments or arguments[0].startswith("-"):
                    arguments.insert(0, "run")
            return polygon(arguments)
        # Help/init use only stdlib. Run/check install dependencies once, then
        # re-enter this same CLI with the environment's Python interpreter.
        if action != "init" and not any(arg in ("--help", "-h") for arg in arguments):
            python = _python_with_dependencies()
            if Path(sys.executable).absolute() != python.absolute():
                return subprocess.call([str(python), "-u", str(ROOT / "pipeline.py"),
                                        action, *arguments], cwd=ROOT)
        return run_pipeline([action, *arguments])
    except (StopRequested, KeyboardInterrupt):
        print("Đã dừng khởi động.", file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Chưa chạy được: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
