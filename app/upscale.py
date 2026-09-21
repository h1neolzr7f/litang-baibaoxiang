from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from app.config import APP_ROOT, bundled_anr_root, discover_anr_root
from app.util import ascii_runtime_dir, child_process_kwargs, path_is_ascii, wait_process, windows_short_path

MAX_OUTPUT_PIXELS = 160_000_000
_DISCOVER_CACHE: dict[str, Path | None] = {}

UPSCALE_CHOICES: list[tuple[str, str]] = [
    ("auto", "自动 · 有模型用最好的二次元超分"),
    ("realcugan-pro", "Real-CUGAN 专业 · 二次元首选"),
    ("realcugan-se", "Real-CUGAN 标准 · 更快"),
    ("realcugan-nose", "Real-CUGAN 干净 · 少涂抹"),
    ("realesrgan-anime", "Real-ESRGAN 动漫"),
    ("realesrgan-photo", "Real-ESRGAN 写实"),
    ("waifu2x", "Waifu2x 线条"),
    ("lanczos", "Lanczos 锐利（本机即可）"),
    ("bicubic", "双三次柔和（本机即可）"),
    ("lanczos-sharp", "Lanczos 清晰锐化（本机即可）"),
    ("line-enhance", "线条强化（本机即可）"),
]
UPSCALE_LABELS = [label for _key, label in UPSCALE_CHOICES]
UPSCALE_LABEL_TO_KEY = {label: key for key, label in UPSCALE_CHOICES}
UPSCALE_KEY_TO_LABEL = {key: label for key, label in UPSCALE_CHOICES}
UPSCALE_NOISE_CHOICES = ["保守细节", "强力降噪", "无降噪"]
_LOCAL_ENGINES = {"lanczos", "bicubic", "lanczos-sharp", "line-enhance"}
_GPU_ENGINES = {
    "",
    "auto",
    "realcugan",
    "realcugan-pro",
    "realcugan-se",
    "realcugan-nose",
    "realesrgan",
    "realesrgan-anime",
    "realesrgan-photo",
    "waifu2x",
}
_CHOICE_MAP = {
    "auto": {"engine": "auto", "model": "models-pro"},
    "realcugan-pro": {"engine": "realcugan", "model": "models-pro"},
    "realcugan-se": {"engine": "realcugan", "model": "models-se"},
    "realcugan-nose": {"engine": "realcugan", "model": "models-nose"},
    "realesrgan-anime": {"engine": "realesrgan", "model": "realesr-animevideov3"},
    "realesrgan-photo": {"engine": "realesrgan", "model": "realesrgan-x4plus"},
    "waifu2x": {"engine": "waifu2x", "model": "models-cunet"},
    "lanczos": {"engine": "lanczos", "model": ""},
    "bicubic": {"engine": "bicubic", "model": ""},
    "lanczos-sharp": {"engine": "lanczos-sharp", "model": ""},
    "line-enhance": {"engine": "line-enhance", "model": ""},
}


_NCNN_LOCK = threading.Lock()


def ncnn_launch_dir(exe: Path) -> tuple[Path, Path]:
    """返回 NCNN 能打开的 (可执行文件, 工作目录)。安装在中文路径时复制到英文目录再跑。"""
    folder = exe.parent
    if path_is_ascii(folder):
        return exe, folder
    short_exe = windows_short_path(exe)
    short_dir = windows_short_path(folder)
    if short_exe and short_dir and path_is_ascii(short_dir):
        return short_exe, short_dir
    stat = exe.stat()
    src_key = f"{folder.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    digest = hashlib.sha1(src_key.encode("utf-8")).hexdigest()[:12]
    cache = ascii_runtime_dir() / "ncnn" / digest
    marker = cache / ".litang-src"
    with _NCNN_LOCK:
        cached_ok = marker.is_file() and marker.read_text(encoding="utf-8", errors="replace").strip() == src_key
        cached_exe = cache / exe.name
        if not cached_ok or not cached_exe.is_file():
            if cache.exists():
                shutil.rmtree(cache, ignore_errors=True)
            shutil.copytree(folder, cache)
            marker.write_text(src_key, encoding="utf-8")
    return cache / exe.name, cache


