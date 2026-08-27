from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

APP_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = APP_ROOT / "data"
OUTPUT_ROOT = APP_ROOT / "输出"
CONFIG_PATH = DATA_DIR / "config.json"
BODY_DIR_NAMES = {"软件本体-请勿删除", "软件本体-安装文件勿删"}

DEFAULT_ANR_ROOTS = (
    os.environ.get("ANR_ROOT", ""),
    r"E:\ai批量生图\Auto-NovelAI-Refactor",
    str(Path.home() / "Desktop" / "Auto-NovelAI-Refactor"),
)

DEFAULTS: dict[str, Any] = {
    "anr_root": "",
    "anr_python": "",
    "output_mode": "folder",
    "output_root": "",
    "keep_structure": True,
    "dated_session": False,
    "skip_existing": True,
    "cleanup_work": True,
    "workers": 2,
    "upscale": {
        "enabled": True,
        "scale": 2,
        "engine": "auto",
        "model": "models-pro",
        "noise": "conservative",
    },
    "mosaic": {
        "enabled": True,
        "method": "像素",
        "intensity": 36,
        "dilate": 28,
        "sensitivity": 8,
        "parts": ["欧金金", "欧芒果", "欧派派", "欧西利"],
        "color": "#808080",
        "emoji_dir": "",
    },
    "metadata": {"enabled": True, "custom_note": ""},
    "perf": {"sec_per_mb": 0.0, "sec_per_image": 0.0, "samples": 0},
}


def package_root(app_root: Path | None = None) -> Path:
    root = Path(app_root or APP_ROOT)
    if root.name in BODY_DIR_NAMES:
        return root.parent
    return root


def default_output_root(app_root: Path | None = None) -> Path:
    return package_root(app_root) / "输出"


def _looks_like_anr(root: Path) -> bool:
    plugin = root / "plugins" / "anr_plugin_auto_mosaics"
    return (plugin / "detector.py").is_file() or (plugin / "mosaics.py").is_file()


def bundled_anr_root(app_root: Path | None = None) -> Path | None:
    root = Path(app_root or APP_ROOT)
    for candidate in (
        root / "runtime" / "anr",
        package_root(root) / "runtime" / "anr",
    ):
        if _looks_like_anr(candidate):
            return candidate.resolve()
    return None


def is_bundled_runtime(app_root: Path | None = None) -> bool:
    return bundled_anr_root(app_root) is not None


def discover_anr_root(app_root: Path | None = None) -> str:
    bundled = bundled_anr_root(app_root)
    if bundled:
        return str(bundled)
    for raw in DEFAULT_ANR_ROOTS:
        if not raw:
            continue
        root = Path(raw).expanduser()
        if _looks_like_anr(root):
            return str(root.resolve())
        nested = (
            root / "release" / "理塘魔改版肘击王_小白一键包_20260606-2145" / "软件本体-安装文件勿删"
        )
        if _looks_like_anr(nested):
            return str(nested.resolve())
    return ""


def discover_anr_python(anr_root: str = "") -> str:
    root = Path(anr_root) if anr_root else Path(discover_anr_root() or ".")
    for bundled in (
        root / "Python" / "python.exe",
        root / "python.exe",
    ):
        if bundled.is_file():
            return str(bundled.resolve())
    return ""


def _usable_output_root(raw: str) -> str:
    text = str(raw or "").strip().strip('"')
    if not text:
        return str(default_output_root())
    path = Path(text).expanduser()
    if path.exists() or path.parent.exists():
        return str(path)
    return str(default_output_root())


def load_config() -> dict[str, Any]:
    cfg = deepcopy(DEFAULTS)
    if CONFIG_PATH.is_file():
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cfg.update(raw)
        except Exception:
            pass
    for block in ("upscale", "mosaic", "metadata", "perf"):
        if not isinstance(cfg.get(block), dict):
            cfg[block] = deepcopy(DEFAULTS[block])
        else:
            merged = deepcopy(DEFAULTS[block])
            merged.update(cfg[block])
            cfg[block] = merged
    bundled = bundled_anr_root()
    if bundled:
        cfg["anr_root"] = str(bundled)
        cfg["anr_python"] = discover_anr_python(str(bundled))
    else:
        if not str(cfg.get("anr_root") or "").strip():
            cfg["anr_root"] = discover_anr_root()
        if not str(cfg.get("anr_python") or "").strip():
            cfg["anr_python"] = discover_anr_python(str(cfg.get("anr_root") or ""))
    cfg["output_root"] = _usable_output_root(str(cfg.get("output_root") or ""))
    return cfg


def _public_config(cfg: dict[str, Any]) -> dict[str, Any]:
    payload = {key: value for key, value in cfg.items() if not str(key).startswith("_")}
    if bundled_anr_root():
        payload["anr_root"] = ""
        payload["anr_python"] = ""
    return payload


def save_config(cfg: dict[str, Any]) -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(_public_config(cfg), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return cfg
