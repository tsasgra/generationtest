"""Load Polygon credentials from environment or a private local .env file."""
from __future__ import annotations

import os
from pathlib import Path
from collections.abc import Mapping


NAMES = ('POLYGON_API_KEY', 'POLYGON_API_SECRET')


def load_credentials(path: Path, environ: Mapping[str, str] | None = None) -> tuple[str, str]:
    environment = os.environ if environ is None else environ
    values = {name: environment.get(name, '') for name in NAMES}
    if all(values.values()):
        return values[NAMES[0]], values[NAMES[1]]
    file_values = {}
    if path.exists():
        try:
            content = path.read_bytes().decode('utf-8-sig')
        except UnicodeError:
            raise ValueError('File .env phải là UTF-8.') from None
        for number, line in enumerate(content.splitlines(), 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('export '):
                line = line[7:].lstrip()
            name, separator, value = line.partition('=')
            if not separator:
                raise ValueError(f'.env dòng {number}: cần định dạng TEN_BIEN=gia_tri.')
            name, value = name.strip(), value.strip()
            if name not in NAMES:
                continue
            if name in file_values:
                raise ValueError(f'.env dòng {number}: trùng biến {name}.')
            if value.startswith(('"', "'")):
                if len(value) < 2 or value[-1] != value[0]:
                    raise ValueError(f'.env dòng {number}: dấu nháy chưa đóng.')
                value = value[1:-1]
            # Literal values only: never evaluate shell commands or expand variables.
            file_values[name] = value
    values = {name: values[name] or file_values.get(name, '') for name in NAMES}
    if not all(values.values()):
        raise ValueError('Thiếu POLYGON_API_KEY/POLYGON_API_SECRET. Điền file .env '
                         'cạnh polygon_upload.py hoặc đặt biến môi trường.')
    return values[NAMES[0]], values[NAMES[1]]
