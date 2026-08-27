# -*- coding: utf-8 -*-
"""由 ANR 自带的 Python 调用，不要用百宝箱自己的解释器跑这个文件。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _parse_color(raw: str) -> tuple[int, int, int]:
    text = str(raw or "").strip().lstrip("#")
    if len(text) == 6:
        try:
            return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
        except ValueError:
            pass
    return (128, 128, 128)


def main() -> int:
    if len(sys.argv) < 7:
        print("ERROR: 参数不足", file=sys.stderr)
        return 1

    anr_cwd = Path(sys.argv[1]).resolve()
    source_path = sys.argv[2]
    method = sys.argv[3]
    intensity = int(sys.argv[4])
    attempts = json.loads(sys.argv[5])
    session_dir = sys.argv[6]
    extra = json.loads(sys.argv[7]) if len(sys.argv) >= 8 else {}

    sys.path.insert(0, str(anr_cwd))
    os.chdir(anr_cwd)
    Path(anr_cwd, "outputs").mkdir(parents=True, exist_ok=True)

    try:
        from plugins.anr_plugin_auto_mosaics.detector import detector
        from plugins.anr_plugin_auto_mosaics.mosaics import ImageMosaicProcessor
    except Exception as exc:
        print(f"ERROR: Failed to import ANR modules: {exc}", file=sys.stderr)
        return 1

    mask_path = ""
    last_error = ""
    for attempt_parts in attempts:
        try:
            candidate = detector(source_path, attempt_parts)
            if candidate and Path(candidate).exists():
                mask_path = str(candidate)
                break
            last_error = "ANR 未产出遮罩文件"
        except Exception as exc:
            last_error = str(exc)
            if "need at least one array to stack" not in last_error:
                print(f"ERROR: {last_error}", file=sys.stderr)
                return 1

    if not mask_path:
        print(f"ERROR: {last_error or 'ANR 未检测到可打码目标'}", file=sys.stderr)
        return 10

    try:
        processor = ImageMosaicProcessor()
        if method == "模糊":
            out = processor.blur_mosaic(
                source_path, mask_path, blur_radius=intensity, output_dir=session_dir
            )
        elif method == "线条":
            out = processor.line_mosaic(
                source_path,
                mask_path,
                line_width_range=(3, 10),
                spacing_range=(10, 15),
                output_dir=session_dir,
            )
        elif method == "纯色":
            out = processor.solid_color_mosaic(
                source_path,
                mask_path,
                color=_parse_color(extra.get("color") or "#808080"),
                output_dir=session_dir,
            )
        elif method == "表情":
            emoji_dir = Path(str(extra.get("emoji_dir") or "")).expanduser()
            if not emoji_dir.is_dir():
                emoji_dir = anr_cwd / "plugins" / "anr_plugin_auto_mosaics" / "emoji"
            emoji_paths = [str(path) for path in emoji_dir.iterdir() if path.is_file()] if emoji_dir.is_dir() else []
            if emoji_paths:
                out = processor.emoji_mosaic(
                    source_path, mask_path, emoji_paths, output_dir=session_dir
                )
            else:
                print("WARNING: 没有表情素材，改用像素打码", file=sys.stderr)
                out = processor.pixel_mosaic(
                    source_path, mask_path, pixel_size=intensity, output_dir=session_dir
                )
        else:
            out = processor.pixel_mosaic(
                source_path, mask_path, pixel_size=intensity, output_dir=session_dir
            )
        if not out or not Path(out).exists():
            print("ERROR: ANR 打码未产出文件", file=sys.stderr)
            return 2
        print(f"SUCCESS: {out}")
        return 0
    except Exception as exc:
        print(f"ERROR: Image processing failed: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
