# Built-in modules
import os, argparse, copy

# Third-party modules
import gpxpy

from tpov_functions import *

# Truncates or extend a gpx file to match a start and end time
def truncate (gpx_path, start, end):
    start_time = dateutil.parser.isoparse (start) if start else None
    end_time = dateutil.parser.isoparse (end) if end else None
    with open (gpx_path, "r") as gpx_file:
        gpx = gpxpy.parse (gpx_file)
        try:
            first_seg = gpx.tracks [0].segments [0]
            last_seg = gpx.tracks [-1].segments [-1]
        except IndexError:
            raise ValueError ("No track segment found in the gpx file")
        first_time = first_seg.points [0].time
        last_time = last_seg.points [-1].time
    
    if start_time and start_time > first_time: # Truncate the beginning
        count = 0
        while first_seg.points [0].time < start_time:
            first_seg.points.pop (0)
            count += 1
            if not first_seg.points:
                raise ValueError ("gpx file does not overlap with start time")
        first_time = first_seg.points [0].time
        print (f"Truncated {count} point(s) from the beginning")
    if end_time and end_time < last_time: # Truncate the end
        count = 0
        while last_seg.points [-1].time > end_time:
            last_seg.points.pop ()
            count += 1
            if not last_seg.points:
                raise ValueError ("gpx file does not overlap with end time")
        last_time = last_seg.points [-1].time
        print (f"Truncated {count} point(s) from the end")

    if start_time and start_time < first_time: # Extend the beginning
        first_seg.points.insert (0, copy.copy (first_seg.points [0]))
        first_seg.points [0].time = start_time
        print ("Extended the beginning")
    if end_time and end_time > last_time: # Extend the end
        last_seg.points.append (copy.copy (last_seg.points [-1]))
        last_seg.points [-1].time = end_time
        print ("Extended the end")
    
    gpx_out = os.path.abspath (os.path.splitext (gpx_path) [0] + ".truncated.gpx")
    with open (gpx_out, "w") as gpx_file:
        gpx_file.write (gpx.to_xml ())
        print (f"Saved truncated/extended file to", gpx_out)

parser = argparse.ArgumentParser (
    description = "Truncate/Extend gpx files to match a video",
    formatter_class = argparse.RawDescriptionHelpFormatter,
    epilog = """\
"""
)
parser.add_argument ("gpx", help = "The gpx file to truncate or extend")
parser.add_argument ("-t", "--time", help = "The start and end time in ISO 8601 format", nargs = 2, metavar = ("START", "END"))
parser.add_argument ("-e", "--exiftool", help = "Run exiftool on a video file to get the start and end time", metavar = "VIDEO")

def main (args):
    if args.exiftool:
        start, end = video_time (args.exiftool)
    elif args.time:
        start, end = args.time
    else:
        raise SystemExit ("No action requested: Use -t or -e to specify the start and end time.")

    if input (f"Start time: {start}  End time: {end}\nProceed (Y/n)? ").lower () == "y":
        truncate (args.gpx, start, end)

def script (args):
    import shlex
    main (parser.parse_args (shlex.split (args)))

if __name__ == "__main__":
    main (parser.parse_args ())