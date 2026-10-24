"""Visible browser workflow. No cookies, passwords or private Gemini API calls."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlencode, urlsplit

from .control import check_stop, exclusive_lock
from .images import PreparedImage, delete_uploaded
from .native import close_native_browser, start_native_browser, wait_for_manual_login

GEMINI_URL = "https://gemini.google.com/app?hl=en"
EDITOR = 'rich-textarea [contenteditable="true"], [contenteditable="true"][role="textbox"]'
COMPOSER = 'input-container, .input-area-container, .input-container, form'
UPLOAD_NAME = re.compile(
    r"add files|add photos|upload files?|upload\s*(?:&|and)\s*tools|open upload file menu|"
    r"tải lên và công cụ|tải lên và các công cụ|"
    r"thêm (tệp|ảnh)|tải (tệp|ảnh) lên|mở trình đơn tải|^(?:add|thêm|\+)\s*$", re.I,
)
LOCAL_UPLOAD_NAME = re.compile(
    r"^\s*(?:upload files?|(?:upload )?from computer|tải (?:tệp|ảnh) lên|tải lên tệp|từ máy tính)\s*$", re.I,
)
PLUS_ICON = re.compile(r"^\s*(?:add|add_2|add_circle|add_circle_outline|attach_file|plus|\+)\s*$")
UPLOAD_MENU = '[role="menu"], .cdk-overlay-container, .mat-mdc-menu-panel, [data-test-id="upload-menu"]'
SEND_NAME = re.compile(r"^(send|send message|submit|gửi|gửi tin nhắn)(\s.*)?$", re.I)
ACCOUNT_NAME = re.compile(r"^(Google Account|Tài khoản Google)(\s*:|\s*$)", re.I)
SIGN_IN_NAME = re.compile(r"^\s*(sign in|đăng nhập)\s*$", re.I)
NEW_CHAT_NAME = re.compile(r"^\s*(?:new chat|cuộc trò chuyện mới|đoạn chat mới|chat mới)(?:\s*\(.*\))?\s*$", re.I)


class GeminiBrowserError(RuntimeError):
    """Browser/UI did not confirm the requested operation."""


@contextmanager
def open_browser(profile: Path, login_timeout: float):
    """Use copy_info_on_gemini's native login before connecting automation."""
    from playwright.sync_api import Error as PlaywrightError, sync_playwright

    with exclusive_lock(profile.resolve() / ".gemini-profile.lock"):
        check_stop()
        login_url = "https://accounts.google.com/ServiceLogin?" + urlencode({
            "continue": GEMINI_URL, "followup": GEMINI_URL, "passive": "1209600",
        })
        try:
            port, session_file, old_tabs = start_native_browser(login_url, profile)
            wait_for_manual_login(port, old_tabs, timeout=login_timeout)
        except (OSError, ValueError) as exc:
            raise GeminiBrowserError(f"{exc}\nChưa tải hoặc xóa ảnh của lần chạy này.") from exc
        # Do not start the Playwright driver or attach CDP during Google sign-in.
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=5000)
            except PlaywrightError as exc:
                check_stop()
                raise GeminiBrowserError(
                    "Không kết nối được Chrome/Edge vừa đăng nhập. Đóng cửa sổ của script rồi chạy lại. "
                    "Chưa tải hoặc xóa ảnh."
                ) from exc
            try:
                if not browser.contexts:
                    raise GeminiBrowserError("Không tìm thấy phiên Chrome/Edge vừa đăng nhập; ảnh được giữ nguyên.")
                yield browser.contexts[0]
            finally:
                close_native_browser(browser, session_file)


