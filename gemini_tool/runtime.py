"""Run the browser with another Python without changing its installed packages.

Image conversion stays in the caller's environment. The temporary manifest
passes only prepared images, their deletion safeguards and browser options.
"""
from __future__ import annotations

from dataclasses import asdict
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from .images import PreparedImage, SourceSnapshot

ROOT = Path(__file__).resolve().parent.parent
PROBE = """import importlib.metadata, json, pathlib, sys
from playwright.sync_api import sync_playwright
with sync_playwright() as playwright:
    executable = playwright.chromium.executable_path
    print(json.dumps({
        'python_executable': sys.executable,
        'playwright_version': importlib.metadata.version('playwright'),
        'chromium_executable': executable,
        'chromium_installed': pathlib.Path(executable).is_file(),
    }))
"""


class BrowserRuntimeError(RuntimeError):
    """The requested Python/browser runtime or its manifest is unusable."""


def _python_path(reference_python: Path | None) -> str:
    # Do not resolve symlinks: a venv's python often links to the base Python,
    # and resolving that link would silently select a different environment.
    return str(Path(reference_python or sys.executable).expanduser().absolute())


def probe_browser_runtime(reference_python: Path | None = None) -> dict:
    """Describe installed Playwright/Chromium without launching a browser."""
    executable = _python_path(reference_python)
    try:
        result = subprocess.run(
            [executable, "-c", PROBE], cwd=ROOT, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BrowserRuntimeError(f"Không kiểm tra được Python {executable}: {exc}") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise BrowserRuntimeError(
            f"Python {executable} không khởi tạo được Playwright. {detail}"
        )
    try:
        information = json.loads(result.stdout)
        if (not isinstance(information, dict)
                or any(not isinstance(information.get(key), str) or not information[key]
                       for key in ("python_executable", "playwright_version", "chromium_executable"))
                or type(information.get("chromium_installed")) is not bool):
            raise ValueError("thiếu thông tin runtime")
        return information
    except (ValueError, TypeError) as exc:
        raise BrowserRuntimeError(f"Python {executable} trả về thông tin runtime không hợp lệ.") from exc


def _absolute_path(value, field: str) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise BrowserRuntimeError(f"Manifest: {field} phải là đường dẫn tuyệt đối.")
    path = Path(value)
    if not path.is_absolute():
        raise BrowserRuntimeError(f"Manifest: {field} phải là đường dẫn tuyệt đối.")
    return path


def _decode_manifest(data) -> tuple[list[PreparedImage], dict]:
    """Validate before opening a browser; retain every deletion safeguard."""
    if (not isinstance(data, dict) or type(data.get("schema_version")) is not int
            or data["schema_version"] != 1):
        raise BrowserRuntimeError("Manifest không hợp lệ hoặc phiên bản chưa được hỗ trợ.")
    if not isinstance(data.get("images"), list) or not data["images"]:
        raise BrowserRuntimeError("Manifest phải có ít nhất một ảnh.")
    images = []
    for item in data["images"]:
        if (not isinstance(item, dict) or not isinstance(item.get("note"), str)
                or type(item.get("complete")) is not bool or "snapshot" not in item):
            raise BrowserRuntimeError("Manifest: thông tin ảnh không hợp lệ.")
        snapshot = item["snapshot"]
        if snapshot is not None:
            if (not isinstance(snapshot, dict)
                    or set(snapshot) != {"device", "inode", "size", "modified_ns", "digest"}
                    or any(type(snapshot[key]) is not int for key in
                           ("device", "inode", "size", "modified_ns"))
                    or any(snapshot[key] < 0 for key in ("device", "inode", "size"))
                    or not isinstance(snapshot["digest"], str)
                    or not re.fullmatch(r"[0-9a-f]{64}", snapshot["digest"])):
                raise BrowserRuntimeError("Manifest: thông tin đối chiếu ảnh gốc không hợp lệ.")
            snapshot = SourceSnapshot(**snapshot)
        images.append(PreparedImage(
            _absolute_path(item.get("source"), "source"),
            _absolute_path(item.get("upload"), "upload"),
            item["note"], snapshot, item["complete"],
        ))
    options = data.get("options")
    required = {"profile", "login_timeout", "upload_timeout", "batch_size", "prompt"}
    optional = {"keep_images", "attach_only"}
    if (not isinstance(options, dict) or not required <= options.keys()
            or options.keys() - required - optional):
        raise BrowserRuntimeError("Manifest: tùy chọn trình duyệt không hợp lệ.")
    options = dict(options)
    options["profile"] = _absolute_path(options["profile"], "profile")
    for key in ("login_timeout", "upload_timeout"):
        value = options[key]
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise BrowserRuntimeError(f"Manifest: {key} phải là số hữu hạn lớn hơn 0.")
    if type(options["batch_size"]) is not int or not 1 <= options["batch_size"] <= 10:
        raise BrowserRuntimeError("Manifest: batch_size phải từ 1 đến 10.")
    if not isinstance(options["prompt"], str) or not options["prompt"].strip():
        raise BrowserRuntimeError("Manifest: prompt không được rỗng.")
    for key in optional:
        options.setdefault(key, False)
        if type(options[key]) is not bool:
            raise BrowserRuntimeError(f"Manifest: {key} phải là boolean.")
    return images, options


def _wait_for_worker(worker) -> int:
    try:
        return worker.wait()
    except KeyboardInterrupt:
        # The worker shares our console/process group and receives Ctrl+C too.
        # subprocess.run would kill it while Playwright is still closing the
        # browser. Keep its inputs alive until it finishes that cleanup.
        print("\nĐang chờ tiến trình trình duyệt đóng. Ảnh chưa xác nhận được giữ lại.", file=sys.stderr)
        timeout = 10
        while True:
            try:
                worker.wait(timeout=timeout)
                return 130
            except subprocess.TimeoutExpired:
                print(
                    f"Tiến trình trình duyệt (PID {worker.pid}) vẫn đang chạy. "
                    "Hãy đóng cửa sổ trình duyệt của lần chạy này; script tiếp tục chờ và giữ file tạm.",
                    file=sys.stderr,
                )
                timeout = None
            except KeyboardInterrupt:
                # A second Ctrl+C also reaches the worker. Do not remove its
                # files or force-kill it before its browser has been closed.
                pass


def run_reference_browser(reference_python: Path, images: list[PreparedImage],
                          options: dict, directory: Path) -> int:
    """Run upload_images with the selected Python; retain temp files until exit."""
    manifest = {
        "schema_version": 1,
        "images": [{
            "source": str(item.source.absolute()), "upload": str(item.upload.absolute()),
            "note": item.note, "snapshot": asdict(item.snapshot) if item.snapshot else None,
            "complete": item.complete,
        } for item in images],
        "options": dict(options),
    }
    if "profile" in manifest["options"]:
        manifest["options"]["profile"] = str(Path(options["profile"]).expanduser().absolute())
    _decode_manifest(manifest)
    manifest_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix="browser-", suffix=".json",
            dir=directory, delete=False,
        ) as stream:
            manifest_path = Path(stream.name)
            json.dump(manifest, stream, ensure_ascii=False, allow_nan=False)
        with subprocess.Popen(
            [_python_path(reference_python), "-m", "gemini_tool.runtime", str(manifest_path)],
            cwd=ROOT,
        ) as worker:
            returncode = _wait_for_worker(worker)
        return returncode if returncode >= 0 else 128 - returncode
    except OSError as exc:
        raise BrowserRuntimeError(f"Không chạy được Python của nhánh Polygon: {exc}") from exc
    except KeyboardInterrupt:
        print("\nĐã nhận yêu cầu dừng. Ảnh chưa xác nhận được giữ lại.", file=sys.stderr)
        return 130
    finally:
        if manifest_path is not None:
            manifest_path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    """Internal subprocess entry point; imports no image decoder packages."""
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        print("Dùng gemini_upload.py --polygon-python để chạy trình duyệt này.", file=sys.stderr)
        return 2
    try:
        with Path(arguments[0]).open(encoding="utf-8") as stream:
            images, options = _decode_manifest(json.load(stream))
        from .browser import upload_images

        upload_images(images, **options)
        return 0
    except KeyboardInterrupt:
        print("\nĐã nhận yêu cầu dừng. Ảnh chưa xác nhận được giữ lại.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Lỗi trình duyệt Polygon: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
