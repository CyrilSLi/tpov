# Processing Divided Roads

Divided roads are roads that consist of a physical barrier (median) with one-way travel lanes on both sides. They are also represented as two one-way roads (`way` objects) in OpenStreetMap, which causes problems when identifying intersections. The `divided_process` function in `tpov_match.py`, along with the `process_divided` list of parameters, control whether to include or exclude certain roads from being included in intersection identification.

## Example of a Divided Road Intersection

The diagram below shows an example of a two-way road that separates into a divided road, which then intersects with another divided road at an angled T-junction. Travel directions are as follows (**This diagram assumes right-hand traffic**):

- Road 1 (East-West):
    - G -> H -> J -> K (Orange)
    - D -> C -> B -> A (Red)
- Road 2 (North-South):
    - P -> N -> M -> J -> F -> C (Blue -> Purple)
    - B -> E -> H -> L -> N -> P (Cyan -> Blue)

All further documentation will refer to the diagram below.

![Example of a divided road intersection](../../media/divided_diagram.png)
*Example of a divided road intersection*