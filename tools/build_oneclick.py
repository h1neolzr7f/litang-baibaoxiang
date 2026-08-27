# -*- coding: utf-8 -*-
"""把理塘百宝箱打成可发给别人的 Windows 一键包。"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
from slim_runtime import slim_optional_assets, slim_site_packages

BODY_NAME = "软件本体-请勿删除"
GUI_PACKAGES = ("customtkinter", "darkdetect", "packaging", "windnd")


def default_dest() -> Path:
    releases = Path(r"E:\Packages\releases")
    if releases.is_dir():
        return releases / "理塘百宝箱一键包"
    return APP_ROOT / "dist" / "理塘百宝箱一键包"


def find_anr_root() -> Path:
    sys.path.insert(0, str(APP_ROOT))
    from app.config import discover_anr_root

    raw = discover_anr_root()
    if not raw:
        raise SystemExit("本机没有找到 ANR。请先保证开发机上的打码环境可用，再打包。")
    root = Path(raw)
    if not (root / "Python" / "python.exe").is_file():
        raise SystemExit(f"ANR 自带 Python 不完整：{root}")
    yolo = root / "plugins" / "anr_plugin_auto_mosaics" / "models" / "yolo" / "censor.pt"
    if not yolo.is_file():
        raise SystemExit(f"缺少打码模型：{yolo}")
    cugan = root / "assets" / "realcugan-ncnn-vulkan" / "realcugan-ncnn-vulkan.exe"
    if not cugan.is_file():
        raise SystemExit(f"缺少 Real-CUGAN：{cugan}")
    return root


def copytree(src: Path, dest: Path, *, ignore=None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest, ignore=ignore, dirs_exist_ok=False)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace("\r\n", "\n").replace("\n", "\r\n"), encoding="utf-8")


def copy_python(src: Path, dest: Path) -> None:
    print(f"复制打码/超分运行时：{src} -> {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)

    def ignore(_directory: str, names: list[str]) -> set[str]:
        skip = set()
        for name in names:
            low = name.lower()
            if name in {"__pycache__", "Doc", ".git"} or low.endswith((".pyc", ".pyo")):
                skip.add(name)
        return skip

    shutil.copytree(src, dest, ignore=ignore)


def copy_gui_packages(dest_python: Path) -> None:
    src_site = APP_ROOT / ".venv" / "Lib" / "site-packages"
    dest_site = dest_python / "Lib" / "site-packages"
    if not src_site.is_dir():
        raise SystemExit("开发环境 .venv 不存在，先在本仓库双击启动一次以安装界面依赖。")
    dest_site.mkdir(parents=True, exist_ok=True)
    for name in GUI_PACKAGES:
        src = src_site / name
        if not src.exists():
            raise SystemExit(f".venv 缺少 {name}，请先 pip install -r requirements.txt")
        print(f"装入界面库：{name}")
        target = dest_site / name
        if src.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(src, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(src, target)
        for info in src_site.glob(f"{name}-*.dist-info"):
            dest_info = dest_site / info.name
            if dest_info.exists():
                shutil.rmtree(dest_info)
            shutil.copytree(info, dest_info, ignore=shutil.ignore_patterns("__pycache__"))


def write_plugin(anr: Path, dest_anr: Path) -> None:
    src_plugin = anr / "plugins" / "anr_plugin_auto_mosaics"
    dest_plugin = dest_anr / "plugins" / "anr_plugin_auto_mosaics"
    dest_plugin.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_plugin / "mosaics.py", dest_plugin / "mosaics.py")
    write_text(
        dest_plugin / "detector.py",
        "def detector(image_path, part):\n"
        "    raise RuntimeError('内置识别未能加载模型')\n",
    )
    write_text(dest_plugin / "__init__.py", "")
    write_text(
        dest_plugin / "config.json",
        '{\n  "detector": "YOLO",\n  "yolo_model": "./plugins/anr_plugin_auto_mosaics/models/yolo/censor.pt",\n  "sam_model": ""\n}\n',
    )
    yolo_src = src_plugin / "models" / "yolo"
    yolo_dest = dest_plugin / "models" / "yolo"
    yolo_dest.mkdir(parents=True, exist_ok=True)
    src = yolo_src / "censor.pt"
    if src.is_file():
        print("复制模型：censor.pt")
        shutil.copy2(src, yolo_dest / "censor.pt")
    emoji_src = src_plugin / "emoji"
    if emoji_src.is_dir():
        copytree(emoji_src, dest_plugin / "emoji", ignore=shutil.ignore_patterns(".git", "__pycache__"))
    (dest_anr / "outputs").mkdir(parents=True, exist_ok=True)


def write_launcher(dest: Path) -> None:
    write_text(
        dest / "启动理塘百宝箱.bat",
        """@echo off
chcp 65001 >nul
title 理塘百宝箱
cd /d "%~dp0"
set "ROOT=%~dp0软件本体-请勿删除"
if not exist "%ROOT%\\app\\__main__.py" set "ROOT=%~dp0"
cd /d "%ROOT%"
set "PY=%ROOT%\\runtime\\anr\\Python\\python.exe"
if not exist "%PY%" (
  echo 软件不完整。请重新解压整个「理塘百宝箱一键包」文件夹，不要只拷启动文件。
  pause
  exit /b 1
)
echo 正在打开理塘百宝箱…
"%PY%" -m app
if errorlevel 1 (
  echo.
  echo 启动失败。请打开 软件本体-请勿删除\\data\\last_error.txt 发给作者。
  pause
)
""",
    )
    write_text(
        dest / "创建桌面快捷方式.bat",
        """@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "TARGET=%~dp0启动理塘百宝箱.bat"
