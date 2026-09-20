# -*- coding: utf-8 -*-
"""用上一版 Release 的完整运行时刷新出当前版本 Windows 一键包。

这个脚本不把第三方模型/运行时提交进 git。CI 从上一版已发布的一键包取运行时，
只替换本仓库 app 源码、默认配置和说明，再做完整性/导入校验并重新压缩。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
BODY_NAMES = ("软件本体-请勿删除", "软件本体-安装文件勿删")
BODY_NAME = "软件本体-请勿删除"


def _safe_extract(archive: zipfile.ZipFile, dest: Path) -> None:
    root = dest.resolve()
    for info in archive.infolist():
        target = (dest / info.filename).resolve()
        if os.path.commonpath([str(root), str(target)]) != str(root):
            raise RuntimeError(f"压缩包包含不安全路径：{info.filename}")
    archive.extractall(dest)


def _zip_has_full_runtime(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as zf:
            names = [name.replace("\\", "/").lower().strip("/") for name in zf.namelist()]
    except zipfile.BadZipFile:
        return False
    has_app = any(name.endswith("app/__main__.py") for name in names)
    has_python = any(name.endswith("python.exe") for name in names)
    return has_app and has_python


def find_seed_zip(seed_dir: Path) -> Path:
    zips = sorted(seed_dir.rglob("*.zip"))
    for path in zips:
        if _zip_has_full_runtime(path):
            return path
    found = "\n".join(str(path) for path in zips) or "（没有 zip）"
    raise SystemExit(
        "没有在上一版 Release 里找到完整 Windows 一键包。\n"
        "要求包内存在 软件本体-请勿删除/runtime/anr/Python/python.exe。\n"
        f"已检查：\n{found}"
    )


def find_body(root: Path) -> Path:
    for name in BODY_NAMES:
        for body in root.rglob(name):
            if (body / "app" / "__main__.py").is_file() and any(body.rglob("python.exe")):
                return body
    for main in root.rglob("__main__.py"):
        if main.parent.name != "app":
            continue
        body = main.parent.parent
        if any(body.rglob("python.exe")):
            return body
    raise SystemExit("解压后没有找到同时包含 app 和内置 Python 的软件本体。")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace("\r\n", "\n").replace("\n", "\r\n"), encoding="utf-8")


def replace_app(body: Path) -> None:
    target = body / "app"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(
        APP_ROOT / "app",
        target,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    shutil.copy2(APP_ROOT / "requirements.txt", body / "requirements.txt")

    data = body / "data"
    data.mkdir(parents=True, exist_ok=True)
    config = {
        "anr_root": "",
        "anr_python": "",
        "output_mode": "folder",
        "output_root": "",
        "keep_structure": True,
        "dated_session": False,
        "skip_existing": True,
    }
    (data / "config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for stale in (data / "last_error.txt", data / "quality_signatures.json"):
        try:
            stale.unlink()
        except FileNotFoundError:
            pass


def write_launcher(package_root: Path) -> None:
    write_text(
        package_root / "启动理塘百宝箱.bat",
        """@echo off
chcp 65001 >nul
title 理塘百宝箱
cd /d "%~dp0"
set "ROOT=%~dp0软件本体-请勿删除"
set "PY=%ROOT%\\runtime\\anr\\Python\\python.exe"
if not exist "%PY%" (
  echo 软件不完整。请重新下载并完整解压整个一键包，不要只复制启动文件。
  pause
  exit /b 1
)
"%PY%" -m app
if errorlevel 1 (
  echo.
  echo 启动失败。请把 软件本体-请勿删除\\data\\last_error.txt 发给作者。
  pause
)
""",
    )


def write_readme(package_root: Path, version: str) -> None:
    write_text(
        package_root / "使用说明.txt",
        f"""理塘百宝箱 Windows 一键包  v{version}

【第一次用】
1. 完整解压 ZIP；不要直接在压缩软件里运行。
2. 双击「启动理塘百宝箱.bat」。
3. 选成品目录，把图片/文件夹拖进去，点「开始处理」。
4. 原图不会被修改，处理结果会写到你选择的目录。

