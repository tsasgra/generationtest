#!/usr/bin/env python3
"""Xuất 10 phần từ một chat Gemini thành 10 file .txt (Python 3.10+).

Chỉ cần tải file này và chạy: python gemini_export.py
Dán URL của chat cần copy; script hiển thị URL, mã chat và tên bài đã đọc.
Kết quả nằm trong thư mục problem cạnh script. Chạy không tham số sẽ thay bộ
10 file cũ sau khi đọc đủ nội dung. Lần đầu tự cài Playwright nếu cần.
Xem các tùy chọn khác: python gemini_export.py --help
"""
from __future__ import annotations

import argparse
import importlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

PARTS = (
    "name problem", "name", "lengend", "input", "output", "note",
    "checker", "gen", "script_sinh_test", "solution",
)
PART_FILES = {part: f"{part}.txt" for part in PARTS}


_HEADING = re.compile(
    r"^\s*(?:#{1,6}\s+)?(?:\*\*|__)?Part\s+(\d+)\s*[:.()\-–—]\s*.+?$",
    re.IGNORECASE,
)
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})([^\r\n]*)$")

# Extract only headings and code bodies from model responses. textContent keeps
# Unicode, indentation, LaTeX and horizontally scrolled code without UI labels.
DOM_RESPONSES = r"""() => {
    let roots = [];
    for (const selector of ['model-response', '.model-response-text']) {
        roots = [...document.querySelectorAll(selector)];
        if (roots.length) break;
    }
    const responses = roots.map(root => {
        const events = [];
        function walk(el) {
            if (el.tagName === 'PRE') {
                events.push({code: (el.querySelector('code') || el).textContent});
                return;
            }
            const text = el.textContent.trim();
            const heading = /^Part\s+(\d+)\s*[:.()\-–—]\s*[^\r\n]+$/i.exec(text);
            if (heading && !el.querySelector('pre') && text.length < 200) {
                events.push({part: Number(heading[1])});
                return; // A <p><strong> heading must be counted only once.
            }
            for (const child of el.children) walk(child);
        }
        walk(root);
        return events;
    });
    return {url: location.href, title: document.title, responses};
}"""


def parts_from_events(events: list[dict]) -> dict[str, str]:
    """Validate all boundaries before permitting any output files to change."""
    sections: dict[int, list[str]] = {}
    current = None
    for event in events:
        if "part" in event:
            current = event["part"]
            if current not in range(1, 11):
                raise ValueError(f"Part {current} không thuộc bộ Part 1–10.")
            if current in sections:
                raise ValueError(f"Trùng Part {current}. Chỉ chọn một câu trả lời Gemini.")
            sections[current] = []
        elif "code" in event and current is not None:
            sections[current].append(event["code"])
    missing = sorted(set(range(1, 11)) - sections.keys())
    if missing:
        raise ValueError("Thiếu Part: " + ", ".join(map(str, missing)) + ". Chờ Gemini trả lời đủ 10 phần.")
    parts = {}
    for number, name in enumerate(PARTS, 1):
        blocks = sections[number]
        if len(blocks) != 1:
            raise ValueError(f"Part {number} phải có đúng một khối code; tìm thấy {len(blocks)}.")
        value = blocks[0]
        if name in ("name problem", "name"):
            if value.endswith("\r\n"):
                value = value[:-2]
            elif value.endswith(("\n", "\r")):
                value = value[:-1]
        if not value.strip():
            if name != "note":
                raise ValueError(f"Part {number} ({PART_FILES[name]}) không được để trống.")
            value = ""
        parts[name] = value
    return parts


def parse_response(text: str) -> dict[str, str]:
    """Parse a response copied as Markdown; headings inside code are content."""
    events: list[dict] = []
    delimiter = None
    body: list[str] = []
    for line in text.removeprefix("\ufeff").splitlines(keepends=True):
        content = line.rstrip("\r\n")
        if delimiter is not None:
            if re.fullmatch(r" {0,3}" + re.escape(delimiter[0]) +
                            "{" + str(len(delimiter)) + r",}[ \t]*", content):
                value = "".join(body)
                # The last line ending positions the Markdown closing fence.
                if value.endswith("\r\n"):
                    value = value[:-2]
                elif value.endswith(("\n", "\r")):
                    value = value[:-1]
                events.append({"code": value})
                delimiter = None
                body = []
            else:
                body.append(line)
            continue
        fence = _FENCE.fullmatch(content)
        if fence:
            delimiter = fence[1]
            continue
        heading = _HEADING.fullmatch(content)
        if heading:
            events.append({"part": int(heading[1])})
    if delimiter is not None:
        raise ValueError("Khối code chưa đóng. Sao chép lại toàn bộ câu trả lời đã hoàn tất.")
    return parts_from_events(events)


