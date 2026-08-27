from pathlib import Path

from PIL import Image

from app.collect import scan_images
from app.config import load_config
from app.engine import run_job
from app.mosaic import mosaic_runtime_status


def test_anr_mosaic_does_not_break_pipeline(tmp_path: Path) -> None:
    cfg = load_config()
    runtime = mosaic_runtime_status(cfg)
    if not runtime.get("ok"):
        return
    src = tmp_path / "sample.png"
    Image.new("RGB", (64, 48), (180, 40, 70)).save(src)
    out = tmp_path / "out"
    result = run_job(
        scan_images([src]),
        {
            **cfg,
            "output_mode": "folder",
            "output_root": str(out),
            "keep_structure": False,
            "dated_session": False,
            "skip_existing": False,
            "persist_perf": False,
            "upscale": {"enabled": False, "scale": 2},
            "mosaic": {**cfg.get("mosaic", {}), "enabled": True},
            "metadata": {"enabled": True},
        },
    )
    assert result["fail_count"] == 0
    assert (out / "sample.png").exists()
