"""Wait for Gemini's complete ten-part response and save the problem locally."""
from __future__ import annotations

from pathlib import Path
import re
import shutil
import tempfile
import time
from urllib.parse import urlsplit

from polygon_tool.input import PARTS, PART_FILES, validate_names

from .control import check_stop
from .state import ordinary_directory


def output_destinations(output: Path, count: int) -> list[Path]:
    # Keep the established multi-chat layout on later single-chat runs, so a
    # completed earlier run's folders never block the next upload or get erased.
    nested = count > 1 or (ordinary_directory(output) and any(
        re.fullmatch(r"chat_\d{4,}", path.name) and ordinary_directory(path)
        for path in output.iterdir()
    ))
    return [output / f"chat_{index + 1:04d}" if nested else output for index in range(count)]


def parts_from_events(events: list[dict]) -> dict[str, str]:
    """Validate Gemini's Part 1–10 using Polygon's canonical field names."""
    sections: dict[int, list[str]] = {}
    current = None
    for event in events:
        if "part" in event:
            current = event["part"]
            if type(current) is not int or current not in range(1, 11):
                raise ValueError(f"Part {current} không thuộc bộ Part 1–10.")
            if current in sections:
                raise ValueError(f"Trùng Part {current}; cần một câu trả lời có đủ 10 phần.")
            sections[current] = []
        elif "code" in event and current is not None:
            sections[current].append(event["code"])
    missing = sorted(set(range(1, 11)) - sections.keys())
    if missing:
        raise ValueError("Thiếu Part: " + ", ".join(map(str, missing)))
    parts = {}
    for number, name in enumerate(PARTS, 1):
        blocks = sections[number]
        if len(blocks) != 1:
            raise ValueError(f"Part {number} phải có đúng một khối code; tìm thấy {len(blocks)}.")
        value = blocks[0]
        if not isinstance(value, str):
            raise ValueError(f"Part {number} không phải nội dung văn bản.")
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
    validate_names(parts)
    return parts


def validate_output(output: Path) -> None:
    output = output.absolute()
    for parent in output.parents:
        if parent.exists() and not ordinary_directory(parent):
            raise ValueError("Thư mục problem không được nằm qua liên kết hoặc đường dẫn không phải thư mục.")
    if output.is_symlink() or (output.exists() and not ordinary_directory(output)):
        raise ValueError("Đầu ra problem phải là thư mục riêng, không phải liên kết.")
    if output.exists():
        for path in output.iterdir():
            if path.name == "img" and ordinary_directory(path):
                continue
            if path.name not in PART_FILES.values() or not path.is_file() or path.is_symlink():
                raise ValueError(f"Chỉ thay bộ 10 file chuẩn và giữ img/; có file/thư mục lạ trong {output}.")


def write_parts(parts: dict[str, str], output: Path) -> None:
    parts = parts_from_events([
        event for number, name in enumerate(PARTS, 1)
        for event in ({"part": number}, {"code": parts[name]})
    ])
    check_stop()
    output = output.absolute()
    validate_output(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".gemini-export-", dir=output.parent))
    previous = temporary / "previous"
    try:
        staging = temporary / "new"
        staging.mkdir()
        for name, filename in PART_FILES.items():
            check_stop()
            payload = parts[name].encode("utf-8")
            target = staging / filename
            target.write_bytes(payload)
            if target.read_bytes() != payload:
                raise OSError(f"Không xác nhận được file đầu ra {filename}.")
        archive = output / "img"
        if archive.exists():
            # Copy the archive before swapping the complete problem directory.
            # Never move the only surviving images into a temporary location:
            # a failed write or forced stop must leave the old copy intact.
            shutil.copytree(archive, staging / "img", symlinks=True)
        check_stop()
        validate_output(output)
        if output.exists():
            output.rename(previous)
        try:
            staging.rename(output)
        except BaseException:
            if previous.exists():
                try:
                    previous.rename(output)
                except OSError as exc:
                    raise OSError(f"Bộ problem cũ còn tại {previous}; chưa khôi phục được thư mục.") from exc
            raise
    except BaseException:
        if not previous.exists():
            shutil.rmtree(temporary)
        raise
    else:
        shutil.rmtree(temporary)


