from __future__ import annotations

import json
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from app.collect import QueueItem
from app.config import save_config
from app.eta import EtaEstimator
from app.mosaic import MosaicSession, mosaic_runtime_status
from app.quality import SignatureStore, get_store, quality_signature
from app.upscale import upscale_status
from app.output import assign_destinations, make_session_dir, output_label, resolve_output_root
from app.pipeline import (
    abort_process,
    advance_mosaic,
    advance_upscale,
    finish_process,
    item_work_dir,
    process_item,
    start_process,
)
from app.preflight import build_preflight
from app.util import allow_sleep, format_bytes, format_duration, prevent_sleep

ProgressCb = Callable[[dict[str, Any]], None]


class JobControl:
    def __init__(self) -> None:
        self.cancel = threading.Event()
        self.pause = threading.Event()

    def wait_if_paused(self) -> None:
        while self.pause.is_set() and not self.cancel.is_set():
            time.sleep(0.15)


def _append(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _mark_existing(items: list[QueueItem], cfg: dict[str, Any]) -> None:
    if not cfg.get("skip_existing", True):
        return
    store = get_store(cfg)
    signature = quality_signature(cfg)
    for item in items:
        dest = item.dest
        if dest and store.matches(dest, signature):
            item.status = "skip"
            item.steps = ["skip:same-quality"]


def _using_gpu_upscale(cfg: dict[str, Any]) -> bool:
    up = cfg.get("upscale") or {}
    if not up.get("enabled", True):
        return False
    engine = str(up.get("engine") or "auto")
    if engine not in {"", "auto", "realcugan", "realcugan-pro"}:
        return False
    return bool(upscale_status(cfg).get("ok"))


def _parallel_plan(cfg: dict[str, Any], mosaic_on: bool) -> tuple[int, bool]:
    """返回 (线程数, 是否超分/打码流水线重叠)。不降低画质。"""
    if _using_gpu_upscale(cfg) and mosaic_on:
        return 1, True
    if _using_gpu_upscale(cfg):
        return 1, False
    return max(1, min(int(cfg.get("workers") or 2), 3)), False


def _record_dir(session_dir: Path | None, cfg: dict[str, Any], items: list[QueueItem] | None = None) -> Path:
    if session_dir is not None:
        return session_dir / "_理塘百宝箱记录"
    if str(cfg.get("output_mode") or "folder") == "beside":
        if items:
            for item in items:
                if item.dest:
                    return item.dest.parent / "_理塘百宝箱记录"
            return items[0].source.parent / "理塘成品" / "_理塘百宝箱记录"
        return Path(tempfile.gettempdir()) / "litang-baibaoxiang" / "logs"
    return resolve_output_root(cfg) / "_理塘百宝箱记录"


def _write_job_readme(record_dir: Path, cfg: dict[str, Any], preflight: dict[str, Any]) -> Path:
    target = record_dir
    target.mkdir(parents=True, exist_ok=True)
    text = (
        f"理塘百宝箱任务\n"
        f"时间：{datetime.now().isoformat(timespec='seconds')}\n"
        f"输出：{preflight.get('output_text')}\n"
        f"数量：{preflight.get('count')} 张\n"
        f"大小：{format_bytes(int(preflight.get('total_bytes') or 0))}\n"
        f"预计：{format_duration(preflight.get('eta_sec'))}\n"
        f"超分：{(cfg.get('upscale') or {}).get('enabled')} x{(cfg.get('upscale') or {}).get('scale')}\n"
        f"打码：{(cfg.get('mosaic') or {}).get('enabled')} {(cfg.get('mosaic') or {}).get('method')} 识别{(cfg.get('mosaic') or {}).get('sensitivity') or 8}\n"
        f"清元数据：{(cfg.get('metadata') or {}).get('enabled')}\n"
        f"已有成品跳过：{cfg.get('skip_existing', True)}\n"
        f"原图不会被修改。\n"
    )
    readme = target / "任务说明.txt"
    readme.write_text(text, encoding="utf-8")
    marker = target / ".litang-job.json"
    marker.write_text(
        json.dumps(
            {
                "app": "litang-baibaoxiang",
                "started": datetime.now().isoformat(timespec="seconds"),
                "count": preflight.get("count"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return target


def _work_root() -> Path:
    root = Path(tempfile.gettempdir()) / "litang-baibaoxiang" / "work"
    root.mkdir(parents=True, exist_ok=True)
    return root


def run_job(
    items: list[QueueItem],
    cfg: dict[str, Any],
    *,
    progress: ProgressCb | None = None,
    cancel_flag: Any | None = None,
    control: JobControl | None = None,
) -> dict[str, Any]:
    control = control or JobControl()
    _mirror_cancel = cancel_flag if cancel_flag is not None and getattr(cancel_flag, "is_set", None) else None

    session_dir = make_session_dir(cfg)
    if session_dir:
        session_dir.mkdir(parents=True, exist_ok=True)
    assign_destinations(items, cfg, session_dir)
    log_dir = _record_dir(session_dir, cfg, items)
    log_dir.mkdir(parents=True, exist_ok=True)
    cfg["_record_dir"] = str(log_dir)
    cfg["_sig_store"] = SignatureStore(log_dir)
    _mark_existing(items, cfg)
    runtime = mosaic_runtime_status(cfg)
    cfg["_mosaic_runtime"] = runtime
    preflight = build_preflight(items, cfg, session_dir, mosaic_available=bool(runtime.get("ok")))
    log_path = log_dir / "处理记录.txt"
    done_path = log_dir / "completed.jsonl"
    fail_path = log_dir / "失败清单.txt"
    miss_path = log_dir / "漏打清单.txt"
    _write_job_readme(log_dir, cfg, preflight)

    pending = [item for item in items if item.status == "pending"]
    skipped = [item for item in items if item.status in {"skip", "ok"}]
    ok = len(skipped)
    fail = 0
    processed_bytes = sum(item.size for item in skipped)
    total = len(items)
    total_bytes = sum(item.size for item in items)
    started = time.monotonic()
    seed = cfg.get("perf") or {}
    eta = EtaEstimator(float(seed.get("sec_per_mb") or 0), float(seed.get("sec_per_image") or 0))
    if skipped:
        _append(log_path, f"[{datetime.now().strftime('%H:%M:%S')}] 跳过已有成品 {len(skipped)} 张")
    work_root = _work_root() / datetime.now().strftime("%Y%m%d-%H%M%S")
    work_root.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    cursor = 0

    def emit(payload: dict[str, Any]) -> None:
        if progress:
            progress(payload)

    def cancelled() -> bool:
        if _mirror_cancel is not None and _mirror_cancel.is_set():
            control.cancel.set()
        return control.cancel.is_set()

    def snapshot(status: str, message: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        elapsed = time.monotonic() - started
        leftover_items = [item for item in pending if item.status == "pending"]
        leftover_bytes = sum(item.size for item in leftover_items)
        remain = eta.remaining(leftover_bytes, len(leftover_items))
        done = ok + fail
        rate = (done / elapsed * 60) if elapsed > 0 and done else 0.0
        payload = {
            "status": status,
            "message": message,
            "total": total,
            "done": done,
            "ok": ok,
            "fail": fail,
            "skip": len(skipped),
            "elapsed_sec": elapsed,
            "eta_sec": remain,
            "rate_per_min": rate,
            "processed_bytes": processed_bytes,
            "total_bytes": total_bytes,
            "session": str(session_dir or log_dir),
            "output_text": output_label(cfg, session_dir),
        }
        if extra:
            payload.update(extra)
        return payload

    if not pending and not skipped:
        message = "没有找到可处理的图片。"
        emit(snapshot("empty", message))
        return {"ok": False, "message": message, "session": str(session_dir or ""), "results": []}

    if not pending:
        message = f"这些图都已经有成品了，无需再跑。位置：{output_label(cfg, session_dir)}"
        emit(snapshot("done", message))
        return {"ok": True, "message": message, "session": str(session_dir or log_dir), "ok_count": ok, "fail_count": 0}

    mosaic_on = bool((cfg.get("mosaic") or {}).get("enabled") and runtime.get("ok"))
    workers, staged = _parallel_plan(cfg, mosaic_on)
    mosaic_session = None
    if mosaic_on:
        try:
            mosaic_session = MosaicSession(cfg)
            cfg["_mosaic_session"] = mosaic_session
        except Exception:
            mosaic_session = None
    prevent_sleep()
    emit(
        snapshot(
            "running",
            f"开始处理 {len(pending)} 张，{output_label(cfg, session_dir)}",
            {"log": f"开始处理 {len(pending)} 张，跳过 {len(skipped)} 张"},
        )
    )

    def take_next() -> QueueItem | None:
        nonlocal cursor
        with lock:
            while cursor < len(pending):
                item = pending[cursor]
                cursor += 1
                if item.status == "pending":
                    item.status = "running"
                    return item
            return None

    def finish_item(item: QueueItem, elapsed: float, error: str = "") -> None:
        nonlocal ok, fail, processed_bytes
        stamp = datetime.now().strftime("%H:%M:%S")
        with lock:
            processed_bytes += item.size
            if error:
                item.status = "fail"
                item.error = error
                fail += 1
                _append(log_path, f"[{stamp}] 失败：{item.source} → {error}")
                _append(fail_path, f"{item.source}\t{error}")
                extra = {"item_status": "fail", "current": str(item.source), "log": f"失败 {item.source.name}：{error}"}
            else:
                if item.status != "skip":
                    item.status = "ok"
                ok += 1
                eta.update(item.size, elapsed)
                dest = str(item.dest) if item.dest else ""
                if any(step.startswith("mosaic:none") or step.startswith("mosaic:skip") for step in item.steps):
                    _append(miss_path, f"{item.source}\t{dest}\t{' / '.join(item.steps)}")
                _append(log_path, f"[{stamp}] 完成：{item.source.name} → {dest}（{' / '.join(item.steps) or '完成'}）")
                _append(
                    done_path,
                    json.dumps({"src": str(item.source), "dest": dest, "steps": item.steps}, ensure_ascii=False),
                )
                extra = {
                    "item_status": "skip" if item.status == "skip" else "ok",
                    "current": str(item.source),
                    "steps": item.steps,
                    "log": f"完成 {item.source.name}",
                }
            leftover = len([row for row in pending if row.status == "pending"])
            remain = eta.remaining(
                sum(row.size for row in pending if row.status == "pending"),
                leftover,
            )
            message = (
                f"{ok + fail}/{total} 张 · 成功 {ok} · 失败 {fail} · "
                f"已用 {format_duration(time.monotonic() - started)} · "
                f"剩余约 {format_duration(remain)}"
            )
        emit(snapshot("running", message, extra))

    def apply_result(item: QueueItem, result) -> None:
        item.steps = result.steps
        item.status = "skip" if result.skipped else ("ok" if result.ok else "fail")
        item.error = "" if result.ok else result.message

    def worker() -> None:
        while not cancelled():
            control.wait_if_paused()
            if cancelled():
                return
            item = take_next()
            if item is None:
                return
            emit(
                snapshot(
                    "running",
                    f"正在处理 {item.source.name}（{format_bytes(item.size)}）",
                    {"current": str(item.source), "item_status": "running", "current_size": item.size},
                )
            )
            began = time.monotonic()
            try:
                process_item(item, work_root, cfg)
                finish_item(item, time.monotonic() - began)
            except Exception as exc:
                finish_item(item, time.monotonic() - began, error=str(exc))

    def run_staged() -> None:
        from queue import Queue

        mid: Queue = Queue(maxsize=1)
        fin: Queue = Queue(maxsize=1)

        def upscale_loop() -> None:
            try:
                while not cancelled():
                    control.wait_if_paused()
                    if cancelled():
                        break
                    item = take_next()
                    if item is None:
                        break
                    emit(
                        snapshot(
                            "running",
                            f"正在处理 {item.source.name}（{format_bytes(item.size)}）",
                            {"current": str(item.source), "item_status": "running", "current_size": item.size},
                        )
                    )
                    began = time.monotonic()
                    try:
                        if item.dest is None:
                            raise RuntimeError("还没有分配成品路径")
                        state = start_process(item.source, item.dest, item_work_dir(item, work_root), cfg)
                        if state.result is not None:
                            apply_result(item, state.result)
                            finish_item(item, time.monotonic() - began)
                            continue
                        advance_upscale(state)
                        mid.put((item, state, began))
                    except Exception as exc:
                        finish_item(item, time.monotonic() - began, error=str(exc))
            finally:
                mid.put(None)

        def mosaic_loop() -> None:
            try:
                while True:
                    payload = mid.get()
                    if payload is None:
                        return
                    item, state, began = payload
                    try:
                        advance_mosaic(state)
                        fin.put((item, state, began))
                    except Exception as exc:
                        abort_process(state)
                        finish_item(item, time.monotonic() - began, error=str(exc))
            finally:
                fin.put(None)

        def finalize_loop() -> None:
            while True:
                payload = fin.get()
                if payload is None:
                    return
                item, state, began = payload
                try:
                    result = finish_process(state)
                    apply_result(item, result)
                    finish_item(item, time.monotonic() - began)
                except Exception as exc:
                    abort_process(state)
                    finish_item(item, time.monotonic() - began, error=str(exc))

        threads = [
            threading.Thread(target=upscale_loop, daemon=True, name="litang-upscale"),
            threading.Thread(target=mosaic_loop, daemon=True, name="litang-mosaic"),
            threading.Thread(target=finalize_loop, daemon=True, name="litang-finalize"),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    try:
        if staged:
            run_staged()
        else:
            threads = [threading.Thread(target=worker, daemon=True, name=f"litang-worker-{idx}") for idx in range(workers)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
    finally:
        if mosaic_session is not None:
            mosaic_session.close()
            cfg.pop("_mosaic_session", None)
        try:
            get_store(cfg).flush()
        except Exception:
            pass
        shutil_rm = True
        try:
            import shutil

            shutil.rmtree(work_root, ignore_errors=True)
        except Exception:
            shutil_rm = False
        allow_sleep()
        _ = shutil_rm

    elapsed = time.monotonic() - started
    if eta.samples:
        perf = dict(cfg.get("perf") or {})
        perf["sec_per_mb"] = eta.sec_per_mb
        perf["sec_per_image"] = eta.sec_per_image
        perf["samples"] = int(perf.get("samples") or 0) + eta.samples
        cfg["perf"] = perf
        if cfg.get("persist_perf", True):
            try:
                save_config(cfg)
            except Exception:
                pass

    if cancelled():
        message = (
            f"已停止：成功 {ok}，失败 {fail}。已经做好的不用重做，下次会自动跳过。"
            f"位置：{output_label(cfg, session_dir)}"
        )
        status = "cancelled"
    else:
        message = f"全部完成：成功 {ok}/{total} 张"
        if fail:
            message += f"，失败 {fail} 张"
        message += f"。{output_label(cfg, session_dir)}"
        status = "done"
    _append(log_path, f"[{datetime.now().strftime('%H:%M:%S')}] {message} 用时 {format_duration(elapsed)}")
    emit(snapshot(status, message, {"log": message}))
    return {
        "ok": fail == 0 and not cancelled(),
        "message": message,
        "session": str(session_dir or log_dir),
        "ok_count": ok,
        "fail_count": fail,
        "skip_count": len(skipped),
        "items": items,
    }


def retry_failed(items: list[QueueItem]) -> list[QueueItem]:
    for item in items:
        if item.status == "fail":
            item.status = "pending"
            item.error = ""
            item.steps = []
    return items
