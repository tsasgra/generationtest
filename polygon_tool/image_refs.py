"""Find statement image references that need manual Polygon resource upload.

This is a local reminder, not a check of the server's resource collection.
Source/checker/generator text is deliberately outside this inspection.
"""
from __future__ import annotations

from collections.abc import Mapping
import re


STATEMENT_FIELDS = ("name", "lengend", "legend", "input", "output", "note")

_LATEX_IMAGE = re.compile(
    r"\\includegraphics\*?\s*(?:\[[^\]]*\]\s*)*\{([^}]+)\}",
    re.IGNORECASE,
)
_HTML_IMAGE = re.compile(
    r'''<img\b[^>]*\bsrc\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))''',
    re.IGNORECASE,
)
_MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\s*\(\s*([^\s)]+)[^)]*\)")
_MARKDOWN_REFERENCE_IMAGE = re.compile(r"!\[[^\]]+\]\s*\[[^\]]*\]")
_IMAGE_PATH = re.compile(
    r'''[^\s<>{}\[\]"']+\.(?:a?png|jpe?g|jfif|gif|webp|bmp|svg|eps|avif|heic|heif|tiff?|ico|jxl)'''
    r'''(?:[?#][^\s<>{}\[\]"']*)?(?=$|[\s<>{}\[\]"',;:!)]|\.(?:\s|$))''',
    re.IGNORECASE,
)


def _mentions_image(text: str) -> bool:
    """Inspect local text only; references need not point to an existing file.

LaTeX references may omit the extension. HTML/Markdown data URLs already carry
their image bytes, so they do not require a separate statement resource file.
"""
    if any(match.group(1).strip() for match in _LATEX_IMAGE.finditer(text)):
        return True
    if _MARKDOWN_REFERENCE_IMAGE.search(text):
        return True
    for match in _HTML_IMAGE.finditer(text):
        source = next((value for value in match.groups() if value is not None), "").strip()
        if source and not source.casefold().startswith("data:"):
            return True
    for match in _MARKDOWN_IMAGE.finditer(text):
        if not match.group(1).casefold().startswith("data:"):
            return True
    return bool(_IMAGE_PATH.search(text))


def image_reference_fields(parts: Mapping[str, str]) -> list[str]:
    """List statement fields containing image references, normalizing legend's alias."""
    fields = []
    for field in STATEMENT_FIELDS:
        if _mentions_image(parts.get(field, "")):
            canonical = "legend" if field == "lengend" else field
            if canonical not in fields:
                fields.append(canonical)
    return fields


def has_image_reference(parts: Mapping[str, str]) -> bool:
    return bool(image_reference_fields(parts))
