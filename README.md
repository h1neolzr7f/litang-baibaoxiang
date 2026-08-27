<div align="center">

# 理塘百宝箱

### 本地超分 · 自动打码 · 清元数据

**Windows 一键包 + Android 安装包。原图不会被修改。**

![Version](https://img.shields.io/badge/Version-2.4.1-3E6B45)
![Windows](https://img.shields.io/badge/Windows-一键包-0078D4?logo=windows&logoColor=white)
![Android](https://img.shields.io/badge/Android-arm64_APK-3DDC84?logo=android&logoColor=white)
![License](https://img.shields.io/badge/License-AGPL--3.0-red)
![Privacy](https://img.shields.io/badge/Privacy-Local--first-7A5AF8)

[下载 Windows 一键包](https://github.com/h1neolzr7f/litang-baibaoxiang/releases/tag/v2.4.1) ·
[下载 Android APK](https://github.com/h1neolzr7f/litang-baibaoxiang/releases/tag/v2.4.1) ·
[使用说明](docs/PRODUCT.md) ·
[参与贡献](CONTRIBUTING.md) ·
[第三方](THIRD_PARTY.md)

</div>

> [!TIP]
> **第一次来？** Windows 下 [v2.4.1 一键包](https://github.com/h1neolzr7f/litang-baibaoxiang/releases/tag/v2.4.1) 完整解压后双击 `启动理塘百宝箱.bat`。手机下同页的 `litang-baibaoxiang-v0.29-android-arm64.apk`，允许未知来源后安装。两边都不用再装 Python 或 ANR。

## 一分钟了解

| 你原来要做的事 | 理塘百宝箱 |
| --- | --- |
| 对着文件夹一张张超分 | 拖进文件夹，按队列跑，可暂停可续 |
| 漏打、打不全 | 低阈值、切块、框外扩；漏打单独记清单 |
| 成品里还留着提示词 | 清元数据，重写成干净 PNG |
| 换电脑还要搭环境 | Windows 一键包自带运行时；手机有现成 APK |

它不是生图软件，只做**已经画好的图**的后处理。

## 下载

| 平台 | 文件 | 大约体积 |
| --- | --- | --- |
| **Windows 10/11** | [`litang-baibaoxiang-v2.4.1-windows.zip`](https://github.com/h1neolzr7f/litang-baibaoxiang/releases/download/v2.4.1/litang-baibaoxiang-v2.4.1-windows.zip) | 压缩约 330 MB，解压约 1 GB |
| **Android arm64** | [`litang-baibaoxiang-v0.29-android-arm64.apk`](https://github.com/h1neolzr7f/litang-baibaoxiang/releases/download/v2.4.1/litang-baibaoxiang-v0.29-android-arm64.apk) | 约 43 MB |

请从 [Releases](https://github.com/h1neolzr7f/litang-baibaoxiang/releases/tag/v2.4.1) 下载。不要只拷一个启动文件。

### Windows

1. 解压整个文件夹  
2. 双击 `启动理塘百宝箱.bat`（想要桌面图标再点 `创建桌面快捷方式.bat`）  
3. 先选成品放哪里，再把图片或文件夹拖进去  

成品默认在包内 `输出`。原图不改。

### Android

1. 安装 APK（需允许未知来源）  
2. 选图后在手机上打码，成品进相册 `Pictures/LitangToolbox`  
3. 只要 64 位 Android。详细说明见 [android/README.md](android/README.md)

## 能做什么

| 能力 | Windows | Android |
| --- | :---: | :---: |
| 自动识别并打码（欧金金 / 欧芒果 / 欧派派） | ✅ | ✅ |
| 识别加强：低阈值、切块、框外扩 | ✅ | 机内 ONNX |
| 超分 2/3/4 倍（Real-CUGAN 专业版优先） | ✅ | — |
| 清元数据 | ✅ | ✅ |
| 十几 GB 文件夹排队、ETA、磁盘预检 | ✅ | — |
| 暂停 / 失败重试 / 漏打清单 | ✅ | — |

欧西利没有独立模型类别，只能靠外扩尽量盖到。漏打请自己再看一眼。

## 自己跑 Windows 源码

需要本机已有 Auto-NovelAI-Refactor 打码环境（自带 Python、YOLO、Real-CUGAN）。

```bat
git clone https://github.com/h1neolzr7f/litang-baibaoxiang.git
cd litang-baibaoxiang
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt pytest
启动理塘百宝箱.bat
```

开发机重新出包：

```bat
打包一键包.bat
```

```bat
.venv\Scripts\python.exe -m pytest tests --ignore=tests/test_anr_smoke.py
```

## 目录

```text
app/                 Windows 界面与流水线
android/             手机版说明（安装包在 Releases）
tools/               打 Windows 一键包、裁运行时
tests/               单元测试
docs/                产品说明
启动理塘百宝箱.bat
打包一键包.bat
```

## 许可与边界

源码使用 [AGPL-3.0](LICENSE)。一键包和 APK 里的模型、ONNX Runtime、Real-CUGAN 仍按各自许可证，见 [THIRD_PARTY.md](THIRD_PARTY.md)。

这是非官方后处理工具，和 NovelAI / pixiv 没有隶属关系。不要把打码结果当成审核或法律意义上的完整覆盖。完整边界见 [DISCLAIMER.md](DISCLAIMER.md)。

---

<div align="center">

**理塘百宝箱 2.4.1** · Windows 一键包 + Android APK  
请从 [Releases](https://github.com/h1neolzr7f/litang-baibaoxiang/releases/tag/v2.4.1) 下载。

</div>
