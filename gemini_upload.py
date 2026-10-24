#!/usr/bin/env python3
"""Prepare images, open fresh Gemini web chats and attach the images."""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys
import tempfile

from gemini_tool.browser import GeminiBrowserError, upload_images
from gemini_tool.control import RUNTIME, StopRequested, check_stop, upload_run
from gemini_tool.images import ImageInputError, collect_images, prepare_images
from gemini_tool.native import find_system_browser
from gemini_tool.state import remember_profile
from gemini_tool.stop import reset_run

ROOT = Path(__file__).resolve().parent


def positive_number(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Giá trị phải là số hữu hạn lớn hơn 0.")
    return number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tự nhận diện ảnh trong img, gửi lên Gemini rồi xóa ảnh đã xác nhận.")
    parser.add_argument("--input", type=Path, default=ROOT / "img", help="Thư mục ảnh (mặc định: img cạnh script).")
    parser.add_argument("--recursive", action="store_true", help="Đọc cả các thư mục con.")
    parser.add_argument("--dry-run", action="store_true", help="Kiểm tra/chuyển ảnh offline, không mở Gemini.")
    parser.add_argument("--profile", type=Path, default=ROOT / ".gemini-browser-native",
                        help="Thư mục profile Chrome/Edge riêng, giống copy_info_on_gemini.")
    parser.add_argument("--browser-info", action="store_true",
                        help="In tên và đường dẫn Chrome/Edge sẽ dùng rồi thoát; không cần ảnh.")
    parser.add_argument("--login-timeout", type=positive_number, default=600, help="Thời gian chờ đăng nhập, giây.")
    parser.add_argument("--upload-timeout", type=positive_number, default=180, help="Thời gian chờ tải ảnh, giây.")
    parser.add_argument("--response-timeout", type=positive_number, default=600,
                        help="Thời gian chờ Gemini hoàn tất đủ 10 Part để lưu vào problem, giây.")
    parser.add_argument("--batch-size", type=int, choices=range(1, 11), default=10, help="Tối đa 10 ảnh mỗi chat mới.")
    parser.add_argument("--max-file-mb", type=positive_number, default=20, help="Giới hạn MiB mỗi PNG sau chuyển đổi.")
    parser.add_argument("--prompt", default="apply polygon-problem-setter skill", help="Nội dung gửi kèm ảnh trong mỗi chat.")
    parser.add_argument("--keep-images", action="store_true", help="Giữ ảnh gốc sau khi gửi thành công.")
    parser.add_argument("--attach-only", action="store_true", help="Chỉ đính kèm, không gửi và không xóa ảnh.")
    args = parser.parse_args(argv)
    if args.prompt is not None and not args.prompt.strip():
        parser.error("--prompt không được rỗng.")
    try:
        if args.browser_info:
            name, executable = find_system_browser()
            print(f"Trình duyệt: {name.title()}\nĐường dẫn: {executable}")
            print(f"Profile: {(args.profile / name).resolve()}")
            print("Đăng nhập trực tiếp trước, kết nối Playwright sau khi quay về Gemini.")
            return 0
        for selected in (args.profile, args.input):
            if selected.resolve().is_relative_to(RUNTIME.resolve()):
                raise ValueError("Không đặt ảnh gốc hoặc profile đăng nhập trong .gemini-runtime (thư mục tạm).")
        def cleanup():
            reset_run(RUNTIME.parent, [args.profile], stop_processes=False)
            print("Đã dọn toàn bộ checkpoint, tab, bản nháp, cache và ảnh tạm; giữ thư viện đã cài và đăng nhập Google.", flush=True)

        with upload_run(cleanup=cleanup):
            files = collect_images(args.input.resolve(), args.recursive)
            remember_profile(RUNTIME, args.profile)
            # A forced Windows Stop bypasses Python's finally blocks. Keep all
            # prepared files in a known owned directory that Stop can remove.
            with tempfile.TemporaryDirectory(prefix="upload-", dir=RUNTIME) as directory:
                images = prepare_images(files, Path(directory), args.max_file_mb, skip_invalid=True)
                for item in images:
                    print(f"{item.source.name} → {item.upload.name}: {item.note}")
                print(f"{len(images)} ảnh; {(len(images) + args.batch_size - 1) // args.batch_size} chat mới.")
                if args.dry_run:
                    print("Kiểm tra offline thành công. Chưa mở Gemini hoặc tải ảnh lên mạng.")
                    return 0
                upload_images(
                    images, profile=args.profile,
                    login_timeout=args.login_timeout, upload_timeout=args.upload_timeout,
                    batch_size=args.batch_size, prompt=args.prompt,
                    keep_images=args.keep_images, attach_only=args.attach_only,
                    output=RUNTIME.parent / "problem", response_timeout=args.response_timeout,
                )
        return 0
    except (ImageInputError, GeminiBrowserError, ValueError, OSError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(f"Thiếu thư viện ({exc.name}). Chạy: python -m pip install -r requirements-gemini.txt", file=sys.stderr)
        return 1
    except StopRequested:
        print("\nĐã dừng uploader theo yêu cầu Stop. Ảnh chưa xác nhận được giữ lại.", file=sys.stderr)
        return 130
    except KeyboardInterrupt:
        print("\nĐã dừng. Ảnh chưa xác nhận được giữ lại; các chat đã gửi vẫn tồn tại trên Gemini.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
