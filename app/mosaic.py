from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from app.config import discover_anr_python, is_bundled_runtime, load_config
from app.detect_geom import box_expand_for_sensitivity, sensitivity_to_conf
from app.util import child_process_kwargs, wait_process

MOSAIC_PARTS = ["欧金金", "欧芒果", "欧派派", "欧西利"]
MOSAIC_METHODS = ["像素", "模糊", "线条", "纯色", "表情"]


class MosaicNoTarget(RuntimeError):
    """ANR 跑过了，但没找到需要打码的部位。"""


_RUNTIME_CACHE: tuple[str, dict[str, Any]] | None = None


def _allowed_python_name(path: str) -> bool:
    return Path(path).name.lower() in {"python.exe", "python", "pythonw.exe", "pythonw"}


def mosaic_runtime_status(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    global _RUNTIME_CACHE
    cfg = cfg or load_config()
    cache_key = f"{cfg.get('anr_root')}|{cfg.get('anr_python')}"
    if _RUNTIME_CACHE and _RUNTIME_CACHE[0] == cache_key and _RUNTIME_CACHE[1].get("ok"):
        python_ok = Path(str(_RUNTIME_CACHE[1].get("anr_python") or "")).is_file()
        if python_ok:
            return dict(_RUNTIME_CACHE[1])
        _RUNTIME_CACHE = None
    anr_root = Path(str(cfg.get("anr_root") or "")).expanduser()
    plugin = anr_root / "plugins" / "anr_plugin_auto_mosaics"
    required = [plugin / "detector.py", plugin / "mosaics.py"]
    missing = [path.name for path in required if not path.is_file()]
    python_path = str(cfg.get("anr_python") or discover_anr_python(str(anr_root)))
    if missing:
        result = {
            "ok": False,
            "anr_root": str(anr_root),
            "anr_python": python_path,
            "message": "未找到 ANR 打码插件，超分和清元数据仍可用",
        }
    elif not python_path or not Path(python_path).is_file() or not _allowed_python_name(python_path):
        result = {
            "ok": False,
            "anr_root": str(anr_root),
            "anr_python": python_path,
            "message": "找到了 ANR，但缺少它自带的 Python，打码暂不可用",
        }
    else:
        result = {
            "ok": True,
            "anr_root": str(anr_root.resolve()),
            "anr_python": python_path,
            "message": (
                "已内置打码环境（加强识别：低阈值 + 切块 + 框外扩）"
                if is_bundled_runtime()
                else "ANR 打码可用（加强识别：低阈值 + 切块 + 框外扩）"
            ),
        }
    if result.get("ok"):
        _RUNTIME_CACHE = (cache_key, result)
    elif _RUNTIME_CACHE and _RUNTIME_CACHE[0] == cache_key:
        _RUNTIME_CACHE = None
    return dict(result)


def mosaic_detect_extra(mosaic_cfg: dict[str, Any]) -> dict[str, Any]:
    sensitivity = max(1, min(int(mosaic_cfg.get("sensitivity") or 8), 10))
    return {
        "color": str(mosaic_cfg.get("color") or "#808080"),
        "emoji_dir": str(mosaic_cfg.get("emoji_dir") or ""),
        "dilate": int(mosaic_cfg.get("dilate") or 28),
        "sensitivity": sensitivity,
        "conf": float(mosaic_cfg.get("conf") or sensitivity_to_conf(sensitivity)),
        "box_expand": float(mosaic_cfg.get("box_expand") or box_expand_for_sensitivity(sensitivity)),
        "imgsz": int(mosaic_cfg.get("imgsz") or 1280),
        "tiles": bool(mosaic_cfg.get("tiles", True)),
        "augment": bool(mosaic_cfg.get("augment", True)),
        "enhance": bool(mosaic_cfg.get("enhance", True)),
    }


def _detector_parts_with_fallback(parts: list[str]) -> list[list[str]]:
    normalized = [str(item).strip() for item in parts if str(item).strip() in MOSAIC_PARTS]
    broad = list(MOSAIC_PARTS)
    attempts: list[list[str]] = []
    if normalized:
        attempts.append(normalized)
    if set(normalized) != set(broad):
        attempts.append(broad)
    return attempts or [broad]


class MosaicSession:
    def __init__(self, cfg: dict[str, Any]) -> None:
        self.cfg = cfg
        self.runtime = mosaic_runtime_status(cfg)
        self.proc: subprocess.Popen[str] | None = None
        self.lock = threading.Lock()
        self._lines: queue.Queue[str | None] = queue.Queue()
        if self.runtime.get("ok"):
            self._start()

    def _start(self) -> None:
        daemon = Path(__file__).resolve().parent / "anr_mosaic_daemon.py"
        self.proc = subprocess.Popen(
            [str(self.runtime["anr_python"]), str(daemon), str(self.runtime["anr_root"])],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(self.runtime["anr_root"]),
            **child_process_kwargs(),
        )
        self._lines = queue.Queue()
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        threading.Thread(target=self._pump_stdout, args=(self.proc, self._lines), daemon=True).start()
        ready = self._read_message(timeout=90)
        if ready != "READY":
            self.close()
            raise RuntimeError((ready or "打码进程没有就绪").strip())

    def _drain_stderr(self) -> None:
        if not self.proc or not self.proc.stderr:
            return
        for _line in self.proc.stderr:
            pass

    def _pump_stdout(self, proc: subprocess.Popen[str], box: queue.Queue[str | None]) -> None:
        stdout = proc.stdout
        if stdout is None:
            box.put(None)
            return
        try:
            for line in stdout:
                box.put(line)
        finally:
            box.put(None)

    def _cancelled(self) -> bool:
        cancel = self.cfg.get("_cancel")
        return bool(cancel is not None and getattr(cancel, "is_set", lambda: False)())

    def _read_message(self, timeout: float = 600) -> str:
        deadline = time.monotonic() + timeout
        seen = 0
        while seen < 4000:
            if self._cancelled():
                self.close()
                raise RuntimeError("已停止")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.close()
                raise RuntimeError("打码超时")
            try:
                line = self._lines.get(timeout=min(0.3, remaining))
            except queue.Empty:
                if self.proc is not None and self.proc.poll() is not None:
                    return ""
                continue
            if line is None:
                return ""
            seen += 1
            text = line.strip()
            if text.startswith("LITANG:"):
                return text[7:]
        return ""

    def _alive(self) -> bool:
        return bool(self.proc) and self.proc.poll() is None

    def run(self, source: Path, output_dir: Path) -> Path:
        with self.lock:
            if not self._alive():
                self._start()
            mosaic_cfg = self.cfg.get("mosaic") or {}
            req = {
                "source": str(source.resolve()),
                "method": str(mosaic_cfg.get("method") or "像素"),
                "intensity": int(mosaic_cfg.get("intensity") or 36),
                "attempts": _detector_parts_with_fallback(list(mosaic_cfg.get("parts") or MOSAIC_PARTS)),
                "session_dir": str(output_dir.resolve()),
                "extra": mosaic_detect_extra(mosaic_cfg),
            }
            assert self.proc and self.proc.stdin and self.proc.stdout
            self.proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
            text = self._read_message(timeout=600)
            if text.startswith("SUCCESS:"):
                out = Path(text.split(":", 1)[1].strip())
                if out.is_file():
                    return out
                raise RuntimeError("打码声明成功，但文件不存在")
            if "未检测" in text or "未产出遮罩" in text:
                raise MosaicNoTarget(text.replace("ERROR:", "").strip() or "未检测到可打码目标")
            raise RuntimeError(text.replace("ERROR:", "").strip() or "打码进程无响应")

    def close(self) -> None:
        proc = self.proc
        self.proc = None
        if not proc:
            return
        try:
            if proc.stdin:
                proc.stdin.write('{"cmd":"quit"}\n')
                proc.stdin.flush()
        except Exception:
            pass
        try:
            proc.kill()
        except Exception:
            pass


def run_anr_mosaic(source: Path, output_dir: Path, cfg: dict[str, Any]) -> Path:
    session = cfg.get("_mosaic_session")
    run = getattr(session, "run", None)
    if callable(run):
        return session.run(source, output_dir)
    runtime = mosaic_runtime_status(cfg)
    if not runtime.get("ok"):
        raise RuntimeError(str(runtime.get("message") or "ANR 打码不可用"))
    mosaic_cfg = cfg.get("mosaic") or {}
    extra = mosaic_detect_extra(mosaic_cfg)
    output_dir.mkdir(parents=True, exist_ok=True)
    worker = Path(__file__).resolve().parent / "anr_mosaic_daemon.py"
    proc = subprocess.Popen(
        [
            str(runtime["anr_python"]),
            str(worker),
            "--once",
            str(runtime["anr_root"]),
            str(source.resolve()),
            str(mosaic_cfg.get("method") or "像素"),
            str(int(mosaic_cfg.get("intensity") or 36)),
            json.dumps(_detector_parts_with_fallback(list(mosaic_cfg.get("parts") or MOSAIC_PARTS)), ensure_ascii=False),
            str(output_dir.resolve()),
            json.dumps(extra, ensure_ascii=False),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        **child_process_kwargs(),
    )
    stdout, stderr, code = wait_process(proc, 600, cfg.get("_cancel"))
    result_stdout = stdout
    result_stderr = stderr
    result_code = code
    if result_code == 10:
        err = (result_stderr or "").strip()
        if err.startswith("ERROR: "):
            err = err[7:]
        raise MosaicNoTarget(err or "未检测到可打码目标")
    if result_code != 0:
        err = (result_stderr or result_stdout or "").strip()
        raise RuntimeError(err or f"ANR 打码失败 (code {result_code})")
    success_lines = [line for line in (result_stdout or "").splitlines() if line.startswith("SUCCESS: ")]
    if not success_lines:
        raise RuntimeError(f"ANR 打码未返回成功结果：{(result_stdout or '').strip()}")
    out_path = Path(success_lines[0][9:].strip()).resolve()
    if not out_path.is_file():
        raise RuntimeError("ANR 打码声明成功，但输出文件不存在")
    return out_path