def wait_for_editor(page, timeout: float):
    from playwright.sync_api import Error as PlaywrightError

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        check_stop()
        if page.is_closed():
            raise GeminiBrowserError("Tab Gemini đã đóng trước khi sẵn sàng.")
        try:
            location = urlsplit(page.url)
            if location.hostname == "accounts.google.com" and "/signin/rejected" in location.path:
                raise GeminiBrowserError(
                    "Google đã từ chối đăng nhập trong Chrome/Edge. "
                    "Chưa tải hoặc xóa ảnh của nhóm này. Giữ cửa sổ để bạn kiểm tra thông báo của Google."
                )
            if urlsplit(page.url).hostname == "gemini.google.com":
                editor = page.locator(EDITOR).first
                account = _first_ready(page.get_by_role("button", name=ACCOUNT_NAME).or_(
                    page.get_by_role("link", name=ACCOUNT_NAME)))
                sign_in = _first_ready(page.get_by_role("button", name=SIGN_IN_NAME).or_(
                    page.get_by_role("link", name=SIGN_IN_NAME)))
                # A guest also has an editable composer. Require the account
                # control, not merely a redirect back to gemini.google.com.
                if account is not None and sign_in is None and editor.is_visible() and editor.is_editable():
                    return editor
        except PlaywrightError:
            # The user may be completing Google sign-in/navigation.
            pass
        page.wait_for_timeout(300)
    raise GeminiBrowserError(
        "Hết thời gian chờ ô chat. Hãy đăng nhập Google, hoàn tất màn hình chào mừng "
        "và kiểm tra tài khoản có quyền dùng Gemini. Có thể tăng --login-timeout."
    )


NEW_CHAT_STATE = r"""editorSelector => {
    const visible = el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
    const editor = [...document.querySelectorAll(editorSelector)].find(visible);
    const root = editor?.closest('input-container, .input-area-container, .input-container, form');
    const text = (editor?.innerText || '').replace(/[\u200b-\u200d\u2060\ufeff]/g, '').trim();
    const messages = [...document.querySelectorAll(
        'user-query, .user-query-container, [data-message-author-role="user"]')].filter(visible).length;
    const attachments = root ? [...root.querySelectorAll(
        'uploader-preview, .file-preview-container, .upload-preview, .attachment-preview')].filter(visible).length : 0;
    return {home: location.hostname === 'gemini.google.com' && /^\/(?:u\/\d+\/)?app\/?$/.test(location.pathname),
        empty: !!editor && editor.isContentEditable && !text && !messages && !attachments};
}"""


def new_chat(page, timeout: float):
    from playwright.sync_api import Error as PlaywrightError

    check_stop()
    page.goto(GEMINI_URL, wait_until="commit", timeout=min(10000, timeout * 1000))
    deadline = time.monotonic() + timeout
    wait_for_editor(page, timeout)
    stable_since = None
    requested = False
    while time.monotonic() < deadline:
        check_stop()
        try:
            state = page.evaluate(NEW_CHAT_STATE, EDITOR)
        except PlaywrightError as exc:
            if page.is_closed():
                raise GeminiBrowserError("Tab Gemini đã đóng khi đang mở chat mới.") from exc
            # Account redirects can replace the document after the editor
            # first appears. Wait for the next document before confirming it.
            stable_since = None
            page.wait_for_timeout(100)
            continue
        if state["home"] and state["empty"]:
            if stable_since is None:
                stable_since = time.monotonic()
            if time.monotonic() - stable_since >= 1:
                return page
        else:
            stable_since = None
            if not requested:
                button = _first_ready(page.get_by_role("button", name=NEW_CHAT_NAME).or_(
                    page.get_by_role("link", name=NEW_CHAT_NAME)))
                if button is not None:
                    button.click(timeout=min(3000, max(1, (deadline - time.monotonic()) * 1000)))
                    requested = True
        page.wait_for_timeout(100)
    raise GeminiBrowserError(
        f"Hết thời gian chờ chat mới trống tại {urlsplit(page.url).path}. "
        "Chưa tải ảnh; kiểm tra nút New chat và nội dung đang có trong ô soạn thảo."
    )


def _file_input(root):
    inputs = root.locator('input[type="file"]')
    for i in range(inputs.count()):
        candidate = inputs.nth(i)
        accept = (candidate.get_attribute("accept") or "").lower()
        if not candidate.is_disabled() and (not accept or "image" in accept or ".png" in accept):
            return candidate
    return None


def _first_ready(locator):
    for index in range(locator.count()):
        candidate = locator.nth(index)
        if candidate.is_visible() and candidate.is_enabled():
            return candidate
    return None


def _composer(page):
    return _first_ready(page.locator(COMPOSER).filter(has=page.locator(EDITOR)))


