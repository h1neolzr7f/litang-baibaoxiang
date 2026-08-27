from __future__ import annotations

import os
import shutil
from pathlib import Path


def path_key(path: str | Path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def format_bytes(size: int | float) -> str:
    value = float(max(0, size))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "计算中"
    if seconds < 0:
        seconds = 0
    total = int(round(seconds))
    if total < 60:
        return f"{total} 秒"
    minutes, sec = divmod(total, 60)
    if minutes < 60:
        return f"{minutes} 分 {sec} 秒" if sec else f"{minutes} 分钟"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} 小时 {minutes} 分"
    days, hours = divmod(hours, 24)
    return f"{days} 天 {hours} 小时"


def disk_usage(path: str | Path) -> tuple[int, int]:
    target = Path(path)
    probe = target if target.exists() else target.parent
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    usage = shutil.disk_usage(probe if probe.exists() else os.path.abspath(os.sep))
    return int(usage.free), int(usage.total)


def prevent_sleep() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    except Exception:
        pass


def allow_sleep() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
    except Exception:
        pass


def shorten_for_windows(dest: Path) -> Path:
    text = str(dest)
    if len(text) <= 240:
        return dest
    digest = abs(hash(text)) % 10_000_000
    stem = dest.stem[:24] or "image"
    return dest.with_name(f"{stem}-{digest}.png")
