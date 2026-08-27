from pathlib import Path

from PIL import Image

from app.collect import assign_output_names, collect_images, scan_images
from app.output import assign_destinations


def _png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), (10, 20, 30)).save(path)


def test_collect_files_and_folder(tmp_path: Path) -> None:
    folder = tmp_path / "inbox"
    folder.mkdir()
    _png(folder / "a.png")
    (folder / "note.txt").write_text("skip", encoding="utf-8")
    nested = folder / "more"
    nested.mkdir()
    _png(nested / "b.jpg")
    single = tmp_path / "c.webp"
    _png(single)

    found = collect_images([folder, single])
    names = sorted(path.name for path in found)
    assert names == ["a.png", "b.jpg", "c.webp"]


def test_skip_work_dir(tmp_path: Path) -> None:
    hidden = tmp_path / ".work"
    hidden.mkdir()
    _png(hidden / "secret.png")
    visible = tmp_path / "ok.png"
    _png(visible)
    found = collect_images([tmp_path])
    assert [path.name for path in found] == ["ok.png"]


def test_skip_output_root_and_session(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    out = tmp_path / "out"
    _png(inbox / "keep.png")
    _png(out / "old.png")
    session = out / "20260827-160000"
    session.mkdir(parents=True)
    (session / "任务说明.txt").write_text("job", encoding="utf-8")
    _png(session / "done.png")
    _png(inbox / "理塘成品" / "side.png")
    items = scan_images([tmp_path], skip_roots=[out])
    assert [item.source.name for item in items] == ["keep.png"]
    assert items[0].rel_parent == "inbox"


def test_keep_original_names_and_collision() -> None:
    assigned = assign_output_names(
        [Path(r"E:\one\cat.png"), Path(r"D:\two\cat.jpg"), Path(r"E:\one\dog.webp")]
    )
    names = [name for _, name in assigned]
    assert names == ["cat.png", "cat_2.png", "dog.png"]


def test_assign_destinations_keep_structure(tmp_path: Path) -> None:
    src = tmp_path / "pics" / "a" / "cat.png"
    _png(src)
    items = scan_images([tmp_path / "pics"])
    assign_destinations(
        items,
        {"output_mode": "folder", "output_root": str(tmp_path / "dest"), "keep_structure": True},
        tmp_path / "dest",
    )
    assert items[0].dest == tmp_path / "dest" / "a" / "cat.png"
