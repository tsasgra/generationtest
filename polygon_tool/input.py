"""Read ten UTF-8 files, with support for legacy combined marker inputs."""

from __future__ import annotations

from pathlib import Path
import re


PARTS = (
    "name problem",
    "name",
    "lengend",
    "input",
    "output",
    "note",
    "checker",
    "gen",
    "script_sinh_test",
    "solution",
)
PART_FILES = {part: f"{part}.txt" for part in PARTS}

_MARKER = re.compile(r"(?m)^<<<PART: ([^>\r\n]+)>>>(?:\r\n|\n|\r|$)")
_MARKER_LIKE = re.compile(r"(?m)^[ \t]*<<<PART:[^\r\n]*")
_LEADING_BLANK_LINES = re.compile(r"\A(?:[ \t]*(?:\r\n|\n|\r))+")
_TRAILING_BOUNDARY = re.compile(r"(?:(?:\r\n|\n|\r)[ \t]*)+\Z")
_FENCE_OPEN = re.compile(r"\A(`{3,}|~{3,})([A-Za-z0-9_+.-]*)(\r\n|\n|\r)")
# A conservative accepted profile, not an undocumented server length limit.
# Polygon's public API reference does not enumerate the complete slug grammar.
_SLUG = re.compile(r"[a-z0-9-]+\Z", flags=re.ASCII)


def template() -> str:
    """Return the blank template. Empty mandatory sections intentionally fail validation."""
    return "\n\n".join(f"<<<PART: {part}>>>" for part in PARTS) + "\n"


def init_directory(path: str | Path) -> None:
    """Create a new directory with the ten empty input files; never overwrite."""
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=False)
    for filename in PART_FILES.values():
        (directory / filename).touch(exist_ok=False)


def _decode_file(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"File {path.name!r} phải là UTF-8 (có hoặc không có BOM).") from exc


def parse_directory(path: str | Path) -> dict[str, str]:
    """Files are their own boundaries: preserve all content whitespace."""
    directory = Path(path)
    files = dict(PART_FILES)
    if (directory / "legend.txt").exists():
        if (directory / "lengend.txt").exists():
            raise ValueError("Trùng phần lengend: không được có cả legend.txt và lengend.txt.")
        files["lengend"] = "legend.txt"
    missing = [name for name in files.values() if not (directory / name).is_file()]
    if missing:
        raise ValueError("Thiếu file đầu vào: " + ", ".join(missing) + ".")
    unexpected = sorted(entry.name for entry in directory.iterdir()
                        if entry.suffix.lower() == ".txt" and entry.name not in files.values())
    if unexpected:
        raise ValueError("Thư mục chỉ được có đúng 10 file .txt đầu vào; file không nhận diện: "
                         + ", ".join(unexpected) + ".")
    parts = {}
    for part, filename in files.items():
        value = _unwrap_fence(_decode_file(directory / filename))
        # A text editor normally adds one final line ending to a one-line name.
        # Keep all other spaces/newlines in names so invalid names are rejected.
        if part in ("name problem", "name"):
            if value.endswith("\r\n"):
                value = value[:-2]
            elif value.endswith(("\n", "\r")):
                value = value[:-1]
        if not value.strip():
            if part != "note":
                raise ValueError(f"File {filename!r} không được để trống.")
            value = ""
        parts[part] = value
    validate_names(parts)
    return parts


def _boundaries(value: str) -> str:
    if not value.strip():
        return ""
    value = _LEADING_BLANK_LINES.sub("", value)
    return _TRAILING_BOUNDARY.sub("", value)


def _unwrap_fence(value: str) -> str:
    """Unwrap one complete, unambiguous outer fence; leave internal text unchanged."""
    opening = _FENCE_OPEN.match(value)
    if opening is None:
        return value
    delimiter = opening.group(1)
    closing = re.compile(
        r"(?m)^" + re.escape(delimiter) + r"[ \t]*(?:\r\n|\n|\r|$)"
    )
    closings = list(closing.finditer(value, opening.end()))
    if len(closings) != 1 or closings[0].end() != len(value):
        return value
    body = value[opening.end() : closings[0].start()]
    # The newline that positions the closing fence belongs to the envelope.
    if body.endswith("\r\n"):
        body = body[:-2]
    elif body.endswith(("\n", "\r")):
        body = body[:-1]
    return body


def validate_names(parts: dict[str, str]) -> None:
    slug = parts["name problem"]
    if not _SLUG.fullmatch(slug):
        raise ValueError(
            "Phần 'name problem' chỉ được chứa chữ thường a-z, chữ số 0-9 "
            "và dấu '-'; không được có dấu cách. "
            "Công cụ không tự đổi tên. Polygon sẽ kiểm tra thêm khi tạo bài."
        )
    if any(character in parts["name"] for character in "\r\n\u2028\u2029"):
        raise ValueError("Phần 'name' phải là tên hiển thị trên một dòng.")


def parse_text(text: str) -> dict[str, str]:
    """Return canonical section keys (including the user's spelling ``lengend``).

    BOM, empty separator lines at section boundaries, and an unambiguous single
    outer code fence are structural. Whitespace within content, including CRLF,
    indentation, trailing spaces, backslashes and Unicode, is preserved.
    """
    if text.startswith("\ufeff"):
        text = text[1:]
    markers = list(_MARKER.finditer(text))
    if not markers:
        raise ValueError("Không tìm thấy marker <<<PART: ...>>> nào.")
    marker_offsets = {match.start() for match in markers}
    for approximate in _MARKER_LIKE.finditer(text):
        if approximate.start() not in marker_offsets:
            raise ValueError(
                f"Marker không đúng định dạng: {approximate.group(0)!r}."
            )
    if text[: markers[0].start()].strip():
        raise ValueError("Có nội dung nằm trước marker đầu tiên.")

    parts: dict[str, str] = {}
    for position, match in enumerate(markers):
        raw_name = match.group(1)
        name = "lengend" if raw_name == "legend" else raw_name
        if name not in PARTS:
            raise ValueError(f"Phần không được hỗ trợ: {raw_name!r}.")
        if name in parts:
            raise ValueError(
                f"Trùng phần {name!r}; không được dùng đồng thời legend và lengend."
            )
        end = markers[position + 1].start() if position + 1 < len(markers) else len(text)
        value = _unwrap_fence(_boundaries(text[match.end() : end]))
        if name == "note" and not value.strip():
            value = ""
        if name != "note" and not value.strip():
            raise ValueError(f"Phần {name!r} không được để trống.")
        parts[name] = value
    missing = [name for name in PARTS if name not in parts]
    if missing:
        raise ValueError("Thiếu phần: " + ", ".join(missing) + ".")
    validate_names(parts)
    return parts


def parse_problem(path: str | Path) -> dict[str, str]:
    path = Path(path)
    if path.is_dir():
        return parse_directory(path)
    # read_text() defaults to universal-newline translation, which would alter
    # C++/LaTeX text on Windows. Decode bytes directly instead.
    return parse_text(_decode_file(path))
