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


DEFAULT_PROMPT = "Đây là đề một bài tập cp, hãy viết lại đề bằng cách sử dụng skill polygon-problem-setter và xuát ra các kết quả cần thiết để tôi đưa lên polygon"


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


RESPONSE_STATE = r"""({prompt, revision = null, refresh = false, reveal = false, inspect = false}) => {
    const visible = el => {
        const style = getComputedStyle(el);
        if (style.visibility === 'hidden' || style.display === 'none') return false;
        return !!el.getClientRects().length ||
            style.display === 'contents' && [...el.children].some(visible);
    };
    const normalize = text => text.replace(/\s+/g, ' ').trim();
    const users = [...document.querySelectorAll('user-query, .user-query-container, [data-message-author-role="user"]')]
        .filter(visible).filter(el => !el.parentElement?.closest('user-query, .user-query-container, [data-message-author-role="user"]'));
    const matching = users.filter(el => normalize(el.textContent).includes(normalize(prompt)));
    const user = matching.length === 1 && matching[0] === users[users.length - 1] ? matching[0] : null;
    let roots = [];
    for (const selector of ['model-response', '.model-response-text', '[data-message-author-role="assistant"]']) {
        roots = [...document.querySelectorAll(selector)].filter(visible).filter(root =>
            user && (user.compareDocumentPosition(root) & Node.DOCUMENT_POSITION_FOLLOWING));
        if (roots.length) break;
    }
    const root = roots[roots.length - 1];
    const stop = [...document.querySelectorAll('.stop-button, [data-test-id="stop-button"], button[aria-label]')]
        .filter(visible).filter(el => !el.matches(':disabled, [aria-disabled="true"]')).find(el => {
            const label = el.getAttribute('aria-label') || '';
            // Some layouts reuse a button and leave its old stop-button class.
            if (/^(send|send message|submit|gửi|gửi tin nhắn)(\s|$)/i.test(label)) return false;
            return el.matches('.stop-button, [data-test-id="stop-button"]') ||
                /^(stop (response|generating|generation)|dừng (phản hồi|tạo|trả lời))/i.test(label);
        });
    const streaming = !!root && (root.matches('[aria-busy="true"], [data-is-streaming="true"], [data-state="streaming"]') ||
            [...root.querySelectorAll('.model-response-text[aria-busy="true"], [data-is-streaming="true"], [data-state="streaming"]')].some(visible));
    const busy = !!stop || streaming;
    const error = [...document.querySelectorAll('[role="alert"]')].filter(visible).map(el => el.innerText)
        .filter(text => /error|failed|unable|limit|lỗi|không thể|giới hạn/i.test(text)).join('\n');
    const state = {url: location.href, user: !!user, response: !!root, busy, events: null, revision: null, error};
    if (inspect) {
        // Sample progress only for the 15-second heartbeat. Never send the
        // partial source text over CDP or use this fingerprint to accept output.
        const text = normalize(root?.textContent || '');
        let hash = 2166136261;
        for (let i = 0; i < text.length; i++) hash = Math.imul(hash ^ text.charCodeAt(i), 16777619);
        const pres = root ? [...root.querySelectorAll('pre')].filter(visible) : [];
        const blocks = pres.length || (root ? [...root.querySelectorAll('code-block, .code-block')]
            .filter(visible).filter(el => !el.parentElement?.closest('code-block, .code-block')).length : 0);
        state.diagnostic = {signature: text.length + ':' + (hash >>> 0), characters: text.length,
            code_blocks: blocks, visibility: document.visibilityState, focused: document.hasFocus(),
            online: navigator.onLine, busy_source: stop ? 'Stop' : streaming ? 'streaming' : 'none'};
    }
    // Between heartbeats, only inspect readiness. Walking every code block
    // and sending its text over CDP on every poll slows down large responses.
    if (busy || !user || !root || error) return state;
    let cache = window.__geminiPartsCache;
    if (!cache || cache.root !== root || cache.prompt !== prompt) {
        cache?.observer.disconnect();
        cache = {root, prompt, id: crypto.randomUUID(), version: 0, dirty: true, events: [], revealed: false};
        cache.observer = new MutationObserver(() => { cache.version++; cache.dirty = true; });
        cache.observer.observe(root, {subtree: true, childList: true, characterData: true,
            attributes: true, attributeFilter: ['class', 'style', 'hidden', 'aria-hidden']});
        window.__geminiPartsCache = cache;
    }
    if (refresh) {
        // Layout/CSS changes outside root need not trigger its observer.
        cache.version++;
        cache.dirty = true;
    }
    if (reveal && !cache.revealed) {
        // Recover lazy rendering once, only after generation stopped and the
        // initial read was incomplete. Never scroll on every streaming poll.
        (root.lastElementChild || root).scrollIntoView({block: 'end', behavior: 'instant'});
        cache.revealed = true;
    }
    const events = [];
    const codeSelector = 'pre, code-block, .code-block, [data-test-id="code-block"]';
    function walk(el) {
        if (!visible(el)) return;
        if (el.matches(codeSelector)) {
            // Gemini also renders <code-block><code> without a <pre>.
            // Read code only, excluding the language/copy-button toolbar.
            let blocks = el.tagName === 'PRE' ? [el] : [...el.querySelectorAll('pre')];
            if (!blocks.length) blocks = [...el.querySelectorAll('code')];
            for (const block of blocks.filter(visible)) {
                events.push({code: (block.querySelector('code') || block).textContent});
            }
            return;
        }
        // Containers with code cannot be headings. Avoid concatenating all
        // their descendant code just to test a short heading expression.
        if (!el.querySelector(codeSelector)) {
            const text = normalize(el.textContent);
            const heading = /^(?:Part|Phần)\s+(\d+)(?:\s*[:.()\-–—]\s*.*|\s+.*)?$/i.exec(text);
            if (heading && text.length < 200 && [...text.matchAll(/(?:Part|Phần)\s+\d+/gi)].length === 1) {
                events.push({part: Number(heading[1])});
                return;
            }
        }
        for (const child of el.children) walk(child);
    }
    if (cache.dirty) {
        walk(root);
        cache.events = events;
        cache.dirty = false;
    }
    state.revision = cache.id + ':' + cache.version;
    // The caller acknowledges its last revision, so a failed CDP read cannot
    // accidentally lose the only copy of a completed response.
    if (revision !== state.revision) state.events = cache.events;
    return state;
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
    revision = None
    result = None
    stable_since = None
    idle_since = None
    next_refresh = 0
    last_status = None
    started = last_log = time.monotonic()
    next_inspection = started
    progress_signature = None
    progress_at = started
    last_diagnostic = ""
    last_error = "Chưa có câu trả lời đủ 10 Part."
    while time.monotonic() < deadline:
        check_stop()
        new_diagnostic = ""
        if page.is_closed():
            raise ValueError("Tab Gemini đã đóng trước khi lưu đủ 10 Part vào problem.")
        try:
            refresh = (result is None and idle_since is not None and
                       time.monotonic() >= max(idle_since + 2, next_refresh))
            inspect = time.monotonic() >= next_inspection
            snapshot = page.evaluate(RESPONSE_STATE, {"prompt": prompt, "revision": revision,
                                                       "refresh": refresh, "reveal": refresh, "inspect": inspect})
            if refresh:
                next_refresh = time.monotonic() + 2
        except PlaywrightError:
            if page.is_closed() or (page.context.browser is not None and not page.context.browser.is_connected()):
                raise ValueError("Mất kết nối Gemini trước khi lưu đủ 10 Part.")
            stable_since = None
            idle_since = None
            revision = None
            page.wait_for_timeout(200)
            continue
        if conversation_key(snapshot["url"]) != expected:
            raise ValueError("Đã chuyển sang chat khác khi đang chờ 10 Part.")
        if snapshot["error"]:
            raise ValueError(f"Gemini báo lỗi khi tạo 10 Part: {snapshot['error']}")
        if inspect:
            now = time.monotonic()
            next_inspection = now + 15
            diagnostic = snapshot.get("diagnostic")
            if diagnostic is not None:
                if diagnostic["signature"] != progress_signature:
                    progress_signature = diagnostic["signature"]
                    progress_at = now
                window = ("tab ẩn/nền" if diagnostic["visibility"] != "visible" else
                          "tab hiện, cửa sổ không có focus" if not diagnostic["focused"] else
                          "trang đang hoạt động")
                last_diagnostic = (
                    f"Đã chờ {now - started:.0f}s; vùng phản hồi: {diagnostic['characters']} ký tự, "
                    f"{diagnostic['code_blocks']} khối code; nội dung không đổi khoảng {now - progress_at:.0f}s; "
                    f"{window}; tín hiệu: {diagnostic['busy_source']}."
                )
                if not diagnostic["online"]:
                    last_diagnostic += " Trình duyệt báo mất mạng."
                new_diagnostic = last_diagnostic
        if snapshot["busy"] or not snapshot["user"] or snapshot["revision"] is None:
            stable_since = None
            idle_since = None
            previous = result = revision = None
            if not snapshot["user"]:
                last_error = "Chưa nhận diện được tin nhắn chứa prompt đã gửi trong chat hiện tại."
            elif snapshot["busy"]:
                last_error = "Giao diện Gemini vẫn báo đang tạo câu trả lời (Stop/streaming)."
            else:
                last_error = "Chưa nhận diện được vùng câu trả lời Gemini trong chat hiện tại."
            status = last_error
        else:
            if idle_since is None:
                idle_since = time.monotonic()
            events = snapshot["events"]
            if events is not None:
                revision = snapshot["revision"]
                if events != previous:
                    stable_since = time.monotonic()
                    result = None
                    try:
                        result = parts_from_events(events)
                    except ValueError as exc:
                        last_error = str(exc)
                previous = events
            if stable_since is None:
                stable_since = time.monotonic()
            if result is None:
                status = f"Đang chờ 10 Part: {last_error}"
            else:
                if time.monotonic() - stable_since >= 2:
                    return result
                status = "Đã thấy 10 Part; đang chờ nội dung ổn định..."
        if new_diagnostic or status != last_status or time.monotonic() - last_log >= 15:
            print(f"{status} {new_diagnostic}" if new_diagnostic else status, flush=True)
            last_status = status
            last_log = time.monotonic()
        # Streaming may take minutes while a skill runs. One DOM read/second is
        # enough; retain fast polling for the final two-second stability check.
        interval = 1000 if snapshot["busy"] or snapshot["revision"] is None else 200
        remaining = max(0, (deadline - time.monotonic()) * 1000)
        page.wait_for_timeout(min(interval, remaining))
    raise ValueError(
        f"Hết {timeout:g} giây chờ 10 Part: {last_error} "
        f"{last_diagnostic} Chat: {page.url}. "
        "Giữ ảnh gốc và bộ problem cũ; kiểm tra lịch sử Gemini trước khi gửi lại."
    )
