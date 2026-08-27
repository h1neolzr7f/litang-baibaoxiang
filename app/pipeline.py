from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageFile, ImageOps
from PIL.PngImagePlugin import PngInfo

from app.collect import QueueItem, collect_images
from app.mosaic import MosaicNoTarget, mosaic_runtime_status, run_anr_mosaic
from app.pngmeta import is_png, write_clean_png
from app.quality import get_store, quality_signature
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


@dataclass
class ProcessState:
    source: Path
    final_path: Path
    work_dir: Path
    cfg: dict[str, Any]
    current: Path
    steps: list[str]
    signature: str
    tmp_final: Path
    scale: int
    need_upscale: bool
    mosaic_ok: bool
    need_meta: bool
    note: str
    cleanup: bool
    missed_mosaic: bool = False
    result: ProcessResult | None = None


def _normalize(img: Image.Image) -> Image.Image:
    img = ImageOps.exif_transpose(img)
    if img.mode in {"RGBA", "LA"}:
        return img.convert("RGBA")
    if img.mode == "P":
        return img.convert("RGBA" if "transparency" in img.info else "RGB")
    return img.convert("RGB")


def _strip_to(source: Path, dest: Path, note: str = "") -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if is_png(source):
        try:
            return write_clean_png(source, dest, note=note)
        except Exception:
            pass
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


def _mosaic_runtime(cfg: dict[str, Any], need_mosaic: bool) -> dict[str, Any]:
    cached = cfg.get("_mosaic_runtime")
    if isinstance(cached, dict):
        return cached
    if not need_mosaic:
        return {"ok": False}
    return mosaic_runtime_status(cfg)


def start_process(source: Path, final_path: Path, work_dir: Path, cfg: dict[str, Any]) -> ProcessState:
    output_name = final_path.name
    upscale_cfg = cfg.get("upscale") or {}
    mosaic_cfg = cfg.get("mosaic") or {}
    meta_cfg = cfg.get("metadata") or {}
    skip_existing = bool(cfg.get("skip_existing", True))
    cleanup = bool(cfg.get("cleanup_work", True))
    signature = quality_signature(cfg)
    store = get_store(cfg)

    if skip_existing and store.matches(final_path, signature):
        return ProcessState(
            source=source,
            final_path=final_path,
            work_dir=work_dir,
            cfg=cfg,
            current=source,
            steps=["skip:same-quality"],
            signature=signature,
            tmp_final=final_path.with_name(final_path.name + ".partial"),
            scale=1,
            need_upscale=False,
            mosaic_ok=False,
            need_meta=False,
            note="",
            cleanup=cleanup,
            result=ProcessResult(
                ok=True,
                source=source,
                output_name=output_name,
                final_path=final_path,
                steps=["skip:same-quality"],
                message="同等效果成品已在，跳过",
                skipped=True,
            ),
        )

    need_upscale = bool(upscale_cfg.get("enabled", True))
    scale = max(1, min(int(upscale_cfg.get("scale") or 2), 4)) if need_upscale else 1
    need_mosaic = bool(mosaic_cfg.get("enabled"))
    runtime = _mosaic_runtime(cfg, need_mosaic)
    mosaic_ok = bool(need_mosaic and runtime.get("ok"))
    steps: list[str] = []
    if need_mosaic and not mosaic_ok:
        steps.append("mosaic:unavailable")

    if work_dir.exists():
        shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    tmp_final = final_path.with_name(final_path.name + ".partial")
    if tmp_final.exists():
        tmp_final.unlink()

    return ProcessState(
        source=source,
        final_path=final_path,
        work_dir=work_dir,
        cfg=cfg,
        current=source,
        steps=steps,
        signature=signature,
        tmp_final=tmp_final,
        scale=scale,
        need_upscale=need_upscale,
        mosaic_ok=mosaic_ok,
        need_meta=bool(meta_cfg.get("enabled", True)),
        note=str(meta_cfg.get("custom_note") or ""),
        cleanup=cleanup,
    )


def advance_upscale(state: ProcessState) -> ProcessState:
    if not state.need_upscale:
        return state
    up_path = state.work_dir / f"up{state.scale}x.png"
    current, engine = upscale_best(state.current, up_path, state.scale, state.cfg)
    state.current = current
    state.steps.append(f"upscale:{state.scale}x:{engine}")
    return state


def advance_mosaic(state: ProcessState) -> ProcessState:
    if not state.mosaic_ok:
        return state
    mosaic_cfg = state.cfg.get("mosaic") or {}
    try:
        state.current = run_anr_mosaic(state.current, state.work_dir, state.cfg)
        state.steps.append(f"mosaic:{mosaic_cfg.get('method', '像素')}")
    except MosaicNoTarget:
        state.steps.append("mosaic:none")
        state.missed_mosaic = True
    except Exception as exc:
        state.steps.append(f"mosaic:skip({exc})")
        state.missed_mosaic = True
    return state


def abort_process(state: ProcessState) -> None:
    if state.tmp_final.exists():
        try:
            state.tmp_final.unlink()
        except OSError:
            pass
    if state.cleanup:
        shutil.rmtree(state.work_dir, ignore_errors=True)


def finish_process(state: ProcessState) -> ProcessResult:
    try:
        if state.need_meta:
            _strip_to(state.current, state.tmp_final, note=state.note)
            state.steps.append("metadata:clean")
        else:
            _copy_as_png(state.current, state.tmp_final)

        if not state.tmp_final.exists() or state.tmp_final.stat().st_size <= 0:
            raise RuntimeError("没有写出成品文件")
        state.final_path.parent.mkdir(parents=True, exist_ok=True)
        state.tmp_final.replace(state.final_path)
        get_store(state.cfg).put(state.final_path, state.signature)
    except Exception:
        abort_process(state)
        raise
    if state.cleanup:
        shutil.rmtree(state.work_dir, ignore_errors=True)
    return ProcessResult(
        ok=True,
        source=state.source,
        output_name=state.final_path.name,
        final_path=state.final_path,
        steps=state.steps,
        message="漏打，请复查" if state.missed_mosaic else "完成",
        missed_mosaic=state.missed_mosaic,
    )


def process_one(
    source: Path,
    final_path: Path,
    work_dir: Path,
    cfg: dict[str, Any],
) -> ProcessResult:
    state = start_process(source, final_path, work_dir, cfg)
    if state.result is not None:
        return state.result
    try:
        advance_upscale(state)
        advance_mosaic(state)
        return finish_process(state)
    except Exception:
        abort_process(state)
        raise


def process_item(item: QueueItem, work_root: Path, cfg: dict[str, Any]) -> ProcessResult:
    if item.dest is None:
        raise RuntimeError("还没有分配成品路径")
    work_dir = work_root / (item.key.replace(":", "").replace("\\", "_").replace("/", "_")[-80:])
    result = process_one(item.source, item.dest, work_dir, cfg)
    item.steps = result.steps
    item.status = "skip" if result.skipped else ("ok" if result.ok else "fail")
    item.error = "" if result.ok else result.message
    return result


def item_work_dir(item: QueueItem, work_root: Path) -> Path:
    return work_root / (item.key.replace(":", "").replace("\\", "_").replace("/", "_")[-80:])


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
