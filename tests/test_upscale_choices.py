from pathlib import Path

from PIL import Image

from app.upscale import (
    UPSCALE_CHOICES,
    apply_upscale_choice,
    choice_from_cfg,
    choice_uses_noise,
    label_from_noise,
    noise_from_label,
    upscale_best,
    upscale_status,
)


def _png(path: Path, size: tuple[int, int] = (10, 8)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, (90, 40, 20))
    pix = img.load()
    for x in range(size[0]):
        for y in range(size[1]):
            pix[x, y] = ((x * 18) % 255, (y * 22) % 255, (x * y * 7) % 255)
    img.save(path)


def test_choice_roundtrip_and_noise() -> None:
    assert [key for key, _label in UPSCALE_CHOICES] == [
        "auto",
        "realcugan-pro",
        "realcugan-se",
        "realcugan-nose",
        "lanczos",
        "bicubic",
        "lanczos-sharp",
    ]
    assert apply_upscale_choice("realcugan-se") == {"engine": "realcugan", "model": "models-se"}
    assert choice_from_cfg({"engine": "realcugan", "model": "models-nose"}) == "realcugan-nose"
    assert choice_from_cfg({"engine": "lanczos-sharp"}) == "lanczos-sharp"
    assert choice_uses_noise("auto")
    assert not choice_uses_noise("lanczos")
    assert noise_from_label("无降噪") == "none"
    assert label_from_noise("denoise3x") == "强力降噪"


def test_local_upscale_effects_differ(tmp_path: Path) -> None:
    src = tmp_path / "a.png"
    _png(src, (12, 10))
    sizes = {}
    pixels = {}
    for engine in ("lanczos", "bicubic", "lanczos-sharp"):
        dest = tmp_path / f"{engine}.png"
        path, used = upscale_best(
            src,
            dest,
            2,
            {"upscale": {"enabled": True, "engine": engine, "scale": 2}},
        )
        assert used == engine
        with Image.open(path) as img:
            sizes[engine] = img.size
            pixels[engine] = img.getpixel((6, 5))
    assert sizes["lanczos"] == sizes["bicubic"] == sizes["lanczos-sharp"] == (24, 20)
    assert len({pixels["lanczos"], pixels["bicubic"], pixels["lanczos-sharp"]}) >= 2


def test_status_for_local_and_missing_cugan() -> None:
    local = upscale_status({"upscale": {"engine": "bicubic"}, "anr_root": ""})
    assert local["ok"]
    assert "双三次" in local["message"]
    missing = upscale_status({"upscale": {"engine": "realcugan", "model": "models-pro"}, "anr_root": ""})
    assert not missing["ok"]
    assert "Lanczos" in missing["message"]
