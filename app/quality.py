from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.detect_geom import box_expand_for_sensitivity


def quality_signature(cfg: dict[str, Any]) -> str:
    up = cfg.get("upscale") or {}
    mo = cfg.get("mosaic") or {}
    md = cfg.get("metadata") or {}
    sensitivity = int(mo.get("sensitivity") or 8)
    payload = {
        "v": 4,
        "up": {
            "on": bool(up.get("enabled", True)),
            "scale": int(up.get("scale") or 2),
            "engine": str(up.get("engine") or "auto"),
            "model": str(up.get("model") or "models-pro"),
            "noise": str(up.get("noise") or "conservative"),
        },
        "mo": {
            "on": bool(mo.get("enabled")),
            "method": str(mo.get("method") or "像素"),
            "intensity": int(mo.get("intensity") or 36),
            "parts": list(mo.get("parts") or []),
            "dilate": int(mo.get("dilate") or 28),
            "sensitivity": sensitivity,
            "box_expand": round(float(mo.get("box_expand") or box_expand_for_sensitivity(sensitivity)), 3),
        },
        "md": {"on": bool(md.get("enabled", True))},
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def signature_path(record_dir: Path) -> Path:
    return Path(record_dir) / "quality-signatures.json"


def load_signatures(record_dir: Path | None) -> dict[str, str]:
    if not record_dir:
        return {}
    path = signature_path(record_dir)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_signature(record_dir: Path | None, dest: Path, signature: str) -> None:
    if not record_dir:
        return
    Path(record_dir).mkdir(parents=True, exist_ok=True)
    store = load_signatures(record_dir)
    store[str(dest)] = signature
    signature_path(record_dir).write_text(
        json.dumps(store, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def same_quality(record_dir: Path | None, dest: Path, signature: str) -> bool:
    if not dest.exists() or dest.stat().st_size <= 0:
        return False
    return load_signatures(record_dir).get(str(dest)) == signature