def _unique_png(directory: Path, prefix: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=prefix, suffix=".png", dir=directory)
    os.close(fd)
    path = Path(name)
    try:
        path.unlink()
    except OSError:
        pass
    return path


def _search_roots(anr_root: str = "") -> list[Path]:
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
    unique: list[Path] = []
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def discover_binary(folder: str, names: tuple[str, ...], anr_root: str = "") -> Path | None:
    cache_key = f"{folder}|{anr_root}"
    cached = _DISCOVER_CACHE.get(cache_key)
    if isinstance(cached, Path):
        if cached.is_file():
            return cached
        _DISCOVER_CACHE.pop(cache_key, None)
    for root in _search_roots(anr_root):
        candidates = [root / "assets" / folder / name for name in names]
        candidates.extend(root / name for name in names)
        for exe in candidates:
            if exe.is_file():
                found = exe.resolve()
                _DISCOVER_CACHE[cache_key] = found
                return found
    return None


def discover_realcugan(anr_root: str = "") -> Path | None:
    return discover_binary(
        "realcugan-ncnn-vulkan",
        ("realcugan-ncnn-vulkan.exe", "realcugan-ncnn-vulkan"),
        anr_root,
    )


def discover_realesrgan(anr_root: str = "") -> Path | None:
    return discover_binary(
        "realesrgan-ncnn-vulkan",
        ("realesrgan-ncnn-vulkan.exe", "realesrgan-ncnn-vulkan"),
        anr_root,
    )


def discover_waifu2x(anr_root: str = "") -> Path | None:
    return discover_binary(
        "waifu2x-ncnn-vulkan",
        ("waifu2x-ncnn-vulkan.exe", "waifu2x-ncnn-vulkan"),
        anr_root,
    )


def _normalize(img: Image.Image) -> Image.Image:
    img = ImageOps.exif_transpose(img)
    if img.mode in {"RGBA", "LA"}:
        return img.convert("RGBA")
    if img.mode == "P":
        return img.convert("RGBA" if "transparency" in img.info else "RGB")
    return img.convert("RGB")


def _resample_filter(kind: str):
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
            img = img.resize((img.width * scale, img.height * scale), _resample_filter(kind))
        if kind == "lanczos-sharp":
            img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=85, threshold=2))
        elif kind == "line-enhance":
            img = img.filter(ImageFilter.EDGE_ENHANCE)
            img = img.filter(ImageFilter.UnsharpMask(radius=0.8, percent=110, threshold=1))
            img = ImageEnhance.Contrast(img).enhance(1.06)
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
    if engine == "realesrgan":
        if "x4plus" in model and "anime" not in model:
            return "realesrgan-photo"
        return "realesrgan-anime"
    if engine == "waifu2x":
        return "waifu2x"
    if engine in _LOCAL_ENGINES:
        return engine
    return "auto"


def apply_upscale_choice(choice: str) -> dict[str, str]:
    return dict(_CHOICE_MAP.get(choice) or _CHOICE_MAP["auto"])


def choice_uses_noise(choice: str) -> bool:
    key = choice_from_cfg(apply_upscale_choice(choice))
    return key not in _LOCAL_ENGINES and not key.startswith("realesrgan")


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


def _waifu_noise(name: str) -> int:
    key = str(name or "conservative")
    if key in {"denoise3", "denoise3x", "strong", "强力降噪"}:
        return 2
    if key in {"none", "0", "无降噪"}:
        return -1
    return 1


def _probe_pixels(source: Path, scale: int) -> None:
    with Image.open(source) as img:
        width, height = img.size
    if width * height * (max(scale, 1) ** 2) > MAX_OUTPUT_PIXELS:
        raise RuntimeError("放大后像素太多。请改成 2 倍，或先切图再处理。")


