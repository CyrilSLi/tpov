# Match Parameters

`tpov_match.py` is used to match GPX tracks to a map. Its parameters are stored in a JSON file, given as a required argument. The default parameters in `match_params.json` should be sufficient for most use cases.

## Schema

To ensure proper formatting of parameters, the parameter file is validated against a [JSON schema](https://json-schema.org/) file stored in `match_schema.json`.

## Parameters

- `map_matcher` - A class which matches roads from a map to a GPX path. Must be inherited from [leuvenmapmatching.matcher.base.BaseMatcher](https://leuvenmapmatching.readthedocs.io/en/latest/classes/matcher/BaseMatcher.html).
  - Supported matchers:
    - `SimpleMatcher` - "A simple matcher that prefers paths where each matched location is as close as possible to the observed position." ([Source](https://leuvenmapmatching.readthedocs.io/en/latest/classes/matcher/SimpleMatcher.html)) (**Recommended**)
    - `DistanceMatcher` - "Map Matching that takes into account the distance between matched locations on the map compared to the distance between the observations (that are matched to these locations)." ([source](https://leuvenmapmatching.readthedocs.io/en/latest/classes/matcher/DistanceMatcher.html))

- `stop_matcher` - A function which matches public transport stops to a GPX path.
  - Supported matchers:
    - `NaiveStopMatcher` - Matches each stop to the closest point on the path. Known to fail on overlapping or intersecting paths.
    - If you have a better algorithm, please consider contributing to the project. **Thank you!**
  - Implementation details for developers:
    - The function takes a path to a GPX file, a JSON object (not file) output by `tpov_extract.py`, and `lattice_best` and `map_con` from the map matcher as input.
    - Please consult `leuvenmapmatching`'s source code or message this project's maintainers on GitHub for help.
    - It should return a list of GPX point indices representing the closest point on the path to each stop.
    - The output list is expected to be **in increasing order**. Raise an exception inside the matcher if this is not the case. See `NaiveStopMatcher` for an example.

- `use_rtree` - Passed directly to the map matcher. Use `false` in most cases.

- `exit_filter` - A Python expression which gets evaluated for each road segment. If it evaluates to `False`, the segment is excluded from matching.
  - Map files filtered using `tpov_filter.txt` will result in the dictionary `way` having the following keys:
    - `highway` - The type of road (e.g. `primary`, `tertiary_link`)
    - `name` - The name of the road
    - `oneway` - Whether the road is one-way
  - Specifically, `way` is a dictionary with keys corresponding to OSM tags in the map file. Use a different filter file with `tpov_filter.py` to include different keys.
  - Search the [OSM wiki](https://wiki.openstreetmap.org/wiki/) for more information on OSM tags.

- `default_name` - What name to use when a road has no `name` tag (e.g. Unnamed Road).

- `forward_angle` - The maximum turning angle in degrees for it to be considered going straight through an intersection.

- `follow_link` Whether to replace the name of `link` roads (e.g. `secondary_link`) when matching. Use one of the following:
  - `false` to keep the original name.
  - The replacement name as a string, with `%n` in place of the destination of the link road.

- `snap_gpx` - Whether to snap the recorded GPX path to the matched path. Use one of the following:
  - `false` to disable snapping.
  - A non-negative integer enables snapping. The integer is how many matched segments in front and behind the current point, in addition to the current matched segment, to consider for snapping.

- `process_divided` - See [process_divided.md](process_divided.md).

- `visualize` - Whether to generate an HTML visualization of the matched path.

- `hw_priority` - An object with OSM `highway` types as keys and integer priorities as values. The matcher will prefer to display roads with higher priority at intersections. Unlisted `highway` types are given a priority of 0.

- `matcher_params` - Parameters passed directly to the map matcher. See the documentation for the map matcher you are using for more information. The [BaseMatcher docs](https://leuvenmapmatching.readthedocs.io/en/latest/classes/matcher/BaseMatcher.html#leuvenmapmatching.matcher.base.BaseMatcher) provide some information on the parameters.

- `display_params` - An object with parameters to control how to display the data.
  - `display` - A function which converts the data into lists of GPX tags and metadata to display.
    - Supported display functions:
      - `SimpleTextDisplay" - A simple display function which outputs eveything as text.
  - **Note:** The following parameters may change depending on the display function used.
  - `duration` - How many GPX points to display intersections for.
  - `transfer_separator` - A string to separate different lines at a transfer stop.
  - `bar_reverse` - If `true`, the progress bar will start long and shorten. If `false`, the progress bar will start short and lengthen.
  - `use_reference` - If `true`, saves stop names as references to GPX metadata. Reduce file size but slows processing. Use `false` in most cases.

- `visu_template` - The path to an HTML template file used for visualization.