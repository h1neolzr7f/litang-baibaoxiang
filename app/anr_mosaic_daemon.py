# -*- coding: utf-8 -*-
"""ANR 打码常驻进程：模型只加载一次。由 ANR 自带 Python 启动。"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


_APP_DIR = Path(__file__).resolve().parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

from detect_geom import (  # noqa: E402
    box_expand_for_sensitivity,
    expand_named_boxes,
    sensitivity_to_conf,
    tile_windows,
)


def _parse_color(raw: str) -> tuple[int, int, int]:
    text = str(raw or "").strip().lstrip("#")
    if len(text) == 6:
        try:
            return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
        except ValueError:
            pass
    return (128, 128, 128)


def _needs_ascii_copy(path: Path) -> bool:
    try:
        str(path).encode("ascii")
        return False
    except UnicodeEncodeError:
        return True


def _work_dir(session_dir: str) -> Path:
    raw = Path(str(session_dir or "")).expanduser()
    if raw.is_dir() and not _needs_ascii_copy(raw):
        dest = raw / "_detect_tmp"
        dest.mkdir(parents=True, exist_ok=True)
        return dest
    dest = Path(tempfile.gettempdir()) / "litang-detect"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def dilate_mask(mask_path: str, pixels: int) -> str:
    pixels = max(0, min(int(pixels or 0), 64))
    if pixels <= 0:
        return mask_path
    try:
        import numpy as np
        from PIL import Image
        from scipy import ndimage
    except Exception:
        return mask_path
    path = Path(mask_path)
    with Image.open(path) as img:
        arr = np.array(img.convert("L"))
    grown = ndimage.binary_dilation(arr > 180, iterations=pixels)
    Image.fromarray((grown.astype("uint8") * 255)).save(path)
    return mask_path


def apply_mosaic(source_path: str, mask_path: str, method: str, intensity: int, session_dir: str, extra: dict, anr_cwd: Path) -> str:
    from plugins.anr_plugin_auto_mosaics.mosaics import ImageMosaicProcessor

    processor = ImageMosaicProcessor()
    if method == "模糊":
        out = processor.blur_mosaic(source_path, mask_path, blur_radius=intensity, output_dir=session_dir)
    elif method == "线条":
        out = processor.line_mosaic(
            source_path,
            mask_path,
            line_width_range=(4, 12),
            spacing_range=(8, 14),
            output_dir=session_dir,
        )
    elif method == "纯色":
        out = processor.solid_color_mosaic(
            source_path,
            mask_path,
            color=_parse_color((extra or {}).get("color") or "#808080"),
            output_dir=session_dir,
        )
    elif method == "表情":
        emoji_dir = Path(str((extra or {}).get("emoji_dir") or "")).expanduser()
        if not emoji_dir.is_dir():
            emoji_dir = anr_cwd / "plugins" / "anr_plugin_auto_mosaics" / "emoji"
        emoji_paths = [str(path) for path in emoji_dir.iterdir() if path.is_file()] if emoji_dir.is_dir() else []
        if emoji_paths:
            out = processor.emoji_mosaic(source_path, mask_path, emoji_paths, output_dir=session_dir)
        else:
            out = processor.pixel_mosaic(source_path, mask_path, pixel_size=intensity, output_dir=session_dir)
    else:
        out = processor.pixel_mosaic(source_path, mask_path, pixel_size=intensity, output_dir=session_dir)
    if not out or not Path(out).exists():
        raise RuntimeError("ANR 打码未产出文件")
    return str(out)


def _parse_yolo_results(results, ox: float = 0.0, oy: float = 0.0) -> list[tuple[str, float, float, float, float]]:
    found: list[tuple[str, float, float, float, float]] = []
    for result in results or []:
        names = getattr(result, "names", None) or {}
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            continue
        for box in boxes:
            cls_raw = box.cls[0]
            cls_id = int(cls_raw.item()) if hasattr(cls_raw, "item") else int(cls_raw)
            name = names.get(cls_id, str(cls_id))
            xyxy = box.xyxy[0]
            vals = xyxy.tolist() if hasattr(xyxy, "tolist") else list(xyxy)
            x1, y1, x2, y2 = [float(v) for v in vals[:4]]
            found.append((str(name), x1 + ox, y1 + oy, x2 + ox, y2 + oy))
    return found


def _yolo_predict(model, source, conf: float, imgsz: int, augment: bool):
    if hasattr(source, "shape"):
        import numpy as np

        payload = np.ascontiguousarray(source)
    else:
        payload = str(source)
    kwargs = {
        "source": payload,
        "conf": float(conf),
        "imgsz": int(imgsz),
        "iou": 0.45,
        "max_det": 200,
        "verbose": False,
        "augment": bool(augment),
    }
    try:
        return model.predict(**kwargs)
    except Exception:
        if not augment:
            raise
        kwargs["augment"] = False
        return model.predict(**kwargs)


def _load_rgb_array(source: Path):
    import numpy as np
    from PIL import Image

    with Image.open(source) as raw:
        img = raw.convert("RGB")
        width, height = img.size
        return width, height, np.asarray(img)


def _enhance_rgb(arr):
    import numpy as np
    from PIL import Image, ImageEnhance, ImageOps

    img = Image.fromarray(arr)
    img = ImageOps.autocontrast(img, cutoff=1)
    img = ImageEnhance.Contrast(img).enhance(1.18)
    img = ImageEnhance.Sharpness(img).enhance(1.22)
    return np.asarray(img)


def collect_strong_boxes(model, source_path: str, extra: dict) -> list[tuple[str, float, float, float, float]]:
    extra = extra or {}
    sensitivity = int(extra.get("sensitivity") or 8)
    conf = float(extra.get("conf") or sensitivity_to_conf(sensitivity))
    conf = max(0.04, min(conf, 0.45))
    imgsz = int(extra.get("imgsz") or 1280)
    imgsz = max(640, min(imgsz, 1600))
    use_tiles = bool(extra.get("tiles", True))
    use_enhance = bool(extra.get("enhance", True))
    use_augment = bool(extra.get("augment", True))
    src = Path(source_path)
    width, height, arr = _load_rgb_array(src)
    sizes = []
    for size in (640, imgsz):
        if size not in sizes:
            sizes.append(size)
    boxes: list[tuple[str, float, float, float, float]] = []
    for size in sizes:
        boxes.extend(_parse_yolo_results(_yolo_predict(model, arr, conf, size, use_augment and size >= 960)))
    if use_enhance:
        enhanced = _enhance_rgb(arr)
        boxes.extend(_parse_yolo_results(_yolo_predict(model, enhanced, max(0.04, conf - 0.02), imgsz, False)))
    if use_tiles:
        for x1, y1, x2, y2 in tile_windows(width, height)[1:]:
            crop = arr[y1:y2, x1:x2]
            tile_size = 960 if max(x2 - x1, y2 - y1) >= 900 else 640
            boxes.extend(
                _parse_yolo_results(
                    _yolo_predict(model, crop, max(0.04, conf - 0.02), tile_size, False),
                    ox=x1,
                    oy=y1,
                )
            )
    return boxes


def write_mask(source_path: str, boxes: list[list[int]], dest: Path) -> Path:
    from PIL import Image, ImageDraw

    with Image.open(source_path) as original:
        width, height = original.size
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    for rect in boxes:
        x1, y1, x2, y2 = [int(v) for v in rect[:4]]
        draw.rectangle((min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)), fill=255)
    dest.parent.mkdir(parents=True, exist_ok=True)
    mask.save(dest)
    return dest


def mask_has_signal(mask_path: str) -> bool:
    try:
        import numpy as np
        from PIL import Image

        with Image.open(mask_path) as img:
            arr = np.array(img.convert("L"))
        return bool((arr > 180).any())
    except Exception:
        return Path(mask_path).is_file() and Path(mask_path).stat().st_size > 0


def expand_detected_boxes(
    raw_boxes: list[tuple[str, float, float, float, float]],
    parts: list[str],
    width: int,
    height: int,
    extra: dict,
) -> list[list[int]]:
    extra = extra or {}
    sensitivity = int(extra.get("sensitivity") or 8)
    ratio = float(extra.get("box_expand") or box_expand_for_sensitivity(sensitivity))
    return expand_named_boxes(raw_boxes, parts, width, height, ratio)


def _anr_detector_mask(detector, source_path: str, attempts: list) -> str:
    last_error = ""
    for attempt_parts in attempts:
        try:
            candidate = detector(source_path, attempt_parts)
            if candidate and Path(candidate).exists() and mask_has_signal(str(candidate)):
                return str(candidate)
            last_error = "ANR 未产出遮罩文件"
        except Exception as exc:
            last_error = str(exc)
            if "need at least one array to stack" not in last_error:
                raise
    if last_error:
        raise RuntimeError(last_error)
    raise RuntimeError("ANR 未检测到可打码目标")


def detect_and_mosaic(runtime: dict, req: dict, anr_cwd: Path) -> str:
    source_path = req["source"]
    attempts = req.get("attempts") or []
    extra = dict(req.get("extra") or {})
    extra["session_dir"] = str(req.get("session_dir") or extra.get("session_dir") or "")
    model = runtime.get("model")
    detector = runtime.get("detector")
    mask_path = ""
    from PIL import Image

    with Image.open(source_path) as probe:
        width, height = probe.size

    if model is not None:
        raw_boxes = collect_strong_boxes(model, source_path, extra)
        for attempt_parts in attempts:
            expanded = expand_detected_boxes(raw_boxes, attempt_parts, width, height, extra)
            if expanded:
                dest = Path(extra["session_dir"] or ".") / "litang_mask.png"
                try:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                except Exception:
                    dest = _work_dir(extra["session_dir"]) / "litang_mask.png"
                write_mask(source_path, expanded, dest)
                if mask_has_signal(str(dest)):
                    mask_path = str(dest)
                    break
    if not mask_path and detector is not None:
        mask_path = _anr_detector_mask(detector, source_path, attempts)
    if not mask_path:
        raise RuntimeError("ANR 未检测到可打码目标")
    dilate_mask(mask_path, int(extra.get("dilate") or 0))
    return apply_mosaic(
        source_path,
        mask_path,
        str(req.get("method") or "像素"),
        int(req.get("intensity") or 36),
        str(req.get("session_dir") or ""),
        extra,
        anr_cwd,
    )


def setup_anr(anr_cwd: Path) -> dict:
    sys.path.insert(0, str(anr_cwd))
    os.chdir(anr_cwd)
    Path(anr_cwd, "outputs").mkdir(parents=True, exist_ok=True)
    runtime: dict = {"model": None, "detector": None}
    yolo_path = anr_cwd / "plugins" / "anr_plugin_auto_mosaics" / "models" / "yolo" / "censor.pt"
    try:
        if yolo_path.is_file():
            from ultralytics import YOLO

            runtime["model"] = YOLO(str(yolo_path))
    except Exception:
        runtime["model"] = None
    if runtime["model"] is None:
        from plugins.anr_plugin_auto_mosaics.detector import detector

        runtime["detector"] = detector
    return runtime


def run_once(argv: list[str]) -> int:
    if len(argv) < 7:
        print("ERROR: 参数不足", file=sys.stderr)
        return 1
    anr_cwd = Path(argv[1]).resolve()
    extra = json.loads(argv[7]) if len(argv) >= 8 else {}
    try:
        runtime = setup_anr(anr_cwd)
        out = detect_and_mosaic(
            runtime,
            {
                "source": argv[2],
                "method": argv[3],
                "intensity": int(argv[4]),
                "attempts": json.loads(argv[5]),
                "session_dir": argv[6],
                "extra": extra,
            },
            anr_cwd,
        )
        print(f"LITANG:SUCCESS:{out}")
        print(f"SUCCESS: {out}")
        return 0
    except RuntimeError as exc:
        text = str(exc)
        print(f"ERROR: {text}", file=sys.stderr)
        print(f"LITANG:ERROR:{text}")
        return 10 if "未检测" in text or "未产出遮罩" in text else 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"LITANG:ERROR:{exc}")
        return 3


def serve(anr_cwd: Path) -> int:
    try:
        runtime = setup_anr(anr_cwd)
    except Exception as exc:
        print(f"LITANG:ERROR:Failed to import ANR modules: {exc}", flush=True)
        return 1
    print("LITANG:READY", flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception as exc:
            print(f"LITANG:ERROR:坏请求 {exc}", flush=True)
            continue
        if req.get("cmd") in {"quit", "exit"}:
            print("LITANG:BYE", flush=True)
            return 0
        try:
            out = detect_and_mosaic(runtime, req, anr_cwd)
            print(f"LITANG:SUCCESS:{out}", flush=True)
        except RuntimeError as exc:
            print(f"LITANG:ERROR:{exc}", flush=True)
        except Exception as exc:
            print(f"LITANG:ERROR:{exc}", flush=True)
    return 0


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--once":
        return run_once([sys.argv[0], *sys.argv[2:]])
    if len(sys.argv) < 2:
        print("ERROR: 缺少 ANR 路径", file=sys.stderr)
        return 1
    return serve(Path(sys.argv[1]).resolve())


if __name__ == "__main__":
    raise SystemExit(main())
