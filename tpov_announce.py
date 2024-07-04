# Built-in modules:
import os, json, wave, argparse

# Third-party modules:
import jsonschema

def create_folder (gpx_path, stop_data, params, output):
    def format_name (name, scope, stop_index = None):
        nonlocal stop_data, gpx_path
        if scope == "line":
            tags = {k: str (v) for k, v in stop_data.items () if k != "__stops__"} # Get all global (line) tags
            tags ["%g"] = os.path.splitext (os.path.basename (gpx_path)) [0] # GPX filename
            return name.format (**tags)
        elif scope == "stop":
            tags = {k: str (v) for k, v in stop_data ["__stops__"] [stop_index]} # Get stop-specific tags
            tags ["%i"] = str (stop_index) # Stop index
            tags ["%I"] = str (stop_index + 1) # Stop index (1-based)
            return name.format (**tags)
        raise ValueError ("Invalid scope. Possible values: 'line', 'stop'")


if __name__ == "__main__":
    parser = argparse.ArgumentParser (
        description = "Create an audio track with stop announcements",
        formatter_class = argparse.RawDescriptionHelpFormatter,
        epilog = """\
""" # TODO: Add epilog
    )
    parser.add_argument ("params", help = "Path to JSON parameter file")
    parser.add_argument ("gpx", help = "Path to .gpx track file")
    parser.add_argument ("stop", help = "Path to JSON stop data")
    parser.add_argument ("output", help = "Parent directory of output")
    args = parser.parse_args ()

    params = json.load (open (args.params, "r"))
    schema = json.load (open ("announce_schema.json", "r"))
    jsonschema.validate (instance = params, schema = schema)
    stop_data = json.load (open (args.stop, "r"))

    create_folder (args.gpx, stop_data, params, args.output)
