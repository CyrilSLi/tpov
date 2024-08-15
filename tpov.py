# Built-in modules

import os, sys, argparse, json, subprocess, shlex

from tpov_convert import script as tpov_convert
from tpov_extract import script as tpov_extract
from tpov_match import script as tpov_match
from tpov_truncate import script as tpov_truncate
from tpov_functions import *

tpov_commands = {
    "convert": tpov_convert,
    "extract": tpov_extract,
    "match": tpov_match,
    "truncate": tpov_truncate
}

parser = argparse.ArgumentParser (
    description = "Create a POV video from a GPX track and OSM map",
    formatter_class = argparse.RawDescriptionHelpFormatter,
    epilog = """"""
)
parser.add_argument ("commands", help = "A JSON file containing commands and arguments")
args = parser.parse_args ()

with open (args.commands, "r") as f:
    cmds = f.read ()
    if "%video" in cmds:
        p_video = True
    else:
        p_video = Null # Variable not needed

# p_{name} variables are set as %{name} in the commands file
# %video matches any video file (determined using the 'file' command)
p_dir = os.path.dirname (os.path.abspath (__file__))
p_name = os.path.basename (os.getcwd ())

if p_video:
    # Ask the user for a video file
    files, file_cmd = os.listdir (), ["file", "--mime"]
    file_cmd.extend (files)
    file_cmd.pop ()
    types = subprocess.run (file_cmd, capture_output = True)
    types.check_returncode ()
    types = tuple ((i.split () [-2].replace (";", "") for i in types.stdout.decode ().split ("\n") if i))

    types = tuple ((i, j) for i, j in zip (files, types) if os.path.splitext (i) [0] == p_name and j.startswith ("video/"))
    if not types:
        raise ValueError ("No video files found")
    elif len (types) == 1:
        p_video = types [0] [0]
        print (f"Using video file {p_video}")
    else:
        choicetable (["Filename", "Filetype"], types)
        p_video = next (choice (types, "Choose a video file to process: ", 1, 1)) [0]

cmds = cmds.replace (r"%dir", p_dir).replace (r"%name", p_name).replace (r"%video", p_video)
args = json.loads (cmds) ["args"]
for j, i in enumerate (args):
    if f"${j}" in cmds:
        cmds = cmds.replace (f"${j}", i)
cmds = json.loads (cmds) ["cmds"]

for i in cmds:
    if i.startswith ("%tpov_"):
        try:
            tpov_commands [i.split () [0] [6 : ]] (i.split (None, 1) [1])
        except Exception as e:
            print (f"Error running command {i [1 : ]}")
            raise e
    else:
        cmd = subprocess.run (shlex.split (i), stdout = sys.stdout, stderr = sys.stderr)