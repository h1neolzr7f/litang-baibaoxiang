# 第三方说明

本仓库自己的源码按 AGPL-3.0 发布。Windows 一键包为了让别人双击就能用，会带上开发机上的运行时和模型。这些东西不属于本仓库源码，各自仍按原作者的许可证。

| 部分 | 用途 | 说明 |
| --- | --- | --- |
| Ultralytics YOLO | 打码识别 | AGPL-3.0 |
| PyTorch | 跑 YOLO | 其自身许可证 |
| OpenCV / NumPy / SciPy / Pillow | 图像与遮罩 | 各自许可证 |
| Real-CUGAN ncnn Vulkan | 超分 | 其项目原许可证 |
| `censor.pt` | 敏感部位检测权重 | 来自 ANR 打码插件，不进 git |
| `anr_plugin_auto_mosaics` 的打码绘制 | 像素/模糊等遮罩效果 | GPL-3.0，只打进一键包 |

源码仓库 **不包含** 模型权重、ANR 自带 Python、Real-CUGAN 可执行文件。要复现一键包，请在已经装好 ANR 的开发机上运行 `打包一键包.bat`。