def _upload_button(composer):
    # Scope to the editor: the sidebar's New chat can also have a plus icon.
    button = _first_ready(composer.get_by_role("button", name=UPLOAD_NAME))
    if button is not None:
        return button
    button = _first_ready(composer.locator(
        'button.upload-card-button, button[data-test-id="upload-file-button"], '
        'button[data-test-id="upload-menu-button"]'
    ))
    if button is not None:
        return button
    # A has-locator is evaluated relative to each button, so it must not
    # include the composer's ancestor selector.
    icons = composer.page.locator(
        'mat-icon, .material-icons, .material-symbols-outlined, .material-symbols-rounded, .google-symbols'
    ).filter(has_text=PLUS_ICON).or_(composer.page.locator(
        'mat-icon[fonticon="add"], mat-icon[fonticon="add_2"], mat-icon[fonticon="plus"], '
        '[data-mat-icon-name="add"], [data-mat-icon-name="plus"]'
    ))
    return _first_ready(composer.get_by_role("button").filter(has=icons))


def _upload_option(page):
    option = _first_ready(page.get_by_role("menuitem", name=LOCAL_UPLOAD_NAME))
    if option is not None:
        return option
    # Some Gemini menus use plain clickable text instead of menuitem roles.
    # Limit text matching to the popup so a prior chat message cannot be clicked.
    return _first_ready(page.locator(UPLOAD_MENU).get_by_text(LOCAL_UPLOAD_NAME))


def choose_files(page, paths: list[Path], timeout: float = 15):
    """Open the composer's + menu, choose Upload files, then supply local images."""
    values = [str(p.resolve()) for p in paths]
    choosers = []
    listener = lambda chooser: choosers.append(chooser)
    page.on("filechooser", listener)
    opened_menu = False
    selected_upload = False
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            check_stop()
            if choosers:
                choosers[-1].set_files(values)
                return
            if selected_upload:
                # The file input may be inserted after clicking Upload files
                # without firing a native filechooser event.
                file_input = _file_input(page)
                if file_input is not None:
                    file_input.set_input_files(values)
                    return
            else:
                option = _upload_option(page)
                if option is not None:
                    option.click()
                    selected_upload = True
                    continue
                if opened_menu and _first_ready(page.locator(UPLOAD_MENU).get_by_text(re.compile(
                    r"sign in to try tools|đăng nhập để (?:dùng thử|thử|sử dụng)", re.I,
                ))) is not None:
                    raise GeminiBrowserError(
                        "Gemini yêu cầu đăng nhập Google để tải tệp. "
                        "Hãy đăng nhập trong cửa sổ của script rồi chạy lại; chưa tải, gửi hoặc xóa ảnh."
                    )
                if not opened_menu:
                    composer = _composer(page)
                    if composer is not None:
                        button = _upload_button(composer)
                        if button is not None:
                            button.click()
                            opened_menu = True
                            continue
                        # Retain compatibility with layouts exposing an input
                        # directly in the composer without an upload menu.
                        file_input = _file_input(composer)
                        if file_input is not None:
                            file_input.set_input_files(values)
                            return
            page.wait_for_timeout(100)
        if selected_upload:
            detail = "Đã chọn Upload files nhưng không nhận được ô chọn tệp."
        elif opened_menu:
            detail = "Đã bấm dấu + nhưng không tìm thấy mục Upload files / Tải tệp lên."
        else:
            detail = "Không tìm thấy nút dấu + để thêm ảnh trong ô chat Gemini."
        raise GeminiBrowserError(detail + " Chưa xác nhận tải ảnh; giữ nguyên ảnh gốc.")
    finally:
        page.remove_listener("filechooser", listener)


