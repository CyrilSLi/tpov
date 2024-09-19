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

## `process_divided` Parameters

`process_divided` parameters are shared across all cases of divided road processing.

- `angle` - The maximum angle difference of the two sides of the divided road (e.g. `GH` to `BA`). If the angle difference is greater than this value, they will be treated as separate roads.
- `length` - The maximum distance between the two sides of the divided road (e.g. `BEH` or `JFC`). If the distance is greater than this value, they will be treated as separate roads.
- `same_name` - If `True`, the two sides of the divided road must have the same name to be considered the same road.
- `apply_filter` - If `True`, the `exit_filter` function (TODO: add match param docs) will be applied to divided road processing. For example, this could mean that a four-way intersection with one side being a service road is treated as a T-junction.
- `enabled_cases` - A list of which cases (see below) are enabled. There are currently **4** cases.

## Case 1: Ignore short spur which leads to the opposite side of the divided road

Travel path: G -> H -> J -> K

Sensical intersection representation:

| Current | Left | Forward | Right | Direction |
| :-: | :-: | :-: | :-: | :-: |
| H |   | J | L | Forward |

Purely logical representation:

| Current | Left | Forward | Right | Direction |
| :-: | :-: | :-: | :-: | :-: |
| H |   | J | L | Forward |
| J | F | K |   | Forward |

Case 1 ignores the spur `JFC` as it just leads to the opposite side of the divided road.

Parameters:
- `angle`: `HJ` to `CB`
- `length`: `JFC`

## Case 2: Ignore exit to the opposite side of the divided road at a turn

Travel path: D -> C -> B -> E -> H -> L

Sensical intersection representation:

| Current | Left | Forward | Right | Direction |
| :-: | :-: | :-: | :-: | :-: |
| B | E | A |   | Left |

Purely logical representation:

| Current | Left | Forward | Right | Direction |
| :-: | :-: | :-: | :-: | :-: |
| B | E | A |   | Left |
| H | J | L |   | Forward |

Case 2 ignores the opposite side of the divided road (`HJ`).

Parameters:
- `angle`: `CB` to `HJ`
- `length`: `BEH`

## Case 3: Add exit for a far turn (left in right-hand traffic) onto a divided road at a T-junction

Travel path: M -> J -> F -> C -> B -> A

Sensical intersection representation:

| Current | Left | Forward | Right | Direction |
| :-: | :-: | :-: | :-: | :-: |
| F |   | J | K | Forward |
| C | B |   |   | Left |

Purely logical representation:

| Current | Left | Forward | Right | Direction |
| :-: | :-: | :-: | :-: | :-: |
| F |   | J | K | Forward |

Case 3 adds a row to show that a left turn was made, even though there is no intersection at `C` due to only one possible direction.

Parameters:
- Angles (Both have to be satisfied):
  - `prev_angle`: `MJ` to `JF`
  - `angle`: `JK` to `CB`
- `length`: `JFC`

## Case 4: Ignore "intersection" when a divided road merges back into a two-way road

Travel path: H -> L -> N -> P

Sensical intersection representation:

| Current | Left | Forward | Right | Direction |
| :-: | :-: | :-: | :-: | :-: |
|   |   |   |   |   |

Purely logical representation:

| Current | Left | Forward | Right | Direction |
| :-: | :-: | :-: | :-: | :-: |
| N | M | P |   | Forward |

Case 4 ignores segment `NM` as it is a U-turn back to the same road.

Parameters:
- `angle`: `HL` to `MJ` (**Not currently used**)
- Lengths (Both have to be satisfied):
  - `dist`: `LM`
  - `dist2`: `HJ`