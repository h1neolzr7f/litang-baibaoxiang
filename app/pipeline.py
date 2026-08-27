from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageFile, ImageOps
from PIL.PngImagePlugin import PngInfo

from app.collect import QueueItem, collect_images
from app.mosaic import MosaicNoTarget, mosaic_runtime_status, run_anr_mosaic
from app.quality import quality_signature, same_quality, save_signature
from app.upscale import upscale_best

ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = 400_000_000
ProgressCb = Callable[[dict[str, Any]], None]


@dataclass
class ProcessResult:
    ok: bool
    source: Path
    output_name: str
    final_path: Path | None = None
    steps: list[str] = field(default_factory=list)
    message: str = ""
    skipped: bool = False
    missed_mosaic: bool = False


def _normalize(img: Image.Image) -> Image.Image:
    img = ImageOps.exif_transpose(img)
    if img.mode in {"RGBA", "LA"}:
        return img.convert("RGBA")
    if img.mode == "P":
        return img.convert("RGBA" if "transparency" in img.info else "RGB")
    return img.convert("RGB")


def _strip_to(source: Path, dest: Path, note: str = "") -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as raw:
        img = _normalize(raw)
        meta = PngInfo()
        if note:
            meta.add_text("litang-baibaoxiang", note)
        img.save(dest, format="PNG", pnginfo=meta, compress_level=3)
    return dest


def _copy_as_png(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == ".png" and source.resolve() != dest.resolve():
        shutil.copyfile(source, dest)
        return
    with Image.open(source) as raw:
        _normalize(raw).save(dest, format="PNG", compress_level=3)


def process_one(
    source: Path,
    final_path: Path,
    work_dir: Path,
    cfg: dict[str, Any],
) -> ProcessResult:
    output_name = final_path.name
    upscale_cfg = cfg.get("upscale") or {}
    mosaic_cfg = cfg.get("mosaic") or {}
    meta_cfg = cfg.get("metadata") or {}
    skip_existing = bool(cfg.get("skip_existing", True))
    cleanup = bool(cfg.get("cleanup_work", True))
    record_dir = Path(cfg["_record_dir"]) if cfg.get("_record_dir") else None
    signature = quality_signature(cfg)
    steps: list[str] = []
    missed_mosaic = False

    if skip_existing and same_quality(record_dir, final_path, signature):
        return ProcessResult(
            ok=True,
            source=source,
            output_name=output_name,
            final_path=final_path,
            steps=["skip:same-quality"],
            message="同等效果成品已在，跳过",
            skipped=True,
        )

    need_upscale = bool(upscale_cfg.get("enabled", True))
    scale = max(1, min(int(upscale_cfg.get("scale") or 2), 4)) if need_upscale else 1
    need_mosaic = bool(mosaic_cfg.get("enabled"))
    need_meta = bool(meta_cfg.get("enabled", True))
    note = str(meta_cfg.get("custom_note") or "")
    tmp_final = final_path.with_name(final_path.name + ".partial")
    current = source

    try:
        if work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)
        work_dir.mkdir(parents=True, exist_ok=True)
        if tmp_final.exists():
            tmp_final.unlink()

        runtime = mosaic_runtime_status(cfg) if need_mosaic else {"ok": False}
        mosaic_ok = bool(need_mosaic and runtime.get("ok"))
        if need_mosaic and not mosaic_ok:
            steps.append("mosaic:unavailable")

        if need_upscale:
            up_path = work_dir / f"up{scale}x.png"
            _current, engine = upscale_best(current, up_path, scale, cfg)
            current = _current
            steps.append(f"upscale:{scale}x:{engine}")

        if mosaic_ok:
            try:
                current = run_anr_mosaic(current, work_dir, cfg)
                steps.append(f"mosaic:{mosaic_cfg.get('method', '像素')}")
            except MosaicNoTarget:
                steps.append("mosaic:none")
                missed_mosaic = True
            except Exception as exc:
                steps.append(f"mosaic:skip({exc})")
                missed_mosaic = True

        if need_meta:
            _strip_to(current, tmp_final, note=note)
            steps.append("metadata:clean")
        else:
            _copy_as_png(current, tmp_final)

        if not tmp_final.exists() or tmp_final.stat().st_size <= 0:
            raise RuntimeError("没有写出成品文件")
        final_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_final.replace(final_path)
        save_signature(record_dir, final_path, signature)
    except Exception:
        if tmp_final.exists():
            try:
                tmp_final.unlink()
            except OSError:
                pass
        raise
    finally:
        if cleanup:
            shutil.rmtree(work_dir, ignore_errors=True)

    return ProcessResult(
        ok=True,
        source=source,
        output_name=output_name,
        final_path=final_path,
        steps=steps,
        message="漏打，请复查" if missed_mosaic else "完成",
        missed_mosaic=missed_mosaic,
    )


def process_item(item: QueueItem, work_root: Path, cfg: dict[str, Any]) -> ProcessResult:
    if item.dest is None:
        raise RuntimeError("还没有分配成品路径")
    work_dir = work_root / (item.key.replace(":", "").replace("\\", "_").replace("/", "_")[-80:])
    result = process_one(item.source, item.dest, work_dir, cfg)
    item.steps = result.steps
    item.status = "skip" if result.skipped else ("ok" if result.ok else "fail")
    item.error = "" if result.ok else result.message
    return result


def make_session_dir(output_root: str | Path) -> Path:
    from datetime import datetime

    session = Path(output_root) / datetime.now().strftime("%Y%m%d-%H%M%S")
    session.mkdir(parents=True, exist_ok=True)
    return session


def process_batch(
    raw_paths: list[str | Path],
    cfg: dict[str, Any],
    *,
    progress: ProgressCb | None = None,
    cancel_flag: Any | None = None,
) -> dict[str, Any]:
    from app.engine import run_job

    items = [
        QueueItem(source=path, size=path.stat().st_size if path.exists() else 0, drop_root=path.parent, rel_parent="")
        for path in collect_images(list(raw_paths))
    ]
    return run_job(items, cfg, progress=progress, cancel_flag=cancel_flag)
