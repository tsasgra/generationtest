"""Identify sample tests from Polygon's expanded Test objects, never script lines."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import re
import shlex
from typing import Any


def parse_sample_indices(value: str) -> list[int]:
    """Parse a comma-separated CLI value; indices must be positive and distinct."""
    tokens = value.split(",")
    if not tokens or any(not re.fullmatch(r"[0-9]+", item.strip()) for item in tokens):
        raise ValueError("--sample-indices cần danh sách số nguyên dương, ví dụ 1,3,7.")
    indices = [int(item) for item in tokens]
    if any(index <= 0 for index in indices) or len(set(indices)) != len(indices):
        raise ValueError("--sample-indices không được chứa số 0, số âm hoặc chỉ số trùng.")
    return sorted(indices)


def is_sample_command(command: str) -> bool:
    """Recognize an exact positional sample token or an option value equal to sample.

    Tokenizing does not execute anything. Shell redirection and comments are
    ignored; tokens such as nonsample, not_sample and sample.txt do not match.
    """
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars="><|;&")
        lexer.whitespace_split = True
        lexer.commenters = "#"
        tokens = list(lexer)
    except ValueError:
        return False
    # The first token is the executable, not a mode argument.
    for token in tokens[1:]:
        if token and all(character in "><|;&" for character in token):
            break
        if token == "sample":
            return True
        if token.startswith("-") and "=" in token and token.split("=", 1)[1] == "sample":
            return True
    return False


def detect_sample_indices(
    tests: Iterable[Mapping[str, Any]],
    explicit: Iterable[int] | str | None = None,
) -> list[int]:
    tests = list(tests)
    by_index: dict[int, Mapping[str, Any]] = {}
    for test in tests:
        index = test.get("index")
        if isinstance(index, bool) or not isinstance(index, int) or index <= 0:
            raise ValueError("Polygon trả về test không có index nguyên dương hợp lệ.")
        if index in by_index:
            raise ValueError(f"Polygon trả về test index {index} bị trùng.")
        by_index[index] = test
    if not by_index:
        raise ValueError("Polygon chưa trả về test nào sau khi lưu script.")

    if explicit is not None:
        indices = parse_sample_indices(explicit) if isinstance(explicit, str) else list(explicit)
        if any(isinstance(index, bool) or not isinstance(index, int) or index <= 0 for index in indices):
            raise ValueError("Danh sách sample chỉ được chứa chỉ số nguyên dương.")
        if len(set(indices)) != len(indices):
            raise ValueError("Danh sách sample có chỉ số trùng.")
        absent = sorted(set(indices) - by_index.keys())
        if absent:
            raise ValueError("Không có test với sample index: " + ", ".join(map(str, absent)))
    else:
        indices = [
            index
            for index, test in by_index.items()
            if not test.get("manual", False)
            and isinstance(test.get("scriptLine"), str)
            and is_sample_command(test["scriptLine"])
        ]
    if not indices:
        raise ValueError(
            "Không xác định được sample. Kiểm tra test thực tế trên Polygon rồi "
            "chạy resume với --sample-indices 1,3 (thay bằng index đúng)."
        )
    return sorted(indices)
