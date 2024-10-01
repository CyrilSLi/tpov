# 匹配参数

`tpov_match.py` 用于将 GPX 路径与地图匹配，其参数存储在一个 JSON 文件中，作为必要参数提供。`match_params.json` 中的默认参数应该适用于大多数场合。

## Schema

为保证参数的格式正确，参数文件将根据存储在 `match_schema.json` 中的 [JSON schema（英文）](https://json-schema.org/) 文件进行验证。

## 参数

- `map_matcher` - 一个用于将地图中的道路与 GPX 路径匹配的类。必须继承自 [leuvenmapmatching.matcher.base.BaseMatcher（英文）](https://leuvenmapmatching.readthedocs.io/en/latest/classes/matcher/BaseMatcher.html)。
  - 支持的匹配器：
    - `SimpleMatcher` - 优先选择尽可能接近每个路径坐标的道路。 ([来源（英文）](https://leuvenmapmatching.readthedocs.io/en/latest/classes/matcher/SimpleMatcher.html))（**推荐**）
    - `DistanceMatcher` - 考虑匹配路径到地图道路的距离与路径坐标之间的距离的比例。" ([来源（英文）](https://leuvenmapmatching.readthedocs.io/en/latest/classes/matcher/DistanceMatcher.html))
- `stop_matcher` - 一个用于将公共交通站点与 GPX 路径匹配的函数。
  - 支持的匹配器：
    - `NaiveStopMatcher` - 将每个站点匹配到路径上最近的点。在存在重叠或交叉的路径上可能失败。
    - 如果您有更好的算法，请考虑为项目做出贡献，**谢谢！**
  - 给开发者的实现细节：
    - 该函数接受 GPX 文件路径、`tpov_extract.py` 输出的 JSON 对象以及地图匹配器的 `lattice_best` 和 `map_con` 作为输入。
    - 请参考 `leuvenmapmatching` 的源代码，如需帮助请通过 GitHub 联系本项目的维护者。
    - 函数应返回一个含有 GPX 点索引的 list ，表示路径中离每个站点最近的坐标。
    - 输出列表应**按升序排列**，否则请在匹配器内引发异常。参见 `NaiveStopMatcher` 为示例。

- `use_rtree` - 直接给地图匹配器的参数。绝大多数情况用 `false`。

- `exit_filter` - 一个 Python 表达式，对于每个道路段进行求值。如结果为 `False` 则在匹配时忽略该道路段。
  - 使用 `tpov_filter.txt` 过滤的地图文件将导致字典 `way` 具有以下键：
    - `highway` - 道路类型（例如 `primary`、`tertiary_link`）
    - `name` - 道路名称
    - `oneway` - 道路是否单行
  - 具体来说，`way` 是一个键为地图文件中的 OSM 标签的字典。运行 `tpov_filter.py` 时使用不同的过滤文件以包含不同的键。
  - 在 [OSM 维基](https://wiki.openstreetmap.org/wiki/Zh-hans:Main_Page) 上可搜索 OSM 标签信息。

- `default_name` - 当道路没有 `name` 标签时使用的名称，例如《无名路》。

- `forward_angle` - 在路口视为直行时最大允许的转向角度。

- `follow_link` - 匹配时是否替换 `link` 道路（辅路/匝道，例如 `secondary_link`）的路名。使用以下之一：
  - `false` 保留原路名。
  - 替换的路名字符串，`%n` 会被自动替换为辅路的目的地路名。

- `snap_gpx` - 是否将记录的 GPX 路径对齐到匹配完的路径。使用以下之一：
  - `false` 禁用对齐。
  - 一个非负整数启用对齐。数值表示除当前匹配路段之外考虑与前后各多少个路段对齐。

- `process_divided` - 参见 [process_divided.md](process_divided.md)。

- `visualize` - 是否用 HTML 可视化匹配的路径。

- `hw_priority` - 一个以 OSM `highway` 种类为键、整数优先级为值的对象。匹配器将优先显示优先级更高的道路。未列出的 `highway` 种类默认优先级为 0。

- `matcher_params` - 直接传递给地图匹配器的参数。详情请参阅您使用的地图匹配器的文档。[BaseMatcher 文档（英文）](https://leuvenmapmatching.readthedocs.io/en/latest/classes/matcher/BaseMatcher.html#leuvenmapmatching.matcher.base.BaseMatcher)提供一些参数信息。

- `display_params` - 一个控制数据显示方式的参数对象。
  - `display` - 一个将数据转换为 GPX 标签与元数据列表的函数。
    - 支持的显示函数：
      - `SimpleTextDisplay` - 一个简单的显示函数，将所有内容输出为纯文本。
  - **注意：** 下面的参数可能会根据使用的显示函数而变化。
  - `duration` - 路口信息显示时长，以 GPX 点数量表示。
  - `transfer_separator` - 用于分隔换乘站不同线路的字符串。
  - `bar_reverse` - 如 `true` 进度条将从长变短。如 `false` 进度条将从短变长。
  - `use_reference` - 如 `true` 则将站名保存为 GPX 元数据指针。可减小文件大小但会减慢处理速度。在大多数情况下使用 `false`。

- `visu_template` - 用于可视化的 HTML 模板文件路径。