# Troubleshooting

Here you can find some common issues and how to solve them.

Tip: If you need help with an error message, try searching the first few words on this page.

**Use** `-h` **on any script to view a help message with basic usage information.**

## tpov_convert.py

- `Filter file [...] not found.` - Refer to the [Quickstart](quickstart.md#downloading-the-map) for details on the filter file.

- `Invalid file format.` - The map file is not compatible with `osmconvert`. Try downloading from another source, and make sure the file is decompressed before running the script.

## tpov_extract.py

Please refer to the section for the data source you are using.

### GTFS

- `Route [...] not found` - Try specifying the route in another way (e.g. with the route number instead of the name or vice versa). Note that **some transit agencies pad route numbers with leading zeroes** (e.g. `099` instead of `99`).

- Multiple trips with the same route and direction - The GTFS format stores each trip separately, so a frequent route may have hundreds of trips. Exact duplicate trips have been filtered out during indexing, however the remaining trips are kept for user information. Usually select the trip with the closest departure time to your video. A hash of all the stops on each trip is provided in the trips table. Trips with the same hash may not depart and arrive at the same time, but they do cover the same stops in the same order, so you can choose any of them.

### OSM

- `Error querying Overpass API` - Check your Internet connection, etc.

- `No results found.` - Check that you have the correct relation ID by visiting `https://www.openstreetmap.org/relation/[relation ID]`.

### Baidu Maps

- `No results found. Try entering the route name in full.` - Try entering the full route name instead of an abbreviation (e.g. `300路快车外环` instead of `300快外`).

- `Error querying Baidu Maps API` - Check your Internet connection and try again with a SECKEY if you did not provide one. Refer to the [Quickstart](quickstart.md#baidu-maps) for obtaining a SECKEY.

- `No stop information found. Try providing a seckey.` - Same as above.

## tpov_match.py

- `No points matched. Try increasing max_dist_init in the matcher parameters.` - The start of the GPX track is too far away from any road. Try increasing the `max_dist_init` parameter (in meters) in the parameter file ([docs](match_params.md)). **Do not use a high value, as it seems to offset map matching.** This is probably an issue with `leuvenmapmatching`, the map matching library used by this script, however in the meantime `100` should a safe maximum. If it is still too far, try truncating the beginning of the track in an external editor (e.g. [gpx.studio](https://gpx.studio/)).

- `Not all points were matched.` - Some points in the GPX track are too far away from any road. This often happens if the track ends in a parking lot or similar area not near a public road. Look up the last matched coordinates provided in the message on a map. If they are satifactory for your purposes, enter `y` to continue processing. If not, try increasing the `max_dist` parameter in the parameter file ([docs](match_params.md)). If the last matched coordinates are near an intersection with roads at a very slight angle (e.g. a highway exit), try increasing `max_lattice_width` to avoid getting stuck going the wrong direction.

- `Path discontinuity at [...]` - Check for a discontinued or corrupted section of the GPX track at the given coordinates. This can happen if the track was recorded in a tunnel or other area with poor GPS reception. If not, please [open an issue](#other).

- `NaiveStopMatcher failed to match stops. Try using a different matcher.` - NaiveStopMatcher is currently the only stop matcher available, and matches stops simply to the nearest point on the track. This is expected to fail on looping or otherwise overlapping routes. Please [open an issue](#other), and if you have a solution, consider contributing to the project.

- When using `snap_gpx` and there are erratic jumps in the matched track - try to increase the value of `snap_gpx` in the parameter file ([docs](match_params.md)).

## tpov_combine.py

- `Duration not found in exiftool output` - See below

- `Start or end time not found in exiftool output` - See below

- `Video segments [...] and [...] overlap or are out of order` - The second segment does not begin after the first segment ends. Check the order of the arguments provided.

- `Video segment [...] has a negative duration` - Verify that the video is not corrupted using tools such as `exiftool` or `ffprobe`. If you believe that this is a bug, please [open an issue](#other).

## tpov_truncate.py

- `Duration not found in exiftool output` - Your video file does not contain the necessary metadata to infer the start and end times. This can happen if you use an online service to transfer the video. Refer to the [Quickstart](quickstart.md#matching-and-truncating-the-gps-track) for manual input of the times.

- `Start or end time not found in exiftool output` - Same as above.

- The truncated track does not line up with the video when using `exiftool` to infer the times - There is expected to be some deviation between video metadata and the actual recording time. Try running `exiftool` on the video file to check if the times are stored in another field, and [manually input the times](quickstart.md#matching-and-truncating-the-gps-track) if necessary.

## gopro-dashboard-overlay

This is a separate project that has been forked and adapted for use with `tpov`. Please refer to [its documentation](https://github.com/CyrilSLi/gopro-dashboard-overlay/tree/main/docs) for troubleshooting, and open an issue there if necessary.

## Other

If you encounter an issue not listed here or need further assistance, please open an issue on the [GitHub repository](https://github.com/CyrilSLi/tpov). Provide as much detail as possible, **including the error message, the command you ran, your GPX file, video metadata (if applicable), and configuation files (e.g.** `match_params.json`**)**.