# Read the composer only, so sidebar pictures and earlier chat attachments cannot
# accidentally be counted as confirmation of a new upload.
ATTACHMENT_STATE = r"""({editorSelector, names}) => {
    const editor = document.querySelector(editorSelector);
    if (!editor) return {count: 0, ready: false, busy: true, error: ''};
    const root = editor.closest('input-container, .input-area-container, .input-container, form');
    if (!root) return {count: 0, ready: false, busy: true, error: ''};
    const visible = el => !!(el.getClientRects().length) && getComputedStyle(el).visibility !== 'hidden';
    const query = selector => [...root.querySelectorAll(selector)].filter(visible);
    const labels = query('[title], [aria-label], img[alt]').filter(el => !editor.contains(el)).flatMap(el =>
        ['title', 'aria-label', 'alt'].map(attr => el.getAttribute(attr) || ''));
    const previews = query('uploader-preview, .file-preview-container, .upload-preview, .attachment-preview, .file-preview');
    const topPreviews = previews.filter(el => !previews.some(other => other !== el && other.contains(el)));
    const named = names.filter(name => labels.some(label => label.includes(name)) ||
        topPreviews.some(el => (el.innerText || '').includes(name))).length;
    const removers = query('button[aria-label]').filter(el =>
        /^(remove|delete|xóa|gỡ)\s.*(file|image|attachment|tệp|ảnh)/i.test(el.getAttribute('aria-label')));
    const thumbnails = query('img').filter(el => !el.closest('button, .avatar, .profile-image') && !editor.contains(el)
        && (topPreviews.length ? topPreviews.some(preview => preview.contains(el)) :
            names.some(name => (el.alt || '').includes(name))));
    const loaded = img => img.complete && img.naturalWidth > 0 && img.naturalHeight > 0;
    // Some layouts use a CSS background for the thumbnail instead of <img>.
    // Decode it as well; the filename/preview shell alone is never readiness.
    const backgrounds = topPreviews.filter(el => !el.querySelector('img')).map(el => {
        const background = [el, ...el.querySelectorAll('*')].filter(visible)
            .map(node => getComputedStyle(node).backgroundImage).find(value => /^url\(/.test(value));
        if (!background) return false;
        const url = background.slice(4, -1).replace(/^["']|["']$/g, '');
        const cache = window.__geminiUploaderBackgrounds ||= new WeakMap();
        let cached = cache.get(el);
        if (!cached || cached.url !== url) {
            const image = new Image();
            image.src = url;
            cached = {url, image};
            cache.set(el, cached);
        }
        return loaded(cached.image);
    });
    const loadingStatus = [...document.querySelectorAll('[role="status"], [aria-live]:not([aria-live="off"])')].filter(visible).filter(el =>
        !editor.contains(el) && !el.contains(editor)).some(el =>
        /uploading|loading|processing|đang tải|đang xử lý/i.test(el.innerText || ''));
    const busySelector = '[role="progressbar"], mat-progress-spinner, mat-spinner, [aria-busy="true"], ' +
        '.uploading, .loading, [data-upload-state="uploading"], [data-upload-state="pending"], ' +
        '[data-upload-state="processing"], [data-upload-state="loading"], [data-upload-state="queued"], ' +
        '[data-state="uploading"], [data-state="loading"], [data-state="processing"]';
    const portalProgress = [...document.querySelectorAll('[role="progressbar"], mat-spinner, mat-progress-spinner')].some(visible);
    const errors = [...document.querySelectorAll('[role="alert"], .upload-error, .file-error')]
        .filter(visible).map(el => el.innerText).filter(value =>
        /error|failed|couldn.t|unable|limit|too many|too large|unsupported|lỗi|không thể|giới hạn|quá lớn/i.test(value));
    return {
        count: Math.max(named, topPreviews.length, removers.length),
        ready: thumbnails.length + backgrounds.length === names.length &&
            thumbnails.every(loaded) && backgrounds.every(Boolean),
        busy: root.matches(busySelector) || query(busySelector).length > 0 || loadingStatus || portalProgress,
        error: errors.join('\n')
    };
}"""


def wait_for_upload(page, paths: list[Path], timeout: float, *, require_send: bool = False):
    deadline = time.monotonic() + timeout
    stable_since = None
    while time.monotonic() < deadline:
        check_stop()
        state = page.evaluate(ATTACHMENT_STATE, {
            "editorSelector": EDITOR, "names": [p.name for p in paths],
        })
        if state["error"]:
            raise GeminiBrowserError(f"Gemini từ chối ảnh: {state['error']}")
        button = None
        if require_send:
            composer = _composer(page)
            if composer is not None:
                button = _first_ready(composer.get_by_role("button", name=SEND_NAME))
        if (state["count"] == len(paths) and state["ready"] and not state["busy"]
                and (not require_send or button is not None)):
            if stable_since is None:
                stable_since = time.monotonic()
            if time.monotonic() - stable_since >= 2:
                return button
        else:
            stable_since = None
        page.wait_for_timeout(200)
    raise GeminiBrowserError(
        "Chưa xác nhận đủ ảnh xem trước đã tải xong hoặc nút Gửi chưa sẵn sàng. "
        "Kiểm tra tab Gemini (hạn mức, lỗi tải hoặc giao diện thay đổi); không tự gửi lại."
    )


