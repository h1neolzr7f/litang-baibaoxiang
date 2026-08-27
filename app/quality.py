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


class SignatureStore:
    """签名只读盘一次，内存比对；避免每张图都把整个 JSON 读回来。"""

    def __init__(self, record_dir: Path | None) -> None:
        self.record_dir = Path(record_dir) if record_dir else None
        self._data = load_signatures(self.record_dir)
        self._dirty = False

    def matches(self, dest: Path, signature: str) -> bool:
        if not dest.exists() or dest.stat().st_size <= 0:
            return False
        return self._data.get(str(dest)) == signature

    def put(self, dest: Path, signature: str, flush: bool = True) -> None:
        if not self.record_dir:
            return
        self._data[str(dest)] = signature
        self._dirty = True
        if flush:
            self.flush()

    def flush(self) -> None:
        if not self.record_dir or not self._dirty:
            return
        self.record_dir.mkdir(parents=True, exist_ok=True)
        signature_path(self.record_dir).write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self._dirty = False


def get_store(cfg: dict[str, Any] | None) -> SignatureStore:
    cfg = cfg or {}
    store = cfg.get("_sig_store")
    if isinstance(store, SignatureStore):
        return store
    record = Path(cfg["_record_dir"]) if cfg.get("_record_dir") else None
    store = SignatureStore(record)
    cfg["_sig_store"] = store
    return store


def save_signature(record_dir: Path | None, dest: Path, signature: str) -> None:
    SignatureStore(record_dir).put(dest, signature)


def same_quality(record_dir: Path | None, dest: Path, signature: str) -> bool:
    return SignatureStore(record_dir).matches(dest, signature)
