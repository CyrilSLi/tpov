# Processing Divided Roads

Divided roads are roads that consist of a physical barrier (median) with one-way travel lanes on both sides. They are also represented as two one-way roads (`way` objects) in OpenStreetMap, which causes problems when identifying intersections. The `divided_process` function in `tpov_match.py`, along with the `process_divided` list of parameters, control whether to include or exclude certain roads from being included in intersection identification.

## Example of a Divided Road Intersection

![Example of a divided road intersection](../../media/divided_diagram.png)
*Example of a divided road intersection*