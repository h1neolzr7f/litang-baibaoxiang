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


def test_load_config_clamps_garbage_numbers(tmp_path: Path, monkeypatch) -> None:
    import json

    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "APP_ROOT", tmp_path)
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "upscale": {"scale": "nope"},
                "mosaic": {"intensity": "big", "sensitivity": 99, "dilate": -5, "parts": "全部"},
                "workers": "many",
            }
        ),
        encoding="utf-8",
    )
    cfg = config.load_config()
    assert cfg["upscale"]["scale"] == 2
    assert cfg["mosaic"]["intensity"] == 36
    assert cfg["mosaic"]["sensitivity"] == 10
    assert cfg["mosaic"]["dilate"] == 0
    assert cfg["mosaic"]["parts"]
    assert cfg["workers"] == 2


def test_runtime_rejects_non_python_executable(tmp_path: Path) -> None:
    from app.mosaic import mosaic_runtime_status

    plugin = tmp_path / "plugins" / "anr_plugin_auto_mosaics"
    plugin.mkdir(parents=True)
    (plugin / "detector.py").write_text("x", encoding="utf-8")
    (plugin / "mosaics.py").write_text("x", encoding="utf-8")
    evil = tmp_path / "evil.exe"
    evil.write_bytes(b"MZ")
    status = mosaic_runtime_status({"anr_root": str(tmp_path), "anr_python": str(evil)})
    assert not status["ok"]


def test_daemon_relocates_unicode_image_paths(tmp_path: Path) -> None:
    import app.anr_mosaic_daemon as daemon
    from app.util import path_is_ascii

    src = tmp_path / "原图.png"
    src.write_bytes(b"not-a-real-png")
    copied = daemon._materialize_ascii(str(src))
    assert path_is_ascii(copied)
    assert Path(copied).read_bytes() == b"not-a-real-png"
    session = daemon._ascii_session(str(tmp_path / "成品目录"))
    assert path_is_ascii(session)


def test_oneclick_launcher_starts_inside_app_root(tmp_path: Path) -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    from refresh_release_oneclick import LAUNCHER_BAT, write_launcher

    assert 'cd /d "%ROOT%"' in LAUNCHER_BAT
    assert LAUNCHER_BAT.index('cd /d "%ROOT%"') < LAUNCHER_BAT.index('"%PY%" -m app')
    assert "PYTHONPATH=%ROOT%" in LAUNCHER_BAT
    assert "PYTHONUTF8=1" in LAUNCHER_BAT
    stale = tmp_path / "old-launcher.bat"
    stale.write_text("old", encoding="utf-8")
    write_launcher(tmp_path)
    names = sorted(path.name for path in tmp_path.glob("*.bat"))
    assert names == ["创建桌面快捷方式.bat", "启动理塘百宝箱.bat"]
    assert 'cd /d "%ROOT%"' in (tmp_path / "启动理塘百宝箱.bat").read_text(encoding="utf-8")


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
