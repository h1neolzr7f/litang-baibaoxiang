# 理塘百宝箱

本地图片后处理工具：超分、自动打码、清元数据。原图不会被修改。

普通用户请直接下 **Windows 一键包**，不用装 Python，也不用再装 ANR。

## 给别人用（推荐）

1. 打开 [Releases](https://github.com/h1neolzr7f/litang-baibaoxiang/releases) 下载 `litang-baibaoxiang-v2.4.1-windows.zip`
2. 解压整个文件夹，不要只拷启动文件
3. 双击 `启动理塘百宝箱.bat`
4. 先选成品放哪里，再把图片或文件夹拖进去

一键包大约 1 GB，里面已经带好打码模型、Real-CUGAN 专业版和运行环境。成品默认在包内的 `输出` 文件夹。

## 能做什么

- **超分**：优先 Real-CUGAN 专业版（2/3/4 倍），找不到再退回 Lanczos
- **打码**：欧金金 / 欧芒果 / 欧派派；欧西利没有独立类别，靠外扩尽量盖到
- **识别**：低阈值、多尺寸、大图切块、对比度增强、框外扩
- **清元数据**：去掉提示词一类残留
- **大批量**：队列、预估时间、磁盘预检、暂停、失败重试、漏打清单

## 自己跑源码

需要 Windows，以及本机已有的 [Auto-NovelAI-Refactor](https://github.com/search?q=Auto-NovelAI-Refactor) 打码环境（自带 Python、YOLO 模型和 Real-CUGAN）。

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip install pytest
启动理塘百宝箱.bat
```

或：

```bat
.venv\Scripts\python.exe -m app
```

开发机打包给别人：

```bat
打包一键包.bat
```

默认打到 `E:\Packages\releases\理塘百宝箱一键包`。也可以：

```bat
.venv\Scripts\python.exe tools\build_oneclick.py --dest D:\理塘百宝箱一键包
```

## 测试

```bat
.venv\Scripts\python.exe -m pytest tests --ignore=tests/test_anr_smoke.py
```

## 许可证

本仓库源码使用 [AGPL-3.0](LICENSE)。

一键包还会带上第三方运行时和模型（Ultralytics、PyTorch、Real-CUGAN、打码权重等），各自仍按原许可证。详见 [THIRD_PARTY.md](THIRD_PARTY.md)。

打码模型只有三类，不能把它当成医学或审核意义上的完整覆盖。漏打会写入成品旁的记录，请自己再看一眼。
