"""Reset disposable browser/run state in place, preserving Google login files."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import stat


def ordinary_directory(path: Path) -> bool:
    if not path.is_dir() or path.is_symlink():
        return False
    return not (getattr(path.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def remove_state(path: Path) -> int:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return 0
    if path.is_symlink():
        path.unlink()
    elif getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        # Never traverse a Windows junction into another profile/directory.
        path.rmdir() if path.is_dir() else path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    return 1


def reset_browser_state(browser: Path) -> int:
    if not ordinary_directory(browser):
        return 0
    removed = 0
    for name in ("gemini-export-session.json", "DevToolsActivePort", "SingletonLock",
                 "SingletonCookie", "SingletonSocket", "lockfile", "BrowserMetrics",
                 "ShaderCache", "GrShaderCache", "GraphiteDawnCache"):
        removed += remove_state(browser / name)
    for profile in browser.iterdir():
        if profile.name != "Default" and not profile.name.startswith("Profile "):
            continue
        if not ordinary_directory(profile):
            continue
        # Keep Local State, Preferences, Secure Preferences, Cookies, Network,
        # Login Data, Web Data and account/sync databases in their original
        # locations. Moving encrypted cookies to a new profile can log out
        # Windows Chrome accounts (app-bound encryption).
        for name in ("Sessions", "Current Session", "Current Tabs", "Last Session", "Last Tabs",
                     "Session Storage", "Local Storage", "IndexedDB", "Service Worker",
                     "Cache", "Code Cache", "GPUCache", "DawnCache", "DawnGraphiteCache",
                     "DawnWebGPUCache", "WebStorage", "File System", "blob_storage",
                     "History", "History-journal", "Visited Links", "Top Sites", "Top Sites-journal"):
            removed += remove_state(profile / name)
    return removed


def remember_profile(runtime: Path, profile: Path) -> None:
    runtime.mkdir(parents=True, exist_ok=True)
    path = runtime / "profiles.json"
    roots = saved_profiles(runtime)
    roots.add(profile.resolve())
    path.write_text(json.dumps([str(root) for root in sorted(roots)]), encoding="utf-8")


def saved_profiles(runtime: Path) -> set[Path]:
    if not ordinary_directory(runtime):
        return set()
    path = runtime / "profiles.json"
    if path.is_symlink():
        return set()
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(values, list):
            return set()
        return {Path(value) for value in values if isinstance(value, str) and Path(value).is_absolute()}
    except (OSError, ValueError):
        return set()