SAVED_MESSAGE = r"""({editorSelector, prompt, names}) => {
    if (location.hostname !== 'gemini.google.com') return false;
    if (!/^\/(?:u\/\d+\/)?app\/[^/]+\/?$/.test(location.pathname)) return false;
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


def wait_for_saved_message(page, arguments: dict, timeout: float):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        check_stop()
        if page.evaluate(SAVED_MESSAGE, arguments):
            return
        page.wait_for_timeout(100)
    raise GeminiBrowserError("Hết thời gian xác nhận ảnh trong chat đã lưu.")


def send_prompt(page, prompt: str, paths: list[Path], timeout: float):
    check_stop()
    editor = page.locator(EDITOR).first
    editor.fill(prompt)
    # Filling the prompt can update the composer. Recheck the attachments and
    # enabled Send control together before clicking, even when called directly.
    button = wait_for_upload(page, paths, timeout, require_send=True)
    check_stop()
    button.click(timeout=min(3000, timeout * 1000))
    try:
        arguments = {"editorSelector": EDITOR, "prompt": prompt, "names": [p.name for p in paths]}
        wait_for_saved_message(page, arguments, timeout)
        # A cleared composer/optimistic preview alone is not a durable upload.
        # Require the sent images again after fetching the conversation anew.
        page.reload(wait_until="commit", timeout=min(10000, timeout * 1000))
        wait_for_saved_message(page, arguments, timeout)
    except Exception as exc:
        raise GeminiBrowserError(
            "Đã bấm Gửi nhưng chưa xác nhận được đủ ảnh trong chat sau khi tải lại. "
            "Giữ nguyên ảnh gốc. Kiểm tra lịch sử chat Gemini trước khi chạy lại để tránh gửi trùng."
        ) from exc


def keep_tabs_open(pages):
    print("Đóng các tab Gemini do script mở hoặc nhấn Ctrl+C khi xem xong.")
    while any(not page.is_closed() for page in pages):
        check_stop()
        page = next(page for page in pages if not page.is_closed())
        browser = page.context.browser
        if browser is not None and not browser.is_connected():
            return
        try:
            page.wait_for_timeout(300)
        except Exception:
            check_stop()
            if not page.is_closed() and (browser is None or browser.is_connected()):
                raise


def upload_images(images: list[PreparedImage], *, profile: Path,
                  login_timeout: float, upload_timeout: float,
                  batch_size: int, prompt: str, keep_images: bool = False,
                  attach_only: bool = False):
    from playwright.sync_api import Error as PlaywrightError

    pages = []
    kept = []
    try:
        with open_browser(profile, login_timeout) as context:
            print("Đã kết nối Chrome/Edge sau bước đăng nhập Gemini.")
            print(f"Phiên đăng nhập lưu trong {profile.resolve()}.")
            try:
                for start in range(0, len(images), batch_size):
                    check_stop()
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
                    print(f"Chat {len(pages)}: đang chờ {len(batch)} ảnh tải xong hoàn toàn...", flush=True)
                    wait_for_upload(page, paths, upload_timeout)
                    print(f"Chat {len(pages)}: đã thấy đủ {len(batch)} ảnh, không còn báo đang tải.")
                    if not attach_only:
                        send_prompt(page, prompt, paths, upload_timeout)
                        print(f"Đã kiểm tra đủ ảnh trong chat đã lưu: {page.url}")
                        if not keep_images:
                            kept.extend(delete_uploaded(batch))
                if attach_only:
                    print("Ảnh đang đính kèm, chưa gửi. Giữ nguyên toàn bộ ảnh gốc.")
            except Exception:
                print("Đã dừng lần chạy lỗi; giữ ảnh chưa xác nhận và đóng phiên trình duyệt này.", file=sys.stderr)
                raise
            if kept:
                raise GeminiBrowserError("Ảnh đã gửi nhưng một số bản gốc được giữ lại; xem lý do phía trên.")
            if attach_only:
                keep_tabs_open(pages)
            else:
                print("Đã gửi và xác nhận ảnh. Đang đóng trình duyệt và dọn trạng thái lần chạy...", flush=True)
    except PlaywrightError as exc:
        check_stop()
        raise GeminiBrowserError(
            f"Lỗi trình duyệt: {exc}\n"
            "Đóng cửa sổ của script rồi chạy lại start_gemini.bat. "
            "Không chạy đồng thời công cụ khác dùng cùng --profile. "
            "Ảnh chưa xác nhận được giữ lại."
        ) from exc