def write_parts(parts: dict[str, str], output: Path, *, overwrite: bool = False) -> None:
    """Stage a full set, then replace only a dedicated ten-file directory."""
    # Validate callers as well as parsed responses before staging anything.
    parts = parts_from_events([
        event for number, name in enumerate(PARTS, 1)
        for event in ({"part": number}, {"code": parts[name]})
    ])
    output = output.absolute()
    if output.is_symlink():
        raise ValueError("Thư mục đầu ra không được là symbolic link.")
    if output.exists():
        if not output.is_dir():
            raise ValueError("Đường dẫn đầu ra đã tồn tại và không phải thư mục.")
        if not overwrite:
            raise ValueError("Thư mục đầu ra đã tồn tại. Thêm --overwrite để thay bộ 10 file.")
        if any(p.name not in PART_FILES.values() or not p.is_file() or p.is_symlink()
               for p in output.iterdir()):
            raise ValueError("Chỉ thay thư mục chứa bộ 10 file chuẩn; có file/thư mục lạ trong đầu ra.")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".gemini-export-", dir=output.parent))
    previous = temporary / "previous"
    try:
        staging = temporary / "new"
        staging.mkdir()
        for name, filename in PART_FILES.items():
            (staging / filename).write_bytes(parts[name].encode("utf-8"))
        if output.exists():
            output.rename(previous)
        try:
            staging.rename(output)
        except OSError:
            if previous.exists():
                try:
                    previous.rename(output)
                except OSError as exc:
                    # Keep the backup if an external lock prevents rollback.
                    raise OSError(f"Không khôi phục được thư mục cũ; bộ file cũ còn tại {previous}") from exc
            raise
    except BaseException:
        if not previous.exists():
            shutil.rmtree(temporary)
        raise
    else:
        shutil.rmtree(temporary)


def validate_gemini_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise ValueError("Link Gemini không hợp lệ.") from exc
    if (parsed.scheme != "https" or parsed.netloc != "gemini.google.com" or
            not re.fullmatch(r"/(?:u/\d+/)?(?:app|share)/[A-Za-z0-9_-]+/?", parsed.path)):
        raise ValueError("Dùng link cuộc trò chuyện https://gemini.google.com/app/... hoặc /share/...")
    return value


def _conversation_key(value: str) -> list[str]:
    """Ignore account prefixes and query parameters added during login."""
    return urlsplit(validate_gemini_url(value)).path.rstrip("/").split("/")[-2:]


def read_browser(url: str, profile: Path, channel: str) -> dict[str, str]:
    url = validate_gemini_url(url.strip())
    print(f"\nChat Gemini sẽ copy: {url}")
    print(f"Mã chat: {_conversation_key(url)[1]}")
    print("Script chỉ đọc chat có mã này trong cửa sổ trình duyệt được mở.")
    try:
        importlib.import_module("playwright.sync_api")
    except ImportError:
        print("Lần đầu: đang cài Playwright...", flush=True)
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "playwright>=1.48,<2"], check=True)
            importlib.invalidate_caches()
            importlib.import_module("playwright.sync_api")
        except (ImportError, OSError, subprocess.CalledProcessError) as exc:
            raise ValueError("Chưa cài được Playwright. Chạy: python -m pip install playwright") from exc
    from playwright.sync_api import sync_playwright, Error as PlaywrightError
    profile = profile.resolve()
    print("Đăng nhập Gemini trong cửa sổ mở ra, nếu cần.")
    print("Kiểm tra link trên thanh địa chỉ, chờ đủ Part 1–10 và cuộn tới cuối.")
    print("Sẽ lấy câu trả lời cuối cùng có các tiêu đề Part trong chat đã chọn.")
    with sync_playwright() as playwright:
        context = None
        channels = ["chrome", "msedge", "chromium"] if channel == "auto" else [channel]
        for candidate in channels:
            try:
                context = playwright.chromium.launch_persistent_context(
                    str(profile), headless=False,
                    **({"channel": candidate} if candidate != "chromium" else {}),
                )
                break
            except PlaywrightError:
                continue
        if context is None:
            raise ValueError(
                "Không mở được trình duyệt. Đóng cửa sổ dùng cùng --browser-profile rồi thử lại. "
                "Cài Chrome/Edge, hoặc chạy python -m playwright install chromium. "
                "Nếu Google chặn đăng nhập, dùng --from-file (xem --help)."
            )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except PlaywrightError:
                print("Trang chưa tải xong. Bạn có thể mở link thủ công trong cửa sổ vừa mở.")
            while True:
                input("Khi đã sẵn sàng, quay lại cửa sổ này và nhấn Enter để xuất 10 file: ")
                pages = []
                if not context.pages:
                    raise ValueError("Cửa sổ Gemini đã đóng trước khi xuất dữ liệu.")
                for tab in context.pages:
                    if not tab.is_closed():
                        try:
                            if _conversation_key(tab.url) == _conversation_key(url):
                                pages.append(tab)
                        except ValueError:
                            pass
                if len(pages) != 1:
                    print(f"Giữ đúng một tab mở chat {url}, rồi thử lại.", file=sys.stderr)
                    continue
                try:
                    if pages[0].locator(
                        '.stop-button:visible, [data-test-id="stop-button"]:visible, '
                        'button[aria-label="Stop response"]:visible, '
                        'button[aria-label="Dừng phản hồi"]:visible'
                    ).count():
                        raise ValueError("Gemini đang trả lời. Chờ hoàn tất rồi nhấn Enter lại.")
                    snapshot = pages[0].evaluate(DOM_RESPONSES)
                    # Check the URL in the same DOM snapshot as the answer, so
                    # navigating to another chat cannot export the wrong one.
                    if _conversation_key(snapshot["url"]) != _conversation_key(url):
                        raise ValueError(f"Trang đã chuyển sang chat khác. Mở lại {url}.")
                    responses = snapshot["responses"]
                    candidates = [events for events in responses if any("part" in e for e in events)]
                    if not candidates:
                        raise ValueError("Không thấy Part 1–10 trong câu trả lời; cuộn tới câu trả lời cần xuất.")
                    # Never fall back to an older complete response if a newer
                    # ten-part answer is truncated or still being generated.
                    parts = parts_from_events(candidates[-1])
                    print(f'\nĐã đọc từ chat: {snapshot["url"]}')
                    print(f'Tiêu đề trang: {snapshot["title"]}')
                    print(f'Tên bài (Part 1): {parts["name problem"]}')
                    print(f'Tên hiển thị (Part 2): {parts["name"]}')
                    return parts
                except (ValueError, PlaywrightError) as exc:
                    print(f"Chưa xuất được: {exc}\nCó thể sửa trang rồi nhấn Enter lại, hoặc Ctrl+C để dừng.",
                          file=sys.stderr)
        finally:
            context.close()


