from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from app.pipeline import process_one


def _nai_like_png(path: Path, size: tuple[int, int] = (32, 24)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    info = PngInfo()
    info.add_text("Comment", "prompt: 1girl, secret tags")
    info.add_text("parameters", "NovelAI leftover")
    Image.new("RGB", size, (80, 40, 120)).save(path, pnginfo=info)


def _cfg(**extra):
    cfg = {
        "upscale": {"enabled": True, "scale": 2, "engine": "lanczos"},
        "mosaic": {"enabled": False},
        "metadata": {"enabled": True},
        "anr_root": "",
        "anr_python": "",
        "skip_existing": False,
    }
    cfg.update(extra)
    return cfg


def test_upscale_and_strip_keep_original_name(tmp_path: Path) -> None:
    source = tmp_path / "假期海边.png"
    _nai_like_png(source)
    final = tmp_path / "out" / "假期海边.png"
    result = process_one(source, final, tmp_path / "work", _cfg())
    assert result.ok
    assert final.name == "假期海边.png"
    with Image.open(final) as img:
        assert img.size == (64, 48)
        assert not img.info.get("Comment")
    assert any(step.startswith("upscale:2x") for step in result.steps)
    assert "metadata:clean" in result.steps


def test_missing_anr_does_not_block(tmp_path: Path) -> None:
    source = tmp_path / "plain.png"
    _nai_like_png(source)
    final = tmp_path / "done" / "plain.png"
    result = process_one(
        source,
        final,
        tmp_path / "work",
        _cfg(
            upscale={"enabled": False, "scale": 2, "engine": "lanczos"},
            mosaic={"enabled": True},
            anr_root=str(tmp_path / "no-anr"),
        ),
    )
    assert result.ok
    assert "mosaic:unavailable" in result.steps
    assert final.exists()


def test_skip_only_when_quality_matches(tmp_path: Path) -> None:
    source = tmp_path / "a.png"
    _nai_like_png(source, (16, 16))
    final = tmp_path / "out" / "a.png"
    record = tmp_path / "rec"
    cfg = _cfg(skip_existing=True)
    cfg["_record_dir"] = str(record)
    first = process_one(source, final, tmp_path / "w1", cfg)
    assert first.ok and not first.skipped
    second = process_one(source, final, tmp_path / "w2", cfg)
    assert second.skipped
    cfg["upscale"] = {"enabled": True, "scale": 3, "engine": "lanczos"}
    third = process_one(source, final, tmp_path / "w3", cfg)
    assert not third.skipped
    with Image.open(final) as img:
        assert img.size == (48, 48)


def test_old_file_without_signature_is_redone(tmp_path: Path) -> None:
    source = tmp_path / "a.png"
    _nai_like_png(source, (16, 16))
    final = tmp_path / "out" / "a.png"
    final.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (9, 9), (1, 2, 3)).save(final)
    result = process_one(source, final, tmp_path / "work", _cfg(skip_existing=True))
    assert not result.skipped
    with Image.open(final) as img:
        assert img.size == (32, 32)
