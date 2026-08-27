from __future__ import annotations

import shutil
from pathlib import Path

KEEP_PREFIXES = (
    "torch",
    "torchgen",
    "torchvision",
    "functorch",
    "ultralytics",
    "thop",
    "numpy",
    "scipy",
    "cv2",
    "opencv",
    "pil",
    "pillow",
    "customtkinter",
    "darkdetect",
    "packaging",
    "windnd",
    "yaml",
    "_yaml",
    "pyyaml",
    "requests",
    "urllib3",
    "certifi",
    "charset_normalizer",
    "idna",
    "sympy",
    "mpmath",
    "networkx",
    "fsspec",
    "jinja2",
    "markupsafe",
    "filelock",
    "pydantic",
    "annotated_types",
    "typing_inspection",
    "typing_extensions",
    "psutil",
    "tqdm",
    "colorama",
    "pip",
)

# ANR 里带的网页/表格/视频库，打码和超分都用不到
DROP_PREFIXES = (
    "gradio",
    "polars",
    "_polars",
    "imageio",
    "moviepy",
    "ffmpy",
    "pydub",
    "audioop",
    "pyarrow",
    "onnxruntime",
    "onnx",
    "ml_dtypes",
    "flatbuffers",
    "pandas",
    "pytz",
    "tzdata",
    "debugpy",
    "streamlit",
    "pydeck",
    "altair",
    "matplotlib",
    "mpl_toolkits",
    "fonttools",
    "contourpy",
    "cycler",
    "kiwisolver",
    "huggingface_hub",
    "hf_xet",
    "git",
    "gitdb",
    "smmap",
    "fastapi",
    "starlette",
    "uvicorn",
    "websockets",
    "httptools",
    "httpx",
    "httpcore",
    "ruff",
    "send2trash",
    "playsound",
    "piexif",
    "loguru",
    "orjson",
    "segment_anything",
    "watchdog",
    "narwhals",
    "openpyxl",
    "google",
    "typer",
    "rich",
    "pygments",
)


def _stem(name: str) -> str:
    text = name.lower()
    if text.endswith(".dist-info"):
        text = text[: -len(".dist-info")]
    if text.endswith(".libs"):
        text = text[: -len(".libs")]
    if text.endswith(".pth"):
        text = text[: -len(".pth")]
    return text.split("-")[0]


def should_keep_site_item(name: str) -> bool:
    if name.startswith("_") and name not in {"_yaml"}:
        if name.startswith("_polars"):
            return False
        if name in {"__pycache__", "_distutils_hack"}:
            return False
    stem = _stem(name)
    for prefix in DROP_PREFIXES:
        if stem == prefix or stem.startswith(prefix):
            return False
    for prefix in KEEP_PREFIXES:
        if stem == prefix or name.lower() == prefix or name.lower().startswith(prefix + "-"):
            return True
    if name.lower() in {"six.py", "typing_extensions.py", "filelock.py"}:
        return True
    return False


def slim_site_packages(site: Path) -> int:
    if not site.is_dir():
        return 0
    removed = 0
    for item in list(site.iterdir()):
        if should_keep_site_item(item.name):
            continue
        try:
            size = _size(item)
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            removed += size
        except OSError:
            continue
    trash = site / "__pycache__"
    if trash.is_dir():
        shutil.rmtree(trash, ignore_errors=True)
    return removed


def slim_optional_assets(anr: Path) -> int:
    removed = 0
    onnx = anr / "plugins" / "anr_plugin_auto_mosaics" / "models" / "yolo" / "censor.onnx"
    if onnx.is_file():
        removed += onnx.stat().st_size
        onnx.unlink()
    cugan = anr / "assets" / "realcugan-ncnn-vulkan"
    for name in ("models-se", "models-nose"):
        folder = cugan / name
        if folder.is_dir():
            removed += _size(folder)
            shutil.rmtree(folder)
    return removed


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return total
