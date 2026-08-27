@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 理塘百宝箱
set "PY="
if exist "runtime\anr\Python\python.exe" set "PY=runtime\anr\Python\python.exe"
if not defined PY if exist "软件本体-请勿删除\runtime\anr\Python\python.exe" (
  cd /d "%~dp0软件本体-请勿删除"
  set "PY=runtime\anr\Python\python.exe"
)
if not defined PY if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY (
  echo [理塘百宝箱] 第一次打开，正在准备运行环境，请稍等…
  py -3 -m venv .venv 2>nul
  if not exist ".venv\Scripts\python.exe" python -m venv .venv
  if not exist ".venv\Scripts\python.exe" (
    echo 没有找到 Python。请先安装 Python 3.10 或更新版本后再双击本文件。
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install -U pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo 依赖安装失败。请把这屏文字发给开发者。
    pause
    exit /b 1
  )
  set "PY=.venv\Scripts\python.exe"
)
"%PY%" -m app
if errorlevel 1 (
  echo.
  echo 程序异常退出。如有 data\last_error.txt，把它发给开发者即可。
  pause
)
