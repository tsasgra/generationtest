"""Visible browser workflow. No cookies, passwords or private Gemini API calls."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlsplit

from .images import PreparedImage, delete_uploaded

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


@contextmanager
def open_browser(playwright, profile: Path):
    """Match copy_info_on_polygon's polygon_tool/problem_url.py browser launch."""
    profile = profile.resolve()
    profile.mkdir(parents=True, exist_ok=True)
    context = playwright.chromium.launch_persistent_context(str(profile), headless=False)
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
            location = urlsplit(page.url)
            if location.hostname == "accounts.google.com" and "/signin/rejected" in location.path:
                raise GeminiBrowserError(
                    "Google đã từ chối đăng nhập trong Chromium. Đây là cùng cơ chế trình duyệt "
                    "của copy_info_on_polygon; đăng nhập được Polygon không bảo đảm Google chấp nhận. "
                    "Chưa tải hoặc xóa ảnh của nhóm này. Giữ cửa sổ để bạn kiểm tra thông báo của Google."
                )
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


SAVED_MESSAGE = r"""({editorSelector, prompt, names}) => {
    if (!/^\/app\/[^/]+/.test(location.pathname)) return false;
    const editor = document.querySelector(editorSelector);
    if (!editor || editor.innerText.trim()) return false;
    const visible = el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
    const alerts = [...document.querySelectorAll('[role="alert"], .upload-error, .file-error')];
    if (alerts.some(el => visible(el) && /error|failed|unable|limit|lỗi|không thể|giới hạn/i.test(el.innerText))) return false;
    const normalize = text => text.replace(/\s+/g, ' ').trim();
    const turns = [...document.querySelectorAll('user-query, .user-query-container, [data-message-author-role="user"]')];
    return turns.some(turn => {
        if (!visible(turn) || !normalize(turn.innerText).includes(normalize(prompt))) return false;
        const attachments = [...turn.querySelectorAll(
            'user-query-file-preview, .file-preview-container, .file-preview, .attachment-preview, img')].filter(visible);
        const labels = attachments.flatMap(el => [el.innerText || '', ...['title', 'aria-label', 'alt']
            .map(attr => el.getAttribute(attr) || '')]);
        // A filename merely mentioned in the prompt is not an attachment.
        const named = names.filter(name => labels.some(label => label.includes(name))).length;
        const images = [...turn.querySelectorAll('img')].filter(img => visible(img) && img.complete &&
            img.naturalWidth > 0 && !img.closest('.avatar, .profile-image') &&
            !/avatar|profile/i.test(img.className + ' ' + img.alt));
        const busy = [...turn.querySelectorAll('[role="progressbar"], [aria-busy="true"]')].some(visible);
        return !busy && (named === names.length || images.length === names.length);
    });
}"""


def send_prompt(page, prompt: str, paths: list[Path], timeout: float):
    editor = page.locator(EDITOR).first
    editor.fill(prompt)
    button = page.get_by_role("button", name=SEND_NAME).first
    button.wait_for(state="visible", timeout=timeout * 1000)
    button.click(timeout=timeout * 1000)
    try:
        arguments = {"editorSelector": EDITOR, "prompt": prompt, "names": [p.name for p in paths]}
        page.wait_for_function(SAVED_MESSAGE, arg=arguments, timeout=timeout * 1000)
        # A cleared composer/optimistic preview alone is not a durable upload.
        # Require the sent images again after fetching the conversation anew.
        page.reload(wait_until="domcontentloaded", timeout=timeout * 1000)
        page.wait_for_function(SAVED_MESSAGE, arg=arguments, timeout=timeout * 1000)
    except Exception as exc:
        raise GeminiBrowserError(
            "Đã bấm Gửi nhưng chưa xác nhận được đủ ảnh trong chat sau khi tải lại. "
            "Giữ nguyên ảnh gốc. Kiểm tra tab hiện tại trước khi chạy lại để tránh gửi trùng."
        ) from exc


def keep_tabs_open(pages):
    print("Đóng các tab Gemini do script mở hoặc nhấn Ctrl+C khi xem xong.")
    while any(not page.is_closed() for page in pages):
        page = next(page for page in pages if not page.is_closed())
        try:
            page.wait_for_timeout(300)
        except Exception:
            if any(not item.is_closed() for item in pages):
                raise


def upload_images(images: list[PreparedImage], *, profile: Path,
                  login_timeout: float, upload_timeout: float,
                  batch_size: int, prompt: str, keep_images: bool = False,
                  attach_only: bool = False):
    from playwright.sync_api import Error as PlaywrightError, sync_playwright

    pages = []
    kept = []
    try:
        with sync_playwright() as playwright:
            with open_browser(playwright, profile) as context:
                print("Đã mở Chromium như nhánh copy_info_on_polygon.")
                print(f"Đăng nhập Google ngay trong cửa sổ này nếu cần. Phiên lưu tại {profile.resolve()}.")
                try:
                    for start in range(0, len(images), batch_size):
                        batch = images[start:start + batch_size]
                        # Reuse the launcher's empty tab, preserving any restored chats.
                        if not pages and context.pages and context.pages[0].url == "about:blank":
                            page = context.pages[0]
                        else:
                            page = context.new_page()
                        pages.append(page)
                        new_chat(page, login_timeout)
                        paths = [item.upload for item in batch]
                        choose_files(page, paths)
                        wait_for_upload(page, paths, upload_timeout)
                        print(f"Chat {len(pages)}: đã thấy đủ {len(batch)} ảnh, không còn báo đang tải.")
                        if not attach_only:
                            send_prompt(page, prompt, paths, upload_timeout)
                            print(f"Đã kiểm tra đủ ảnh trong chat đã lưu: {page.url}")
                            if not keep_images:
                                kept.extend(delete_uploaded(batch))
                    if attach_only:
                        print("Ảnh đang đính kèm, chưa gửi. Giữ nguyên toàn bộ ảnh gốc.")
                except Exception as exc:
                    print(f"Lỗi: {exc}\nGiữ tab và ảnh chưa xác nhận để kiểm tra.", file=sys.stderr)
                    keep_tabs_open(pages)
                    raise
                if kept:
                    keep_tabs_open(pages)
                    raise GeminiBrowserError("Ảnh đã gửi nhưng một số bản gốc được giữ lại; xem lý do phía trên.")
                print("Hoàn tất. Các tab Gemini vẫn mở để bạn xem kết quả.")
                keep_tabs_open(pages)
    except PlaywrightError as exc:
        raise GeminiBrowserError(
            f"Lỗi trình duyệt: {exc}\n"
            "Cài Chromium bằng python -m playwright install chromium trong đúng môi trường Python, "
            "hoặc mở lại start_gemini.bat để tự cài. Đóng phiên khác dùng cùng --profile nếu đang mở. "
            "Ảnh chưa xác nhận được giữ lại."
        ) from exc
