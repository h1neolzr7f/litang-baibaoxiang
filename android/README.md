# 理塘百宝箱 · 手机版

Android arm64 安装包已经随仓库 Releases 发布。手机上用机内 **ONNX** 做识别和打码，不用电脑、不用 ANR。

## 安装

1. 打开 [v2.4.1 Release](https://github.com/h1neolzr7f/litang-baibaoxiang/releases/tag/v2.4.1)
2. 下载 `litang-baibaoxiang-v0.29-android-arm64.apk`（约 43 MB）
3. 允许「未知来源」后安装
4. 只要 **64 位** Android。32 位机型装不上

成品写到相册目录 `Pictures/LitangToolbox`。

## 它是什么

历史包名是 `com.codex.anrmobile`，应用目录名 `LitangToolbox`。机内带着同一套 `censor.onnx` 打码权重，和 Windows 端识别的是同一类部位（欧金金 / 欧芒果 / 欧派派）。

Windows 端后来补了切块、灵敏度、Real-CUGAN 超分和大批量队列；手机包是 **v0.29** 安装版，适合单张或小批量在手机上处理。

## 源码说明

当前 git 里的是 Windows 端源码。这份 APK 是已经编好的手机安装包，历史 Java 工程没有放在本仓库里，避免把模型权重和中间产物推进 git。

要改手机端，请基于这份 APK 的行为对照 `app/` 里的识别与打码逻辑另开 Android 工程，或把历史工程放进本目录后再开 PR。不要把 `.apk`、`.onnx` 大文件提交进 git，继续走 Releases。
