from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from app.collect import scan_images
from app.engine import JobControl, _parallel_plan, run_job
from app.output import assign_destinations, make_session_dir


def _png(path: Path, n: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    info = PngInfo()
    info.add_text("Comment", f"secret-{n}")
    Image.new("RGB", (12, 10), (n % 200, 40, 80)).save(path, pnginfo=info)


def _cfg(tmp_path: Path, **extra):
    cfg = {
        "output_mode": "folder",
        "output_root": str(tmp_path / "out"),
        "keep_structure": True,
        "dated_session": False,
        "skip_existing": True,
        "cleanup_work": True,
        "workers": 2,
        "upscale": {"enabled": True, "scale": 2, "engine": "lanczos"},
        "mosaic": {"enabled": False},
        "metadata": {"enabled": True},
        "anr_root": "",
        "anr_python": "",
        "persist_perf": False,
    }
    cfg.update(extra)
    return cfg


def test_lanczos_jobs_can_use_multiple_workers() -> None:
    workers, staged = _parallel_plan(
        {"upscale": {"enabled": True, "engine": "lanczos", "scale": 2}, "workers": 2, "mosaic": {"enabled": False}},
        mosaic_on=False,
    )
    assert workers == 2
    assert staged is False


def test_engine_custom_folder_and_resume(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    for i in range(40):
        _png(inbox / f"img_{i:03d}.png", i)
        _png(inbox / "set" / f"n_{i:03d}.png", i)
    cfg = _cfg(tmp_path)
    items = scan_images([inbox])
    assert len(items) == 80
    result = run_job(items, cfg)
    assert result["fail_count"] == 0
    assert result["ok_count"] == 80
    out = tmp_path / "out"
    finals = list(out.rglob("*.png"))
    assert len(finals) == 80
    assert (out / "set" / "n_001.png").exists()
    with Image.open(out / "img_000.png") as img:
        assert img.size == (24, 20)
        assert not img.info.get("Comment")
    assert (out / "_理塘百宝箱记录" / "处理记录.txt").exists()
    assert not (out / "处理记录.txt").exists()

    again = scan_images([inbox], skip_roots=[out])
    second = run_job(again, cfg)
    assert second["ok_count"] == 80
    assert second["fail_count"] == 0
    assert "已经有成品" in second["message"] or second.get("skip_count", 0) == 80


def test_engine_cancel_keeps_done(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    for i in range(12):
        _png(inbox / f"x_{i}.png", i)
    cfg = _cfg(tmp_path, workers=1)
    items = scan_images([inbox])
    control = JobControl()

    def progress(payload: dict) -> None:
        if int(payload.get("ok") or 0) >= 2:
            control.cancel.set()

    run_job(items, cfg, progress=progress, control=control)
    done = list((tmp_path / "out").glob("*.png"))
    assert 2 <= len(done) < 12
    assert not any(item.status == "running" for item in items)
    assert any(item.status == "pending" for item in items)


def test_beside_mode(tmp_path: Path) -> None:
    src = tmp_path / "photo.png"
    _png(src, 7)
    items = scan_images([src])
    result = run_job(
        items,
        _cfg(tmp_path, output_mode="beside", upscale={"enabled": False, "scale": 2}),
    )
    assert result["ok_count"] == 1
    final = src.parent / "理塘成品" / "photo.png"
    assert final.exists()
    with Image.open(final) as img:
        assert img.size == (12, 10)
        assert not img.info.get("Comment")


def test_retry_preserves_duplicate_name_destination(tmp_path: Path) -> None:
    first = tmp_path / "one" / "cat.png"
    second = tmp_path / "two" / "cat.png"
    _png(first, 11)
    _png(second, 22)
    cfg = _cfg(
        tmp_path,
        keep_structure=False,
        skip_existing=False,
        upscale={"enabled": False, "scale": 2},
    )
    items = scan_images([first, second])
    session = make_session_dir(cfg)
    assign_destinations(items, cfg, session)
    assert items[0].dest is not None and items[0].dest.name == "cat.png"
    assert items[1].dest is not None and items[1].dest.name == "cat_2.png"

    # 模拟第一张已经成功；只重试第二张时不能重新分配成 cat.png 覆盖它。
    items[0].dest.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (3, 3), (1, 2, 3)).save(items[0].dest)
    retry_cfg = {**cfg, "_preserve_destinations": True}
    result = run_job([items[1]], retry_cfg)
    assert result["fail_count"] == 0
    assert items[1].dest.name == "cat_2.png"
    assert items[1].dest.exists()
    with Image.open(items[0].dest) as img:
        assert img.size == (3, 3)
