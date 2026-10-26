#!/usr/bin/env python3
"""One entry point for imgN → Gemini → problemN → Polygon → report.txt."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from gemini_tool.browser import UploadTask, upload_tasks
from gemini_tool.control import StopRequested, check_stop, exclusive_lock, start_run
from gemini_tool.images import (ImageInputError, PreparedImage, SourceSnapshot,
                                archive_uploaded, collect_images, prepare_images)
from gemini_tool.parts import DEFAULT_PROMPT, validate_output
from gemini_tool.state import ordinary_directory, remember_profile, remove_state
from gemini_tool.cli import numbered_folders
from polygon_tool.credentials import load_credentials
from polygon_tool.input import MAX_PROBLEMS, parse_problem
from polygon_tool.cli import positive as positive_number, validate_options
from polygon_tool.workflow import atomic_json

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
    from polygon_tool.batch import upload_batch

    image_dirs, problem_dirs = directories(root)
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
        selected = []
        resume = args.command == "resume"
        held.enter_context(fresh_run(root, problem_dirs, args.profile, resume=resume))
        load_credentials(root / ".env")
        runtime.mkdir(parents=True, exist_ok=True)
        # Keep the exact upload and source identities through Stop/Resume until
        # Polygon succeeds. Browser runtime cleanup must not discard these.
        image_state = root / ".pipeline-state" / "images"
        if resume:
            manifest = json.loads((root / ".pipeline-state/polygon/batch.json").read_text(encoding="utf-8"))
            selected.extend(Path(entry["path"]) for entry in manifest["inputs"])
            if any(path not in problem_dirs for path in selected):
                raise ValueError("Thư mục bài trong checkpoint không thuộc lượt chạy này.")
        else:
            tasks.extend(prepare_tasks(root, image_state, args.max_file_mb))
            selected.extend(task.output for task in tasks)
        initialize(root)
        remember_profile(runtime, args.profile)

        def generate(output):
            check_stop()
            # A stop after atomic export but before recording its digest must
            # reuse that complete response instead of sending the images again.
            if resume:
                try:
                    parse_problem(output)
                except (OSError, ValueError):
                    pass
                else:
                    print(f"{output.name}: dùng lại bộ 10 phần đã lưu; tiếp tục Polygon.", flush=True)
                    return
            task = next((task for task in tasks if task.output == output), None)
            if task is None:
                number = problem_dirs.index(output)
                source = image_dirs[number]
                images = prepare_images(collect_images(source), image_state / f"img{number + 1}",
                                        args.max_file_mb, skip_invalid=False)
                if not 1 <= len(images) <= 10 or any(not image.complete for image in images):
                    raise ImageInputError(f"{source.name}: cần 1–10 ảnh một trang của cùng một bài.")
                task = UploadTask(images, output, output.name)
            atomic_json(image_state / f"{output.name}.json", {
                "version": 1, "archived": False,
                "images": [{"source": str(item.source.relative_to(root)),
                            "upload": str(item.upload.relative_to(image_state)),
                            "snapshot": asdict(item.snapshot), "note": item.note,
                            "complete": item.complete} for item in task.images],
            })
            print(f"{output.name} — bước 1/3: gửi ảnh và chờ Gemini.", flush=True)
            upload_tasks([task], profile=args.profile, login_timeout=args.login_timeout,
                         upload_timeout=args.upload_timeout, response_timeout=args.response_timeout,
                         prompt=args.prompt, keep_images=True, workers=1)
            parse_problem(output)
            print(f"{output.name} — bước 2/3: đã lưu đủ 10 phần; bước 3/3: tải lên Polygon.", flush=True)

        def finish(output):
            checkpoint = image_state / f"{output.name}.json"
            if not checkpoint.is_file():
                # Older versions archived at Gemini export, before Polygon.
                # Never collect newly added inputs when resuming such a run.
                if resume and ordinary_directory(output / "img"):
                    return
                raise ImageInputError(f"{output.name}: thiếu checkpoint ảnh; giữ nguyên ảnh trong img/.")
            saved = json.loads(checkpoint.read_text(encoding="utf-8"))
            if (not isinstance(saved, dict) or saved.get("version") != 1 or
                    not isinstance(saved.get("images"), list) or not 1 <= len(saved["images"]) <= 10):
                raise ImageInputError(f"{output.name}: checkpoint ảnh không hợp lệ.")
            if saved.get("archived") is True:
                return
            number = problem_dirs.index(output)
            uploads = image_state / f"img{number + 1}"
            images = []
            for item in saved["images"]:
                source, upload = root / item["source"], image_state / item["upload"]
                if (source.parent != image_dirs[number] or upload.parent != uploads or
                        not ordinary_directory(source.parent) or not ordinary_directory(upload.parent)):
                    raise ImageInputError(f"{output.name}: đường dẫn ảnh khác checkpoint của bài.")
                images.append(PreparedImage(source, upload, item["note"],
                                            SourceSnapshot(**item["snapshot"]), item["complete"]))
            print(f"{output.name}: Polygon đã hoàn tất; chuyển ảnh vào {output / 'img'}.", flush=True)
            if archive_uploaded(images, output / "img", allow_missing=True):
                raise ImageInputError(f"{output.name}: Polygon đã xong nhưng chưa chuyển đủ ảnh; xem lỗi phía trên.")
            atomic_json(checkpoint, {**saved, "archived": True})
            remove_state(uploads)

        print(f"Xử lý tuần tự {len(selected)} bài; mỗi bài hoàn tất Polygon rồi mới sang bài kế tiếp.", flush=True)
        results = upload_batch(
            selected, state_dir=root / ".pipeline-state" / "polygon",
            output_dir=root / "polygon_results", report_path=root / "report.txt",
            options={"timeLimit": args.time_limit, "memoryLimit": args.memory_limit,
                     "source_type": args.source_type, "request_interval": args.request_interval,
                     "poll_timeout": args.poll_timeout},
            workers=1, resume=resume, prepare=generate, finish=finish,
            pipeline_options={key: str(value) if isinstance(value, Path) else value
                              for key, value in vars(args).items() if key != "command"},
        )
        print(f"Hoàn tất {len(results)}/{len(selected)} bài. Tổng hợp link: {root / 'report.txt'}", flush=True)
    return 0


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("command", choices=("run", "check", "init", "resume"), nargs="?", default="run",
                     help="run: xóa checkpoint và toàn bộ dữ liệu problem rồi chạy mới; check: kiểm tra ảnh offline.")
    cli.add_argument("--profile", type=Path, default=ROOT / ".gemini-browser-native")
    cli.add_argument("--workers", type=int, choices=(1,), default=1, help="Chạy tuần tự từng bài.")
    cli.add_argument("--polygon-workers", type=int, choices=(1,), default=1, help="Chạy tuần tự từng bài.")
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


def saved_pipeline_options(root: Path = ROOT):
    path = root / ".pipeline-state/polygon/batch.json"
    if not path.is_file():
        return None
    manifest = json.loads(path.read_text(encoding="utf-8"))
    options = manifest.get("pipeline_options")
    if options is not None and not isinstance(options, dict):
        raise ValueError("Tùy chọn pipeline trong checkpoint không hợp lệ.")
    return options


def run_pipeline(argv: list[str] | None = None) -> int:
    cli = parser()
    if argv and argv[0] == "resume":
        saved = dict(saved_pipeline_options() or {})
        if "profile" in saved:
            saved["profile"] = Path(saved["profile"])
        cli.set_defaults(**saved)
    args = cli.parse_args(argv)
    if not args.prompt.strip():
        parser().error("--prompt không được rỗng.")
    try:
        return execute(args)
    except (StopRequested, KeyboardInterrupt):
        print("Đã dừng. Mở start.bat để dọn lượt cũ và chạy mới từ ảnh trong img/.", file=sys.stderr)
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
        print("Dùng: python pipeline.py [run|check|init|resume|gemini|polygon|polygon-one|polygon-legacy|stop] [tùy chọn]\n"
              "  run          ảnh → Gemini → problem → Polygon (mặc định)\n"
              "  check        kiểm tra ảnh offline\n"
              "  init         tạo thư mục img/img1…img10 và problem/problem1…problem10\n"
              "  resume       tiếp tục bài đang dở và các bài còn lại\n"
              "  gemini       chỉ gửi ảnh và lấy 10 phần về problem\n"
              "  polygon      tải lô problem đã có (run/resume)\n"
              "  polygon-one  xử lý hoặc khôi phục một bài Polygon (run/resume)\n"
              "  polygon-legacy  launcher Polygon cũ (auto/check/resume/stop)\n"
              "  stop         dừng và giữ checkpoint\n"
              "Xem tùy chọn: python pipeline.py run --help hoặc <chế độ> --help.")
        return 0
    action = arguments.pop(0) if arguments and not arguments[0].startswith("-") else "run"
    if action not in ("run", "check", "init", "resume", "gemini", "polygon", "polygon-one", "polygon-legacy", "stop"):
        print("Chế độ không hợp lệ. Chạy python pipeline.py --help.", file=sys.stderr)
        return 2
    try:
        if action == "stop" or (action == "gemini" and arguments[:1] == ["--stop"]):
            from gemini_tool.stop import main as stop
            return stop(arguments[1:] if action == "gemini" else arguments)
        if action == "gemini":
            return _run_gemini(arguments)
        if action == "polygon-legacy":
            from polygon_tool.cli import legacy_launch
            return legacy_launch(arguments)
        if (action == "resume" and not (ROOT / ".pipeline-state/polygon/batch.json").is_file()
                and (ROOT / "run_state.json").is_file()):
            from polygon_tool.cli import legacy_launch
            return legacy_launch(["resume", "--state", str(ROOT / "run_state.json"), *arguments])
        sequential_resume = action == "resume" and saved_pipeline_options() is not None
        if action in ("resume", "polygon", "polygon-one") and not sequential_resume:
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
            if action == "run":
                from pipeline_reset import stop_previous_run
                selected = parser().parse_args(["run", *arguments])
                # Stop an interrupted bootstrap before waiting for its setup lock.
                stop_previous_run(ROOT, selected.profile)
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
