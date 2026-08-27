from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from app.util import path_key

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
SKIP_DIR_NAMES = {
    ".work",
    ".venv",
    "__pycache__",
    ".git",
    ".pipeline",
    "理塘成品",
    "_理塘百宝箱记录",
    "node_modules",
}
WINDOWS_BAD_CHARS = re.compile(r'[<>:"/\\|?*]+')
SESSION_DIR = re.compile(r"^\d{8}-\d{6}$")
ScanCb = Callable[[int, int], None]


@dataclass(slots=True)
class QueueItem:
    source: Path
    size: int
    drop_root: Path
    rel_parent: str
    dest: Path | None = None
    status: str = "pending"
    error: str = ""
    key: str = ""
    steps: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.key:
            self.key = path_key(self.source)


def is_image_name(name: str) -> bool:
    return Path(name).suffix.lower() in IMAGE_EXTENSIONS


def is_image(path: Path) -> bool:
    return path.is_file() and is_image_name(path.name)


def safe_stem(name: str) -> str:
    stem = WINDOWS_BAD_CHARS.sub("-", str(name or "image")).strip(" .")
    return stem or "image"


def _is_our_session(path: Path) -> bool:
    record = path / "_理塘百宝箱记录"
    return (
        (path / "任务说明.txt").is_file()
        or (path / ".litang-job.json").is_file()
        or (record / "任务说明.txt").is_file()
        or (record / ".litang-job.json").is_file()
    )


def _should_skip_dir(entry_path: str, name: str, skip_keys: set[str]) -> bool:
    if name in SKIP_DIR_NAMES:
        return True
    key = path_key(entry_path)
    if key in skip_keys:
        return True
    folder = Path(entry_path)
    if SESSION_DIR.match(name) and _is_our_session(folder):
        return True
    if _is_our_session(folder):
        return True
    return False


def _walk(root: Path, skip_keys: set[str], progress: ScanCb | None = None):
    stack = [str(root)]
    found = 0
    scanned = 0
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    scanned += 1
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if _should_skip_dir(entry.path, entry.name, skip_keys):
                                continue
                            stack.append(entry.path)
                            continue
                        if not entry.is_file(follow_symlinks=False):
                            continue
                        if not is_image_name(entry.name):
                            continue
                        size = int(entry.stat(follow_symlinks=False).st_size)
                        found += 1
                        if progress and found % 200 == 0:
                            progress(found, scanned)
                        yield Path(entry.path), size
                    except OSError:
                        continue
        except OSError:
            continue


def scan_images(
    raw_paths: Iterable[str | Path],
    *,
    skip_roots: Iterable[str | Path] | None = None,
    progress: ScanCb | None = None,
) -> list[QueueItem]:
    skip_keys = {path_key(item) for item in (skip_roots or []) if str(item).strip()}
    items: list[QueueItem] = []
    seen: set[str] = set()

    def add(source: Path, size: int, drop_root: Path) -> None:
        key = path_key(source)
        if key in seen or key in skip_keys:
            return
        try:
            rel_parent = str(source.parent.relative_to(drop_root)).replace("\\", "/")
            if rel_parent == ".":
                rel_parent = ""
        except ValueError:
            rel_parent = ""
        seen.add(key)
        items.append(
            QueueItem(source=source, size=size, drop_root=drop_root, rel_parent=rel_parent, key=key)
        )

    for raw in raw_paths:
        path = Path(str(raw).strip().strip('"'))
        if not path.exists():
            continue
        if path.is_file():
            if is_image(path):
                try:
                    add(path, path.stat().st_size, path.parent)
                except OSError:
                    continue
            continue
        if not path.is_dir():
            continue
        if path_key(path) in skip_keys:
            continue
        for source, size in _walk(path, skip_keys, progress):
            add(source, size, path)
    return items


def collect_images(
    raw_paths: list[str | Path],
    skip_roots: Iterable[str | Path] | None = None,
) -> list[Path]:
    return [item.source for item in scan_images(raw_paths, skip_roots=skip_roots)]


def assign_output_names(sources: list[Path]) -> list[tuple[Path, str]]:
    used: set[str] = set()
    assigned: list[tuple[Path, str]] = []
    for source in sources:
        base = safe_stem(source.stem)
        name = f"{base}.png"
        index = 2
        while name.lower() in used:
            name = f"{base}_{index}.png"
            index += 1
        used.add(name.lower())
        assigned.append((source, name))
    return assigned
