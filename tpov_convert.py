# Built-in modules
import os, sys, argparse, subprocess

from tpov_functions import *

# File formats which osmconvert can read
osmconvert_formats = (".osm", ".osc", ".osc.gz", ".osh", ".o5m", ".o5c", ".pbf")

def convert (map_file, filter_file):
    if os.path.splitext (map_file) [1] not in osmconvert_formats:
        raise ValueError (f"Invalid file format. Supported formats: {', '.join (osmconvert_formats)}")
    elif os.path.splitext (map_file) [1] not in (".osm", ".o5m"): # Convert to .o5m format
        print (f"Converting {map_file} to .o5m format...")
        o5m_file = os.path.splitext (map_file) [0] + ".temp.o5m" # Temporary file
        sys.stdout.flush () # Force print to display before running subprocess
        sys.stderr.flush ()
        osmconvert = subprocess.run (["osmconvert", map_file, "-o=" + o5m_file], stdout = sys.stdout, stderr = sys.stderr)
        osmconvert.check_returncode ()
    else:
        o5m_file = map_file

    print (f"Filtering {o5m_file} with {filter_file}...")
    output_file = os.path.splitext (map_file) [0] + ".out.o5m"
    sys.stdout.flush ()
    sys.stderr.flush ()
    osmfilter = subprocess.run (["osmfilter", o5m_file, "--parameter-file=" + filter_file, "-o=" + output_file], stdout = sys.stdout, stderr = sys.stderr)
    osmfilter.check_returncode ()
    print (f"Saved filtered .o5m file as {output_file}")

    if o5m_file != map_file:
        os.remove (o5m_file)
        print (f"Deleted temporary file {o5m_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser (
        description = "Convert and filter OSM map files for use with tpov_match.py",
        formatter_class = argparse.RawDescriptionHelpFormatter,
        epilog = f"""\
This program and the tpov suite require the tools osmconvert and osmfilter.

Currently supported input file formats:
{', '.join (osmconvert_formats)}

The filter file contains a list of osmfilter commands.
For more information, see https://wiki.openstreetmap.org/wiki/Osmfilter
A default filter file is provided at "tpov_filter.txt".
"""
    )
    parser.add_argument ("map", help = "The OSM map file to convert")
    parser.add_argument ("filter", help = "The filter file to apply")
    args = parser.parse_args ()
    convert (args.map, args.filter)