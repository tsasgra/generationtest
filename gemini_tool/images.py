"""Decode by content and prepare temporary PNGs without modifying originals."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
from pathlib import Path
import re
import stat
import sys
import warnings

from .control import check_stop


class ImageInputError(ValueError):
    """An input cannot be safely decoded or uploaded."""


@dataclass(frozen=True)
class SourceSnapshot:
    device: int
    inode: int
    size: int
    modified_ns: int
    digest: str


@dataclass(frozen=True)
class PreparedImage:
    source: Path
    upload: Path
    note: str
    snapshot: SourceSnapshot | None = None
    complete: bool = True


def collect_images(folder: Path, recursive: bool = False, *, allow_empty: bool = False) -> list[Path]:
    if not folder.is_dir():
        raise ImageInputError(f"Không tìm thấy thư mục ảnh: {folder}")
    paths = folder.rglob("*") if recursive else folder.iterdir()
    files = sorted(
        (p for p in paths if p.is_file() and not p.is_symlink()
         and not any(parent.is_symlink() for parent in p.parents if parent != folder.parent)
         and not any(part.startswith(".") for part in p.relative_to(folder).parts)
         and p.name.casefold() not in {"thumbs.db", "desktop.ini"}),
        key=lambda p: p.relative_to(folder).as_posix().casefold(),
    )
    if not files and not allow_empty:
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
                "File hỏng hoặc định dạng chưa được bộ giải mã hỗ trợ. "
                "Hãy xuất ảnh này sang PNG/JPEG; không thể bảo đảm mọi định dạng ảnh."
            ) from exc


def _identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def snapshot_source(source: Path, target: Path) -> SourceSnapshot:
    before = source.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ImageInputError(f"{source.name}: không phải file ảnh thông thường.")
    digest = hashlib.sha256()
    with source.open("rb") as stream, target.open("wb") as copy:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            check_stop()
            digest.update(block)
            copy.write(block)
    after = source.lstat()
    if _identity(before) != _identity(after) or not stat.S_ISREG(after.st_mode):
        raise ImageInputError(f"{source.name}: file đang thay đổi; giữ lại để xử lý lần sau.")
    return SourceSnapshot(*_identity(after), digest.hexdigest())


def prepare_images(files: list[Path], destination: Path,
                   max_file_mb: float = 20, *, skip_invalid: bool = False) -> list[PreparedImage]:
    from PIL import Image, ImageOps
    from pillow_heif import register_heif_opener

    register_heif_opener()
    destination.mkdir(parents=True, exist_ok=True)
    prepared = []
    for index, source in enumerate(files, 1):
        check_stop()
        original_copy = destination / f".source-{index:04d}"
        try:
            snapshot = snapshot_source(source, original_copy)
            if snapshot.size == 0:
                raise ImageInputError(f"{source.name}: file rỗng.")
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                decoded, note = _decode(original_copy)
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
            prepared.append(PreparedImage(source, target, note, snapshot, frames == 1))
        except ImportError:
            raise
        except Exception as exc:
            error = ImageInputError(f"Không xử lý được {source.name}: {exc}")
            if not skip_invalid:
                raise error from exc
            print(f"Bỏ qua, giữ nguyên file: {error}", file=sys.stderr)
        finally:
            original_copy.unlink(missing_ok=True)
    if not prepared:
        raise ImageInputError("Không nhận diện được ảnh hợp lệ trong thư mục. Chưa mở Gemini hoặc xóa file nào.")
    return prepared


def delete_uploaded(images: list[PreparedImage]) -> list[str]:
    """Called only for a batch observed in a saved chat after reloading it.

    Never glob the input directory here: later files and changed sources do not
    belong to the confirmed upload. Check identity and bytes just before unlink.
    """
    kept = []
    for item in images:
        check_stop()
        try:
            if not item.complete:
                raise ImageInputError("chỉ tải khung/trang đầu, cần giữ bản gốc nhiều khung/trang")
            if item.snapshot is None:
                raise ImageInputError("thiếu thông tin đối chiếu ảnh gốc")
            info = item.source.lstat()
            snapshot = item.snapshot
            expected = (snapshot.device, snapshot.inode, snapshot.size, snapshot.modified_ns)
            if not stat.S_ISREG(info.st_mode) or _identity(info) != expected:
                raise ImageInputError("file đã thay đổi sau khi chuẩn bị tải")
            digest = hashlib.sha256()
            with item.source.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            latest = item.source.lstat()
            if (digest.hexdigest() != snapshot.digest or _identity(latest) != expected
                    or not stat.S_ISREG(latest.st_mode)):
                raise ImageInputError("nội dung file đã thay đổi sau khi chuẩn bị tải")
            item.source.unlink()
            print(f"Đã xóa ảnh đã gửi: {item.source.name}")
        except FileNotFoundError:
            print(f"Ảnh đã được di chuyển/xóa trước đó: {item.source.name}")
        except (OSError, ImageInputError) as exc:
            message = f"Giữ lại {item.source.name}: {exc}."
            kept.append(message)
            print(message, file=sys.stderr)
    return kept
