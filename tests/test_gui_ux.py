"""回归：主界面交互、完成态文案、跨平台打开文件夹。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.collect import QueueItem
from app.gui import (
    actionable_blockers,
    finish_status_text,
    format_progress_text,
    resolve_open_output_target,
    resolve_open_output_targets,
    run_candidates,
    summarize_queue,
)
from app.util import image_dialog_filetypes, open_in_file_manager


def test_progress_and_finish_copy() -> None:
    assert format_progress_text(0, 0) == "0 / 0"
    assert format_progress_text(3, 10) == "3 / 10"
    counts = {"ok": 8, "fail": 1, "skip": 2}
    assert "失败 1" in finish_status_text(counts)
    assert "重试失败" in finish_status_text(counts)
    assert finish_status_text({"ok": 5, "fail": 0, "skip": 1}).startswith("全部完成")
    assert finish_status_text(counts, cancelled=True).startswith("已停止")


def test_actionable_blockers_ignore_empty_pending() -> None:
    assert actionable_blockers(["没有待处理图片。"]) == []
    assert actionable_blockers(["没有待处理图片。", "磁盘空间不够。"]) == ["磁盘空间不够。"]


def test_summarize_queue() -> None:
    items = [
        SimpleNamespace(status="ok"),
        SimpleNamespace(status="fail"),
        SimpleNamespace(status="skip"),
        SimpleNamespace(status="pending"),
    ]
    counts = summarize_queue(items)
    assert counts == {"ok": 1, "fail": 1, "skip": 1, "pending": 1, "running": 0}


def test_image_dialog_filetypes_platform() -> None:
    win = image_dialog_filetypes("nt")
    unix = image_dialog_filetypes("posix")
    assert ";" in win[0][1]
    assert " " in unix[0][1]
    assert ";" not in unix[0][1]


def test_resolve_open_output_target(tmp_path: Path) -> None:
    src = tmp_path / "a.png"
    item = QueueItem(source=src, size=1, drop_root=tmp_path, rel_parent="")
    assert resolve_open_output_target("beside", [], "", tmp_path) is None
    assert resolve_open_output_target("beside", [item], "", tmp_path) == src.parent / "理塘成品"
    assert resolve_open_output_target("folder", [item], str(tmp_path / "sess"), tmp_path) == tmp_path / "sess"
    assert resolve_open_output_target("folder", [item], "", tmp_path / "out") == tmp_path / "out"


def test_resolve_open_output_targets_deduplicates_beside_dirs(tmp_path: Path) -> None:
    a = QueueItem(source=tmp_path / "one" / "a.png", size=1, drop_root=tmp_path, rel_parent="")
    b = QueueItem(source=tmp_path / "one" / "b.png", size=1, drop_root=tmp_path, rel_parent="")
    c = QueueItem(source=tmp_path / "two" / "c.png", size=1, drop_root=tmp_path, rel_parent="")
    targets = resolve_open_output_targets("beside", [a, b, c], "", tmp_path)
    assert targets == [tmp_path / "one" / "理塘成品", tmp_path / "two" / "理塘成品"]


def test_run_candidates_retry_only_keeps_success_untouched() -> None:
    ok = SimpleNamespace(status="ok")
    fail = SimpleNamespace(status="fail")
    skip = SimpleNamespace(status="skip")
    assert run_candidates([ok, fail, skip], retry_only=True) == [fail]
    assert run_candidates([ok, fail, skip], retry_only=False) == [ok, fail, skip]


def test_open_in_file_manager_uses_xdg_on_linux(monkeypatch, tmp_path: Path) -> None:
    called: list[list[str]] = []
    monkeypatch.setattr("app.util.os.name", "posix")
    monkeypatch.setattr("app.util.sys.platform", "linux")
    monkeypatch.setattr("app.util.subprocess.run", lambda args, **kwargs: called.append(list(args)))
    open_in_file_manager(tmp_path)
    assert called
    assert called[0][0] == "xdg-open"
    assert called[0][1].replace("\\", "/") == str(tmp_path).replace("\\", "/")


pytest.importorskip("customtkinter")


def test_selected_parts_do_not_silently_select_all() -> None:
    from app.gui import LitangApp
    from app.mosaic import MOSAIC_PARTS

    app = LitangApp()
    try:
        app.update_idletasks()
        for name in MOSAIC_PARTS:
            app.var_parts[name].set(False)
        assert app._selected_parts() == []
        for name in MOSAIC_PARTS:
            app.var_parts[name].set(True)
        assert app._selected_parts() == MOSAIC_PARTS
    finally:
        app.destroy()


def test_finish_status_survives_estimate_refresh() -> None:
    from app.gui import LitangApp

    app = LitangApp()
    try:
        app.update_idletasks()
        item = QueueItem(source=Path("done.png"), size=12, drop_root=Path("."), rel_parent="")
        item.status = "ok"
        app.items = [item]
        app._last_result_text = finish_status_text({"ok": 1, "fail": 0, "skip": 0})
        app._refresh_estimate_now()
        assert "全部完成" in app.status.cget("text")
        assert "没有待处理" not in app.status.cget("text")
        assert app.progress_text.cget("text") == "0 / 0"
    finally:
        app.destroy()


def test_clear_queue_asks_and_can_cancel(monkeypatch) -> None:
    from app.gui import LitangApp

    app = LitangApp()
    try:
        app.update_idletasks()
        app.items = [QueueItem(source=Path("a.png"), size=1, drop_root=Path("."), rel_parent="")]
        asked: list[str] = []
        monkeypatch.setattr("app.gui.messagebox.askyesno", lambda *_a, **_k: asked.append("no") or False)
        app._clear_queue()
        assert asked
        assert len(app.items) == 1

        monkeypatch.setattr("app.gui.messagebox.askyesno", lambda *_a, **_k: True)
        app._clear_queue()
        assert app.items == []
        assert app.drop_title.cget("text") == "把图片或文件夹拖到这里"
        assert app.progress_text.cget("text") == "0 / 0"
    finally:
        app.destroy()


def test_stale_scan_does_not_repopulate_queue() -> None:
    from app.gui import LitangApp

    app = LitangApp()
    try:
        app.update_idletasks()
        app._scan_token = 2
        found = [QueueItem(source=Path("late.png"), size=1, drop_root=Path("."), rel_parent="")]
        app._merge_items(found, token=1)
        assert app.items == []
        app._merge_items(found, token=2)
        assert len(app.items) == 1
    finally:
        app.destroy()


def test_open_output_beside_without_items(monkeypatch) -> None:
    from app.gui import LitangApp

    app = LitangApp()
    shown: list[str] = []
    monkeypatch.setattr("app.gui.messagebox.showinfo", lambda _t, msg: shown.append(msg))
    try:
        app.update_idletasks()
        app.var_mode.set("beside")
        app._open_output()
        assert shown
        assert "旁边" in shown[0]
    finally:
        app.destroy()


def test_dependent_controls_follow_feature_toggles() -> None:
    from app.gui import LitangApp
    from app.upscale import UPSCALE_KEY_TO_LABEL, UPSCALE_LABELS

    app = LitangApp()
    try:
        app.update_idletasks()
        assert list(app.model_menu.cget("values")) == UPSCALE_LABELS
        app.var_upscale.set(False)
        app.var_mosaic.set(False)
        app._sync_dependent_states()
        assert str(app.scale_btn.cget("state")) == "disabled"
        assert str(app.model_menu.cget("state")) == "disabled"
        assert str(app.method_menu.cget("state")) == "disabled"
        app.var_upscale.set(True)
        app.var_mosaic.set(True)
        app.var_up_choice.set(UPSCALE_KEY_TO_LABEL["lanczos"])
        app._sync_dependent_states()
        assert str(app.scale_btn.cget("state")) == "normal"
        assert str(app.model_menu.cget("state")) == "normal"
        assert str(app.noise_menu.cget("state")) == "disabled"
        assert str(app.method_menu.cget("state")) == "normal"
        app.var_up_choice.set(UPSCALE_KEY_TO_LABEL["auto"])
        app._sync_dependent_states()
        assert str(app.noise_menu.cget("state")) == "normal"
        cfg = app._upscale_from_ui()
        assert cfg["engine"] == "auto"
        assert cfg["model"] == "models-pro"
    finally:
        app.destroy()


def test_interaction_lock_disables_queue_and_settings() -> None:
    from app.gui import LitangApp

    app = LitangApp()
    try:
        app.update_idletasks()
        app._set_interaction_locked(True)
        assert str(app.pick_files_btn.cget("state")) == "disabled"
        assert str(app.start_btn.cget("state")) == "disabled"
        assert str(app.footer_start_btn.cget("state")) == "disabled"
        assert str(app.retry_btn.cget("state")) == "disabled"
        app._set_interaction_locked(False)
        assert str(app.pick_files_btn.cget("state")) == "normal"
        assert str(app.start_btn.cget("state")) == "normal"
    finally:
        app.destroy()


def test_output_change_forgets_previous_session(monkeypatch) -> None:
    from app.gui import LitangApp

    app = LitangApp()
    try:
        app.update_idletasks()
        app.session_dir = "old-session"
        app._on_output_change()
        assert app.session_dir == ""
    finally:
        app.destroy()


def test_add_images_and_start_guards(tmp_path: Path, monkeypatch) -> None:
    from PIL import Image

    from app.gui import ConfirmDialog, LitangApp
    from app.mosaic import MOSAIC_PARTS

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    for name in ("one.png", "two.jpg"):
        Image.new("RGB", (16, 12), (80, 40, 20)).save(inbox / name)

    app = LitangApp()
    infos: list[str] = []
    monkeypatch.setattr("app.gui.messagebox.showinfo", lambda _t, msg: infos.append(msg))
    try:
        app.update_idletasks()
        app.out_entry.configure(state="normal")
        app.out_entry.delete(0, "end")
        app.out_entry.insert(0, str(tmp_path / "out"))
        app.var_mode.set("folder")
        from app.collect import scan_images

        found = scan_images([inbox], skip_roots=app._skip_roots())
        app._merge_items(found, app._scan_token)
        app.update_idletasks()
        assert len(app.items) == 2
        assert "2" in app.drop_title.cget("text")
        assert "2 张" in app.stats.cget("text")
        assert app.pick_files_btn.cget("state") == "normal"

        app.var_mosaic.set(True)
        for name in MOSAIC_PARTS:
            app.var_parts[name].set(False)
        app._start()
        assert any("部位" in msg for msg in infos)

        for name in MOSAIC_PARTS:
            app.var_parts[name].set(True)
        app.var_upscale.set(False)
        app.var_mosaic.set(False)
        app.var_meta.set(False)
        app._on_feature_toggle()
        assert str(app.scale_btn.cget("state")) == "disabled"
        app._start()
        assert any("至少勾选" in msg for msg in infos)

        app.var_meta.set(True)
        dialog = ConfirmDialog(
            app,
            {
                "summary": "2 张待处理",
                "output_text": str(tmp_path / "out"),
                "warnings": [],
                "blockers": [],
                "ok": True,
            },
        )
        app.update()
        dialog.update()
        assert dialog.confirm_btn.cget("state") == "normal"
        dialog._no()
        app.update()

        app.items[0].status = "ok"
        app.items[1].status = "fail"
        app._on_finished()
        app.update()
        assert "失败 1" in app.status.cget("text")
        assert app.current_label.cget("text") == "当前：空闲"
        assert "2" in app.progress_text.cget("text")
    finally:
        app.destroy()
