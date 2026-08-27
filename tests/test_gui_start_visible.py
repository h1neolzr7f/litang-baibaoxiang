"""回归：开始处理必须落在窗口客户区内，不能被裁到屏幕外。"""

from __future__ import annotations

import pytest

from app.gui import fit_dialog_geometry, fit_window_geometry

pytest.importorskip("customtkinter")


def test_fit_window_geometry_stays_on_screen() -> None:
    cases = (
        (1920, 1080, 1.0),
        (1920, 1080, 1.25),
        (1366, 768, 1.0),
        (1366, 768, 1.25),
        (1280, 720, 1.0),
        (1280, 720, 1.5),
        (864, 864, 1.25),
        (2560, 1440, 1.5),
    )
    for screen_w, screen_h, scale in cases:
        width, height = fit_window_geometry(screen_w, screen_h, scale)
        assert width * scale <= screen_w - 40
        assert height * scale <= screen_h - 80


def _visible_in_window(widget, window, slack: int = 8) -> bool:
    widget.update_idletasks()
    top = int(widget.winfo_rooty())
    bottom = top + int(widget.winfo_height())
    win_top = int(window.winfo_rooty())
    win_bottom = win_top + int(window.winfo_height())
    return bool(widget.winfo_viewable()) and top >= win_top - slack and bottom <= win_bottom + slack


def test_start_buttons_stay_inside_window() -> None:
    from app.gui import LitangApp

    app = LitangApp()
    try:
        app.update_idletasks()
        app.update()
        scale = max(float(app._get_window_scaling()), 0.5)
        width, height = fit_window_geometry(app.winfo_screenwidth(), app.winfo_screenheight(), scale)
        assert app.winfo_width() <= int(width * scale) + 16
        assert app.winfo_height() <= int(height * scale) + 16
        assert app.winfo_height() <= int(app.winfo_screenheight()) - 32
        assert len(app.start_buttons) >= 2
        for btn in app.start_buttons:
            assert btn.cget("text") == "开始处理"
            assert _visible_in_window(btn, app)

        app.geometry(f"{width}x{min(height, 560)}")
        app.update_idletasks()
        app.update()
        for btn in app.start_buttons:
            assert _visible_in_window(btn, app)
        assert app.current_label.winfo_viewable()
        assert _visible_in_window(app.current_label, app)
    finally:
        app.destroy()


def test_fit_dialog_geometry_stays_on_screen() -> None:
    for screen_w, screen_h, scale in (
        (1920, 1080, 1.25),
        (1366, 768, 1.0),
        (864, 864, 1.25),
        (1280, 720, 1.5),
    ):
        width, height = fit_dialog_geometry(screen_w, screen_h, scale)
        assert width * scale <= screen_w - 40
        assert height * scale <= screen_h - 80


def test_confirm_start_stays_visible() -> None:
    from app.gui import ConfirmDialog, LitangApp

    app = LitangApp()
    try:
        dialog = ConfirmDialog(
            app,
            {
                "summary": "88 张待处理",
                "output_text": r"E:\Packages\litang-baibaoxiang\输出",
                "warnings": [f"磁盘提示 {index}" for index in range(10)],
                "blockers": [f"拦截 {index}" for index in range(6)],
                "ok": True,
            },
        )
        app.update_idletasks()
        app.update()
        dialog.update_idletasks()
        dialog.update()
        assert dialog.confirm_btn.cget("text") == "确认开始"
        assert _visible_in_window(dialog.confirm_btn, dialog)
        dialog.destroy()
    finally:
        app.destroy()
