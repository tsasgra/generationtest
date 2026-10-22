@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
title Gemini Export
set "GEMINI_EXIT_CODE=1"
set "GEMINI_BAT_FILE=%~f0"
set "GEMINI_RUNTIME=%~dp0.gemini-runtime"
set "GEMINI_BOOTSTRAP_ARGS="
set "PYTHONUTF8=1"

if not exist "%GEMINI_RUNTIME%\Scripts\python.exe" goto find_python
"%GEMINI_RUNTIME%\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 goto run_export

:find_python
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto try_python
set "GEMINI_BOOTSTRAP=py"
set "GEMINI_BOOTSTRAP_ARGS=-3"
goto prepare_runtime

:try_python
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto python_missing
set "GEMINI_BOOTSTRAP=python"

:prepare_runtime
echo Lần đầu: đang chuẩn bị môi trường chạy...
"%GEMINI_BOOTSTRAP%" %GEMINI_BOOTSTRAP_ARGS% -m venv "%GEMINI_RUNTIME%"
if errorlevel 1 goto runtime_failed

:run_export
"%GEMINI_RUNTIME%\Scripts\python.exe" -u -c "import os; from pathlib import Path; p=Path(os.environ['GEMINI_BAT_FILE']); source=p.read_text(encoding='utf-8-sig').split('\n:__GEMINI_PYTHON__\n',1)[1]; exec(compile(source,str(p),'exec'),{'__name__':'__main__','__file__':str(p)})"
set "GEMINI_EXIT_CODE=%errorlevel%"
goto done

:python_missing
echo Chưa có Python 3.10 trở lên trên máy.
echo Cài Python từ https://www.python.org/downloads/windows/ rồi mở lại file BAT.
echo Khi cài, chọn Add python.exe to PATH nếu có.
goto done

:runtime_failed
echo Không tạo được môi trường chạy. Đặt file BAT trong thư mục có quyền ghi rồi chạy lại.
goto done

