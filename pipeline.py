#!/usr/bin/env python3
"""Run ten image → Gemini → Polygon jobs and collect their links in report.txt."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile

from gemini_tool.browser import GeminiBrowserError, UploadTask, upload_tasks
from gemini_tool.control import StopRequested, check_stop
from gemini_tool.images import ImageInputError, collect_images, prepare_images
from gemini_tool.parts import validate_output
from gemini_tool.state import ordinary_directory, remember_profile
from gemini_upload import positive_number
from polygon_tool.credentials import load_credentials
from polygon_tool.input import parse_problem
from polygon_upload import validate_options

ROOT = Path(__file__).resolve().parent
PROBLEM_COUNT = 10
DEFAULT_PROMPT = """apply polygon-problem-setter skill
Các ảnh trong tin nhắn này thuộc cùng MỘT bài toán. Đọc đủ ảnh, giữ nguyên đề,
ràng buộc và ví dụ; tạo trọn bộ nội dung Polygon cho bài này bằng tiếng Việt.
Trả về đúng 10 phần theo thứ tự dưới đây. Mỗi tiêu đề viết dạng “Part N: tên phần”,
ngay dưới tiêu đề là đúng một khối code chứa toàn bộ nội dung phần đó.
Part 1: name problem — tên định danh chỉ gồm chữ thường a-z, chữ số và dấu -.
Part 2: name — tên hiển thị trên một dòng.
Part 3: lengend — nội dung đề bằng LaTeX.
Part 4: input — mô tả dữ liệu vào bằng LaTeX.
Part 5: output — mô tả dữ liệu ra bằng LaTeX.
Part 6: note — ghi chú bằng LaTeX; dùng khối code rỗng nếu không có.
Part 7: checker — mã nguồn checker C++17 dùng testlib.h.
Part 8: gen — mã nguồn bộ sinh test C++17 dùng testlib.h.
Part 9: script_sinh_test — script sinh test tương thích Polygon.
Part 10: solution — mã nguồn lời giải tối ưu C++17.
Không bỏ phần, không gộp nhiều bài, không thay code bằng lời giải thích.
"""


def directories(root: Path) -> tuple[list[Path], list[Path]]:
    return ([root / "img" / f"img{i}" for i in range(1, PROBLEM_COUNT + 1)],
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
        files = collect_images(source)
        if not 1 <= len(files) <= 10:
            raise ImageInputError(f"img{number} cần từ 1 đến 10 ảnh của một bài; hiện có {len(files)} file.")
        # A missing/invalid page must fail the entire preflight, not silently
        # turn a multi-page problem into a different statement.
        images = prepare_images(files, temporary / f"img{number}", max_file_mb, skip_invalid=False)
        if any(not image.complete for image in images):
            raise ImageInputError(f"img{number}: hãy tách file nhiều trang/khung thành từng ảnh trước khi chạy.")
        validate_output(output)
        tasks.append(UploadTask(images, output, f"problem{number}"))
        print(f"img/img{number}: {len(images)} ảnh → problem/problem{number}", flush=True)
    return tasks


def execute(args, *, root: Path = ROOT) -> int:
    from pipeline_reset import fresh_run
    from polygon_batch import upload_batch

    image_dirs, problem_dirs = directories(root)
    if args.command == "init":
        initialize(root)
        print("Đã tạo img/img1…img10 và problem/problem1…problem10.")
        return 0
    if args.command == "check":
        # This command never resets a previous run or opens a remote service.
        with tempfile.TemporaryDirectory(prefix="pipeline-check-") as temporary:
            prepare_tasks(root, Path(temporary), args.max_file_mb)
        print("Đủ 10 bài hợp lệ để gửi ảnh. Chưa gọi Gemini hoặc Polygon.")
        return 0

    validate_options({"timeLimit": args.time_limit, "memoryLimit": args.memory_limit,
                      "source_type": args.source_type})
    with fresh_run(root, problem_dirs, args.profile):
        initialize(root)
        runtime = root / ".gemini-runtime"
        remember_profile(runtime, args.profile)
        with tempfile.TemporaryDirectory(prefix="upload-", dir=runtime) as temporary:
            tasks = prepare_tasks(root, Path(temporary), args.max_file_mb)
            # Fail locally before uploading images if Polygon is unconfigured.
            load_credentials(root / ".env")
            print(f"Bước 1–2: gửi ảnh và nhận 10 phần; tối đa {args.workers} bài Gemini song song.", flush=True)
            upload_tasks(tasks, profile=args.profile, login_timeout=args.login_timeout,
                         upload_timeout=args.upload_timeout, response_timeout=args.response_timeout,
                         prompt=args.prompt, keep_images=True, workers=args.workers)
        check_stop()
        # Only this run's full set may enter the Polygon stage. Start already
        # removed all old text files, so stale successful output cannot leak in.
        for directory in problem_dirs:
            parse_problem(directory)
        print(f"Bước 3: tải 10 bài lên Polygon, tối đa {args.polygon_workers} bài song song.", flush=True)
        results = upload_batch(
            problem_dirs, state_dir=root / ".pipeline-state" / "polygon",
            output_dir=root / "polygon_results", report_path=root / "report.txt",
            options={"timeLimit": args.time_limit, "memoryLimit": args.memory_limit,
                     "source_type": args.source_type, "request_interval": args.request_interval,
                     "poll_timeout": args.poll_timeout},
            workers=args.polygon_workers, resume=False,
        )
        print(f"Hoàn tất {len(results)}/10 bài. Tổng hợp link: {root / 'report.txt'}", flush=True)
    return 0


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("command", choices=("run", "check", "init"), nargs="?", default="run",
                     help="run: xóa checkpoint và .txt cũ rồi chạy mới; check: kiểm tra ảnh offline.")
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


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not args.prompt.strip():
        parser().error("--prompt không được rỗng.")
    try:
        return execute(args)
    except (StopRequested, KeyboardInterrupt):
        print("Đã dừng. Start sẽ xóa trạng thái và tạo lượt mới; start_resume chỉ tiếp tục giai đoạn Polygon.", file=sys.stderr)
        return 130
    except ImportError as exc:
        print(f"Thiếu thư viện {exc.name}. Chạy start.bat để cài thư viện, hoặc pip install -r requirements.txt.", file=sys.stderr)
        return 1
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Chưa hoàn tất: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
