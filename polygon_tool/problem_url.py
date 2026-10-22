"""Read Polygon's published problem URL; never synthesize its opaque token.

The documented problem.package endpoint returns a ZIP. Its descriptor may carry
an explicit URL; that field is opportunistic, not part of the API contract. If
absent, an optional browser reads the real link from the problem's current DOM.
"""
from __future__ import annotations

import io
from pathlib import Path
import re
import sys
import time
from urllib.parse import parse_qs, unquote, urlsplit
import xml.etree.ElementTree as ET
import zipfile


class URLResolutionError(ValueError):
    """The server did not provide a verified canonical problem URL."""


class URLIdentityError(URLResolutionError):
    """The returned descriptor belongs to a different problem or revision."""


def validate_problem_url(value: str, problem: dict) -> str:
    """Accept an observed canonical URL only if it matches API owner/name."""
    if not isinstance(value, str) or value != value.strip():
        raise URLResolutionError("Link Polygon trống hoặc chứa khoảng trắng ngoài.")
    try:
        parsed = urlsplit(value)
        valid_origin = (parsed.scheme == "https" and
                        parsed.netloc == "polygon.codeforces.com")
        parts = [unquote(part) for part in parsed.path.split("/")[1:]]
    except ValueError as exc:
        raise URLResolutionError("Link Polygon không hợp lệ.") from exc
    if (not valid_origin or parsed.query or parsed.fragment or len(parts) != 3 or
            any(not re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in parts) or
            parts[0].lower() in {"api", "problem", "problems", "contest", "c"}):
        raise URLResolutionError("Không phải link bài Polygon chính thức (có token, owner và tên bài).")
    if parts[1] != problem.get("owner") or parts[2] != problem.get("name"):
        raise URLIdentityError("Link Polygon không khớp owner/name của Problem ID đang xử lý.")
    return value


def url_from_package(package_bytes: bytes, problem: dict) -> str:
    """Inspect only problem.xml in memory; do not extract or run package files."""
    if not isinstance(package_bytes, bytes):
        raise URLResolutionError("API không trả ZIP dạng bytes.")
    try:
        with zipfile.ZipFile(io.BytesIO(package_bytes)) as archive:
            descriptors = [item for item in archive.infolist() if item.filename == "problem.xml"]
            if len(descriptors) != 1:
                raise URLResolutionError("Package không có đúng một problem.xml ở thư mục gốc.")
            entry = descriptors[0]
            if entry.file_size > 2 * 1024 * 1024:
                raise URLResolutionError("problem.xml vượt giới hạn đọc 2 MiB.")
            content = archive.read(entry)
    except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
        raise URLResolutionError("Không đọc được Standard ZIP từ Polygon.") from exc
    # No external/internal entity expansion in an untrusted descriptor.
    if b"<!doctype" in content.lower() or b"<!entity" in content.lower():
        raise URLResolutionError("problem.xml chứa khai báo DTD/entity không được hỗ trợ.")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise URLResolutionError("problem.xml không phải XML hợp lệ.") from exc
    if root.tag.rsplit("}", 1)[-1] != "problem":
        raise URLResolutionError("Phần tử gốc trong problem.xml không phải problem.")
    for key in ("id", "problemId"):
        server_id = root.get(key)
        # Some descriptors use nonnumeric archival identifiers in `id`.
        if server_id and server_id.isdecimal() and int(server_id) != int(problem["id"]):
            raise URLIdentityError("Problem ID trong package không khớp checkpoint.")
    revision = root.get("revision")
    if revision is not None and "revision" in problem:
        if revision != str(problem["revision"]):
            raise URLIdentityError("Revision trong package không khớp revision đã commit.")
    short_name = root.get("short-name")
    if short_name and short_name != problem["name"]:
        raise URLIdentityError("Tên bài trong package không khớp checkpoint.")
    value = root.get("url")
    if not value:
        raise URLResolutionError("Polygon không cung cấp thuộc tính url trong problem.xml.")
    return validate_problem_url(value, problem)


