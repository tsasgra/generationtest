"""Local statement resources, kept separate from the ten text inputs."""
from pathlib import Path
import hashlib
import stat


def linked(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0)
                                    & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def load_resources(directory: Path) -> dict[str, bytes]:
    if directory.is_symlink() or (directory.exists() and linked(directory)):
        raise ValueError(f'Resource không được là thư mục liên kết: {directory}')
    if not directory.exists():
        return {}
    if not directory.is_dir():
        raise ValueError(f'Resource phải là thư mục: {directory}')
    result, names = {}, set()
    for path in sorted(directory.iterdir()):
        if path.name == '.gitkeep':
            continue
        if linked(path) or not path.is_file():
            raise ValueError(f'Đặt file trực tiếp trong resource/, không dùng thư mục con/liên kết: {path.name}')
        if any(ord(c) < 32 or c in '/\\' for c in path.name):
            raise ValueError(f'Tên resource không hợp lệ: {path.name!r}')
        if path.name.casefold() in names:
            raise ValueError(f'Tên resource trùng khi dùng trên Windows: {path.name}')
        names.add(path.name.casefold())
        result[path.name] = path.read_bytes()
    return result


def resource_manifest(resources: dict[str, bytes]) -> dict[str, str]:
    return {name: hashlib.sha256(data).hexdigest() for name, data in resources.items()}


def remove_uploaded_resource(directory: Path, name: str, expected: str,
                             *, protected: set[Path], input_directory: Path) -> str:
    """Delete only an unchanged uploaded file; never follow resource links."""
    if name.casefold() in ('.', '..', '.gitkeep', '.env') or '/' in name or '\\' in name:
        return 'kept'
    if directory.is_symlink() or (directory.exists() and linked(directory)):
        raise ValueError('Thư mục resource đã thành liên kết; không xóa tài nguyên.')
    path = directory / name
    if not path.exists() and not path.is_symlink():
        return 'missing'
    if linked(path) or not path.is_file():
        return 'kept'
    resolved = path.resolve()
    if resolved in protected or resolved.is_relative_to(input_directory.resolve()):
        return 'kept'
    before = path.stat()
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        return 'kept'
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        return 'kept'
    path.unlink()
    return 'removed'
