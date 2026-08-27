from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from app.config import APP_ROOT, bundled_anr_root, discover_anr_root

MAX_OUTPUT_PIXELS = 160_000_000
_DISCOVER_CACHE: dict[str, Path | None] = {}


def _ascii_ok(path: Path) -> bool:
    try:
        str(path).encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def discover_realcugan(anr_root: str = "") -> Path | None:
    key = str(anr_root or "")
    if key in _DISCOVER_CACHE:
        return _DISCOVER_CACHE[key]
    roots: list[Path] = []
    if anr_root:
        roots.append(Path(anr_root))
    bundled = bundled_anr_root()
    if bundled:
        roots.append(bundled)
    roots.append(APP_ROOT / "runtime" / "anr")
    found = discover_anr_root()
    if found:
        roots.append(Path(found))
    roots.append(Path(r"E:\ai批量生图\Auto-NovelAI-Refactor"))
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        for exe in (
            root / "assets" / "realcugan-ncnn-vulkan" / "realcugan-ncnn-vulkan.exe",
            root / "realcugan-ncnn-vulkan.exe",
        ):
            if exe.is_file():
                found = exe.resolve()
                _DISCOVER_CACHE[key] = found
                return found
    _DISCOVER_CACHE[key] = None
    return None


def _normalize(img: Image.Image) -> Image.Image:
    img = ImageOps.exif_transpose(img)
    if img.mode in {"RGBA", "LA"}:
        return img.convert("RGBA")
    if img.mode == "P":
        return img.convert("RGBA" if "transparency" in img.info else "RGB")
    return img.convert("RGB")


def upscale_lanczos(source: Path, dest: Path, scale: int) -> Path:
    scale = max(1, min(int(scale or 2), 4))
    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as raw:
        img = _normalize(raw)
        if scale > 1:
            resampling = getattr(Image, "Resampling", None)
            method = resampling.LANCZOS if resampling else Image.LANCZOS
            img = img.resize((img.width * scale, img.height * scale), method)
        img.save(dest, format="PNG", compress_level=1)
    return dest


def _noise_flag(name: str) -> int:
    key = str(name or "conservative")
    if key in {"denoise3", "denoise3x", "strong", "强力降噪"}:
        return 3
    if key in {"none", "0", "无降噪"}:
        return 0
    return -1


def _probe_pixels(source: Path, scale: int) -> None:
    with Image.open(source) as img:
        width, height = img.size
    if width * height * (max(scale, 1) ** 2) > MAX_OUTPUT_PIXELS:
        raise RuntimeError("放大后像素太多。请改成 2 倍，或先切图再处理。")


def upscale_realcugan(source: Path, dest: Path, scale: int, cfg: dict[str, Any]) -> Path:
    exe = discover_realcugan(str((cfg or {}).get("anr_root") or ""))
    if not exe:
        raise RuntimeError("未找到 Real-CUGAN")
    scale = max(2, min(int(scale or 2), 4))
    _probe_pixels(source, scale)
    up = cfg.get("upscale") or {}
    model = str(up.get("model") or "models-pro")
    if model not in {"models-pro", "models-se", "models-nose"}:
        model = "models-pro"
    noise = _noise_flag(str(up.get("noise") or "conservative"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    src_tmp = dest.parent / "_cugan_in.png"
    out_tmp = dest.parent / "_cugan_out.png"
    in_path = source if _ascii_ok(source) else src_tmp
    try:
        if in_path == src_tmp:
            shutil.copyfile(source, src_tmp)
        cmd = [
            str(exe),
            "-i",
            str(in_path),
            "-o",
            str(out_tmp),
            "-s",
            str(scale),
            "-n",
            str(noise),
            "-m",
            model,
        ]
        result = subprocess.run(
            cmd,
            cwd=str(exe.parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        if not out_tmp.is_file() or out_tmp.stat().st_size <= 0:
            err = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(err or "Real-CUGAN 没有输出")
        shutil.copyfile(out_tmp, dest)
        return dest
    finally:
        for junk in (src_tmp, out_tmp):
            try:
                junk.unlink()
            except OSError:
                pass


def upscale_best(source: Path, dest: Path, scale: int, cfg: dict[str, Any]) -> tuple[Path, str]:
    scale = max(1, min(int(scale or 2), 4))
    engine = str((cfg.get("upscale") or {}).get("engine") or "auto")
    if scale <= 1:
        shutil.copyfile(source, dest)
        return dest, "copy"
    want_ai = engine in {"", "auto", "realcugan", "realcugan-pro"}
    if want_ai:
        try:
            return upscale_realcugan(source, dest, scale, cfg), "realcugan"
        except Exception:
            if engine.startswith("realcugan"):
                raise
    return upscale_lanczos(source, dest, scale), "lanczos"


def upscale_status(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    exe = discover_realcugan(str((cfg or {}).get("anr_root") or ""))
    if exe:
        return {
            "ok": True,
            "engine": "realcugan",
            "path": str(exe),
            "message": "超分：Real-CUGAN 专业版（已找到，效果优先）",
        }
    return {
        "ok": False,
        "engine": "lanczos",
        "path": "",
        "message": "超分：未找到 Real-CUGAN，暂用 Lanczos",
    }
