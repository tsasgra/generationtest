"""Visible browser workflow. No cookies, passwords or private Gemini API calls."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlsplit

from .images import PreparedImage

GEMINI_URL = "https://gemini.google.com/app?hl=en"
EDITOR = 'rich-textarea [contenteditable="true"], [contenteditable="true"][role="textbox"]'
UPLOAD_NAME = re.compile(
    r"add files|add photos|upload files?|open upload file menu|"
    r"thêm (tệp|ảnh)|tải (tệp|ảnh) lên|mở trình đơn tải", re.I,
)
LOCAL_UPLOAD_NAME = re.compile(r"upload files?|from computer|tải tệp lên|từ máy tính", re.I)
SEND_NAME = re.compile(r"^(send|send message|submit|gửi|gửi tin nhắn)(\s.*)?$", re.I)


class GeminiBrowserError(RuntimeError):
    """Browser/UI did not confirm the requested operation."""


def validate_cdp_url(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"}):
        raise ValueError("--cdp-url phải là địa chỉ HTTP của Chrome trên máy này (localhost).")
    return value


@contextmanager
def open_browser(playwright, profile: Path, channel: str, cdp_url: str | None):
    if cdp_url:
        browser = playwright.chromium.connect_over_cdp(cdp_url)
        if not browser.contexts:
            raise GeminiBrowserError("Chrome CDP chưa có browser context.")
        # The caller owns this browser; never close its context or other tabs.
        yield browser.contexts[0]
    else:
        options = {} if channel == "chromium" else {"channel": channel}
        context = playwright.chromium.launch_persistent_context(
            str(profile.resolve()), headless=False, accept_downloads=False,
            viewport={"width": 1280, "height": 900}, **options,
        )
        try:
            yield context
        finally:
            context.close()


def wait_for_editor(page, timeout: float):
    from playwright.sync_api import Error as PlaywrightError

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if page.is_closed():
            raise GeminiBrowserError("Tab Gemini đã đóng trước khi sẵn sàng.")
        try:
            if urlsplit(page.url).hostname == "gemini.google.com":
                editor = page.locator(EDITOR).first
                if editor.is_visible() and editor.is_editable():
                    return editor
        except PlaywrightError:
            # The user may be completing Google sign-in/navigation.
            pass
        page.wait_for_timeout(300)
    raise GeminiBrowserError(
        "Hết thời gian chờ ô chat. Hãy đăng nhập Google, hoàn tất màn hình chào mừng "
        "và kiểm tra tài khoản có quyền dùng Gemini. Có thể tăng --login-timeout."
    )


def new_chat(page, timeout: float):
    page.goto(GEMINI_URL, wait_until="domcontentloaded", timeout=60000)
    wait_for_editor(page, timeout)
    # A login redirect can restore an old conversation. Navigate again once
    # authenticated and require the blank /app composer before attaching files.
    page.goto(GEMINI_URL, wait_until="domcontentloaded", timeout=60000)
    editor = wait_for_editor(page, timeout)
    if (urlsplit(page.url).path.rstrip("/") != "/app"
            or editor.inner_text().strip()
            or page.locator("user-query").count()):
        raise GeminiBrowserError("Không xác minh được chat mới trống; chưa tải ảnh vào chat này.")
    return page


def _file_input(page):
    inputs = page.locator('input[type="file"]')
    for i in range(inputs.count()):
        candidate = inputs.nth(i)
        accept = (candidate.get_attribute("accept") or "").lower()
        if not candidate.is_disabled() and (not accept or "image" in accept or ".png" in accept):
            return candidate
    return None


def choose_files(page, paths: list[Path]):
    """Prefer the native input, falling back to the visible upload menu."""
    values = [str(p.resolve()) for p in paths]
    file_input = _file_input(page)
    if file_input is not None:
        file_input.set_input_files(values)
        return
    choosers = []
    listener = lambda chooser: choosers.append(chooser)
    page.on("filechooser", listener)
    try:
        button = page.get_by_role("button", name=UPLOAD_NAME).first
        if not button.is_visible():
            raise GeminiBrowserError("Không tìm thấy nút thêm ảnh. Giao diện Gemini có thể đã đổi.")
        button.click()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if choosers:
                choosers[-1].set_files(values)
                return
            file_input = _file_input(page)
            if file_input is not None:
                file_input.set_input_files(values)
                return
            options = page.get_by_role("menuitem", name=LOCAL_UPLOAD_NAME).or_(
                page.get_by_role("button", name=LOCAL_UPLOAD_NAME)
            )
            visible = [options.nth(i) for i in range(options.count()) if options.nth(i).is_visible()]
            if visible:
                with page.expect_file_chooser(timeout=10000) as chooser:
                    visible[-1].click()
                chooser.value.set_files(values)
                return
            page.wait_for_timeout(100)
        raise GeminiBrowserError("Không tìm thấy mục Upload files hoặc ô chọn ảnh trên Gemini.")
    finally:
        page.remove_listener("filechooser", listener)


# Read the composer only, so sidebar pictures and earlier chat attachments cannot
# accidentally be counted as confirmation of a new upload.
ATTACHMENT_STATE = r"""({editorSelector, names}) => {
    const editor = document.querySelector(editorSelector);
    if (!editor) return {count: 0, busy: true, error: ''};
    const root = editor.closest('input-container, .input-area-container, .input-container, form');
    if (!root) return {count: 0, busy: true, error: ''};
    const visible = el => !!(el.getClientRects().length) && getComputedStyle(el).visibility !== 'hidden';
    const query = selector => [...root.querySelectorAll(selector)].filter(visible);
    const labels = query('[title], [aria-label], img[alt]').flatMap(el =>
        ['title', 'aria-label', 'alt'].map(attr => el.getAttribute(attr) || ''));
    const text = root.innerText || '';
    const named = names.filter(name => labels.some(label => label.includes(name)) || text.includes(name)).length;
    const previews = query('uploader-preview, .file-preview-container, .upload-preview, .attachment-preview');
    const topPreviews = previews.filter(el => !previews.some(other => other !== el && other.contains(el)));
    const removers = query('button[aria-label]').filter(el =>
        /^(remove|delete|xóa|gỡ)\s.*(file|image|attachment|tệp|ảnh)/i.test(el.getAttribute('aria-label')));
    const errors = [...document.querySelectorAll('[role="alert"], .upload-error, .file-error')]
        .filter(visible).map(el => el.innerText).filter(value =>
        /error|failed|couldn.t|unable|limit|too many|too large|unsupported|lỗi|không thể|giới hạn|quá lớn/i.test(value));
    return {
        count: Math.max(named, topPreviews.length, removers.length),
        busy: query('[role="progressbar"], mat-progress-spinner, [aria-busy="true"], .uploading').length > 0,
        error: errors.join('\n')
    };
}"""


def wait_for_upload(page, paths: list[Path], timeout: float):
    deadline = time.monotonic() + timeout
    stable_since = None
    while time.monotonic() < deadline:
        state = page.evaluate(ATTACHMENT_STATE, {
            "editorSelector": EDITOR, "names": [p.name for p in paths],
        })
        if state["error"]:
            raise GeminiBrowserError(f"Gemini từ chối ảnh: {state['error']}")
        if state["count"] == len(paths) and not state["busy"]:
            if stable_since is None:
                stable_since = time.monotonic()
            if time.monotonic() - stable_since >= 1:
                return
        else:
            stable_since = None
        page.wait_for_timeout(200)
    raise GeminiBrowserError(
        "Chưa xác nhận đủ ảnh và trạng thái tải xong trong ô chat. "
        "Kiểm tra tab Gemini (hạn mức, lỗi tải hoặc giao diện thay đổi); không tự gửi lại."
    )


def send_prompt(page, prompt: str, timeout: float):
    editor = page.locator(EDITOR).first
    editor.fill(prompt)
    button = page.get_by_role("button", name=SEND_NAME).first
    button.wait_for(state="visible", timeout=timeout * 1000)
    button.click(timeout=timeout * 1000)
    try:
        page.wait_for_function(
            "selector => /^\\/app\\/[^/]+/.test(location.pathname) && "
            "document.querySelector(selector)?.innerText.trim() === ''",
            arg=EDITOR, timeout=timeout * 1000,
        )
    except Exception as exc:
        raise GeminiBrowserError(
            "Đã bấm Gửi nhưng chưa xác nhận được chat đã lưu. "
            "Kiểm tra tab hiện tại trước khi chạy lại để tránh gửi trùng."
        ) from exc


def keep_tabs_open(pages):
    print("Giữ các tab để bạn xem/gửi ảnh. Đóng các tab Gemini do script mở hoặc nhấn Ctrl+C để kết thúc.")
    while any(not page.is_closed() for page in pages):
        page = next(page for page in pages if not page.is_closed())
        try:
            page.wait_for_timeout(300)
        except Exception:
            if any(not item.is_closed() for item in pages):
                raise


def upload_images(images: list[PreparedImage], *, profile: Path, browser: str,
                  cdp_url: str | None, login_timeout: float, upload_timeout: float,
                  batch_size: int, prompt: str | None):
    from playwright.sync_api import Error as PlaywrightError, sync_playwright

    pages = []
    try:
        with sync_playwright() as playwright:
            with open_browser(playwright, profile, browser, cdp_url) as context:
                print("Đăng nhập Google trong cửa sổ trình duyệt nếu được yêu cầu. Script không đọc mật khẩu.")
                try:
                    for start in range(0, len(images), batch_size):
                        batch = images[start:start + batch_size]
                        page = context.new_page()
                        pages.append(page)
                        new_chat(page, login_timeout)
                        paths = [item.upload for item in batch]
                        choose_files(page, paths)
                        wait_for_upload(page, paths, upload_timeout)
                        print(f"Chat {len(pages)}: đã thấy đủ {len(batch)} ảnh, không còn báo đang tải.")
                        if prompt:
                            send_prompt(page, prompt, upload_timeout)
                            print(f"Đã gửi. Link chat: {page.url}")
                    if not prompt:
                        print("Ảnh đang đính kèm trong chat mới. Bạn nhập nội dung và bấm Gửi để lưu vào lịch sử.")
                except Exception as exc:
                    print(f"Lỗi: {exc}\nGiữ tab để kiểm tra. Script chưa xác nhận hoàn tất.", file=sys.stderr)
                    keep_tabs_open(pages)
                    raise
                keep_tabs_open(pages)
    except PlaywrightError as exc:
        raise GeminiBrowserError(
            f"Lỗi trình duyệt: {exc}\n"
            "Cần máy có giao diện và Google Chrome, hoặc --browser msedge. "
            "Với --browser chromium, cài bằng python -m playwright install chromium. "
            "Nếu Google không cho đăng nhập trình duyệt tự động, dùng --cdp-url theo GEMINI.md."
        ) from exc
