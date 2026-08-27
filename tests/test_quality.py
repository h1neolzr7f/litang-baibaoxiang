from pathlib import Path

from PIL import Image

from app.quality import quality_signature, same_quality, save_signature
from app.upscale import discover_realcugan, upscale_best, upscale_status


def test_signature_changes_with_effect_settings() -> None:
    base = {
        "upscale": {"enabled": True, "scale": 2, "engine": "auto", "model": "models-pro", "noise": "conservative"},
        "mosaic": {"enabled": True, "method": "像素", "intensity": 36, "parts": ["欧金金"], "dilate": 18},
        "metadata": {"enabled": True},
    }
    other = {
        **base,
        "mosaic": {**base["mosaic"], "intensity": 48},
    }
    assert quality_signature(base) != quality_signature(other)


def test_signature_store(tmp_path: Path) -> None:
    dest = tmp_path / "a.png"
    Image.new("RGB", (4, 4), (1, 2, 3)).save(dest)
    rec = tmp_path / "rec"
    save_signature(rec, dest, "abc")
    assert same_quality(rec, dest, "abc")
    assert not same_quality(rec, dest, "zzz")


def test_realcugan_or_lanczos_fallback(tmp_path: Path) -> None:
    src = tmp_path / "in.png"
    dest = tmp_path / "out.png"
    Image.new("RGB", (24, 16), (90, 20, 40)).save(src)
    path, engine = upscale_best(
        src,
        dest,
        2,
        {"upscale": {"engine": "lanczos"}, "anr_root": ""},
    )
    assert engine == "lanczos"
    with Image.open(path) as img:
        assert img.size == (48, 32)
    status = upscale_status({})
    if discover_realcugan():
        assert status["ok"]
        ai_dest = tmp_path / "ai.png"
        out, name = upscale_best(
            src,
            ai_dest,
            2,
            {"upscale": {"engine": "auto", "model": "models-pro", "noise": "conservative"}},
        )
        assert name in {"realcugan", "lanczos"}
        with Image.open(out) as img:
            assert img.size[0] >= 48
