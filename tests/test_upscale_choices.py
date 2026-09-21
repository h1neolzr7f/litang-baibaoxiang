from pathlib import Path
import os

from PIL import Image
import pytest

from app.upscale import (
    UPSCALE_CHOICES,
    apply_upscale_choice,
    choice_from_cfg,
    choice_uses_noise,
    discover_realesrgan,
    discover_waifu2x,
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
        "realesrgan-anime",
        "realesrgan-photo",
        "waifu2x",
        "lanczos",
        "bicubic",
        "lanczos-sharp",
        "line-enhance",
    ]
    assert apply_upscale_choice("realcugan-se") == {"engine": "realcugan", "model": "models-se"}
    assert apply_upscale_choice("realesrgan-anime")["engine"] == "realesrgan"
    assert choice_from_cfg({"engine": "realcugan", "model": "models-nose"}) == "realcugan-nose"
    assert choice_from_cfg({"engine": "realesrgan", "model": "realesrgan-x4plus"}) == "realesrgan-photo"
    assert choice_from_cfg({"engine": "lanczos-sharp"}) == "lanczos-sharp"
    assert choice_uses_noise("auto")
    assert choice_uses_noise("waifu2x")
    assert not choice_uses_noise("lanczos")
    assert not choice_uses_noise("realesrgan-anime")
    assert noise_from_label("无降噪") == "none"
    assert label_from_noise("denoise3x") == "强力降噪"


def test_local_upscale_effects_differ(tmp_path: Path) -> None:
    src = tmp_path / "a.png"
    _png(src, (12, 10))
    sizes = {}
    pixels = {}
    for engine in ("lanczos", "bicubic", "lanczos-sharp", "line-enhance"):
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
    assert set(sizes.values()) == {(24, 20)}
    assert len(set(pixels.values())) >= 2


def test_explicit_model_failure_is_not_silent(tmp_path: Path, monkeypatch) -> None:
    src = tmp_path / "in.png"
    _png(src, (8, 6))

    def boom(*_args, **_kwargs):
        raise RuntimeError("vulkan device lost")

    monkeypatch.setattr("app.upscale.upscale_realesrgan", boom)
    with pytest.raises(RuntimeError, match="vulkan"):
        upscale_best(
            src,
            tmp_path / "out.png",
            2,
            {"upscale": {"engine": "realesrgan", "model": "realesr-animevideov3"}},
        )


def test_missing_explicit_model_falls_back(tmp_path: Path, monkeypatch) -> None:
    src = tmp_path / "in.png"
    _png(src, (8, 6))
    monkeypatch.setattr("app.upscale.discover_realesrgan", lambda *_args, **_kwargs: None)
    _path, used = upscale_best(
        src,
        tmp_path / "out.png",
        2,
        {"upscale": {"engine": "realesrgan", "model": "realesr-animevideov3"}},
    )
    assert used == "lanczos-fallback"


def test_ncnn_unicode_install_dir_is_relocated(tmp_path: Path) -> None:
    from app.upscale import ncnn_launch_dir
    from app.util import path_is_ascii

    folder = tmp_path / "中文目录"
    folder.mkdir()
    exe = folder / "realcugan-ncnn-vulkan"
    exe.write_bytes(b"MZ")
    (folder / "models-pro").mkdir()
    launch, cwd = ncnn_launch_dir(exe)
    assert path_is_ascii(launch)
    assert path_is_ascii(cwd)
    assert launch.is_file()
    assert (cwd / "models-pro").is_dir()


def test_status_for_local_and_missing_cugan() -> None:
    local = upscale_status({"upscale": {"engine": "bicubic"}, "anr_root": ""})
    assert local["ok"]
    assert "双三次" in local["message"]
    missing = upscale_status({"upscale": {"engine": "realcugan", "model": "models-pro"}, "anr_root": ""})
    assert not missing["ok"]
    assert "Lanczos" in missing["message"]
    missing_esr = upscale_status({"upscale": {"engine": "realesrgan", "model": "realesr-animevideov3"}, "anr_root": ""})
    assert not missing_esr["ok"]
    assert "Real-ESRGAN" in missing_esr["message"]


def _write_fake_ncnn(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import argparse\n"
        "from PIL import Image\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('-i')\n"
        "p.add_argument('-o')\n"
        "p.add_argument('-s', default='2')\n"
        "p.add_argument('-n', default='')\n"
        "p.add_argument('-m', default='')\n"
        "a, _ = p.parse_known_args()\n"
        "im = Image.open(a.i)\n"
        "scale = max(1, int(str(a.s).split('=')[-1] or 2))\n"
        "im.resize((im.width * scale, im.height * scale)).save(a.o)\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


@pytest.mark.skipif(os.name == "nt", reason="fake shebang runtime is POSIX-only; Windows uses real .exe binaries")
def test_realesrgan_and_waifu2x_with_fake_runtime(tmp_path: Path) -> None:
    src = tmp_path / "in.png"
    _png(src, (8, 6))
    esr = tmp_path / "anr" / "assets" / "realesrgan-ncnn-vulkan" / "realesrgan-ncnn-vulkan"
    wai = tmp_path / "anr" / "assets" / "waifu2x-ncnn-vulkan" / "waifu2x-ncnn-vulkan"
    _write_fake_ncnn(esr)
    _write_fake_ncnn(wai)
    assert discover_realesrgan(str(tmp_path / "anr")) == esr.resolve()
    assert discover_waifu2x(str(tmp_path / "anr")) == wai.resolve()

    dest = tmp_path / "esr.png"
    path, used = upscale_best(
        src,
        dest,
        2,
        {
            "anr_root": str(tmp_path / "anr"),
            "upscale": {"engine": "realesrgan", "model": "realesr-animevideov3", "scale": 2},
        },
    )
    assert used.startswith("realesrgan")
    with Image.open(path) as img:
        assert img.size == (16, 12)

    dest2 = tmp_path / "w2x.png"
    path, used = upscale_best(
        src,
        dest2,
        2,
        {
            "anr_root": str(tmp_path / "anr"),
            "upscale": {"engine": "waifu2x", "model": "models-cunet", "noise": "conservative", "scale": 2},
        },
    )
    assert used.startswith("waifu2x")
    with Image.open(path) as img:
        assert img.size == (16, 12)

    status = upscale_status({"anr_root": str(tmp_path / "anr"), "upscale": {"engine": "realesrgan"}})
    assert status["ok"]
    assert "Real-ESRGAN" in status["message"]
