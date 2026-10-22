#!/usr/bin/env python3
"""Prepare images, open fresh Gemini web chats and attach the images."""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys
import tempfile

from gemini_tool.browser import GeminiBrowserError, upload_images, validate_cdp_url
from gemini_tool.images import ImageInputError, collect_images, prepare_images

ROOT = Path(__file__).resolve().parent


def positive_number(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Giá trị phải là số hữu hạn lớn hơn 0.")
    return number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mở chat Gemini mới và tải ảnh từ thư mục img.")
    parser.add_argument("--input", type=Path, default=ROOT / "img", help="Thư mục ảnh (mặc định: img cạnh script).")
    parser.add_argument("--recursive", action="store_true", help="Đọc cả các thư mục con.")
    parser.add_argument("--dry-run", action="store_true", help="Kiểm tra/chuyển ảnh offline, không mở Gemini.")
    parser.add_argument("--browser", choices=("chrome", "msedge", "chromium"), default="chrome")
    parser.add_argument("--profile", type=Path, default=ROOT / ".gemini-browser", help="Profile riêng lưu phiên đăng nhập.")
    parser.add_argument("--cdp-url", type=validate_cdp_url, help="Kết nối Chrome bạn tự mở qua CDP localhost.")
    parser.add_argument("--login-timeout", type=positive_number, default=300, help="Thời gian chờ đăng nhập, giây.")
    parser.add_argument("--upload-timeout", type=positive_number, default=180, help="Thời gian chờ tải ảnh, giây.")
    parser.add_argument("--batch-size", type=int, choices=range(1, 11), default=10, help="Tối đa 10 ảnh mỗi chat mới.")
    parser.add_argument("--max-file-mb", type=positive_number, default=20, help="Giới hạn MiB mỗi PNG sau chuyển đổi.")
    parser.add_argument("--prompt", help="Nếu có, gửi nội dung này cùng ảnh trong mỗi chat; mặc định chỉ đính kèm.")
    args = parser.parse_args(argv)
    if args.prompt is not None and not args.prompt.strip():
        parser.error("--prompt không được rỗng.")
    try:
        files = collect_images(args.input.resolve(), args.recursive)
        # Validate every image before creating any chats. Temp files stay alive
        # until the browser workflow ends and are removed on success or failure.
        with tempfile.TemporaryDirectory(prefix="gemini-upload-") as directory:
            images = prepare_images(files, Path(directory), args.max_file_mb)
            for item in images:
                print(f"{item.source.name} → {item.upload.name}: {item.note}")
            print(f"{len(images)} ảnh; {(len(images) + args.batch_size - 1) // args.batch_size} chat mới.")
            if args.dry_run:
                print("Kiểm tra offline thành công. Chưa mở Gemini hoặc tải ảnh lên mạng.")
                return 0
            upload_images(
                images, profile=args.profile, browser=args.browser, cdp_url=args.cdp_url,
                login_timeout=args.login_timeout, upload_timeout=args.upload_timeout,
                batch_size=args.batch_size, prompt=args.prompt,
            )
        return 0
    except (ImageInputError, GeminiBrowserError, OSError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(f"Thiếu thư viện ({exc.name}). Chạy: python -m pip install -r requirements-gemini.txt", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nĐã dừng. Ảnh gốc được giữ nguyên; ảnh đã gửi trên Gemini không bị xóa.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