:done
echo(
echo Nhấn phím bất kỳ để đóng cửa sổ.
pause >nul
exit /b %GEMINI_EXIT_CODE%

:__GEMINI_PYTHON__
"""Embedded Gemini exporter: launched by gemini_export.bat."""
from __future__ import annotations

import importlib
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

PARTS = (
    "name problem", "name", "lengend", "input", "output", "note",
    "checker", "gen", "script_sinh_test", "solution",
)
PART_FILES = {part: f"{part}.txt" for part in PARTS}


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


def read_browser(url: str, profile: Path) -> dict[str, str]:
    url = validate_gemini_url(url.strip())
    expected_chat = _conversation_key(url)
    print(f"\nĐang trích xuất từ: {url}", flush=True)
    try:
        importlib.import_module("playwright.sync_api")
    except ImportError:
        print("Lần đầu: đang cài thư viện trình duyệt...", flush=True)
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "playwright>=1.48,<2"], check=True)
            importlib.invalidate_caches()
            importlib.import_module("playwright.sync_api")
        except (ImportError, OSError, subprocess.CalledProcessError) as exc:
            raise ValueError("Không cài được Playwright. Kiểm tra kết nối mạng rồi chạy lại file BAT.") from exc
    from playwright.sync_api import sync_playwright, Error as PlaywrightError

    with sync_playwright() as playwright:
        context = None
        for channel in ("chrome", "msedge", "chromium"):
            try:
                context = playwright.chromium.launch_persistent_context(
                    str(profile), headless=False,
                    **({"channel": channel} if channel != "chromium" else {}),
                )
                break
            except PlaywrightError:
                continue
        if context is None:
            print("Lần đầu: đang cài Chromium...", flush=True)
            try:
                subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
                context = playwright.chromium.launch_persistent_context(str(profile), headless=False)
            except (PlaywrightError, OSError, subprocess.CalledProcessError) as exc:
                raise ValueError(
                    "Không mở được trình duyệt. Đóng cửa sổ Gemini do lần chạy trước mở rồi chạy lại BAT."
                ) from exc
        try:
            page = context.pages[0] if context.pages else context.new_page()
            last_navigation = time.monotonic()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except PlaywrightError:
                pass
            print("Nếu được yêu cầu, đăng nhập Google trong cửa sổ mở ra. Script sẽ tự tiếp tục.", flush=True)
            deadline = time.monotonic() + 600
            last_events = None
            stable_since = time.monotonic()
            last_status = None
            last_error = None
            while time.monotonic() < deadline:
                open_tabs = [tab for tab in context.pages if not tab.is_closed()]
                if not open_tabs:
                    raise ValueError("Cửa sổ Gemini đã đóng trước khi xuất dữ liệu.")
                matches = []
                for tab in open_tabs:
                    try:
                        if _conversation_key(tab.url) == expected_chat:
                            matches.append(tab)
                    except ValueError:
                        pass
                if not matches:
                    status = "Đang chờ đăng nhập và tải chat Gemini..."
                    last_events = None
                    # Login may return to Gemini's home page. Restore the
                    # supplied conversation without requiring another action.
                    if page in open_tabs and time.monotonic() - last_navigation > 15:
                        try:
                            if urlsplit(page.url).netloc == "gemini.google.com":
                                last_navigation = time.monotonic()
                                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        except PlaywrightError:
                            pass
                else:
                    target = matches[-1]
                    try:
                        if target.locator(
                            '.stop-button:visible, [data-test-id="stop-button"]:visible, '
                            'button[aria-label="Stop response"]:visible, '
                            'button[aria-label="Dừng phản hồi"]:visible'
                        ).count():
                            last_events = None
                            status = "Gemini đang trả lời, sẽ tự xuất khi hoàn tất..."
                        else:
                            target.evaluate("""() => {
                                const roots = document.querySelectorAll('model-response, .model-response-text');
                                const last = roots[roots.length - 1];
                                if (last) (last.lastElementChild || last).scrollIntoView({block: 'end'});
                            }""")
                            snapshot = target.evaluate(DOM_RESPONSES)
                            if _conversation_key(snapshot["url"]) != expected_chat:
                                last_events = None
                                status = "Đang chờ đúng chat đã nhập..."
                            else:
                                candidates = [events for events in snapshot["responses"]
                                              if any("part" in event for event in events)]
                                if not candidates:
                                    last_events = None
                                    status = "Đang tải nội dung chat..."
                                else:
                                    events = candidates[-1]
                                    if events != last_events:
                                        last_events = events
                                        stable_since = time.monotonic()
                                    try:
                                        result = parts_from_events(events)
                                    except ValueError as exc:
                                        last_error = str(exc)
                                        if time.monotonic() - stable_since >= 5:
                                            raise ValueError(last_error)
                                        status = "Đang tải đủ 10 phần của câu trả lời..."
                                    else:
                                        if time.monotonic() - stable_since >= 1.5:
                                            print(f'Đã lấy: {result["name"]}', flush=True)
                                            return result
                                        status = "Đang lấy nội dung..."
                    except PlaywrightError:
                        last_events = None
                        status = "Đang chờ trang tải xong..."
                if status != last_status:
                    print(status, flush=True)
                    last_status = status
                # Playwright's wait also handles login and navigation events.
                open_tabs[0].wait_for_timeout(500)
            raise ValueError(last_error or "Hết 10 phút chờ đăng nhập/tải chat. Chạy lại BAT để thử lại.")
        except PlaywrightError as exc:
            raise ValueError("Không đọc được trang Gemini. Chạy lại BAT và đăng nhập nếu cần.") from exc
        finally:
            context.close()


def main() -> int:
    directory = Path(__file__).resolve().parent
    try:
        url = input("Dán link chat Gemini rồi nhấn Enter: ").strip()
        parts = read_browser(url, directory / ".gemini-browser")
        output = directory / "problem"
        write_parts(parts, output, overwrite=True)
    except (ValueError, OSError, EOFError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nĐã dừng.", file=sys.stderr)
        return 130
    print(f"\nĐã lưu đủ 10 file .txt tại: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
