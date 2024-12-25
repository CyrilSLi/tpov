# 常见问题

如何解决一些常见问题。

提示：如果您需要查询报错，请尝试在此页面上搜索错误提示的前几个单词。

**在任何脚本上使用** `-h` **可显示一些基本使用信息 (英文)。**

## tpov_convert.py

- `Filter file [...] not found.` - 请参考[入门教程](quickstart.md#下载地图)中关于过滤文件的详细信息。

- `Invalid file format.` - 地图文件与 `osmconvert` 不兼容。尝试从其他来源下载文件，并确保在运行脚本之前解压文件。

## tpov_extract.py

请根据您使用的数据源查阅相应部分。

### GTFS

- `Route [...] not found` - 尝试用其他方式指定路线（如使用路线号而不是名称，反之亦然）。请注意**一些公交公司会在路线号前加零对齐**（例如 `099` 而不是 `99`）。

- 多个路线和方向相同的行程 - 因 GTFS 格式将每个行程单独存储，服务频繁的路线可能有数百个行程。完全相同的行程已在创建索引时被忽略了，但剩余的行程仍保留供用户查看。大多数情况下请选择出发时间最接近视频时间的行程。行程列表中提供每个行程的站点列表的哈希值。哈希值相同的行程可能不在同一时间出发和到达，但它们会以相同的顺序经过相同的站点，因此您可以选择其中任意一个。

### OSM

- `Error querying Overpass API` - 请检查您的网络连接等问题。

- `No results found.` - 请检查关系ID是否正确，尝试访问 `https://www.openstreetmap.org/relation/[关系ID]`。

### 百度地图

- `No results found. Try entering the route name in full.` - 尝试输入完整的路线名称而不是缩写（例如 `300路快车外环` 而不是 `300快外`）。

- `Error querying Baidu Maps API` - 检查您的网络连接，并尝试提供 SECKEY 重试。有关获取 SECKEY 的详细信息，请参考[入门教程](quickstart.md#百度地图)。

- `No stop information found. Try providing a seckey.` - 同上。

## tpov_match.py

- `No points matched. Try increasing max_dist_init in the matcher parameters.` - GPX 轨迹的起点距离路网太远。尝试增大参数文件中的 `max_dist_init` 参数（[文档](match_params.md)，单位: 米）。**不要使用过高的值，因为它可能导致地图匹配偏移。** 这应该是 `leuvenmapmatching`地图匹配库中的问题，但目前而言 `100` 应该是一个安全的最大值。如果仍然太远，请尝试在编辑器（例如 [gpx.studio](https://gpx.studio/)）中截断轨迹的开头。

- `Not all points were matched.` - GPX 轨迹中的一些点距离路网太远。这通常是因为轨迹终点在停车场或其他远离路网的区域。可以在地图上查找消息中提供的最后匹配的坐标。如果您满意此结果，请输入 `y` 继续处理，否则请尝试增大参数文件中的 `max_dist` 参数（[文档](match_params.md)）。 如果最后匹配的坐标接近夹角很小的路口（例如高速公路出口），请尝试增大 `max_lattice_width` 以免陷入错误的方向。

- `Path discontinuity at [...]` - 检查给定坐标处的 GPX 轨迹是否有断裂或损坏的部分。这可能由于轨迹在隧道内或其他 GPS 信号不良的区域。如果不是，请[提交一个问题](#其他)。

- `NaiveStopMatcher failed to match stops. Try using a different matcher.` - NaiveStopMatcher 是目前唯一的站点匹配器，它只简单的将停靠点匹配到轨迹上离它最近的点。这在环线或其他重叠路线上很可能会失败。请[提交一个问题](#其他)，并如果您有解决方案请考虑为此项目做出贡献。

- 用 `snap_gpx` 时匹配轨迹有不规则的跳跃 - 尝试增大参数文件中的 `snap_gpx` 值（[文档](match_params.md)）。

## tpov_combine.py

- `Duration not found in exiftool output` - 同下

- `Start or end time not found in exiftool output` - 同下

- `Video segments [...] and [...] overlap or are out of order` - 第二个视频片段的开始时间不在第一个视频片段结束时间之后。请检查提供的参数的顺序。

- `Video segment [...] has a negative duration` - 视频开始时间在结束时间以前。使用 `exiftool` 或 `ffprobe` 等工具检查视频文件是否损坏。如果您认为这是一个 bug，请[提交一个问题](#其他)。

## tpov_truncate.py

- `Duration not found in exiftool output` - 您的视频文件不包含用来推断开始和结束时间的元数据。这可能由使用过在线服务传输视频导致。请参考[入门教程](quickstart.md#匹配与截断GPS轨迹)手动输入时间。

- `Start or end time not found in exiftool output` - 同上。

- 当使用 `exiftool` 推断时间时，截断的轨迹与视频不匹配 - 视频元数据与实际录制时间之间可能会有一些偏差。尝试在视频文件上运行 `exiftool` 检查时间是否存储在其他属性中，并如有必要[手动输入时间](quickstart.md#匹配与截断GPS轨迹)。

## gopro-dashboard-overlay

此库为被 fork 并与 `tpov` 适配的一个独立的项目。请参阅[其文档 (英文)](https://github.com/CyrilSLi/gopro-dashboard-overlay/tree/main/docs)，并如需在那里提交一个问题。

## 其他

如果您遇到此处未列出的问题或需要进一步帮助，请在[GitHub 仓库](https://github.com/CyrilSLi/tpov)上提交一个问题。请提供尽可能多的细节，**并包括报错输出、运行的命令、您的 GPX 文件、视频元数据（如需）与配置文件（例如** `match_params.json`**）**。