【这个包已经包含】
- Python 运行时
- 打码识别模型与 ANR 打码插件
- Real-CUGAN 二次元超分
- GUI 所需依赖

不需要另外安装 Python、pip 或 ANR。

【提示】
- 推荐 Windows 10/11 64 位。
- AI 超分依赖显卡/Vulkan 驱动；驱动太旧时软件会回退到本机 Lanczos。
- Real-ESRGAN / Waifu2x 只有在运行时里存在对应程序时才会启用；没有时不会阻止使用。
- 打码属于自动识别，发布前仍建议人工复核。
- 遇到启动错误，把「软件本体-请勿删除\\data\\last_error.txt」发给作者。
""",
    )
    write_text(
        package_root / "版本.txt",
        f"理塘百宝箱 {version}\n基于上一版已发布完整运行时刷新；源码为当前 Release 对应版本。\n",
    )


def verify(body: Path, version: str) -> None:
    py = body / "runtime" / "anr" / "Python" / "python.exe"
    required = [
        py,
        body / "app" / "__main__.py",
        body / "runtime" / "anr" / "plugins" / "anr_plugin_auto_mosaics" / "detector.py",
        body / "runtime" / "anr" / "plugins" / "anr_plugin_auto_mosaics" / "mosaics.py",
        body / "runtime" / "anr" / "plugins" / "anr_plugin_auto_mosaics" / "models" / "yolo" / "censor.pt",
        body / "runtime" / "anr" / "assets" / "realcugan-ncnn-vulkan" / "realcugan-ncnn-vulkan.exe",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("刷新后的一键包缺文件：\n" + "\n".join(missing))

    code = (
        "import app, customtkinter, windnd, PIL; "
        "from app.config import bundled_anr_root; "
        "assert app.__version__ == " + repr(version) + "; "
        "assert bundled_anr_root(); "
        "print('oneclick-ok', app.__version__)"
    )
    result = subprocess.run(
        [str(py), "-c", code],
        cwd=str(body),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if result.returncode != 0:
        raise SystemExit((result.stderr or result.stdout or "一键包 Python 自检失败").strip())
    print((result.stdout or "").strip())


def make_zip(package_root: Path) -> Path:
    archive_base = package_root.parent / package_root.name
    archive = Path(
        shutil.make_archive(
            str(archive_base),
            "zip",
            root_dir=str(package_root.parent),
            base_dir=package_root.name,
        )
    )
    return archive


def refresh(seed_dir: Path, dist_dir: Path) -> Path:
    sys.path.insert(0, str(APP_ROOT))
    from app import __version__

    seed_zip = find_seed_zip(seed_dir)
    print(f"使用上一版完整包：{seed_zip}")
    dist_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="litang-oneclick-") as tmp:
        extracted = Path(tmp) / "seed"
        extracted.mkdir()
        with zipfile.ZipFile(seed_zip) as zf:
            _safe_extract(zf, extracted)

        old_body = find_body(extracted)
        old_package = old_body.parent
        package_root = dist_dir / f"理塘百宝箱-Windows-v{__version__}"
        if package_root.exists():
            shutil.rmtree(package_root)
        shutil.copytree(old_package, package_root)

    body = None
    for name in BODY_NAMES:
        candidate = package_root / name
        if candidate.is_dir():
            body = candidate
            break
    if body is None:
        raise SystemExit("复制后找不到软件本体目录。")
    if body.name != BODY_NAME:
        normalized = package_root / BODY_NAME
        if normalized.exists():
            shutil.rmtree(normalized)
        body.rename(normalized)
        body = normalized

    replace_app(body)
    write_launcher(package_root)
    write_readme(package_root, __version__)
    verify(body, __version__)

    archive = make_zip(package_root)
    print(f"完成：{archive}")
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description="从上一版 Release 刷新 Windows 完整一键包")
    parser.add_argument("--seed-dir", required=True, help="gh release download 的目录")
    parser.add_argument("--dist-dir", default="dist", help="输出目录")
    args = parser.parse_args()
    archive = refresh(Path(args.seed_dir), Path(args.dist_dir))
    print(f"ONECLICK_ZIP={archive.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
