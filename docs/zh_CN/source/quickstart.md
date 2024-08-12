# 入门教程

此教程将帮助您熟悉使用 `tpov` 库，并了解如何使用它创建一个简单的公交POV视频。

**目前此库仅支持类Unix命令（例如Linux，MacOS，\*BSD操作系统）。**

## 录制视频

记录您要录制的路线的GPS轨迹，并将其导出为GPX文件。

## 安装

一个用于管理本教程的文件的项目文件夹将被创建。

**推荐使用Python 3.10以获得最佳兼容性, 且是是唯一测试过的版本。**

```bash
git clone https://github.com/CyrilSLi/tpov
cd tpov
pip install -r requirements.txt
mkdir quickstart_project
cd quickstart_project
```

### 命令行程序安装

- `osmfilter` 和 `osmconvert`: Linux可安装`osmctools`，Homebrew可安装`osmfilter`。
- `exiftool`: 收录于大多数包管理器中。
- `ffmpeg`: 大多数系统中已经预装。

## 下载地图

从[OpenStreetMap](https://www.openstreetmap.org/)下载您要录制的区域的地图。[Geofabrik](https://download.geofabrik.de/)是一个不错的选择。如需请解压地图文件。

用 `tpov_convert.py` 将地图文件转换为此库可用的格式。这将在当前目录中创建一个以 `.out.o5m` 结尾的文件。在本教程中，请将输出文件重命名为 `map.out.o5m`。

把`path/to/mapfile`替换为地图文件的路径。

```bash
python3.10 tpov_convert.py /path/to/mapfile ../tpov_filter.txt
```

过滤文件用于过滤地图中的不必要数据。`tpov_filter.txt` 应该适配大多数情况，但如需可修改。详情请见 [osmfilter wiki (英文)](https://wiki.openstreetmap.org/wiki/Osmfilter) 。

## 列表选择

在使用过程中，您将需要从列表中选择项目。列表将以以下格式显示：

```
#  Label  Label  ...
===============  ...
0  Item1  Item2  ...
1  Item3  Item4  ...
2  Item5  Item6  ...
...
Select item(s): 
```

项目用一个类似自然语言的语法进行选择。索引（最左列）与操作符相结合以选择项目。每个项目之间用空格分隔。以下操作符可用：

- `-` (减号) 排除选择中的项目或范围。
- `+` (加号) 包含选择中的项目或范围。
- `to` 配合两侧的索引成为一个包含范围。

一些特殊值用于选择全部或反转选择：

- `all` 选择所有项目。将其视为一个索引（在其后使用操作符）。
- `revall` 选择所有项目并反转选择。将其视为一个索引。
- `rev` 反转选择。将其视为一个操作符（在其后使用索引）。

示例：

- `0` 选择第一个项目。
- `0 to 2 + 4` 选择 `0 1 2 4`。
- `rev 5 to 8 - 6` 选择 `8 7 5`。
- `all - 3` 选择除第四个项目外的所有项目。

## 提取站点数据

`tpov_extract.py` 用于提取公交路线的站点数据（名称、坐标、换乘信息等）。目前支持从GTFS、 OSM与百度地图提取数据。

### GTFS

GTFS是许多公交公司提供数据的常见格式。您通常可以从公交公司的网站或第三方数据源下载GTFS数据。如需请解压。

**第一次运行此脚本时，将花费一些时间对数据进行排序和索引。**

```bash
python3.10 tpov_extract.py gtfs /path/to/gtfs ../stop_data.json
```
```
Enter the route short_name or long_name:
```

输入您录制的路线的编号（例如66）或名称（例如Canada Line）。


```
Enter the time the vehicle left the first stop in HH(:mm)(:ss) format:
```

用24小时制输入时间。允许输入模糊值，如 `15`（小时）或 `15:30`（小时与分钟）。

### OpenStreetMap

站点数据可从OSM关系中提取。您可以在[OpenStreetMap](https://www.openstreetmap.org/)上搜索路线以获取关系ID。关系ID为URL末尾的数字。

```bash
python3.10 tpov_extract.py osm relation_id ../stop_data.json
```

**使用此方法时请注意数据准确性。** 特别是在选择要包含的站点时，请注意 'Role' 列。一些关系有重复的站点，它们分别使用 'stop' 和 'platform' 的 role。

### 百度地图

百度地图通常拥有最准确的中国公交路线数据。为取得最佳成果，您需要获取一个 SECKEY。您可以通过以下步骤获取 SECKEY：

- 访问[百度地图](https://map.baidu.com/)。
- 右键选择“检查”或开发者工具。
- 点击控制台标签页。
- 在控制台中输入SECKEY并回车。
- 复制返回的字符串。

```bash
python3.10 tpov_extract.py baidu [SECKEY] ../stop_data.json
```

## 匹配与截断GPS轨迹

请将GPX文件移动到当前目录并重命名为 `track.gpx`。以下命令会将匹配的数据保存为 `track.matched.gpx`。

```bash
python3.10 tpov_match.py ../match_params_zh.json track.gpx --map map.out.o5m --stop ../stop_data.json
```

`match_params_zh.json` 的文档将在以后提供。

轨迹需要截断与扩展以匹配视频（将 `/path/to/video` 替换为您录制的视频文件的路径）：

```bash
python3.10 tpov_truncate.py track.matched.gpx -e /path/to/video
```

以上命令使用 exiftool 提取视频开头和结尾时间。在继续操作之前，请检查确保时间准确并如需手动更正。所有时间均为UTC和ISO 8601格式（请注意时区）。您可以用以下命令手动输入时间：

```bash
python3.10 tpov_truncate.py track.matched.gpx -t [开头时间] [结尾时间]
```

全部处理完的轨迹将被存为 `track.matched.truncated.gpx`。

## 创建视频

以下命令将使用 [gopro-dashboard-overlay](https://github.com/CyrilSLi/gopro-dashboard-overlay) 与一个默认模板创建一个透明叠加视频，可在视频编辑器中与录制的视频合并。

此模板适配 [Noto Sans CJK](https://github.com/googlefonts/noto-cjk/raw/main/Sans/Variable/OTC/NotoSansCJK-VF.otf.ttc) 字体，但其他字体可以适用。请将 `NotoSansCJK-VF` 替换为您想使用的字体的文件路径。

```bash
gopro-dashboard.py --use-gpx-only --units-speed kph --font NotoSansCJK-VF --profile overlay --overlay-size 1920x1080 --layout-xml ../tpov_layout_zh.xml overlay.mov --gpx track.matched.truncated.gpx
```

如果您不想进一步编辑视频，可替代使用以下命令将叠加与视频合并（将 `/path/to/video` 替换为您录制的视频文件的路径）：

```bash
gopro-dashboard.py --use-gpx-only --units-speed kph --font NotoSansCJK-VF --overlay-size 1920x1080 --layout-xml ../tpov_layout_zh.xml /path/to/video overlay.mp4 --gpx track.matched.truncated.gpx
```

## 尾声

您现在有一个显示路线地图、线路编号、速度、时间、海拔、距离、当前道路、上/下一站、换乘信息、路口信息于进度条的公交POV视频。您可以在视频编辑器中进一步编辑视频以添加音乐、过渡等。

**此库仍在开发中，可能存在bug。请在 [GitHub仓库](https://github.com/CyrilSLi/tpov/tree/main) 上汇报任何问题, 谢谢。**