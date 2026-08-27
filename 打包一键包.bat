@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 打包理塘百宝箱一键包
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" tools\build_oneclick.py %*
) else (
  python tools\build_oneclick.py %*
)
if errorlevel 1 (
  echo 打包失败。
  pause
  exit /b 1
)
echo.
echo 可以把打好的文件夹发给别人了。
pause
