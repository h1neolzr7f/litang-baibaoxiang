from __future__ import annotations

from pathlib import Path
from typing import Any

from app.collect import QueueItem
from app.eta import estimate_output_bytes, estimate_seconds
from app.output import output_label, resolve_output_root
from app.util import disk_usage, format_bytes, format_duration, path_key


def build_preflight(
    items: list[QueueItem],
    cfg: dict[str, Any],
    session_dir: Path | None,
    *,
    mosaic_available: bool = False,
) -> dict[str, Any]:
    ready = [item for item in items if item.status == "pending"]
    skipped = [item for item in items if item.status == "skip"]
    total_bytes = sum(item.size for item in ready)
    cfg = {**cfg, "mosaic_available": mosaic_available}
    need_bytes = estimate_output_bytes(total_bytes, cfg)
    eta = estimate_seconds(total_bytes, len(ready), cfg)
    dest_probe = session_dir or resolve_output_root(cfg)
    if str(cfg.get("output_mode") or "folder") == "beside" and ready:
        dest_probe = ready[0].source.parent
    free, _total = disk_usage(dest_probe)
    headroom = 2 * 1024 * 1024 * 1024
    blockers: list[str] = []
    warnings: list[str] = []

    if not ready:
        blockers.append("没有待处理图片。")
    mode = str(cfg.get("output_mode") or "folder")
    if mode != "beside":
        root = resolve_output_root(cfg)
        if not str(root):
            blockers.append("还没选成品文件夹。")
        else:
            source_keys = {path_key(item.source) for item in ready}
            if path_key(root) in source_keys:
                blockers.append("成品文件夹不能是某一张原图。")
    if free < need_bytes + headroom:
        blockers.append(
            f"磁盘空间不够。大约需要 {format_bytes(need_bytes + headroom)}，"
            f"这里只剩 {format_bytes(free)}。请换一个磁盘更空的文件夹。"
        )
    up = cfg.get("upscale") or {}
    scale = int(up.get("scale") or 2) if up.get("enabled", True) else 1
    if up.get("enabled", True) and scale >= 3 and total_bytes >= 2 * 1024 * 1024 * 1024:
        warnings.append("放大 3 倍或 4 倍时，十几 GB 原图会变成非常大的成品，时间和磁盘都会明显增加。")
    if (cfg.get("mosaic") or {}).get("enabled") and not mosaic_available:
        warnings.append("打码环境不可用，这次会跳过打码，超分和清元数据照常做。")
    if skipped:
        warnings.append(f"有 {len(skipped)} 张成品已经存在，将自动跳过。")

    return {
        "count": len(ready),
        "skip_count": len(skipped),
        "total_bytes": total_bytes,
        "need_bytes": need_bytes,
        "free_bytes": free,
        "eta_sec": eta,
        "output_text": output_label(cfg, session_dir),
        "session_dir": str(session_dir) if session_dir else "",
        "blockers": blockers,
        "warnings": warnings,
        "ok": not blockers,
        "summary": (
            f"{len(ready)} 张 · {format_bytes(total_bytes)} · "
            f"预计 {format_duration(eta)} · 大约占 {format_bytes(need_bytes)}"
        ),
    }
