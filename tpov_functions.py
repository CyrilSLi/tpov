# This file contains functions used by other programs. It should not be run directly.

# Built-in modules
import shutil, os, subprocess
from datetime import datetime, timedelta

# Third-party modules
from texttable import Texttable
import dateutil.parser

def renamedict (d, assignments: dict):
    return type (d) ((assignments.get (k, k), v) for k, v in d.items ())

def listsel (ls, prompt: str, min_len: int = 0, max_len: int = 0):
    # A rough implementation, could be improved with a proper parser
    prompt, args, count, indices, num, reverse = prompt.split (), ["+"], 0, set (), False, False
    while count < len (prompt):
        if count == 0 and prompt [0].lower () in ("rev", "all", "revall"):
            if prompt [0].lower ().startswith ("rev"):
                reverse = True
            if prompt [0].lower ().endswith ("all"):
                args.append (range (len (ls)))
                num = True
            count += 1
            continue
        if prompt [count].lower () == "to":
            if prompt [count - 2].lower () == "to":
                raise ValueError ("Two consecutive 'to' operators.")
            args.pop ()
            if prompt [count + 1].isdigit ():
                to_range = sorted ((int (prompt [count - 1]), int (prompt [count + 1])))
            else:
                raise ValueError (f"Invalid input '{prompt [count + 1]}'.")
            if any (i >= len (ls) for i in to_range):
                raise ValueError ("Range must be within the list.")
            to_range [1] += 1
            args.append (range (*to_range))
            count += 1
            num = False
        elif prompt [count] in ["+", "-"]:
            if len (args) % 2 == 1:
                raise ValueError ("Two consecutive operators.")
            args.append (prompt [count])
            num = False
        elif prompt [count].isdigit ():
            if int (prompt [count]) >= len (ls):
                raise ValueError ("Index must be within the list.")
            if num:
                raise ValueError ("Two consecutive literals.")
            args.append (range (int (prompt [count]), int (prompt [count]) + 1))
            num = True
        else:
            raise ValueError (f"Invalid input '{prompt [count]}'.")
        count += 1
    for i, j in zip (args [ : : 2], args [1 : : 2]):
        if i == "+":
            indices.update (j)
        elif i == "-":
            indices.difference_update (j)
    if min_len and len (indices) < min_len:
        raise ValueError (f"Selection is less than minimum length of {min_len}.")
    if max_len and len (indices) > max_len:
        raise ValueError (f"Selection exceeds maximum length of {max_len}.")
    if reverse:
        return (j for i, j in enumerate (reversed (ls)) if len (ls) - i - 1 in indices)
    return (j for i, j in enumerate (ls) if i in indices)

def choice (ls, question: str, min_len: int = 0, max_len: int = 0):
    while True:
        try:
            return listsel (ls, input (question), min_len, max_len)
        except Exception as e:
            print ("Error parsing list selection:", e)

def choicetable (header, data):
    display = Texttable (max_width = shutil.get_terminal_size ().columns)
    display.set_deco (Texttable.HEADER)
    display.set_cols_align (["l"] + ["l"] * len (header))
    display.set_cols_dtype (["i"] + ["t"] * len (header))
    display.header (["#"] + list (header))
    for j, i in enumerate (data):
        display.add_row ([j] + list (i))
    print (display.draw ())

def proj_path (file): # Return the path of the file in the project directory
    return os.path.join (os.path.dirname (os.path.abspath (__file__)), file)

def iso_time (time): # Convert a datetime object to an ISO 8601 string
    return time.isoformat ().replace ("+00:00", "Z")

def video_time (file, return_object = False): # Use exiftool to get the start and end timestamps of a video
    exif = subprocess.run (["exiftool", "-api", "largefilesupport=1", "-DateTimeOriginal", "-ModifyDate", "-Duration#", "-d", "%Y-%m-%dT%H:%M:%SZ", file], capture_output = True)
    exif.check_returncode ()
    exif = {i.split (":", 1) [0].strip (): i.split (":", 1) [1].strip () for i in exif.stdout.decode ().split ("\n") if i}

    # Try to guess how the start and end time are stored in the exif data
    if "Duration" not in exif:
        raise ValueError ("Duration not found in exiftool output")
    if "Date/Time Original" in exif:
        start = exif ["Date/Time Original"]
        end = iso_time (dateutil.parser.isoparse (start) + timedelta (seconds = round (float (exif ["Duration"]))))
    elif "Modify Date" in exif:
        end = exif ["Modify Date"]
        start = iso_time (dateutil.parser.isoparse (end) - timedelta (seconds = round (float (exif ["Duration"]))))
    else:
        raise ValueError ("Start or end time not found in exiftool output")
    
    if return_object:
        return dateutil.parser.isoparse (start), dateutil.parser.isoparse (end) # A bit redundant, can be cleaned up
    return start, end

def set_video_time (file, start, end): # Use exiftool to set the start and end timestamps of a video
    exif = subprocess.run (["exiftool", "-api", "largefilesupport=1", "-overwrite_original", "-DateTimeOriginal=" + start, "-FileModifyDate=" + start, "-ModifyDate=" + end, file])
    exif.check_returncode ()

if __name__ == "__main__":
    raise SystemExit ("This file contains functions used by other programs. It should not be run directly.")