def _page_has_problem_id(page_url: str, hidden_ids: list[str], problem_id: int) -> bool:
    """Use the current page's query/hidden field, not unrelated navigation links."""
    try:
        parsed = urlsplit(page_url)
        if parsed.scheme != "https" or parsed.netloc != "polygon.codeforces.com":
            return False
        ids = parse_qs(parsed.query).get("problemId", [])
        if ids:
            return len(set(ids)) == 1 and ids[0] == str(problem_id)
        return bool(hidden_ids) and set(hidden_ids) == {str(problem_id)}
    except ValueError:
        return False


def _url_from_dom(values: list[str], problem: dict) -> str | None:
    candidates = set()
    for value in values:
        try:
            candidates.add(validate_problem_url(value, problem))
        except URLResolutionError:
            continue
    if len(candidates) > 1:
        raise URLResolutionError("DOM có nhiều link khác nhau cho bài; không tự chọn một link.")
    return next(iter(candidates), None)


def _browser_url(problem: dict, profile: Path, timeout: float) -> str:
    try:
        from playwright.sync_api import sync_playwright, Error as PlaywrightError
    except ImportError as exc:
        raise URLResolutionError(
            "Cần trình duyệt để đọc link: python -m pip install playwright; "
            "python -m playwright install chromium; chạy resume với --browser."
        ) from exc
    profile = profile.resolve()
    profile.mkdir(parents=True, exist_ok=True)
    print(
        f"Đăng nhập Polygon trong cửa sổ mở ra rồi mở bài ID {problem['id']} "
        f"({problem['name']}). Công cụ chỉ đọc link chính thức từ trang bài. "
        f"Phiên đăng nhập lưu riêng tại {profile}.", file=sys.stderr,
    )
    deadline = time.monotonic() + timeout
    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(str(profile), headless=False)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto("https://polygon.codeforces.com/", wait_until="domcontentloaded")
                while time.monotonic() < deadline:
                    for page in context.pages:
                        if page.is_closed():
                            continue
                        try:
                            hidden_ids = page.locator('input[name="problemId"]').evaluate_all(
                                "els => els.map(e => e.value)"
                            )
                            if not _page_has_problem_id(page.url, hidden_ids, problem["id"]):
                                continue
                            values = page.locator('a[href], input, textarea').evaluate_all(
                                "els => els.flatMap(e => [e.href || '', e.value || '', "
                                "e.tagName === 'A' ? e.textContent.trim() : ''])"
                            )
                            result = _url_from_dom(values, problem)
                            if result:
                                return result
                        except PlaywrightError:
                            # Navigation while the user signs in/open the problem is normal.
                            continue
                    if not context.pages:
                        raise URLResolutionError("Cửa sổ Polygon đã đóng trước khi đọc được link.")
                    context.pages[0].wait_for_timeout(500)
            finally:
                context.close()
    except PlaywrightError as exc:
        raise URLResolutionError(
            "Không khởi chạy/đọc được Chromium. Cài bằng python -m playwright install chromium "
            "và chạy trong phiên máy tính có giao diện."
        ) from exc
    raise URLResolutionError(
        f"Hết thời gian đọc link bài ID {problem['id']}; mở đúng trang bài rồi chạy lại resume --browser."
    )


def resolve_problem_url(api, problem: dict, package_id: int, *, browser: bool = False,
                        profile: Path = Path(".polygon-browser"), timeout: float = 300) -> str:
    """Read the exact READY package's descriptor, then optionally the real DOM."""
    payload = api.call("problem.package", {
        "problemId": problem["id"], "packageId": package_id, "type": "standard",
    }, binary=True)
    try:
        return url_from_package(payload, problem)
    except URLIdentityError:
        raise
    except URLResolutionError as exc:
        if not browser:
            raise URLResolutionError(
                f"{exc} Chạy resume với --browser để đọc ô link thật trên Polygon; "
                "không cần tạo hoặc build lại bài."
            ) from exc
        print(f"{exc} Chuyển sang đọc link từ giao diện Polygon.", file=sys.stderr)
    return _browser_url(problem, Path(profile), timeout)
