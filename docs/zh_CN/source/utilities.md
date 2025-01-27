# 实用工具

tpov 包含一些帮助数据和视频处理的实用脚本。

## tpov_combine.py

此程序依照视频元数据将多个视频片段以正确的顺序和间隔合并为单个视频。视频片段之间的时间间隔会被保留，以与 GPS 数据匹配。**请运行 `tpov_combine.py -h` 查阅使用信息和有关视频格式的重要警告。**

## fetch_keys.py

此程序可获取公开的天地图（用于 `tpov_match` 可视化底图）和百度地图（用于 `tpov_extract` 百度地图数据源）的API密钥。运行 `python fetch_keys.py` 后密钥将被打印到终端。

**请运行以下命令安装此脚本的依赖程序（如创建了虚拟环境请在其中运行）：**

```bash
pip install playwright
playwright install chromium-headless-shell
```

有关更多信息，请参阅 [Playwright 文档](https://playwright.dev/python/docs/library)。

## [tpov_extract_visu](https://www.npmjs.com/package/tpov_extract_visu)

这是一个用于在地图上可视化 `tpov_extract` 创建的 JSON 文件的 Node.js 包。更多信息请参阅 npm 页面。