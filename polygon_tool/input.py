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
MAX_PROBLEMS = 10

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


def init_batch(path: str | Path, count: int = MAX_PROBLEMS) -> None:
    """Create the standalone uploader's numbered templates without overwriting."""
    if not 1 <= count <= MAX_PROBLEMS:
        raise ValueError('Số bài phải từ 1 đến 10.')
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=False)
    for number in range(1, count + 1):
        init_directory(directory / f'problem{number}')


def numbered_directories(path: str | Path, prefix: str) -> dict[int, Path]:
    """Read imgN/problemN (also img(N)/problem(N)) in numeric order."""
    directory = Path(path)
    if not directory.exists():
        return {}
    pattern = re.compile(re.escape(prefix) + r"(?:([1-9][0-9]*)|\(([1-9][0-9]*)\))\Z")
    numbered = {}
    for entry in directory.iterdir():
        if not entry.name.lower().startswith(prefix):
            continue
        match = pattern.fullmatch(entry.name)
        if not match or not entry.is_dir() or entry.is_symlink():
            raise ValueError(f'Cần thư mục thật có tên {prefix}1…{prefix}10: {entry}.')
        index = int(match[1] or match[2])
        if index > MAX_PROBLEMS:
            raise ValueError(f'Chỉ hỗ trợ {prefix}1 đến {prefix}{MAX_PROBLEMS}.')
        if index in numbered:
            raise ValueError(f'Trùng thư mục số {index}: {numbered[index].name}, {entry.name}.')
        numbered[index] = entry
    return dict(sorted(numbered.items()))


def is_blank_template(folder: Path) -> bool:
    """Only the exact, entirely blank ten-file scaffold counts as unused."""
    entries = {entry.name: entry for entry in folder.iterdir()
               if entry.name != 'img' and not entry.name.startswith('.')}
    expected = set(PART_FILES.values())
    if 'legend.txt' in entries:
        expected.remove('lengend.txt')
        expected.add('legend.txt')
    if set(entries) != expected:
        return False
    try:
        return all(path.is_file() and not path.is_symlink() and
                   not path.read_bytes().decode('utf-8-sig').strip() for path in entries.values())
    except UnicodeError:
        return False


def discover_problems(path: str | Path, *, allow_single: bool = False) -> list[Path] | None:
    """Ignore empty/blank template slots; partial sets still fail preflight."""
    directory = Path(path)
    if allow_single and not directory.is_dir():
        return None
    numbered = numbered_directories(directory, 'problem')
    if not numbered:
        if allow_single:
            return None
        raise ValueError(f'Không tìm thấy thư mục problem1…problem10 trong {directory}.')
    if any(entry.suffix.lower() == '.txt' for entry in directory.iterdir()):
        raise ValueError('Không đặt file .txt trực tiếp trong thư mục chứa nhiều bài; chuyển vào problem1, problem2, ...')
    return [folder.resolve() for folder in numbered.values()
            if any(entry.name != 'img' and not entry.name.startswith('.') for entry in folder.iterdir())
            and not is_blank_template(folder)]


def parse_batch(paths: list[Path]) -> list[dict[str, str]]:
    """Validate every input and duplicate slug before any API request."""
    problems, names, errors = [], {}, []
    for path in paths:
        try:
            parts = parse_problem(path)
            slug = parts['name problem']
            if slug in names:
                raise ValueError(f'Tên định danh {slug!r} trùng với {names[slug]}.')
            names[slug] = path.name
            problems.append(parts)
        except (OSError, ValueError) as exc:
            errors.append(f'{path.name}: {exc}')
    if errors:
        raise ValueError('Đầu vào chưa hợp lệ:\n' + '\n'.join(errors))
    return problems


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
