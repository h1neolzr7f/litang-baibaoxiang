from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def path_key(path: str | Path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def path_is_ascii(path: str | Path) -> bool:
    try:
        str(path).encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def ascii_runtime_dir() -> Path:
    """给 NCNN / OpenCV 用的纯英文工作目录。中文用户名下的 Temp 会让超分和打码直接失败。"""
    candidates: list[Path] = [Path(tempfile.gettempdir()) / "litang-baibaoxiang"]
    if os.name == "nt":
        public = os.environ.get("PUBLIC")
        if public:
            candidates.append(Path(public) / "litang-baibaoxiang")
        windir = os.environ.get("SYSTEMROOT") or os.environ.get("WINDIR")
        if windir:
            candidates.append(Path(windir) / "Temp" / "litang-baibaoxiang")
    for cand in candidates:
        if not path_is_ascii(cand):
            continue
        try:
            cand.mkdir(parents=True, exist_ok=True)
            probe = cand / ".write-test"
            probe.write_text("ok", encoding="ascii")
            probe.unlink()
            return cand
        except OSError:
            continue
    fallback = Path(tempfile.gettempdir()) / "litang-baibaoxiang"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def windows_short_path(path: Path) -> Path | None:
    if os.name != "nt":
        return None
    try:
        import ctypes

        buf = ctypes.create_unicode_buffer(32768)
        count = ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, len(buf))
        if not count:
            return None
        short = buf.value
        if short and path_is_ascii(short):
            return Path(short)
    except Exception:
        return None
    return None


def child_process_kwargs() -> dict:
    """子进程强制 UTF-8，并在 Windows 上不弹出黑色控制台。"""
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    kwargs: dict = {"env": env}
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000
    return kwargs


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
    import hashlib

    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    stem = dest.stem[:24] or "image"
    return dest.with_name(f"{stem}-{digest}.png")


def image_dialog_filetypes(os_name: str | None = None) -> list[tuple[str, str]]:
    """Tk 文件对话框的图片过滤器。Windows 用分号，其他平台用空格。"""
    name = os_name if os_name is not None else os.name
    if name == "nt":
        patterns = "*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.tif;*.tiff"
    else:
        patterns = "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"
    return [("图片", patterns), ("全部", "*.*")]


def open_in_file_manager(path: str | Path) -> None:
    """用系统文件管理器打开目录或文件，避免在非 Windows 上调用 startfile。"""
    target = str(Path(path))
    if os.name == "nt":
        os.startfile(target)  # type: ignore[attr-defined]
        return
    opener = ["open", target] if sys.platform == "darwin" else ["xdg-open", target]
    subprocess.run(opener, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
