# Built-in modules
import os, sys, json, subprocess, argparse, shutil

# Third-party modules
from texttable import Texttable

from tpov_functions import *

parser = argparse.ArgumentParser (
    description = "Fill gaps between recorded segments with still videos",
    formatter_class = argparse.RawDescriptionHelpFormatter,
    epilog = """\
This program combines multiple video segments into a single video.
This can be used when recording accidentally stops or when it is split into multiple files.
The output will have the start time of the first segment and the end time of the last segment.

--- WARNING ---
  The video segments must have exactly the same streams. This program does not check for compatibility.
  Segments should normally be fine if they were recorded with the same camera and settings.
  See https://trac.ffmpeg.org/wiki/Concatenate#demuxer for more information.
--- WARNING ---

Not all videos have the required metadata to determine the start and end time.
See https://tpov.readthedocs.io/en/latest/ for the metadata required and what to do if it is missing.
"""
)
parser.add_argument ("output", help = "Output filename")
parser.add_argument ("segment", nargs = "+", help = "List of video segments to combine")

def main (args):
    print (
        "--- WARNING ---\n"
        "  The video segments must have exactly the same streams. This program does not check for compatibility.\n"
        "  Segments should normally be fine if they were recorded with the same camera and settings.\n"
        "  See https://trac.ffmpeg.org/wiki/Concatenate#demuxer for more information.\n"
        "--- WARNING ---\n"
    )
    
    segments = tuple (os.path.abspath (i) for i in args.segment)
    if len (segments) < 2:
        raise ValueError ("At least two video segments are required.")
    output = os.path.abspath (args.output)

    video_times = []
    for i in segments:
        if not os.path.isfile (i):
            raise FileNotFoundError (f"File not found: {i}")
        try:
            video_times.append (video_time (i, return_object = True))
        except Exception as e:
            print (f"Error extracting video times for '{i}':")
            raise e
    
    for k, (i, j) in enumerate (zip (video_times, video_times [1 : ])):
        if i [1] > j [0]:
            print (
                f"Video segments {segments [k]} and {segments [k + 1]} overlap or are out of order.\n"
                "Please check the order of the arguments passed to this program.\n"
                f'End -> Start timestamps: {iso_time (i [1])} -> {iso_time (j [0])}'
            )
        elif i [1] < i [0]:
            print (
                f"Video segment {segments [k]} has a negative duration."
                "Check the video using 'exiftool', 'ffprobe', or similar tools."
                "Please report this issue to GitHub if you believe it is a bug."
                f'Start -> End timestamps: {iso_time (i [0])} -> {iso_time (i [1])}'
            )
    
    table = Texttable (max_width = shutil.get_terminal_size ().columns)
    table.set_deco (Texttable.HEADER)
    table.set_cols_align (["l", "l", "l", "l"])
    table.set_cols_dtype (["t", "t", "t", "t"])
    table.header (["Filename", "Duration", "Start", "End"])

    for k, (i, j) in enumerate (zip (segments, video_times)):
        table.add_row ([os.path.basename (i), f"{(j [1] - j [0]).total_seconds ()} s", iso_time (j [0]), iso_time (j [1])])
        if k + 1 < len (segments):
            table.add_row (["Gap filler", f"{(video_times [k + 1] [0] - j [1]).total_seconds ()} s", iso_time (j [1]), iso_time (video_times [k + 1] [0])])
    print (table.draw ())
    if input (f"Combine {len (segments)} video segments into {output} (Y/n)? ").lower () != "y":
        raise SystemExit ("Operation cancelled.")
    
    timebases = []
    for i in segments:
        timebase = subprocess.run (["ffprobe", "-select_streams", "v", "-show_entries", "stream=time_base", "-of", "default=noprint_wrappers=1:nokey=1", i], capture_output = True)
        timebase.check_returncode ()
        timebase = timebase.stdout.decode ().strip ()
        timebases.append (int (float (timebase.split ("/") [1]) / int (timebase.split ("/") [0]))) # Take reciprocal of time base
    
    if not all (i == timebases [0] for i in timebases):
        print ("Warning: Video segments have different time bases.")
    timebase = timebases [0] # TODO: Set timebase to the majority / gcd of timebases

    temp_dir = os.path.join (os.path.dirname (output), "tpov_combine_temp") # Create temporary directory
    if os.path.exists (temp_dir):
        shutil.rmtree (temp_dir)
    os.mkdir (temp_dir)

    for k, (i, j) in enumerate (zip (segments [ : -1], video_times)):
        # Extend video by extending audio (see https://stackoverflow.com/a/66202619/14056297)
        duration = int ((video_times [k + 1] [0] - j [0]).total_seconds ())
        cmd = ["ffmpeg", "-i", i, "-c:v", "copy", "-af", "apad", "-t", str (duration), "-video_track_timescale", str (timebase), os.path.join (temp_dir, os.path.basename (i))]
        print (f"Executing {' '.join (cmd)}")
        ffmpeg = subprocess.run (cmd, stdout = sys.stdout, stderr = sys.stderr)
        ffmpeg.check_returncode ()
    
    # Combine videos using concat demuxer
    concat = "\n".join (f"file '{os.path.join (temp_dir, os.path.basename (i))}'" for i in segments [ : -1])
    concat += f"\nfile '{segments [-1]}'" # Last segment does not need padding (no copy operation)
    concat_path = os.path.join (temp_dir, "concat.txt")
    with open (concat_path, "w") as f:
        f.write (concat)

    cmd = ["ffmpeg", "-f", "concat", "-safe", "0", "-i", concat_path, "-c", "copy", "-video_track_timescale", str (timebase), output]
    print (f"Executing {' '.join (cmd)}")
    ffmpeg = subprocess.run (cmd, stdout = sys.stdout, stderr = sys.stderr)
    ffmpeg.check_returncode ()
    set_video_time (output, iso_time (video_times [0] [0]), iso_time (video_times [-1] [1])) # Set start and end times of combined video (requires rewrite of video)
    print (f"Saved combined video to {output} with start time {iso_time (video_times [0] [0])} and end time {iso_time (video_times [-1] [1])}")

    if input (f"Delete temporary directory {temp_dir} (Y/n)? ").lower () == "y":
        shutil.rmtree (temp_dir)
        print (f"Successfully deleted {temp_dir}")

def script (args):
    import shlex
    main (parser.parse_args (shlex.split (args)))

if __name__ == "__main__":
    main (parser.parse_args ())