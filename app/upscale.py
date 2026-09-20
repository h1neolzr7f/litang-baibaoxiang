from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageOps

from app.config import APP_ROOT, bundled_anr_root, discover_anr_root

MAX_OUTPUT_PIXELS = 160_000_000
_DISCOVER_CACHE: dict[str, Path | None] = {}

UPSCALE_CHOICES: list[tuple[str, str]] = [
    ("auto", "自动 · Real-CUGAN 专业优先"),
    ("realcugan-pro", "Real-CUGAN 专业版"),
    ("realcugan-se", "Real-CUGAN 标准版"),
    ("realcugan-nose", "Real-CUGAN 干净版"),
    ("lanczos", "Lanczos 锐利（本机即可）"),
    ("bicubic", "双三次柔和（本机即可）"),
    ("lanczos-sharp", "Lanczos 清晰锐化（本机即可）"),
]
UPSCALE_LABELS = [label for _key, label in UPSCALE_CHOICES]
UPSCALE_LABEL_TO_KEY = {label: key for key, label in UPSCALE_CHOICES}
UPSCALE_KEY_TO_LABEL = {key: label for key, label in UPSCALE_CHOICES}
UPSCALE_NOISE_CHOICES = ["保守细节", "强力降噪", "无降噪"]
_LOCAL_ENGINES = {"lanczos", "bicubic", "lanczos-sharp"}
_CHOICE_MAP = {
    "auto": {"engine": "auto", "model": "models-pro"},
    "realcugan-pro": {"engine": "realcugan", "model": "models-pro"},
    "realcugan-se": {"engine": "realcugan", "model": "models-se"},
    "realcugan-nose": {"engine": "realcugan", "model": "models-nose"},
    "lanczos": {"engine": "lanczos", "model": ""},
    "bicubic": {"engine": "bicubic", "model": ""},
    "lanczos-sharp": {"engine": "lanczos-sharp", "model": ""},
}


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
            root / "assets" / "realcugan-ncnn-vulkan" / "realcugan-ncnn-vulkan",
            root / "realcugan-ncnn-vulkan.exe",
            root / "realcugan-ncnn-vulkan",
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


def _resample_method(kind: str):
    resampling = getattr(Image, "Resampling", None)
    if kind == "bicubic":
        return resampling.BICUBIC if resampling else Image.BICUBIC
    return resampling.LANCZOS if resampling else Image.LANCZOS


def upscale_lanczos(source: Path, dest: Path, scale: int) -> Path:
    return upscale_resample(source, dest, scale, "lanczos")


def upscale_resample(source: Path, dest: Path, scale: int, kind: str = "lanczos") -> Path:
    scale = max(1, min(int(scale or 2), 4))
    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as raw:
        img = _normalize(raw)
        if scale > 1:
            img = img.resize((img.width * scale, img.height * scale), _resample_method(kind))
        if kind == "lanczos-sharp":
            img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=85, threshold=2))
        img.save(dest, format="PNG", compress_level=1)
    return dest


def choice_from_cfg(up: dict[str, Any] | None) -> str:
    up = up or {}
    engine = str(up.get("engine") or "auto")
    model = str(up.get("model") or "models-pro")
    if engine in {"", "auto"}:
        return "auto"
    if engine in {"realcugan", "realcugan-pro"}:
        if model == "models-se":
            return "realcugan-se"
        if model == "models-nose":
            return "realcugan-nose"
        return "realcugan-pro"
    if engine in _LOCAL_ENGINES:
        return engine
    return "auto"


def apply_upscale_choice(choice: str) -> dict[str, str]:
    return dict(_CHOICE_MAP.get(choice) or _CHOICE_MAP["auto"])


def choice_uses_noise(choice: str) -> bool:
    return choice_from_cfg(apply_upscale_choice(choice)) not in _LOCAL_ENGINES


def noise_from_label(label: str) -> str:
    text = str(label or "")
    if "强" in text:
        return "denoise3x"
    if "无" in text:
        return "none"
    return "conservative"


def label_from_noise(value: str) -> str:
    key = str(value or "conservative")
    if key in {"denoise3", "denoise3x", "strong", "强力降噪"}:
        return "强力降噪"
    if key in {"none", "0", "无降噪"}:
        return "无降噪"
    return "保守细节"


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
    up = cfg.get("upscale") or {}
    engine = str(up.get("engine") or "auto")
    model = str(up.get("model") or "models-pro")
    if scale <= 1:
        shutil.copyfile(source, dest)
        return dest, "copy"
    if engine in _LOCAL_ENGINES:
        return upscale_resample(source, dest, scale, engine), engine
    want_ai = engine in {"", "auto", "realcugan", "realcugan-pro", "realcugan-se", "realcugan-nose"}
    if want_ai:
        try:
            return upscale_realcugan(source, dest, scale, cfg), f"realcugan:{model}"
        except Exception:
            if engine.startswith("realcugan") and engine != "auto":
                return upscale_lanczos(source, dest, scale), "lanczos-fallback"
    return upscale_lanczos(source, dest, scale), "lanczos"


def upscale_status(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    up = (cfg or {}).get("upscale") or {}
    choice = choice_from_cfg(up)
    exe = discover_realcugan(str((cfg or {}).get("anr_root") or ""))
    if choice in _LOCAL_ENGINES:
        labels = {
            "lanczos": "超分：Lanczos 锐利，不依赖外部模型",
            "bicubic": "超分：双三次柔和，不依赖外部模型",
            "lanczos-sharp": "超分：Lanczos 后再轻度锐化，不依赖外部模型",
        }
        return {"ok": True, "engine": choice, "path": "", "message": labels[choice]}
    if exe:
        if choice == "realcugan-se":
            message = "超分：Real-CUGAN 标准版（更快，适合大批量）"
        elif choice == "realcugan-nose":
            message = "超分：Real-CUGAN 干净版（少涂抹）"
        elif choice == "realcugan-pro":
            message = "超分：Real-CUGAN 专业版（二次元首选）"
        else:
            message = "超分：自动使用 Real-CUGAN 专业版"
        return {"ok": True, "engine": "realcugan", "path": str(exe), "message": message}
    if choice.startswith("realcugan"):
        return {
            "ok": False,
            "engine": "lanczos",
            "path": "",
            "message": "超分：未找到 Real-CUGAN，这次会改用 Lanczos 锐利",
        }
    return {
        "ok": False,
        "engine": "lanczos",
        "path": "",
        "message": "超分：未找到 Real-CUGAN，自动改用 Lanczos 锐利",
    }