def main(argv: list[str] | None = None) -> int:
    interactive = argv is None and len(sys.argv) == 1
    script_directory = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Chọn chat: mở cuộc trò chuyện Gemini, copy URL trên thanh địa chỉ rồi dán khi được hỏi.\n"
            "Hoặc chỉ định: python gemini_export.py --url https://gemini.google.com/app/MA_CHAT --overwrite\n\n"
            "Nếu không đăng nhập được trong trình duyệt tự động: dùng Copy response trên Gemini,\n"
            "lưu một câu trả lời đầy đủ dạng Markdown (giữ tiêu đề Part 1–10 và code fence) vào\n"
            "một file UTF-8, rồi chạy: python gemini_export.py --from-file response.md --overwrite"
        ),
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--url", help="Link cuộc trò chuyện Gemini (mở trình duyệt để đăng nhập).")
    source.add_argument("--from-file", type=Path, help="File UTF-8 chứa một câu trả lời Markdown đã copy.")
    parser.add_argument("--output", type=Path, default=script_directory / "problem",
                        help="Thư mục đầu ra; mặc định là problem cạnh script.")
    parser.add_argument("--overwrite", action="store_true", help="Thay bộ 10 file đã tồn tại.")
    parser.add_argument("--browser-profile", type=Path, default=script_directory / ".gemini-browser")
    parser.add_argument("--channel", choices=("auto", "chrome", "msedge", "chromium"), default="auto")
    args = parser.parse_args(argv)
    try:
        if args.from_file:
            print(f"Nguồn đã copy: {args.from_file.resolve()}")
            parts = parse_response(args.from_file.read_bytes().decode("utf-8-sig"))
        else:
            print(f"Thư mục lưu 10 file: {args.output.resolve()}")
            if interactive or args.overwrite:
                print("Bộ 10 file cũ trong thư mục này sẽ được thay khi đọc đủ nội dung.")
            url = args.url or input("Dán URL trên thanh địa chỉ của chat Gemini cần copy: ").strip()
            parts = read_browser(url, args.browser_profile, args.channel)
        write_parts(parts, args.output, overwrite=args.overwrite or interactive)
    except (ValueError, OSError, EOFError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nĐã dừng.", file=sys.stderr)
        return 130
    print(f"Đã xuất đủ 10 file UTF-8 vào {args.output.resolve()}:")
    for filename in PART_FILES.values():
        print(f"  {filename}")
    return 0


if __name__ == "__main__":
    exit_code = main()
    if os.name == "nt" and len(sys.argv) == 1:
        try:
            input("Nhấn Enter để đóng cửa sổ: ")
        except (EOFError, KeyboardInterrupt):
            pass
    raise SystemExit(exit_code)
