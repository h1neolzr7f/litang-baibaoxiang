from pathlib import Path

from PIL import Image

from app.collect import scan_images
from app.eta import EtaEstimator, estimate_output_bytes
from app.output import assign_destinations, make_session_dir
from app.preflight import build_preflight


def _png(path: Path, size: tuple[int, int] = (8, 8)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (12, 24, 36)).save(path)


def test_output_modes(tmp_path: Path) -> None:
    src = tmp_path / "lib" / "role" / "a.png"
    _png(src)
    items = scan_images([tmp_path / "lib"])
    assign_destinations(items, {"output_mode": "beside"}, None)
    assert items[0].dest == src.parent / "理塘成品" / "a.png"

    items = scan_images([tmp_path / "lib"])
    dest = tmp_path / "mirror"
    assign_destinations(items, {"output_mode": "mirror", "output_root": str(dest), "keep_structure": True}, dest)
    assert items[0].dest == dest / "role" / "a.png"


def test_dated_session_override(tmp_path: Path) -> None:
    cfg = {"output_mode": "folder", "output_root": str(tmp_path / "out"), "dated_session": True}
    first = make_session_dir(cfg)
    assert first is not None and first.parent == tmp_path / "out"
    cfg["_session_dir"] = str(tmp_path / "out" / "fixed")
    assert make_session_dir(cfg) == tmp_path / "out" / "fixed"


def test_eta_and_preflight(tmp_path: Path) -> None:
    eta = EtaEstimator()
    assert eta.remaining(10, 2) is None
    eta.update(2 * 1024 * 1024, 2.0)
    remain = eta.remaining(2 * 1024 * 1024, 1)
    assert remain is not None and 0.5 < remain < 4

    src = tmp_path / "a.png"
    _png(src)
    items = scan_images([src])
    assign_destinations(items, {"output_mode": "folder", "output_root": str(tmp_path / "out")}, tmp_path / "out")
    pre = build_preflight(
        items,
        {
            "output_mode": "folder",
            "output_root": str(tmp_path / "out"),
            "upscale": {"enabled": True, "scale": 2},
            "mosaic": {"enabled": False},
            "metadata": {"enabled": True},
        },
        tmp_path / "out",
    )
    assert pre["ok"]
    assert pre["count"] == 1
    assert estimate_output_bytes(10_000_000, {"upscale": {"enabled": True, "scale": 2}}) > 10_000_000
