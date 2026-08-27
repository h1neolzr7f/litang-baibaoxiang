from __future__ import annotations

import os
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from app import APP_NAME, __version__
from app.collect import QueueItem, scan_images
from app.config import load_config, save_config
from app.engine import JobControl, retry_failed, run_job
from app.mosaic import MOSAIC_METHODS, MOSAIC_PARTS, mosaic_runtime_status
from app.upscale import upscale_status
from app.output import assign_destinations, make_session_dir, resolve_output_root
from app.preflight import build_preflight
from app.util import format_bytes, format_duration

CREAM = "#F4EDE0"
CARD = "#FFF9F0"
LINE = "#E4D8C4"
ACCENT = "#3E6B45"
ACCENT_HOVER = "#2F5336"
DROP_BG = "#E8F2E6"
TEXT = "#2B2418"
MUTED = "#7A6F5D"
WARN = "#9A6B12"
ERR = "#A33B2B"
OK = "#2F6B3A"


class ConfirmDialog(ctk.CTkToplevel):
    def __init__(self, master: ctk.CTk, preflight: dict) -> None:
        super().__init__(master)
        self.title("确认开始")
        self.geometry("560x420")
        self.resizable(False, False)
        self.result = False
        self.configure(fg_color=CREAM)
        self.transient(master)
        try:
            self.grab_set()
        except Exception:
            pass
        ctk.CTkLabel(self, text="核对一下再开始", font=ctk.CTkFont(size=22, weight="bold"), text_color=TEXT).pack(
            anchor="w", padx=24, pady=(20, 8)
        )
        ctk.CTkLabel(self, text=preflight["summary"], font=ctk.CTkFont(size=15), text_color=ACCENT).pack(
            anchor="w", padx=24
        )
        ctk.CTkLabel(
            self,
            text=f"成品放在：{preflight['output_text']}",
            wraplength=500,
            justify="left",
            text_color=TEXT,
        ).pack(anchor="w", padx=24, pady=(12, 6))
        ctk.CTkLabel(self, text="原图不会被修改。做到一半关掉，下次会自动跳过已经做好的。", text_color=MUTED).pack(
            anchor="w", padx=24
        )
        for warn in preflight.get("warnings") or []:
            ctk.CTkLabel(self, text="注意：" + warn, wraplength=500, justify="left", text_color=WARN).pack(
                anchor="w", padx=24, pady=4
            )
        for block in preflight.get("blockers") or []:
            ctk.CTkLabel(self, text="还不能开始：" + block, wraplength=500, justify="left", text_color=ERR).pack(
                anchor="w", padx=24, pady=4
            )
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(side="bottom", fill="x", padx=24, pady=20)
        ctk.CTkButton(row, text="返回修改", width=120, fg_color="#C9B79A", hover_color="#B4A184",
                      text_color=TEXT, command=self._no).pack(side="left")
        start = ctk.CTkButton(row, text="确认开始", width=160, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                              command=self._yes, state="normal" if preflight.get("ok") else "disabled")
        start.pack(side="right")
        self.bind("<Return>", lambda _e: self._yes() if preflight.get("ok") else None)
        self.bind("<Escape>", lambda _e: self._no())

    def _yes(self) -> None:
        self.result = True
        self.destroy()

    def _no(self) -> None:
        self.result = False
        self.destroy()


class LitangApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME}  v{__version__}")
        self.geometry("1120x880")
        self.minsize(980, 760)
        self.configure(fg_color=CREAM)
        self.cfg = load_config()
        self.items: list[QueueItem] = []
        self.scan_lock = threading.Lock()
        self.worker: threading.Thread | None = None
        self.control = JobControl()
        self.session_dir = ""
        self._estimate_job: str | None = None

        self._build()
        self._refresh_anr()
        self._hook_drag_drop()
        self._on_output_change()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build(self) -> None:
        header = ctk.CTkFrame(self, fg_color=CARD, corner_radius=16, border_width=1, border_color=LINE)
        header.pack(fill="x", padx=16, pady=(16, 8))
        ctk.CTkLabel(header, text=APP_NAME, font=ctk.CTkFont(size=28, weight="bold"), text_color=TEXT).pack(
            anchor="w", padx=20, pady=(14, 0)
        )
        ctk.CTkLabel(
            header,
            text="先选成品放哪里，再把图片或文件夹拖进来。十几 GB 也能排队处理。原图保证不改。",
            font=ctk.CTkFont(size=14),
            text_color=MUTED,
        ).pack(anchor="w", padx=20, pady=(2, 14))

        place = ctk.CTkFrame(self, fg_color=CARD, corner_radius=16, border_width=1, border_color=LINE)
        place.pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkLabel(place, text="成品放哪里（点选即可改）", font=ctk.CTkFont(size=16, weight="bold"), text_color=TEXT).pack(
            anchor="w", padx=18, pady=(12, 6)
        )
        self.var_mode = ctk.StringVar(value=str(self.cfg.get("output_mode") or "folder"))
        for value, label in (
            ("folder", "放到我指定的文件夹（最常用，可随时改位置）"),
            ("beside", "放到每张原图旁边的「理塘成品」文件夹"),
            ("mirror", "按原来的文件夹结构，镜像到我指定的地方"),
        ):
            ctk.CTkRadioButton(
                place, text=label, variable=self.var_mode, value=value, command=self._on_output_change, text_color=TEXT
            ).pack(anchor="w", padx=18, pady=2)

        path_row = ctk.CTkFrame(place, fg_color="transparent")
        path_row.pack(fill="x", padx=18, pady=(8, 4))
        self.out_entry = ctk.CTkEntry(path_row, height=36, font=ctk.CTkFont(size=14))
        self.out_entry.pack(side="left", fill="x", expand=True)
        self.out_entry.insert(0, str(self.cfg.get("output_root") or ""))
        self.out_entry.bind("<KeyRelease>", lambda _e: self._on_output_change())
        ctk.CTkButton(path_row, text="改位置", width=90, height=36, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=self._pick_output).pack(side="left", padx=(8, 0))
        ctk.CTkButton(path_row, text="打开", width=70, height=36, fg_color="#C9B79A", hover_color="#B4A184",
                      text_color=TEXT, command=self._open_output).pack(side="left", padx=(8, 0))

        extra = ctk.CTkFrame(place, fg_color="transparent")
        extra.pack(fill="x", padx=18, pady=(4, 12))
        self.var_keep = ctk.BooleanVar(value=bool(self.cfg.get("keep_structure", True)))
        self.var_dated = ctk.BooleanVar(value=bool(self.cfg.get("dated_session", False)))
        self.var_skip = ctk.BooleanVar(value=bool(self.cfg.get("skip_existing", True)))
        ctk.CTkCheckBox(extra, text="保持原来的子文件夹", variable=self.var_keep, command=self._on_output_change,
                        text_color=TEXT).pack(side="left", padx=(0, 16))
        ctk.CTkCheckBox(extra, text="另外新建一个时间文件夹", variable=self.var_dated, command=self._on_output_change,
                        text_color=TEXT).pack(side="left", padx=(0, 16))
        ctk.CTkCheckBox(extra, text="已经做过的自动跳过（可中断后续跑）", variable=self.var_skip,
                        command=self._on_output_change, text_color=TEXT).pack(side="left")

        drop = ctk.CTkFrame(self, fg_color=DROP_BG, corner_radius=16, border_width=2, border_color=ACCENT)
        drop.pack(fill="x", padx=16, pady=(0, 8))
        self.drop_title = ctk.CTkLabel(drop, text="把图片或文件夹拖到这里", font=ctk.CTkFont(size=20, weight="bold"),
                                      text_color=ACCENT)
        self.drop_title.pack(pady=(20, 2))
        self.drop_hint = ctk.CTkLabel(drop, text="十几 GB 会在后台扫描排队，界面不会卡住。", text_color=MUTED)
        self.drop_hint.pack()
        btns = ctk.CTkFrame(drop, fg_color="transparent")
        btns.pack(pady=(8, 16))
        ctk.CTkButton(btns, text="选择图片", width=110, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=self._pick_files).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="选择文件夹", width=110, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=self._pick_folder).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="清空队列", width=90, fg_color="#C9B79A", hover_color="#B4A184",
                      text_color=TEXT, command=self._clear_queue).pack(side="left", padx=6)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        left = ctk.CTkFrame(body, fg_color=CARD, corner_radius=16, border_width=1, border_color=LINE)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        ctk.CTkLabel(left, text="队列与进度", font=ctk.CTkFont(size=16, weight="bold"), text_color=TEXT).pack(
            anchor="w", padx=16, pady=(12, 4)
        )
        self.stats = ctk.CTkLabel(
            left, text="还没有图片。", font=ctk.CTkFont(size=15), text_color=ACCENT, justify="left", wraplength=680
        )
        self.stats.pack(anchor="w", padx=16)
        self.eta_label = ctk.CTkLabel(left, text="预计时间会在加入图片后显示。", text_color=MUTED)
        self.eta_label.pack(anchor="w", padx=16, pady=(0, 6))
        self.current_label = ctk.CTkLabel(left, text="当前：空闲", text_color=TEXT)
        self.current_label.pack(anchor="w", padx=16)
        self.event_box = ctk.CTkTextbox(left, height=220, fg_color=CREAM, text_color=TEXT)
        self.event_box.pack(fill="both", expand=True, padx=12, pady=10)
        self.event_box.insert("end", "把文件夹拖进来即可。不会把几千张图画成卡死的列表。\n")
        self.event_box.configure(state="disabled")

        right = ctk.CTkScrollableFrame(body, fg_color=CARD, corner_radius=16, width=340)
        right.pack(side="right", fill="y")
        ctk.CTkLabel(right, text="这一次做什么", font=ctk.CTkFont(size=16, weight="bold"), text_color=TEXT).pack(
            anchor="w", padx=16, pady=(12, 8)
        )
        up = self.cfg.get("upscale") or {}
        mo = self.cfg.get("mosaic") or {}
        md = self.cfg.get("metadata") or {}
        self.var_upscale = ctk.BooleanVar(value=bool(up.get("enabled", True)))
        self.var_mosaic = ctk.BooleanVar(value=bool(mo.get("enabled", True)))
        self.var_meta = ctk.BooleanVar(value=bool(md.get("enabled", True)))
        self.var_scale = ctk.IntVar(value=int(up.get("scale") or 2))
        self.var_method = ctk.StringVar(value=str(mo.get("method") or "像素"))
        saved_noise = str(up.get("noise") or "conservative")
        self.var_noise = ctk.StringVar(value="强力降噪" if saved_noise in {"denoise3x", "strong"} else "保守细节")
        ctk.CTkCheckBox(right, text="超分（Real-CUGAN 专业版优先）", variable=self.var_upscale,
                        command=self._refresh_estimate, text_color=TEXT).pack(anchor="w", padx=16, pady=4)
        scale_row = ctk.CTkFrame(right, fg_color="transparent")
        scale_row.pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkLabel(scale_row, text="放大倍数", text_color=MUTED).pack(side="left")
        self.scale_btn = ctk.CTkSegmentedButton(scale_row, values=["2", "3", "4"], command=self._on_scale)
        self.scale_btn.pack(side="right")
        self.scale_btn.set(str(min(max(self.var_scale.get(), 2), 4)))
        noise_row = ctk.CTkFrame(right, fg_color="transparent")
        noise_row.pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkLabel(noise_row, text="超分风格", text_color=MUTED).pack(side="left")
        ctk.CTkOptionMenu(
            noise_row,
            values=["保守细节", "强力降噪"],
            variable=self.var_noise,
            width=130,
        ).pack(side="right")
        self.upscale_label = ctk.CTkLabel(right, text="", wraplength=280, justify="left", text_color=MUTED)
        self.upscale_label.pack(anchor="w", padx=16, pady=(0, 8))
        ctk.CTkCheckBox(right, text="打码（自动遮敏感部位）", variable=self.var_mosaic,
                        command=self._refresh_estimate, text_color=TEXT).pack(anchor="w", padx=16, pady=4)
        ctk.CTkLabel(right, text="打码部位（可多选，默认全开）", text_color=MUTED).pack(anchor="w", padx=16, pady=(4, 2))
        saved_parts = set(mo.get("parts") or MOSAIC_PARTS)
        self.var_parts = {name: ctk.BooleanVar(value=name in saved_parts) for name in MOSAIC_PARTS}
        parts_row = ctk.CTkFrame(right, fg_color="transparent")
        parts_row.pack(fill="x", padx=16, pady=(0, 6))
        for index, name in enumerate(MOSAIC_PARTS):
            ctk.CTkCheckBox(parts_row, text=name, variable=self.var_parts[name], width=140, text_color=TEXT).grid(
                row=index // 2, column=index % 2, sticky="w", pady=2
            )
        method_row = ctk.CTkFrame(right, fg_color="transparent")
        method_row.pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkLabel(method_row, text="打码方式", text_color=MUTED).pack(side="left")
        ctk.CTkOptionMenu(method_row, values=MOSAIC_METHODS, variable=self.var_method, width=110).pack(side="right")
        self.var_intensity = ctk.IntVar(value=int(mo.get("intensity") or 36))
        ctk.CTkLabel(right, text="打码强度（越大越实）", text_color=MUTED).pack(anchor="w", padx=16)
        intensity_row = ctk.CTkFrame(right, fg_color="transparent")
        intensity_row.pack(fill="x", padx=16, pady=(0, 8))
        self.intensity_label = ctk.CTkLabel(intensity_row, text=str(self.var_intensity.get()), text_color=TEXT, width=36)
        self.intensity_label.pack(side="right")
        ctk.CTkSlider(
            intensity_row, from_=8, to=80, number_of_steps=72, variable=self.var_intensity, command=self._on_intensity
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.var_dilate = ctk.IntVar(value=int(mo.get("dilate") or 28))
        ctk.CTkLabel(right, text="遮罩外扩（防漏边）", text_color=MUTED).pack(anchor="w", padx=16)
        dilate_row = ctk.CTkFrame(right, fg_color="transparent")
        dilate_row.pack(fill="x", padx=16, pady=(0, 8))
        self.dilate_label = ctk.CTkLabel(dilate_row, text=str(self.var_dilate.get()), text_color=TEXT, width=36)
        self.dilate_label.pack(side="right")
        ctk.CTkSlider(
            dilate_row, from_=0, to=64, number_of_steps=64, variable=self.var_dilate, command=self._on_dilate
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.var_sensitivity = ctk.IntVar(value=int(mo.get("sensitivity") or 8))
        ctk.CTkLabel(right, text="识别灵敏度（越高越能抓到小/暗部位）", text_color=MUTED).pack(anchor="w", padx=16)
        sens_row = ctk.CTkFrame(right, fg_color="transparent")
        sens_row.pack(fill="x", padx=16, pady=(0, 8))
        self.sensitivity_label = ctk.CTkLabel(sens_row, text=str(self.var_sensitivity.get()), text_color=TEXT, width=36)
        self.sensitivity_label.pack(side="right")
        ctk.CTkSlider(
            sens_row, from_=1, to=10, number_of_steps=9, variable=self.var_sensitivity, command=self._on_sensitivity
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkCheckBox(right, text="清元数据（去掉提示词）", variable=self.var_meta,
                        command=self._refresh_estimate, text_color=TEXT).pack(anchor="w", padx=16, pady=4)
        self.anr_label = ctk.CTkLabel(right, text="", wraplength=280, justify="left", text_color=MUTED)
        self.anr_label.pack(anchor="w", padx=16, pady=(10, 8))
        self.disk_label = ctk.CTkLabel(right, text="", wraplength=280, justify="left", text_color=MUTED)
        self.disk_label.pack(anchor="w", padx=16, pady=(0, 8))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=16, pady=(0, 14))
        self.progress = ctk.CTkProgressBar(footer, progress_color=ACCENT, height=10)
        self.progress.pack(fill="x")
        self.progress.set(0)
        self.status = ctk.CTkLabel(footer, text="空闲。先选成品位置，再拖入图片。", text_color=MUTED)
        self.status.pack(anchor="w", pady=6)
        actions = ctk.CTkFrame(footer, fg_color="transparent")
        actions.pack(fill="x")
        self.start_btn = ctk.CTkButton(actions, text="开始处理", width=150, height=42,
                                      font=ctk.CTkFont(size=16, weight="bold"),
                                      fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self._start)
        self.start_btn.pack(side="left")
        self.pause_btn = ctk.CTkButton(actions, text="暂停", width=80, height=42, fg_color="#C9B79A",
                                      hover_color="#B4A184", text_color=TEXT, command=self._toggle_pause,
                                      state="disabled")
        self.pause_btn.pack(side="left", padx=8)
        self.stop_btn = ctk.CTkButton(actions, text="停止", width=80, height=42, fg_color="#C9B79A",
                                     hover_color="#B4A184", text_color=TEXT, command=self._stop, state="disabled")
        self.stop_btn.pack(side="left")
        ctk.CTkButton(actions, text="重试失败", width=90, height=42, fg_color="#C9B79A", hover_color="#B4A184",
                      text_color=TEXT, command=self._retry).pack(side="left", padx=8)
        ctk.CTkButton(actions, text="打开成品文件夹", width=130, height=42, fg_color="#C9B79A",
                      hover_color="#B4A184", text_color=TEXT, command=self._open_output).pack(side="right")

    def _busy(self) -> bool:
        return bool(self.worker and self.worker.is_alive())

    def _hook_drag_drop(self) -> None:
        try:
            import windnd

            def on_drop(files: list) -> None:
                paths: list[str] = []
                for item in files:
                    if isinstance(item, bytes):
                        for enc in ("utf-8", "gbk", "mbcs"):
                            try:
                                paths.append(item.decode(enc))
                                break
                            except UnicodeDecodeError:
                                continue
                    else:
                        paths.append(str(item))
                self.after(0, lambda: self._add_paths(paths))

            windnd.hook_dropfiles(self, func=on_drop)
            self.drop_hint.configure(text="已开启拖放。文件夹再大也会在后台排队。")
        except Exception:
            self.drop_hint.configure(text="拖放不可用，请用「选择图片 / 选择文件夹」。")

    def _refresh_anr(self) -> None:
        status = mosaic_runtime_status(self.cfg)
        self.anr_label.configure(
            text=str(status.get("message") or ""),
            text_color=OK if status.get("ok") else WARN,
        )
        up = upscale_status(self.cfg)
        self.upscale_label.configure(
            text=str(up.get("message") or ""),
            text_color=OK if up.get("ok") else WARN,
        )

    def _on_scale(self, value: str) -> None:
        self.var_scale.set(int(value))
        self._refresh_estimate()

    def _on_intensity(self, value: float) -> None:
        self.intensity_label.configure(text=str(int(round(float(value)))))

    def _on_dilate(self, value: float) -> None:
        self.dilate_label.configure(text=str(int(round(float(value)))))

    def _on_sensitivity(self, value: float) -> None:
        self.sensitivity_label.configure(text=str(int(round(float(value)))))
        self._refresh_estimate()

    def _selected_parts(self) -> list[str]:
        parts = [name for name in MOSAIC_PARTS if self.var_parts[name].get()]
        return parts or list(MOSAIC_PARTS)

    def _mosaic_cfg(self, base: dict | None = None) -> dict:
        current = dict((base or self.cfg).get("mosaic") or {})
        current.update(
            {
                "enabled": self.var_mosaic.get(),
                "method": self.var_method.get(),
                "intensity": int(self.var_intensity.get()),
                "dilate": int(self.var_dilate.get()),
                "sensitivity": int(self.var_sensitivity.get()),
                "parts": self._selected_parts(),
            }
        )
        return current

    def _collect_cfg(self) -> dict:
        cfg = dict(self.cfg)
        cfg["output_mode"] = self.var_mode.get()
        cfg["output_root"] = self.out_entry.get().strip() or str(cfg.get("output_root") or "")
        cfg["keep_structure"] = self.var_keep.get()
        cfg["dated_session"] = self.var_dated.get()
        cfg["skip_existing"] = self.var_skip.get()
        cfg["upscale"] = {
            **cfg.get("upscale", {}),
            "enabled": self.var_upscale.get(),
            "scale": int(self.var_scale.get()),
            "engine": "auto",
            "model": "models-pro",
            "noise": "denoise3x" if "强" in self.var_noise.get() else "conservative",
        }
        cfg["mosaic"] = self._mosaic_cfg(cfg)
        cfg["metadata"] = {**cfg.get("metadata", {}), "enabled": self.var_meta.get()}
        self.cfg = save_config(cfg)
        return cfg

    def _on_output_change(self) -> None:
        beside = self.var_mode.get() == "beside"
        state = "disabled" if beside else "normal"
        self.out_entry.configure(state=state)
        self._refresh_estimate()

    def _skip_roots(self) -> list[str]:
        cfg = self._peek_cfg()
        roots = [str(resolve_output_root(cfg))]
        return roots

    def _peek_cfg(self) -> dict:
        cfg = dict(self.cfg)
        cfg["output_mode"] = self.var_mode.get()
        cfg["output_root"] = self.out_entry.get().strip() or str(cfg.get("output_root") or "")
        cfg["keep_structure"] = self.var_keep.get()
        cfg["dated_session"] = self.var_dated.get()
        cfg["skip_existing"] = self.var_skip.get()
        cfg["upscale"] = {
            **cfg.get("upscale", {}),
            "enabled": self.var_upscale.get(),
            "scale": int(self.var_scale.get()),
            "engine": "auto",
            "model": "models-pro",
            "noise": "denoise3x" if "强" in self.var_noise.get() else "conservative",
        }
        cfg["mosaic"] = self._mosaic_cfg(cfg)
        cfg["metadata"] = {**cfg.get("metadata", {}), "enabled": self.var_meta.get()}
        return cfg

    def _add_paths(self, raw_paths: list[str]) -> None:
        if self._busy():
            self._append_event("正在处理，先不要继续往里丢。处理完或停止后再加。")
            return
        self.drop_title.configure(text="正在扫描，请稍等…")
        skip_roots = self._skip_roots()

        def work() -> None:
            found = scan_images(raw_paths, skip_roots=skip_roots)
            self.after(0, lambda: self._merge_items(found))

        threading.Thread(target=work, daemon=True).start()

    def _merge_items(self, found: list[QueueItem]) -> None:
        existed = {item.key for item in self.items}
        added = 0
        with self.scan_lock:
            for item in found:
                if item.key in existed:
                    continue
                self.items.append(item)
                existed.add(item.key)
                added += 1
        if added == 0:
            self._append_event("没有新的图片。可能都已在队列里，或文件夹里没有图。")
        else:
            self._append_event(f"加入 {added} 张，当前共 {len(self.items)} 张。")
        self.drop_title.configure(text=f"队列里有 {len(self.items)} 张图")
        self._refresh_estimate()

    def _clear_queue(self) -> None:
        if self._busy():
            return
        self.items.clear()
        self.progress.set(0)
        self.drop_title.configure(text="把图片或文件夹拖到这里")
        self.current_label.configure(text="当前：空闲")
        self.status.configure(text="队列已清空。")
        self._refresh_estimate()

    def _refresh_estimate(self) -> None:
        cfg = self._peek_cfg()
        runtime = mosaic_runtime_status(cfg)
        clones = [
            QueueItem(
                source=item.source,
                size=item.size,
                drop_root=item.drop_root,
                rel_parent=item.rel_parent,
                key=item.key,
            )
            for item in self.items
        ]
        session = make_session_dir(cfg)
        assign_destinations(clones, cfg, session)
        for src, clone in zip(self.items, clones):
            src.dest = clone.dest
            if cfg.get("skip_existing") and clone.dest and clone.dest.exists() and clone.dest.stat().st_size > 0:
                clone.status = "skip"
        pre = build_preflight(clones, cfg, session, mosaic_available=bool(runtime.get("ok")))
        if not self.items:
            self.stats.configure(text="还没有图片。")
            self.eta_label.configure(text="预计：加入图片后显示张数、大小、时间和磁盘。")
        else:
            sample = "、".join(item.source.name for item in self.items[:3])
            more = " …" if len(self.items) > 3 else ""
            self.stats.configure(text=pre["summary"] + f"\n例如：{sample}{more}")
            self.eta_label.configure(text=f"成品：{pre['output_text']}")
        self.disk_label.configure(
            text=f"这盘还剩 {format_bytes(pre['free_bytes'])}。大约需要 {format_bytes(pre['need_bytes'])}。",
            text_color=ERR if pre["blockers"] else MUTED,
        )
        if pre["blockers"] and self.items:
            self.status.configure(text=pre["blockers"][0])

    def _append_event(self, message: str) -> None:
        self.event_box.configure(state="normal")
        self.event_box.insert("end", message.rstrip() + "\n")
        self.event_box.see("end")
        self.event_box.configure(state="disabled")

    def _pick_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="选择图片",
            filetypes=[("图片", "*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.tif;*.tiff"), ("全部", "*.*")],
        )
        if paths:
            self._add_paths(list(paths))

    def _pick_folder(self) -> None:
        folder = filedialog.askdirectory(title="选择图片文件夹")
        if folder:
            self._add_paths([folder])

    def _pick_output(self) -> None:
        folder = filedialog.askdirectory(title="选择成品放置文件夹")
        if folder:
            self.out_entry.configure(state="normal")
            self.out_entry.delete(0, "end")
            self.out_entry.insert(0, folder)
            self.var_mode.set("folder")
            self._on_output_change()

    def _open_output(self) -> None:
        cfg = self._peek_cfg()
        if self.var_mode.get() == "beside":
            target = self.items[0].source.parent / "理塘成品" if self.items else Path.home()
        else:
            target = Path(self.session_dir) if self.session_dir else resolve_output_root(cfg)
        target.mkdir(parents=True, exist_ok=True)
        os.startfile(target)

    def _start(self) -> None:
        if self._busy():
            return
        if not self.items:
            messagebox.showinfo(APP_NAME, "先把图片或文件夹拖进来。")
            return
        if not any((self.var_upscale.get(), self.var_mosaic.get(), self.var_meta.get())):
            messagebox.showinfo(APP_NAME, "请至少勾选超分、打码、清元数据中的一项。")
            return
        cfg = self._collect_cfg()
        for item in self.items:
            item.status = "pending"
            item.error = ""
            item.steps = []
        session = make_session_dir(cfg)
        assign_destinations(self.items, cfg, session)
        runtime = mosaic_runtime_status(cfg)
        pre = build_preflight(self.items, cfg, session, mosaic_available=bool(runtime.get("ok")))
        dialog = ConfirmDialog(self, pre)
        self.wait_window(dialog)
        if not getattr(dialog, "result", False):
            return
        if not pre["ok"]:
            return
        if session and cfg.get("dated_session"):
            cfg["_session_dir"] = str(session)
            self.cfg = save_config({k: v for k, v in cfg.items() if k != "_session_dir"})
            cfg = {**self.cfg, "_session_dir": str(session)}
        self.control = JobControl()
        self.start_btn.configure(state="disabled")
        self.pause_btn.configure(state="normal", text="暂停")
        self.stop_btn.configure(state="normal")
        self.progress.set(0)
        self.status.configure(text="开始处理…")
        items = self.items

        def work() -> None:
            run_job(items, cfg, progress=self._on_progress, control=self.control)
            self.after(0, self._on_finished)

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _on_progress(self, payload: dict) -> None:
        def apply() -> None:
            total = int(payload.get("total") or 0)
            done = int(payload.get("done") or 0)
            if total:
                self.progress.set(done / total)
            self.status.configure(text=str(payload.get("message") or ""))
            if payload.get("session"):
                self.session_dir = str(payload["session"])
            current = payload.get("current")
            if current and payload.get("item_status") == "running":
                self.current_label.configure(text=f"当前：{Path(str(current)).name}")
            eta = payload.get("eta_sec")
            rate = payload.get("rate_per_min") or 0
            if eta is not None:
                self.eta_label.configure(
                    text=f"已用 {format_duration(payload.get('elapsed_sec'))} · 剩余约 {format_duration(eta)} · {rate:.1f} 张/分"
                )
            if payload.get("log"):
                self._append_event(str(payload["log"]))

        self.after(0, apply)

    def _on_finished(self) -> None:
        self.start_btn.configure(state="normal")
        self.pause_btn.configure(state="disabled", text="暂停")
        self.stop_btn.configure(state="disabled")
        self.control.pause.clear()
        self._refresh_estimate()

    def _toggle_pause(self) -> None:
        if not self._busy():
            return
        if self.control.pause.is_set():
            self.control.pause.clear()
            self.pause_btn.configure(text="暂停")
            self.status.configure(text="已继续。")
        else:
            self.control.pause.set()
            self.pause_btn.configure(text="继续")
            self.status.configure(text="已暂停，当前这张做完后会停住。")

    def _stop(self) -> None:
        self.control.cancel.set()
        self.control.pause.clear()
        self.status.configure(text="正在停止，当前这张做完就停。已完成的下次会跳过。")

    def _retry(self) -> None:
        if self._busy():
            return
        failed = [item for item in self.items if item.status == "fail"]
        if not failed:
            messagebox.showinfo(APP_NAME, "没有失败的图片。")
            return
        retry_failed(self.items)
        self._append_event(f"重新排队 {len(failed)} 张失败图片。")
        self._start()

    def _on_close(self) -> None:
        if self._busy():
            if not messagebox.askyesno(APP_NAME, "正在处理。关闭后已完成的不用重做，确定关闭吗？"):
                return
            self.control.cancel.set()
        self.destroy()


def run_app() -> None:
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("green")
    app = LitangApp()
    app.mainloop()
