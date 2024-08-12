# Quickstart Guide

This guide will help you get familiar with the basics of using the `tpov` library and how to use it to create a simple transit POV video.

**This library currently requires Unix-like commands (e,g, Linux, MacOS, \*BSD).**

## Recording the Video
Make sure to record a GPS track of the route you are recording and export it as a GPX file.

## Installation

A project folder will be created to organize the files for this tutorial.

**Python 3.10 is recommended for the best compatibility and is the only version tested.**

```bash
git clone https://github.com/CyrilSLi/tpov
cd tpov
pip install -r requirements.txt
mkdir quickstart_project
cd quickstart_project
```

### Command-line prerequisites

- `osmfilter` and `osmconvert`: Can be installed as `osmctools` on most Linux distributions and as `osmfilter` on Homebrew.
- `exiftool`: Should be available in most package managers.
- `ffmpeg`: Should be pre-installed on most systems.

## Downloading the Map

Download the map of the area you are recording from [OpenStreetMap](https://www.openstreetmap.org/). A good source to use is [Geofabrik](https://download.geofabrik.de/). Uncompress the map file if necessary.

Use `tpov_convert.py` to convert the map file to a format that can be used by the library. This will create a file ending in `.out.o5m` in the current directory. For this tutorial, please rename the output file to `map.out.o5m`.

```bash
python3.10 tpov_convert.py /path/to/mapfile ../tpov_filter.txt
```

The filter file is used to filter out unnecessary data from the map. The sample filter file `tpov_filter.txt` should be sufficient for most cases, but you can modify it if necessary. Read the [osmfilter wiki](https://wiki.openstreetmap.org/wiki/Osmfilter) for more information.

## List Selection

Throughout the process, you will be asked to select item(s) from a list. The list will be displayed in the following format:

```
#  Label  Label  ...
===============  ...
0  Item1  Item2  ...
1  Item3  Item4  ...
2  Item5  Item6  ...
...
Select item(s): 
```

Items are selected using a mini-language roughly based on human language. Indices (the left-most column) are combined with operators to select items. Each item is separated by a space. The following operators are used:

- `-` (dash) excludes an item or range from the selection.
- `+` (plus) includes an item or range in the selection.
- `to` forms an inclusive range of the two indices beside it.

Special values are used to select all or reverse the selection:

- `all` selects all items. Treat this as an index (use an operator after it).
- `revall` selects all items and reverses the selection. Treat this as an index.
- `rev` reverses the selection. Treat this as an operator (use an index after it).

Examples:

- `0` selects the first item.
- `0 to 2 + 4` selects `0 1 2 4`.
- `rev 5 to 8 - 6` selects `8 7 5`.
- `all - 3` selects all items except the fourth.

## Extracting Stop Data

`tpov_extract.py` is used to extract stop data of a transit route (e.g. names, coordinates, transfers, etc). It can currently extract data from GTFS feeds, OSM relations, and Baidu Maps.

Choose one of the following methods to extract stop data: The data will be saved as `stop_data.json` in the current directory.

### GTFS

GTFS is a common format used by many transit agencies to provide data on their service. You can usually download GTFS feeds from the transit agency's website or third-party feeds. Uncompress the GTFS feed if necessary.

**Note: The first time you run this script, it will take a while to sort and index the data.**

```bash
python3.10 tpov_extract.py gtfs /path/to/gtfs ../stop_data.json
```
```
Enter the route short_name or long_name:
```

Enter the route number (e.g. 66) or name (e.g. Canada Line) of the route you recorded.

```
Enter the time the vehicle left the first stop in HH(:mm)(:ss) format:
```

Enter the time in 24-hour format. Approximate values such as `15` (hour) or `15:30` (hour and minute) are allowed.

### OpenStreetMap

Stop data can be extracted from an OSM relation. You can find the relation ID by searching for the route on [OpenStreetMap](https://www.openstreetmap.org/). The relation ID is the number at the end of the URL.

```bash
python3.10 tpov_extract.py osm relation_id ../stop_data.json
```

**Be careful when using this method as the data may not be accurate.** In particular, pay attention to the 'Role' column when selecting stops to include as some relations have duplicate stops with 'stop' and 'platform' roles.

### Baidu Maps

Baidu Maps usually has the most accurate data for routes in China. You will need to obtain a SECKEY for best results. You can find the SECKEY by:

- Visit [Baidu Maps](https://map.baidu.com/).
- Right-click and select 'Inspect'.
- Switch to the 'Console' tab.
- Type SECKEY in the console and press Enter.
- Copy the value returned. It should be a long string of characters.

```bash
python3.10 tpov_extract.py baidu [SECKEY] ../stop_data.json
```

## Matching and Truncating the GPS Track

For this tutorial, please move the GPX file to the current directory and rename it to `track.gpx`. The following command will save the matched data as `track.matched.gpx`.

```bash
python3.10 tpov_match.py ../match_params.json track.gpx --map map.out.o5m --stop ../stop_data.json
```

Documentation for `match_params.json` will be provided in the near future.

The track needs to be truncated and/or extended to match the video (replace `/path/to/video` with the path to your video file):

```bash
python3.10 tpov_truncate.py track.matched.gpx -e /path/to/video
```

The script above uses exiftool to extract the start and end times. Make sure to review the times before proceeding and correct them manually if necessary. All times are in UTC and ISO 8601 format (be careful with time zones). You can input the times manually as follows:

```bash
python3.10 tpov_truncate.py track.matched.gpx -t [Start time] [End time]
```

The final processed track will be saved as `track.matched.truncated.gpx`.

## Creating the Video

The following command will use [gopro-dashboard-overlay](https://github.com/CyrilSLi/gopro-dashboard-overlay) and a default template to create a transparent overlay, which then can be combined with the recorded video in a video editor.

This template is tested with the [Noto Sans CJK](https://github.com/googlefonts/noto-cjk/raw/main/Sans/Variable/OTC/NotoSansCJK-VF.otf.ttc) font, however other fonts probably work as well. Replace `NotoSansCJK-VF` with the filepath of the font you want to use.

```bash
gopro-dashboard.py --use-gpx-only --units-speed kph --font NotoSansCJK-VF --profile overlay --overlay-size 1920x1080 --layout-xml ../tpov_layout.xml overlay.mov --gpx track.matched.truncated.gpx
```

If you don't want to further edit the video, you can use the following command instead to combine the overlay with the video (replace `/path/to/video` with the path to your video file):

```bash
gopro-dashboard.py --use-gpx-only --units-speed kph --font NotoSansCJK-VF --overlay-size 1920x1080 --layout-xml ../tpov_layout.xml /path/to/video overlay.mp4 --gpx track.matched.truncated.gpx
```

## Conclusion

You should now have a transit POV video that shows the route on a map, the line number, speed, time, current road, the previous and next stops, transfer information, intersections, and a progress bar. You can further edit the video in a video editor to add music, transitions, etc.

**Please note that the library is still in development and may have bugs. Please report any issues on the [GitHub repository](https://github.com/CyrilSLi/tpov/tree/main).**