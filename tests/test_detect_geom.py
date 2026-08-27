from app.detect_geom import (
    box_expand_for_sensitivity,
    classes_for_parts,
    expand_box,
    expand_named_boxes,
    sensitivity_to_conf,
    tile_windows,
    wants_anus_assist,
)
from app.mosaic import mosaic_detect_extra
from app.quality import quality_signature


def test_sensitivity_maps_to_lower_conf() -> None:
    assert sensitivity_to_conf(1) == 0.32
    assert sensitivity_to_conf(8) == 0.11
    assert sensitivity_to_conf(10) == 0.05
    assert box_expand_for_sensitivity(8) > 0.4


def test_expand_box_grows_and_clamps() -> None:
    box = expand_box(40, 40, 60, 60, 100, 100, 0.5)
    assert box == [30, 30, 70, 70]
    edge = expand_box(0, 0, 10, 10, 20, 20, 0.8)
    assert edge[0] == 0 and edge[1] == 0
    assert edge[2] == 18 and edge[3] == 18


def test_anus_assist_extends_genital_downward() -> None:
    raw = [("pussy", 40.0, 40.0, 60.0, 60.0), ("nipple_f", 10.0, 10.0, 20.0, 20.0)]
    parts = ["欧芒果", "欧西利"]
    boxes = expand_named_boxes(raw, parts, 200, 200, 0.2, down_extra=0.5)
    assert len(boxes) == 1
    _x1, y1, _x2, y2 = boxes[0]
    assert y2 - (60 + 20 * 0.2) >= 8
    assert y1 <= 40
    assert not wants_anus_assist(["欧金金"])
    assert classes_for_parts(["欧西利"]) == []


def test_tiles_only_on_large_images() -> None:
    assert tile_windows(400, 400) == [(0, 0, 400, 400)]
    wins = tile_windows(2000, 1600)
    assert wins[0] == (0, 0, 2000, 1600)
    assert len(wins) >= 5


def test_signature_changes_with_sensitivity() -> None:
    base = {
        "upscale": {"enabled": True, "scale": 2, "engine": "auto", "model": "models-pro", "noise": "conservative"},
        "mosaic": {"enabled": True, "method": "像素", "intensity": 36, "parts": ["欧金金"], "dilate": 28, "sensitivity": 8},
        "metadata": {"enabled": True},
    }
    other = {**base, "mosaic": {**base["mosaic"], "sensitivity": 10}}
    assert quality_signature(base) != quality_signature(other)
    extra = mosaic_detect_extra(base["mosaic"])
    assert extra["conf"] == 0.11
    assert extra["tiles"] is True
