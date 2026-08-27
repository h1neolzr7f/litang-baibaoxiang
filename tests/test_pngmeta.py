from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from app.pngmeta import is_png, write_clean_png
from app.pipeline import _strip_to


def test_strip_png_keeps_pixels_drops_text(tmp_path: Path) -> None:
    src = tmp_path / "in.png"
    dest = tmp_path / "out.png"
    info = PngInfo()
    info.add_text("Comment", "prompt: secret")
    info.add_text("parameters", "NovelAI leftover")
    Image.new("RGB", (17, 13), (11, 22, 33)).save(src, pnginfo=info)
    assert is_png(src)
    write_clean_png(src, dest, note="ok")
    with Image.open(src) as a, Image.open(dest) as b:
        assert a.tobytes() == b.tobytes()
        assert a.size == b.size
        assert not b.info.get("Comment")
        assert not b.info.get("parameters")


def test_strip_to_fallback_jpeg(tmp_path: Path) -> None:
    src = tmp_path / "in.jpg"
    dest = tmp_path / "out.png"
    Image.new("RGB", (8, 6), (9, 8, 7)).save(src, quality=95)
    _strip_to(src, dest)
    with Image.open(dest) as img:
        assert img.size == (8, 6)
        assert img.format == "PNG"
