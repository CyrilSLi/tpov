# 处理分隔式道路

分隔式道路指中间设有隔离带，两侧各有若干单向车道的道路。在 OpenStreetMap 中，分隔式道路以两条单向道路（`way` 对象）表示。这会导致识别路口时出现问题。`tpov_match.py` 中的 `divided_process` 函数与 `process_divided` 参数列表控制了是否在识别路口时包括或排除某些道路。

## 分隔式道路路口示例

![分隔式道路路口示例](../../media/divided_diagram.png)
*分隔式道路路口示例*