set "WORKDIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $env:USERPROFILE 'Desktop\\理塘百宝箱.lnk')); $s.TargetPath=$env:TARGET; $s.WorkingDirectory=$env:WORKDIR; $s.Description='理塘百宝箱'; $s.Save()"
if errorlevel 1 (
  echo 创建快捷方式失败。你也可以把「启动理塘百宝箱.bat」发送到桌面。
  pause
  exit /b 1
)
echo 桌面已经有「理塘百宝箱」快捷方式了。
pause
""",
    )


def write_readme(dest: Path, version: str) -> None:
    write_text(
        dest / "使用说明.txt",
        f"理塘百宝箱 一键包  v{version}\n"
        "\n"
        "这是给别人用的完整包：超分、打码、清元数据都已经装在里面。\n"
        "对方电脑不用再装 Python，也不用再装 ANR / 肘击王。\n"
        "\n"
        "怎么用\n"
        "1. 把整个「理塘百宝箱一键包」文件夹拷到对方电脑。可以放 D 盘、桌面都可以。\n"
        "2. 不要只拷一个启动文件，整个文件夹都要在。\n"
        "3. 双击「启动理塘百宝箱.bat」。第一次打开会稍慢，在加载打码模型。\n"
        "4. 想要桌面图标，再双击「创建桌面快捷方式.bat」。\n"
        "5. 先选成品放哪里，再把图片或文件夹拖进去，点开始。原图不会被改。\n"
        "\n"
        "成品默认在本文件夹里的「输出」。可以在软件里改到别的盘。\n"
        "\n"
        "注意\n"
        "- 建议 Windows 10/11 64 位。显卡驱动尽量是新的，超分会快很多。\n"
        "- 路径尽量不要特别深，也不要放到只读网盘里运行。\n"
        "- 「软件本体-请勿删除」不要改名、不要拆开。\n"
        "- 杀毒软件如果拦截，把整个文件夹加入白名单后再开。\n"
        "- 打码模型认欧金金 / 欧芒果 / 欧派派。欧西利没有独立识别，只能靠外扩尽量盖到。\n"
        "\n"
        "出问题\n"
        "把「软件本体-请勿删除\\data\\last_error.txt」发给作者即可。\n",
    )


def copy_app(body: Path) -> None:
    dest_app = body / "app"
    if dest_app.exists():
        shutil.rmtree(dest_app)
    copytree(
        APP_ROOT / "app",
        dest_app,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "anr_mosaic_worker.py"),
    )
    shutil.copy2(APP_ROOT / "requirements.txt", body / "requirements.txt")
    (body / "data").mkdir(parents=True, exist_ok=True)
    write_text(
        body / "data" / "config.json",
        '{\n  "anr_root": "",\n  "anr_python": "",\n  "output_mode": "folder",\n  "output_root": "",\n  "keep_structure": true\n}\n',
    )


def verify(body: Path) -> None:
    py = body / "runtime" / "anr" / "Python" / "python.exe"
    checks = [
        py,
        body / "app" / "__main__.py",
        body / "runtime" / "anr" / "plugins" / "anr_plugin_auto_mosaics" / "models" / "yolo" / "censor.pt",
        body / "runtime" / "anr" / "plugins" / "anr_plugin_auto_mosaics" / "mosaics.py",
        body / "runtime" / "anr" / "assets" / "realcugan-ncnn-vulkan" / "realcugan-ncnn-vulkan.exe",
    ]
    missing = [str(path) for path in checks if not path.exists()]
    if missing:
        raise SystemExit("打包后缺文件：\n" + "\n".join(missing))
    print("校验内置 Python 能否加载界面和打码库…")
    result = __import__("subprocess").run(
        [
            str(py),
            "-c",
            "import customtkinter, windnd, torch, PIL, cv2, scipy, yaml; from ultralytics import YOLO; print('ok', torch.__version__)",
        ],
        cwd=str(body),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise SystemExit((result.stderr or result.stdout or "内置 Python 自检失败").strip())
    print((result.stdout or "").strip())


def build(dest: Path) -> Path:
    sys.path.insert(0, str(APP_ROOT))
    from app import __version__

    anr = find_anr_root()
    print(f"打包到：{dest}")
    print(f"运行时来源：{anr}")
    if dest.exists():
        print("清理旧包…")
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    body = dest / BODY_NAME
    body.mkdir(parents=True, exist_ok=True)
    copy_app(body)
    dest_anr = body / "runtime" / "anr"
    dest_anr.mkdir(parents=True, exist_ok=True)
    copy_python(anr / "Python", dest_anr / "Python")
    copy_gui_packages(dest_anr / "Python")
    print("裁掉用不到的库…")
    saved = slim_site_packages(dest_anr / "Python" / "Lib" / "site-packages")
    print(f"运行时已减去约 {saved / (1024 * 1024):.0f} MB")
    write_plugin(anr, dest_anr)
    print("复制 Real-CUGAN 专业版…")
    copytree(
        anr / "assets" / "realcugan-ncnn-vulkan",
        dest_anr / "assets" / "realcugan-ncnn-vulkan",
        ignore=shutil.ignore_patterns(".git", "models-se", "models-nose"),
    )
    (dest / "输出").mkdir(exist_ok=True)
    write_launcher(dest)
    write_readme(dest, __version__)
    write_text(
        dest / "版本.txt",
        f"理塘百宝箱 {__version__}\n内置精简运行时、Real-CUGAN 专业版和打码模型。\n",
    )
    verify(body)
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description="打包理塘百宝箱一键包")
    parser.add_argument("--dest", default="", help="输出文件夹")
    args = parser.parse_args()
    dest = Path(args.dest).expanduser() if args.dest else default_dest()
    built = build(dest)
    print(f"完成：{built}")
    print("把整个文件夹发给别人即可。对方双击「启动理塘百宝箱.bat」。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