RESPONSE_STATE = r"""prompt => {
    const visible = el => !!el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
    const normalize = text => text.replace(/\s+/g, ' ').trim();
    const users = [...document.querySelectorAll('user-query, .user-query-container, [data-message-author-role="user"]')]
        .filter(visible).filter(el => !el.parentElement?.closest('user-query, .user-query-container, [data-message-author-role="user"]'));
    const user = users.length === 1 && normalize(users[0].innerText).includes(normalize(prompt)) ? users[0] : null;
    let roots = [];
    for (const selector of ['model-response', '.model-response-text']) {
        roots = [...document.querySelectorAll(selector)].filter(visible).filter(root =>
            user && (user.compareDocumentPosition(root) & Node.DOCUMENT_POSITION_FOLLOWING));
        if (roots.length) break;
    }
    const root = roots[roots.length - 1];
    const busy = [...document.querySelectorAll('.stop-button, [data-test-id="stop-button"], button[aria-label]')]
        .filter(visible).some(el => el.matches('.stop-button, [data-test-id="stop-button"]') ||
            /^(stop (response|generating|generation)|dừng (phản hồi|tạo|trả lời))/i.test(el.getAttribute('aria-label') || '')) ||
        !!root && (root.matches('[aria-busy="true"], [data-is-streaming="true"], [data-state="streaming"]') ||
            [...root.querySelectorAll('[aria-busy="true"], [data-is-streaming="true"], [data-state="streaming"]')].some(visible));
    const events = [];
    function walk(el) {
        if (!visible(el)) return;
        if (el.tagName === 'PRE') {
            events.push({code: (el.querySelector('code') || el).textContent});
            return;
        }
        const text = el.textContent.trim();
        const heading = /^Part\s+(\d+)\s*[:.()\-–—]\s*[^\r\n]+$/i.exec(text);
        if (heading && !el.querySelector('pre') && text.length < 200) {
            events.push({part: Number(heading[1])});
            return;
        }
        for (const child of el.children) walk(child);
    }
    if (root) {
        (root.lastElementChild || root).scrollIntoView({block: 'end'});
        walk(root);
    }
    const error = [...document.querySelectorAll('[role="alert"]')].filter(visible).map(el => el.innerText)
        .filter(text => /error|failed|unable|limit|lỗi|không thể|giới hạn/i.test(text)).join('\n');
    return {url: location.href, user: !!user, busy, events, error};
}"""


def conversation_key(url: str) -> str:
    parsed = urlsplit(url)
    match = re.fullmatch(r"/(?:u/\d+/)?app/([^/]+)/?", parsed.path)
    if parsed.scheme != "https" or parsed.netloc != "gemini.google.com" or match is None:
        raise ValueError("Không còn ở cuộc trò chuyện Gemini vừa gửi ảnh.")
    return match[1]


def wait_for_parts(page, prompt: str, timeout: float) -> dict[str, str]:
    from playwright.sync_api import Error as PlaywrightError

    expected = conversation_key(page.url)
    deadline = time.monotonic() + timeout
    previous = None
    stable_since = None
    last_status = None
    last_error = "Chưa có câu trả lời đủ 10 Part."
    while time.monotonic() < deadline:
        check_stop()
        if page.is_closed():
            raise ValueError("Tab Gemini đã đóng trước khi lưu đủ 10 Part vào problem.")
        try:
            snapshot = page.evaluate(RESPONSE_STATE, prompt)
        except PlaywrightError:
            if page.is_closed() or (page.context.browser is not None and not page.context.browser.is_connected()):
                raise ValueError("Mất kết nối Gemini trước khi lưu đủ 10 Part.")
            stable_since = None
            page.wait_for_timeout(200)
            continue
        if conversation_key(snapshot["url"]) != expected:
            raise ValueError("Đã chuyển sang chat khác khi đang chờ 10 Part.")
        if snapshot["error"]:
            raise ValueError(f"Gemini báo lỗi khi tạo 10 Part: {snapshot['error']}")
        events = snapshot["events"]
        if snapshot["busy"] or not snapshot["user"]:
            stable_since = None
            status = "Gemini đang trả lời; tiếp tục chờ đủ 10 Part..."
        else:
            if events != previous or stable_since is None:
                stable_since = time.monotonic()
            try:
                result = parts_from_events(events)
            except ValueError as exc:
                last_error = str(exc)
                status = f"Đang chờ 10 Part: {last_error}"
            else:
                if time.monotonic() - stable_since >= 2:
                    return result
                status = "Đã thấy 10 Part; đang chờ nội dung ổn định..."
        previous = events
        if status != last_status:
            print(status, flush=True)
            last_status = status
        page.wait_for_timeout(200)
    raise ValueError(
        f"Hết {timeout:g} giây chờ 10 Part: {last_error} "
        "Giữ ảnh gốc và bộ problem cũ; kiểm tra lịch sử Gemini trước khi gửi lại."
    )
