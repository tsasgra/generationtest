"""Decode by content and prepare temporary PNGs without modifying originals."""
from __future__ import annotations

from dataclasses import dataclass
import io
from pathlib import Path
import re
import warnings


class ImageInputError(ValueError):
    """An input cannot be safely decoded or uploaded."""


@dataclass(frozen=True)
class PreparedImage:
    source: Path
    upload: Path
    note: str


def collect_images(folder: Path, recursive: bool = False) -> list[Path]:
    if not folder.is_dir():
        raise ImageInputError(f"Không tìm thấy thư mục ảnh: {folder}")
    paths = folder.rglob("*") if recursive else folder.iterdir()
    files = sorted(
        (p for p in paths if p.is_file()
         and not any(part.startswith(".") for part in p.relative_to(folder).parts)
         and p.name.casefold() not in {"thumbs.db", "desktop.ini"}),
        key=lambda p: p.relative_to(folder).as_posix().casefold(),
    )
    if not files:
        raise ImageInputError(f"Thư mục chưa có ảnh. Hãy đặt ảnh vào: {folder}")
    return files


def _decode(source: Path):
    from PIL import Image, UnidentifiedImageError

    # SVG needs a renderer rather than a raster decoder. Detect the contents,
    # including an XML declaration, instead of relying on the filename extension.
    with source.open("rb") as stream:
        prefix = stream.read(8192)
    if re.search(rb"<svg(?:\s|>)", prefix, re.IGNORECASE):
        import resvg_py

        # Do not give the renderer a base directory for external image resources.
        png = resvg_py.svg_to_bytes(svg_string=source.read_text(encoding="utf-8-sig"))
        return Image.open(io.BytesIO(png)), "SVG → PNG"
    try:
        return Image.open(source), ""
    except UnidentifiedImageError:
        import rawpy

        try:
            with rawpy.imread(str(source)) as raw:
                pixels = raw.postprocess(use_camera_wb=True)
            return Image.fromarray(pixels), "RAW → PNG (màu theo camera)"
        except (rawpy.LibRawError, OSError) as exc:
            raise ImageInputError(
                f"{source.name}: file hỏng hoặc định dạng chưa được bộ giải mã hỗ trợ. "
                "Hãy xuất ảnh này sang PNG/JPEG; không thể bảo đảm mọi định dạng ảnh."
            ) from exc


def prepare_images(files: list[Path], destination: Path,
                   max_file_mb: float = 20) -> list[PreparedImage]:
    from PIL import Image, ImageOps
    from pillow_heif import register_heif_opener

    register_heif_opener()
    destination.mkdir(parents=True, exist_ok=True)
    prepared = []
    for index, source in enumerate(files, 1):
        if source.stat().st_size == 0:
            raise ImageInputError(f"{source.name}: file rỗng.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                decoded, note = _decode(source)
                with decoded:
                    source_format = decoded.format or "image"
                    frames = getattr(decoded, "n_frames", 1)
                    decoded.seek(0)
                    oriented = ImageOps.exif_transpose(decoded)
                    try:
                        alpha = "A" in oriented.getbands() or "transparency" in oriented.info
                        with oriented.convert("RGBA" if alpha else "RGB") as normalized:
                            # Drop metadata and names that could be invalid on Windows.
                            normalized.info.clear()
                            stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", source.stem)[:80]
                            target = destination / f"{index:04d}_{stem or 'image'}.png"
                            normalized.save(target, format="PNG")
                    finally:
                        if oriented is not decoded:
                            oriented.close()
                    note = note or f"{source_format} → PNG"
                    if frames > 1:
                        note += f"; chỉ dùng khung/trang đầu trong {frames} khung/trang"
            if target.stat().st_size > max_file_mb * 1024 * 1024:
                raise ImageInputError(
                    f"{source.name}: PNG vượt {max_file_mb:g} MiB. "
                    "Hãy giảm kích thước ảnh trước khi chạy lại."
                )
            prepared.append(PreparedImage(source, target, note))
        except ImageInputError:
            raise
        except Exception as exc:
            raise ImageInputError(f"Không xử lý được {source.name}: {exc}") from exc
    return prepared