def _fit_scale(path: Path, source: Path, scale: int) -> None:
    with Image.open(source) as src, Image.open(path) as out:
        want = (src.width * scale, src.height * scale)
        if out.size == want:
            return
        img = _normalize(out)
        img = img.resize(want, _resample_filter("lanczos"))
    img.save(path, format="PNG", compress_level=1)


def _run_ncnn(exe: Path, args: list[str], source: Path, dest: Path, scale: int, cfg: dict[str, Any] | None = None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    launch_exe, cwd = ncnn_launch_dir(exe)
    io_dir = ascii_runtime_dir() / "ncnn-io"
    in_path = _unique_png(io_dir, "in-")
    out_tmp = _unique_png(io_dir, "out-")
    try:
        shutil.copyfile(source, in_path)
        proc = subprocess.Popen(
            [str(launch_exe), "-i", str(in_path), "-o", str(out_tmp), *args],
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            **child_process_kwargs(),
        )
        cancel = (cfg or {}).get("_cancel") if isinstance(cfg, dict) else None
        stdout, stderr, _code = wait_process(proc, 600, cancel)
        if not out_tmp.is_file() or out_tmp.stat().st_size <= 0:
            err = (stderr or stdout or "").strip()
            raise RuntimeError(err or f"{exe.name} 没有输出")
        shutil.copyfile(out_tmp, dest)
        _fit_scale(dest, source, scale)
        return dest
    finally:
        for junk in (in_path, out_tmp):
            try:
                junk.unlink()
            except OSError:
                pass


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
    return _run_ncnn(
        exe,
        ["-s", str(scale), "-n", str(_noise_flag(str(up.get("noise") or "conservative"))), "-m", model],
        source,
        dest,
        scale,
        cfg,
    )


def upscale_realesrgan(source: Path, dest: Path, scale: int, cfg: dict[str, Any]) -> Path:
    exe = discover_realesrgan(str((cfg or {}).get("anr_root") or ""))
    if not exe:
        raise RuntimeError("未找到 Real-ESRGAN")
    scale = max(2, min(int(scale or 2), 4))
    _probe_pixels(source, scale)
    up = cfg.get("upscale") or {}
    model = str(up.get("model") or "realesr-animevideov3")
    if model not in {"realesr-animevideov3", "realesrgan-x4plus", "realesrgan-x4plus-anime", "realesrnet-x4plus"}:
        model = "realesr-animevideov3"
    run_scale = 4 if "x4plus" in model else scale
    return _run_ncnn(exe, ["-s", str(run_scale), "-n", model], source, dest, scale, cfg)


def upscale_waifu2x(source: Path, dest: Path, scale: int, cfg: dict[str, Any]) -> Path:
    exe = discover_waifu2x(str((cfg or {}).get("anr_root") or ""))
    if not exe:
        raise RuntimeError("未找到 Waifu2x")
    scale = max(2, min(int(scale or 2), 4))
    _probe_pixels(source, scale)
    up = cfg.get("upscale") or {}
    model = str(up.get("model") or "models-cunet")
    run_scale = 2 if scale == 3 else scale
    if run_scale not in {1, 2, 4, 8, 16, 32}:
        run_scale = 2
    return _run_ncnn(
        exe,
        ["-s", str(run_scale), "-n", str(_waifu_noise(str(up.get("noise") or "conservative"))), "-m", model],
        source,
        dest,
        scale,
        cfg,
    )


def _try_ai(fn, source: Path, dest: Path, scale: int, cfg: dict[str, Any], tag: str) -> tuple[Path, str] | None:
    try:
        return fn(source, dest, scale, cfg), tag
    except Exception as exc:
        # 自动模式可以换下一个模型，但不能把「停止」和「超时」吃掉再改走 Lanczos。
        cancel = cfg.get("_cancel") if isinstance(cfg, dict) else None
        stopped = cancel is not None and getattr(cancel, "is_set", lambda: False)()
        if stopped or str(exc) in {"已停止", "处理超时"}:
            raise
        return None


def _explicit_ai(fn, source: Path, dest: Path, scale: int, cfg: dict[str, Any], tag: str) -> tuple[Path, str]:
    """手选的模型找不到时才回退；跑起来失败必须让这张图失败，不能悄悄换成 Lanczos。"""
    try:
        return fn(source, dest, scale, cfg), tag
    except Exception as exc:
        if "未找到" in str(exc):
            return upscale_lanczos(source, dest, scale), "lanczos-fallback"
        raise


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
    if engine == "realesrgan":
        return _explicit_ai(upscale_realesrgan, source, dest, scale, cfg, f"realesrgan:{model}")
    if engine == "waifu2x":
        return _explicit_ai(upscale_waifu2x, source, dest, scale, cfg, f"waifu2x:{model}")
    if engine in {"", "auto"}:
        for fn, tag in (
            (upscale_realcugan, f"realcugan:{model or 'models-pro'}"),
            (upscale_realesrgan, "realesrgan:realesr-animevideov3"),
            (upscale_waifu2x, "waifu2x:models-cunet"),
        ):
            hit = _try_ai(fn, source, dest, scale, cfg, tag)
            if hit:
                return hit
        return upscale_lanczos(source, dest, scale), "lanczos"
    if engine.startswith("realcugan"):
        return _explicit_ai(upscale_realcugan, source, dest, scale, cfg, f"realcugan:{model}")
    return upscale_lanczos(source, dest, scale), "lanczos"


def is_gpu_upscale_engine(engine: str) -> bool:
    return str(engine or "auto") in _GPU_ENGINES and str(engine) not in _LOCAL_ENGINES


def upscale_status(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    up = (cfg or {}).get("upscale") or {}
    anr_root = str((cfg or {}).get("anr_root") or "")
    choice = choice_from_cfg(up)
    cugan = discover_realcugan(anr_root)
    esrgan = discover_realesrgan(anr_root)
    waifu = discover_waifu2x(anr_root)
    found = [name for name, path in (("Real-CUGAN", cugan), ("Real-ESRGAN", esrgan), ("Waifu2x", waifu)) if path]
    extra = "、".join(found) if found else ""

    if choice in _LOCAL_ENGINES:
        labels = {
            "lanczos": "超分：Lanczos 锐利，不依赖外部模型",
            "bicubic": "超分：双三次柔和，不依赖外部模型",
            "lanczos-sharp": "超分：Lanczos 后再轻度锐化，不依赖外部模型",
            "line-enhance": "超分：放大后加强线条，不依赖外部模型",
        }
        return {"ok": True, "engine": choice, "path": "", "message": labels[choice]}
    if choice.startswith("realesrgan"):
        if esrgan:
            kind = "写实" if choice == "realesrgan-photo" else "动漫"
            return {"ok": True, "engine": "realesrgan", "path": str(esrgan), "message": f"超分：Real-ESRGAN {kind}"}
        return {"ok": False, "engine": "lanczos", "path": "", "message": "超分：未找到 Real-ESRGAN，这次会改用 Lanczos"}
    if choice == "waifu2x":
        if waifu:
            return {"ok": True, "engine": "waifu2x", "path": str(waifu), "message": "超分：Waifu2x 线条"}
        return {"ok": False, "engine": "lanczos", "path": "", "message": "超分：未找到 Waifu2x，这次会改用 Lanczos"}
    if cugan:
        if choice == "realcugan-se":
            message = "超分：Real-CUGAN 标准版（更快，适合大批量）"
        elif choice == "realcugan-nose":
            message = "超分：Real-CUGAN 干净版（少涂抹）"
        elif choice == "realcugan-pro":
            message = "超分：Real-CUGAN 专业版（二次元首选）"
        else:
            message = "超分：自动使用已找到的模型（" + extra + "）"
        return {"ok": True, "engine": "realcugan", "path": str(cugan), "message": message}
    if choice == "auto" and (esrgan or waifu):
        engine = "realesrgan" if esrgan else "waifu2x"
        path = esrgan or waifu
        return {"ok": True, "engine": engine, "path": str(path), "message": f"超分：自动使用 {extra}"}
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
        "message": "超分：未找到 AI 超分程序，自动改用 Lanczos 锐利",
    }
