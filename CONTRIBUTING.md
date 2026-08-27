# 参与贡献

欢迎修 Bug、补测试、改说明、改进识别或打包。

## 开始前

1. 从 `main` 开分支
2. 不要提交 `data/`、`runtime/`、`输出/`、`.venv/`、一键包、APK、模型权重、私人图片
3. 行为变化请带测试；Windows 端可跑：

```bat
.venv\Scripts\python.exe -m pytest tests --ignore=tests/test_anr_smoke.py
```

4. Issue / PR / 截图里不要放别人的原图、完整提示词或本机绝对路径

## 适合改的地方

- `app/` 流水线、识别几何、界面文案
- `tools/build_oneclick.py` 与精简运行时
- `tests/`
- 文档与 Release 说明

手机安装包走 Releases，不把 APK 推进 git。
