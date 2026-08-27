from pathlib import Path

from PIL import Image

from app.collect import scan_images
from app.engine import run_job


def test_three_hundred_images_changeable_output(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    for i in range(300):
        folder = inbox / f"pack{i // 50}"
        folder.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (20, 16), (i % 255, 30, 90)).save(folder / f"p_{i:04d}.png")
    out = tmp_path / "我指定的成品位置"
    result = run_job(
        scan_images([inbox]),
        {
            "output_mode": "folder",
            "output_root": str(out),
            "keep_structure": True,
            "dated_session": False,
            "skip_existing": True,
            "cleanup_work": True,
            "workers": 2,
            "upscale": {"enabled": True, "scale": 2, "engine": "lanczos"},
            "mosaic": {"enabled": False},
            "metadata": {"enabled": True},
            "persist_perf": False,
            "anr_root": "",
            "anr_python": "",
        },
    )
    assert result["ok_count"] == 300
    assert result["fail_count"] == 0
    pngs = [path for path in out.rglob("*.png")]
    assert len(pngs) == 300
    assert (out / "pack0" / "p_0000.png").exists()
    with Image.open(out / "pack5" / "p_0299.png") as img:
        assert img.size == (40, 32)
