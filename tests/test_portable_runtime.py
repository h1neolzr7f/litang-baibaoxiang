from pathlib import Path

import sys
from pathlib import Path

from app import config
from app.upscale import discover_realcugan

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from slim_runtime import should_keep_site_item


def _fake_bundle(root: Path) -> Path:
    body = root / "软件本体-请勿删除"
    plugin = body / "runtime" / "anr" / "plugins" / "anr_plugin_auto_mosaics"
    plugin.mkdir(parents=True)
    (plugin / "detector.py").write_text("def detector(image_path, part):\n    raise RuntimeError('x')\n", encoding="utf-8")
    (plugin / "mosaics.py").write_text("class ImageMosaicProcessor:\n    pass\n", encoding="utf-8")
    py = body / "runtime" / "anr" / "Python"
    py.mkdir(parents=True)
    (py / "python.exe").write_bytes(b"MZ")
    cugan = body / "runtime" / "anr" / "assets" / "realcugan-ncnn-vulkan"
    cugan.mkdir(parents=True)
    (cugan / "realcugan-ncnn-vulkan.exe").write_bytes(b"MZ")
    return body


def test_bundled_runtime_wins_over_machine_paths(tmp_path: Path, monkeypatch) -> None:
    body = _fake_bundle(tmp_path)
    monkeypatch.setattr(config, "APP_ROOT", body)
    assert config.package_root() == tmp_path
    assert config.default_output_root() == tmp_path / "输出"
    assert config.is_bundled_runtime()
    found = Path(config.discover_anr_root())
    assert found.name == "anr"
    assert found.parent.name == "runtime"
    assert Path(config.discover_anr_python(str(found))).name == "python.exe"
    exe = discover_realcugan(str(found))
    assert exe is not None
    assert exe.name == "realcugan-ncnn-vulkan.exe"


def test_save_config_strips_bundled_absolute_paths(tmp_path: Path, monkeypatch) -> None:
    body = _fake_bundle(tmp_path)
    monkeypatch.setattr(config, "APP_ROOT", body)
    monkeypatch.setattr(config, "DATA_DIR", body / "data")
    monkeypatch.setattr(config, "CONFIG_PATH", body / "data" / "config.json")
    cfg = {
        "anr_root": r"E:\secret\anr",
        "anr_python": r"E:\secret\python.exe",
        "output_root": str(tmp_path / "输出"),
        "_mosaic_session": "nope",
    }
    config.save_config(cfg)
    saved = (body / "data" / "config.json").read_text(encoding="utf-8")
    assert "E:\\secret" not in saved
    assert "_mosaic_session" not in saved


def test_slim_keeps_mosaic_stack_and_drops_anr_extras() -> None:
    assert should_keep_site_item("torch")
    assert should_keep_site_item("ultralytics-8.4.21.dist-info")
    assert should_keep_site_item("cv2")
    assert should_keep_site_item("scipy.libs")
    assert should_keep_site_item("customtkinter")
    assert not should_keep_site_item("gradio")
    assert not should_keep_site_item("_polars_runtime_32")
    assert not should_keep_site_item("imageio_ffmpeg")
    assert not should_keep_site_item("streamlit")
    assert not should_keep_site_item("onnxruntime")
