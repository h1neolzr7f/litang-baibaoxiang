from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from app.collect import QueueItem, safe_stem
from app.config import OUTPUT_ROOT
from app.util import path_key, shorten_for_windows


def resolve_output_root(cfg: dict[str, Any]) -> Path:
    raw = str(cfg.get("output_root") or "").strip().strip('"')
    return Path(raw) if raw else OUTPUT_ROOT


def make_session_dir(cfg: dict[str, Any], *, now: datetime | None = None) -> Path | None:
    mode = str(cfg.get("output_mode") or "folder")
    if mode == "beside":
        return None
    root = resolve_output_root(cfg)
    override = str(cfg.get("_session_dir") or "").strip()
    if override:
        return Path(override)
    if cfg.get("dated_session", False):
        stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
        return root / stamp
    return root


def _unique_png(dest_dir: Path, stem: str, used: set[str]) -> Path:
    base = safe_stem(stem)
    name = f"{base}.png"
    index = 2
    while True:
        dest = shorten_for_windows(dest_dir / name)
        key = path_key(dest)
        if key not in used:
            used.add(key)
            return dest
        name = f"{base}_{index}.png"
        index += 1


def assign_destinations(
    items: list[QueueItem],
    cfg: dict[str, Any],
    session_dir: Path | None,
) -> list[QueueItem]:
    mode = str(cfg.get("output_mode") or "folder")
    keep = bool(cfg.get("keep_structure", True))
    used: set[str] = set()
    for item in items:
        if mode == "beside":
            dest_dir = item.source.parent / "理塘成品"
        else:
            root = session_dir or resolve_output_root(cfg)
            dest_dir = root / item.rel_parent if keep and item.rel_parent else root
        item.dest = _unique_png(dest_dir, item.source.stem, used)
    return items


def output_label(cfg: dict[str, Any], session_dir: Path | None) -> str:
    mode = str(cfg.get("output_mode") or "folder")
    if mode == "beside":
        return "每张原图旁边的「理塘成品」文件夹"
    target = session_dir or resolve_output_root(cfg)
    if mode == "mirror":
        return f"按原目录结构镜像到：{target}"
    if cfg.get("keep_structure", True):
        return f"指定文件夹（保持子目录）：{target}"
    return f"指定文件夹：{target}"
