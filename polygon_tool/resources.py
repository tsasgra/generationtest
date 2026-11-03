"""Local statement resources, kept separate from the ten text inputs."""
from pathlib import Path
import hashlib
import stat


def load_resources(directory: Path) -> dict[str, bytes]:
    def linked(path):
        return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0)
                                        & stat.FILE_ATTRIBUTE_REPARSE_POINT)

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
