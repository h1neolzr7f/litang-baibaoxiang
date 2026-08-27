from __future__ import annotations

PART_TO_CLASS = {
    "欧金金": "penis",
    "欧芒果": "pussy",
    "欧派派": "nipple_f",
}
GENITAL_CLASSES = {"penis", "pussy"}


def classes_for_parts(parts: list[str]) -> list[str]:
    return [PART_TO_CLASS[name] for name in parts if name in PART_TO_CLASS]


def wants_anus_assist(parts: list[str]) -> bool:
    return "欧西利" in (parts or [])


def box_expand_for_sensitivity(level: int) -> float:
    level = max(1, min(int(level or 8), 10))
    return round(0.28 + level * 0.018, 3)


def expand_named_boxes(
    raw_boxes: list[tuple[str, float, float, float, float]],
    parts: list[str],
    width: int,
    height: int,
    ratio: float,
    down_extra: float = 0.42,
) -> list[list[int]]:
    wanted = set(classes_for_parts(parts))
    anus = wants_anus_assist(parts)
    out: list[list[int]] = []
    for name, x1, y1, x2, y2 in raw_boxes:
        if wanted and name not in wanted:
            continue
        extra = down_extra if anus and name in GENITAL_CLASSES else 0.0
        out.append(expand_box(x1, y1, x2, y2, width, height, ratio, down_extra=extra))
    return out


def expand_box(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    width: int,
    height: int,
    ratio: float,
    down_extra: float = 0.0,
) -> list[int]:
    box_w = max(1.0, x2 - x1)
    box_h = max(1.0, y2 - y1)
    x1 = x1 - box_w * ratio
    y1 = y1 - box_h * ratio
    x2 = x2 + box_w * ratio
    y2 = y2 + box_h * (ratio + max(0.0, down_extra))
    return [
        max(0, int(x1)),
        max(0, int(y1)),
        min(width, int(x2)),
        min(height, int(y2)),
    ]


def tile_windows(width: int, height: int, min_side: int = 900) -> list[tuple[int, int, int, int]]:
    windows = [(0, 0, width, height)]
    if min(width, height) < min_side:
        return windows
    overlap = 0.28
    tile_w = int(width * (0.5 + overlap / 2))
    tile_h = int(height * (0.5 + overlap / 2))
    xs = [0, max(0, width - tile_w)]
    ys = [0, max(0, height - tile_h)]
    for y in ys:
        for x in xs:
            windows.append((x, y, min(width, x + tile_w), min(height, y + tile_h)))
    uniq = []
    seen = set()
    for win in windows:
        if win not in seen:
            seen.add(win)
            uniq.append(win)
    return uniq


def sensitivity_to_conf(level: int) -> float:
    level = max(1, min(int(level or 8), 10))
    return round(0.32 - (level - 1) * 0.03, 3)
