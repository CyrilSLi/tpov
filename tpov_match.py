# Built-in modules:
import subprocess, struct, pickle, os, math, json, bisect, argparse, shutil

# Third-party modules:
import osmium, gpxpy, jsonschema
from tqdm import tqdm
from texttable import Texttable
from leuvenmapmatching.map.inmem import InMemMap
from leuvenmapmatching.matcher.simple import SimpleMatcher
from leuvenmapmatching.matcher.distance import DistanceMatcher

# Try to load LXML or fallback to cET or ET
try:
    import lxml.etree as etree
except ImportError:
    try:
        import xml.etree.cElementTree as etree
    except ImportError:
        import xml.etree.ElementTree as etree

from tpov_functions import *

class lmmHandler (osmium.SimpleHandler):
    def __init__ (
            self,
            map_con = InMemMap ("map", use_latlon = True, index_edges = True), # rtree is slower
            stats = {}):
        super (lmmHandler, self).__init__ ()
        self.map_con = map_con
        self.stats = stats
        self.node_cnt = tqdm (total = int (self.stats.get ("nodes", 0)), desc = "Reading nodes", mininterval = 0.5)
        self.tags = {}
    
    def node (self, n):
        self.map_con.add_node (n.id, (n.location.lat, n.location.lon))
        self.node_cnt.update ()

    def way (self, w):
        if self.node_cnt:
            self.node_cnt.close ()
            self.node_cnt = None
            self.way_cnt = tqdm (total = int (self.stats.get ("ways", 0)), desc = "Reading ways", mininterval = 0.5)
        self.tags [w.id] = dict (w.tags)
        if w.tags.get ("oneway") != "-1":
            for i, j in zip (tuple (w.nodes), tuple (w.nodes) [1 : ]):
                self.map_con.add_edge (i.ref, j.ref)
                self.tags [struct.pack ("<Q", i.ref) + struct.pack ("<Q", j.ref)] = w.id # two 64-bit keys
        if w.tags.get ("oneway") != "yes":
            for i, j in zip (tuple (w.nodes) [1 : ], tuple (w.nodes)):
                self.map_con.add_edge (i.ref, j.ref)
                self.tags [struct.pack ("<Q", i.ref) + struct.pack ("<Q", j.ref)] = w.id
        self.way_cnt.update ()

# Visualize each intersection and action (e.g. process_divided) in a HTML file with a map background
class HTMLVisualizer:
    def __init__ (self, lat, lon, template = proj_path ("visualization_template.html"), combine_duplicates = True):
        with open (template, "r") as f:
            self.template = f.read ()
        self.combine_duplicates = combine_duplicates
        self.lat, self.lon = lat, lon
        self.uids, self.markers = set (), {}
        self.points = []
        self.replacements = {
            r"%lat": lambda: str (self.lat),
            r"%lon": lambda: str (self.lon),
            r"%markers": lambda: str (list (self.markers.values ())),
            r"%points": lambda: str (self.points)
        }
    def add_marker (self, uid, lat, lon, text = ""):
        if uid in self.uids:
            if self.combine_duplicates:
                self.markers [uid] ["text"] += f"<br><br>{text}"
        else:
            self.markers [uid] = {"lat": lat, "lon": lon, "text": text}
            self.uids.add (uid)
    def add_point (self, lat, lon):
        self.points.append ([lat, lon])
    def write (self, path = proj_path ("visualization.html")):
        page = self.template
        for i, j in self.replacements.items ():
            page = page.replace (i, j ())
        with open (path, "w") as f:
            f.write (page)

def match_gpx (
    gpx_path,
    map_path,
    matcher_cls = "SimpleMatcher", # Matcher class
    use_rtree = False, # Whether to use rtree in InMemMap (slow)
    exit_filter = lambda way: True, # Filter for intersection exits
    default_name = "Unnamed Road", # Default name for unnamed roads
    forward_angle = 45, # Angle threshold for forward direction
    follow_link = "%n", # Replace %n with link destination name, "" to disable
    process_divided = None, # Divided road processing parameters
    visualize = False, # Visualize intersections and actions in HTML
    hw_priority = {}, # Priority for highway types, default is 0
    matcher_params = {}): # Matcher parameters

    with open (gpx_path, "r") as f:
        gpx = gpxpy.parse (f)
        points = tuple (gpx.walk (True))
    if visualize:
        if not os.path.exists (proj_path ("visualization_template.html")):
            raise FileNotFoundError ("Could not find visualization_template.html.")
        bounds = gpx.get_bounds ()
        visualizer = HTMLVisualizer (bounds.min_latitude + (bounds.max_latitude - bounds.min_latitude) / 2,
                                     bounds.min_longitude + (bounds.max_longitude - bounds.min_longitude) / 2)

    if not os.path.exists (map_path):
        raise FileNotFoundError ("Could not find map file.")
    
    # Test for processed file (.filtered.o5m) and/or pickled index (.pkl)
    if os.path.exists (os.path.splitext (map_path) [0] + ".filtered.o5m"):
        map_path = os.path.splitext (map_path) [0] + ".filtered.o5m"
    if os.path.exists (map_path + ".pkl"):
        map_path = map_path + ".pkl"

    if os.path.splitext (map_path) [1] == ".pkl":
        with open (map_path, "rb") as f:
            print ("Loading map from pickle... ", end = "", flush = True)
            map_con, tags = pickle.load (f)
            map_con = InMemMap.deserialize (map_con)
            print ("Done")
    else:
        print ("Loading map from OSM file...")
        stats = subprocess.run (["osmconvert", map_path, "--out-statistics"], capture_output = True)
        stats.check_returncode ()
        stats = {i.split (": ") [0]: i.split (": ") [1] for i in stats.stdout.decode ().split ("\n") if i}

        handler = lmmHandler (InMemMap (map_path, use_latlon = True, index_edges = True, use_rtree = use_rtree), stats)
        handler.apply_file (map_path)
        map_con, tags = handler.map_con, handler.tags
        del handler # Free memory
        with open (map_path + ".pkl", "wb") as f:
            pickle.dump ((map_con.serialize (), tags), f)
        print (f"Saved pickle to {map_path}.pkl")

    print (f"Running {matcher_cls.__name__}...")
    matcher = matcher_cls (map_con, **matcher_params)

    _, lastidx = matcher.match([(i.latitude, i.longitude, i.time) for i in points], tqdm = tqdm)
    if lastidx < len (points) - 1:
        if not lastidx: # No points matched - likely due to origin being too far from a road
            raise SystemExit ("No points matched. Try increasing max_dist_init in the matcher parameters.")
        last_l1, last_l2 = matcher.lattice_best [lastidx].edge_m.l1, matcher.lattice_best [lastidx].edge_m.l2
        if input (
            f"Not all points were matched. Last matched {last_l1} -> {last_l2} at ({map_con.graph [last_l1] [0] [1]}, {map_con.graph [last_l1] [0] [0]})."
            "\nThis may be fixed by increasing max_dist and/or max_dist_init in the matcher parameters."
            "\nContinue processing (Y/n)? ").lower () != "y":
            raise SystemExit ("Processing cancelled.")
    for i, j in zip (matcher.lattice_best, matcher.lattice_best [1 : ]):
        if not (i.edge_m.l1 == j.edge_m.l1 and i.edge_m.l2 == j.edge_m.l2) and i.edge_m.l2 != j.edge_m.l1:
            raise NotImplementedError (f"Path discontinuity at ({i.edge_m.l1}, {i.edge_m.l2}) -> ({j.edge_m.l1}, {j.edge_m.l2})")

    exit_name = tags [tags [struct.pack ("<Q", matcher.lattice_best [0].edge_m.l1) +
                            struct.pack ("<Q", matcher.lattice_best [0].edge_m.l2)]].get ("name", default_name)
    last_name = exit_name
    # [gpx index, intersection node, current name, left name, forward name, right name, exit direction]
    directions = [(0, matcher.lattice_best [0].edge_m.l1, exit_name, "", "", "", "")]

    # Add a dict of information about a node into a marker
    def add_marker (node, info, title = "Marker"):
        if visualize:
            nonlocal visualizer, map_con
            template = "<b>{title}</b><br>Node ID: {node}<br>Latitude: {lat}<br>Longitude: {lon}<br>{info}"
            lat, lon = map_con.graph [node] [0]
            info = "<br>".join (f"{k}: {v}" for k, v in info.items ())
            visualizer.add_marker (node, lat, lon, template.format (title = title, node = node, lat = lat, lon = lon, info = info))

    def divided_process (case, dest, orig, orig_id = None, orig_angle = None):
        # Return true if exit should be ignored, false otherwise
        nonlocal directions, map_con, tags, process_divided, matcher, default_name, visualize, add_marker
        for i in ("length", "angle", "same_name", "apply_filter"):
            if i not in process_divided:
                raise KeyError (f"process_divided: Missing parameter '{i}'")

        if case == 1: # Case 1: Ignore short spur which leads to the opposite side of the divided road
            dist = gpxpy.geo.Location (map_con.graph [dest] [0] [1], map_con.graph [dest] [0] [0]).distance_2d (
                   gpxpy.geo.Location (map_con.graph [orig] [0] [1], map_con.graph [orig] [0] [0]))
            visited = [orig] # Visited nodes to ignore backtracking
            names = {tags [tags [struct.pack ("<Q", orig) + struct.pack ("<Q", dest)]].get ("name", default_name)}
            while dist <= process_divided ["length"]:
                exits = []
                for j in map_con.graph [dest] [1]:
                    if j in visited:
                        continue
                    way = tags [tags [struct.pack ("<Q", dest) + struct.pack ("<Q", j)]]
                    if not process_divided ["apply_filter"] or exit_filter (way):
                        exits.append (j)
                if len (exits) != 1:
                    break

                orig, dest = dest, exits [0] # Move to next node
                name = tags [tags [struct.pack ("<Q", orig) + struct.pack ("<Q", dest)]].get ("name", default_name)
                visited.append (orig)
                angle = (math.degrees (math.atan2 (map_con.graph [dest] [0] [1] - map_con.graph [orig] [0] [1],
                                                   map_con.graph [dest] [0] [0] - map_con.graph [orig] [0] [0])) - orig_angle) % 360
                angle_diff = abs (180 - angle)
                #print (way.get ("name", default_name), angle_diff, dist, orig, dest)
                if angle_diff <= process_divided ["angle"]:
                    if not process_divided ["same_name"] or tags [orig_id].get ("name", default_name) == name:
                        print (f"process_divided (1): Ignoring {', '.join (names)} {visited [0]} -> {orig} with angle {angle_diff:.4f} and length {dist:.4f}")
                        add_marker (visited [0], {"Name(s)": ", ".join (names), "Angle": angle_diff, "Length": dist}, "process_divided (1)")
                        return True
                dist += gpxpy.geo.Location (map_con.graph [dest] [0] [1], map_con.graph [dest] [0] [0]).distance_2d (
                        gpxpy.geo.Location (map_con.graph [orig] [0] [1], map_con.graph [orig] [0] [0]))
                names.add (name)
            return False

        elif case == 2: # Case 2: Ignore exit to the opposite side of the divided road at a turn
            if directions [-1] [0] == 0: # Ignore first intersection
                return False
            prev = directions [-1] [1] # Previous intersection node
            prev2 = matcher.lattice_best [directions [-1] [0] - 1].edge_m.l1 # Previous road

            orig_name = tags [tags [struct.pack ("<Q", prev2) + struct.pack ("<Q", prev)]].get ("name", default_name)
            dest_name = tags [tags [struct.pack ("<Q", orig) + struct.pack ("<Q", dest)]].get ("name", default_name)
            if process_divided ["same_name"] and orig_name != dest_name:
                return False

            orig_angle = math.degrees (math.atan2 (map_con.graph [prev] [0] [1] - map_con.graph [prev2] [0] [1],
                                                   map_con.graph [prev] [0] [0] - map_con.graph [prev2] [0] [0]))
            angle = (math.degrees (math.atan2 (map_con.graph [dest] [0] [1] - map_con.graph [orig] [0] [1],
                                               map_con.graph [dest] [0] [0] - map_con.graph [orig] [0] [0])) - orig_angle) % 360
            angle_diff = abs (180 - angle)
            if angle_diff > process_divided ["angle"]:
                return False

            # If straight-line distance is larger than threshold, no need to check individual segments
            rough_dist = gpxpy.geo.Location (map_con.graph [orig] [0] [1], map_con.graph [orig] [0] [0]).distance_2d (
                         gpxpy.geo.Location (map_con.graph [prev] [0] [1], map_con.graph [prev] [0] [0]))
            if rough_dist > process_divided ["length"]:
                return False
            dist, last_node = 0, prev
            for i in matcher.lattice_best [directions [-1] [0] : ]:
                if i.edge_m.l2 != last_node:
                    dist += gpxpy.geo.Location (map_con.graph [i.edge_m.l2] [0] [1], map_con.graph [i.edge_m.l2] [0] [0]).distance_2d (
                            gpxpy.geo.Location (map_con.graph [last_node] [0] [1], map_con.graph [last_node] [0] [0]))
                    if dist > process_divided ["length"]:
                        return False
                    last_node = i.edge_m.l2
                if i.edge_m.l2 == orig:
                    print (f"process_divided (2): Ignoring {dest_name} {orig} -> {dest} with angle {angle_diff:.4f} and length {dist:.4f}")
                    add_marker (orig, {"Name": dest_name, "Angle": angle_diff, "Length": dist}, "process_divided (2)")
                    return True

        raise NotImplementedError ("Divided road processing for case {case} not implemented.")
    link_until = (None, -1) # (name, last index of link road)
    def link_follow (index, way): # Return the name of the destination road
        nonlocal matcher, tags, default_name, link_until, follow_link, add_marker
        if index <= link_until [1]:
            return link_until [0]

        way = way.copy () # Avoid modifying the original
        if way.get ("highway").endswith ("_link") and not way.get ("name"): # Link road without name
            for l, k in enumerate (matcher.lattice_best [index + 1 : ]): # Start from next match
                dest = tags [tags [struct.pack ("<Q", k.edge_m.l1) + struct.pack ("<Q", k.edge_m.l2)]]
                if not dest.get ("highway").endswith ("_link"):
                    link_until = (follow_link.replace ("%n", dest.get ("name", default_name)), index + l)
                    print (f"follow_link: Followed link {matcher.lattice_best [index].edge_m.l1} -> {k.edge_m.l1} to {dest.get ('name', default_name)}")
                    add_marker (matcher.lattice_best [index].edge_m.l1, {"Destination": dest.get ("name", default_name)}, "follow_link")
                    return link_until [0]
        return way.get ("name", default_name)

    for j, i in enumerate (matcher.lattice_best [1 : ]):
        orig = i.edge_m.l1
        if orig == matcher.lattice_best [j].edge_m.l2:
            dirs = ["", "", ""] # [left, forward, right]
            orig_angle = math.degrees (math.atan2 (map_con.graph [orig] [0] [1] - map_con.graph [matcher.lattice_best [j].edge_m.l1] [0] [1],
                                                   map_con.graph [orig] [0] [0] - map_con.graph [matcher.lattice_best [j].edge_m.l1] [0] [0]))
            orig_id = tags [struct.pack ("<Q", matcher.lattice_best [j].edge_m.l1) + struct.pack ("<Q", orig)]
            exits, min_angle, min_index = [], None, 0

            for dest in map_con.graph [orig] [1]:
                way = tags [tags [struct.pack ("<Q", orig) + struct.pack ("<Q", dest)]]
                if dest == matcher.lattice_best [j].edge_m.l1:
                    if dest != i.edge_m.l2:
                        continue # Skip previous road
                    print (f"Warning: Loop detected at node {orig} (may be a U-turn)")
                    add_marker (orig, {}, "Warning: Loop detected")
                elif not (exit_filter (way) or dest == i.edge_m.l2):
                    continue # Use filter to exclude certain exits not leading to the next road
                elif process_divided and dest != i.edge_m.l2:
                    if divided_process (1, dest, orig, orig_id, orig_angle):
                        continue
                    elif divided_process (2, dest, orig):
                        continue

                angle = (math.degrees (math.atan2 (map_con.graph [dest] [0] [1] - map_con.graph [orig] [0] [1],
                                                   map_con.graph [dest] [0] [0] - map_con.graph [orig] [0] [0])) - orig_angle) % 360
                if angle > 180:
                    angle -= 360 # Normalize angle to (-180, 180]
                if dest == i.edge_m.l2:
                    exit_angle = angle # Save exit angle for next segment
                    exit_name = way.get ("name", default_name)
                    if follow_link:
                        followed_name = link_follow (j + 1, way)
                if orig_id == tags [struct.pack ("<Q", orig) + struct.pack ("<Q", dest)]:
                    min_angle = angle # The same road is always treated as forward
                exits.append ((angle, way))

            if len (exits) == 0:
                print (f"Warning: No exits found at node {orig}")
                continue # Skip if no exits
            elif len (exits) == 1:
                if last_name != exit_name: # Road name change
                    directions.append ((j + 1, orig, exit_name, "", "", "", ""))
                    last_name = exit_name
                continue
            last_name = exit_name
            if follow_link:
                exit_name = followed_name
            exits = {k: v for k, v in sorted (exits, key = lambda x: x [0])} # Keep sorted order in dict

            if not min_angle:
                min_angle = min (exits.keys (), key = abs) # Minimum angle (slightest turn/straight)
            if min_angle == exit_angle: # Check if forward direction is the exit
                if min_angle > forward_angle: # T-junction right
                    dirs [2] = exit_name
                    exit_dir = "right"
                elif min_angle < -forward_angle: # T-junction left
                    dirs [0] = exit_name
                    exit_dir = "left"
                else: # Straight
                    dirs [1] = exit_name
                    exit_dir = "forward"
            elif min_angle > exit_angle: # Left turn
                dirs [0] = exit_name
                if min_angle > forward_angle: # T-junction
                    min_index = -1 # Include min_angle exit in dir_calc
                else:
                    dirs [1] = exits [min_angle].get ("name", default_name)
                exit_dir = "left"
            else: # Right turn
                dirs [2] = exit_name
                if min_angle < -forward_angle: # T-junction
                    min_index = 1 # Include min_angle exit in dir_calc
                else:
                    dirs [1] = exits [min_angle].get ("name", default_name)
                exit_dir = "right"

            min_index += tuple (exits.keys ()).index (min_angle) # Index of minimum angle
            dir_calc = ((0, -90, tuple (exits.items ()) [ : min_index]), # left
                        (2, 90, tuple (exits.items ()) [min_index + 1 : ])) # right

            for index, target, exits in dir_calc:
                if dirs [index] or not exits:
                    continue # Skip if already set or no ways left
                max_pri = -1
                for angle, way in exits:
                    pri = hw_priority.get (way ["highway"], 0)
                    angle_diff = abs (angle - target)
                    if pri > max_pri:
                        candidate = (way, angle_diff)
                        max_pri = pri
                    elif pri == max_pri and angle_diff < candidate [1]:
                        candidate = (way, angle_diff)
                dirs [index] = candidate [0].get ("name", default_name)
            # [gpx index, intersection node, current name, left name, forward name, right name, exit direction]
            directions.append ((j + 1, orig, last_name, dirs [0], dirs [1], dirs [2], exit_dir))
            add_marker (orig, {"Current": last_name, "Left": dirs [0], "Forward": dirs [1], "Right": dirs [2], "Exit": exit_dir}, "Intersection")

    return directions, matcher.lattice_best, map_con, visualizer if visualize else None

def SimpleTextDisplay (
        gpx,
        dirs,
        params,
        stop_indices = [],
        stop_data = {}):
    # gopro_overlay converts "" to "-", use zero width space to not display anything
    field = {
        "tpov.current": "\u200c",
        "tpov.left": "\u200c",
        "tpov.forward": "\u200c",
        "tpov.right": "\u200c",
        "tpov.left_exit": "\u200c",
        "tpov.forward_exit": "\u200c",
        "tpov.right_exit": "\u200c",
        "tpov.inter_dash": "0"
    }
    fields, metadata = None, {}
    stop_data = stop_data.copy () # Do not modify original data

    point = lambda i: gpx [max (0, min (i, len (gpx) - 1))]
    def range_set (start, stop, key, value):
        nonlocal fields, gpx
        for i in range (max (0, start), min (stop, len (gpx))):
            fields [i] [key] = value

    if stop_indices and stop_data:
        field.update ({
            "tpov.prev_stop": "\u200c",
            "tpov.next_stop": "\u200c",
            "tpov.transfers": "\u200c"
        })
        fields = tuple ((field.copy () for _ in gpx))
        stops = stop_data.pop ("__stops__")
        metadata.update ({f"tpov.{k}": v for k, v in stop_data.items ()})
        for j, i in enumerate (stops):
            metadata [f"tpov.stop.{j}"] = i ["stop_name"]
            if i ["__transfer__"]: # Do not display empty transfers
                metadata [f"tpov.transfer.{j}"] = params ["transfer_separator"].join (i ["__transfer__"])
            else:
                metadata [f"tpov.transfer.{j}"] = "\u200c"

        stop_indices = [i + 1 for i in stop_indices] # Use the first point after the stop
        # Using references in the gpx allows for easier editing but slower processing
        reference = lambda string: string if params ["use_reference"] else metadata [string]
        for k, (j, i) in enumerate (zip ([0] + stop_indices, stop_indices + [len (gpx)])):
            if 0 <= k - 1 < len (stops):
                range_set (j, i, "tpov.prev_stop", reference (f"tpov.stop.{k - 1}"))
            else:
                range_set (j, i, "tpov.prev_stop", "\u200c")
            if 0 <= k < len (stops):
                range_set (j, i, "tpov.next_stop", reference (f"tpov.stop.{k}"))
                range_set (j, i, "tpov.transfers", reference (f"tpov.transfer.{k}"))
            else:
                range_set (j, i, "tpov.next_stop", "\u200c")
                range_set (j, i, "tpov.transfers", "\u200c")
            
            if params ["bar_reverse"]:
                for m in range (j, i):
                    fields [m] ["tpov.stop_bar"] = str ((i - 1 - m) / (i - 1 - j))
            else:
                for m in range (j, i):
                    fields [m] ["tpov.stop_bar"] = str ((m - j) / (i - 1 - j))
    else:
        fields = tuple ((field.copy () for _ in range (len (gpx))))

    for j, i in enumerate (dirs):
        # Set current road name for all points in the segment
        range_set (i [0], dirs [j + 1] [0] if j + 1 < len (dirs) else len (gpx), "tpov.current", i [2])
        if i [6]: # Intersection
            for k, l in zip (("left", "forward", "right"), i [3 : 6]):
                if k == i [6]:
                    range_set (i [0] - params ["duration"], i [0], f"tpov.{k}_exit", l)
                    range_set (i [0] - params ["duration"], i [0], f"tpov.{k}", "\u200c") # Clear non-exit
                elif l: # Allow for close intersection exits to overlap (useful for dual carriageways)
                    range_set (i [0] - params ["duration"], i [0], f"tpov.{k}", l)
                    range_set (i [0] - params ["duration"], i [0], f"tpov.{k}_exit", "\u200c") # Clear exit
                else:
                    # Only show the most recent exit for close intersections
                    range_set (i [0] - params ["duration"], i [0], f"tpov.{k}_exit", "\u200c")
                range_set (i [0] - params ["duration"], i [0], "tpov.inter_dash", "1") # Display transparent overlay

    return metadata, fields

def NaiveStopMatcher (gpx_path, stop_data, lattice_best = None, map_con = None):
    # This is a naive implementation that matches stops to the nearest point in the GPX file
    # It is known to fail with lines which visit geographically close stops multiple times.
    # A better implementation would be to use a map-matching algorithm on the stop data.
    # That is why lattice_best and map_con are included as arguments, but they are not used in this function.
    def sq_dist (stop, point):
        dx = float (stop ["stop_lon"]) - point.longitude
        dy = (float (stop ["stop_lat"]) - point.latitude) * math.cos (math.radians (point.latitude)) # Latitude correction
        return dx * dx + dy * dy
    with open (gpx_path, "r") as f:
        gpx = gpxpy.parse (f)
        points = tuple (gpx.walk (True))

    indices = [min (range (len (points)), key = lambda x: sq_dist (i, points [x])) for i in stop_data ["__stops__"]]
    if indices != sorted (indices):
        raise SystemExit ("NaiveStopMatcher failed to match stops. Try using a different matcher.")
    print (f"NaiveStopMatcher: Matched {len (indices)} stops successfully.")
    return indices

map_matchers = {
    "SimpleMatcher": SimpleMatcher,
    "DistanceMatcher": DistanceMatcher
}
stop_matchers = {
    "NaiveStopMatcher": NaiveStopMatcher
}
displays = {
    "SimpleTextDisplay": SimpleTextDisplay
}

parser = argparse.ArgumentParser (
    description = "Process intersection and stop data using OSM",
    formatter_class = argparse.ArgumentDefaultsHelpFormatter,
    epilog = """""" # TODO: Add epilog
)
parser.add_argument ("params", help = "Path to JSON parameter file")
parser.add_argument ("gpx", help = "Path to .gpx track file")
parser.add_argument ("--map", help = "Path to .o5m map file")
parser.add_argument ("--stop", metavar = "JSON", help = "Path to stop data")

def main (args):
    params = json.load (open (args.params, "r"))
    schema = json.load (open (proj_path ("match_schema.json"), "r"))
    jsonschema.validate (instance = params, schema = schema)

    map_matcher = map_matchers [params ["map_matcher"]]
    stop_matcher = stop_matchers [params ["stop_matcher"]]
    use_rtree = params ["use_rtree"]
    exit_filter = lambda way: eval (params ["exit_filter"], {"way": way})
    default_name = params ["default_name"]
    forward_angle = params ["forward_angle"]
    follow_link = params ["follow_link"]
    snap_gpx = params ["snap_gpx"]
    process_divided = params ["process_divided"]
    visualize = params ["visualize"]
    hw_priority = params ["hw_priority"]
    matcher_params = params ["matcher_params"]
    display_params = params ["display_params"]
    display = displays [display_params ["display"]]

    if args.map:
        dirs, lattice_best, map_con, visualizer = match_gpx (
            gpx_path = args.gpx,
            map_path = args.map,
            matcher_cls = map_matcher,
            use_rtree = use_rtree,
            exit_filter = exit_filter,
            default_name = default_name,
            forward_angle = forward_angle,
            follow_link = follow_link,
            process_divided = process_divided,
            visualize = visualize,
            hw_priority = hw_priority,
            matcher_params = matcher_params)
    else:
        dirs, lattice_best, map_con, visualizer = [], [], None, None

    if args.stop:
        with open (args.stop, "r") as f:
            stop_data = json.load (f)
        stop_indices = stop_matcher (args.gpx, stop_data, lattice_best, map_con)
        if visualizer:
            for i in stop_data ["__stops__"]:
                visualizer.add_marker (object (), i ["stop_lat"], i ["stop_lon"], f"<b>Matched stop:</b> {i ['stop_name']}")
    else:
        stop_data, stop_indices = {}, []

    if dirs:
        table = Texttable (max_width = shutil.get_terminal_size ().columns)
        table.set_deco (Texttable.HEADER)
        table.set_cols_align (["l", "l", "l", "l", "l", "l", "l"])
        table.set_cols_dtype (["i", "i", "t", "t", "t", "t", "t"])
        table.header (["Point", "Node ID", "Current", "Left", "Forward", "Right", "Exit"])
        table.add_rows (dirs, header = False)
        print (table.draw ())

    gpx_out = os.path.abspath (os.path.splitext (args.gpx) [0] + ".matched.gpx")
    if input (f"Write stop and intersection data to {gpx_out} (Y/n)? ").lower () != "y":
        raise SystemExit ("Write cancelled.")
    with open (args.gpx, "r") as f:
        gpx = gpxpy.parse (f)

    metadata, fields = display (
        gpx = tuple (gpx.walk (True)),
        dirs = dirs,
        params = display_params,
        stop_indices = stop_indices,
        stop_data = stop_data
    )
    if not gpx.name:
        gpx.name = "tpov" # gpxpy does not write extensions without a normal tag

    if stop_data:
        for i in stop_data ["__stops__"]:
            gpx.waypoints.append (gpxpy.gpx.GPXWaypoint (latitude = i ["stop_lat"], longitude = i ["stop_lon"], name = i ["stop_name"]))
    if False and snap_gpx: # Snap GPX points to the nearest road # TODO: Fix snapping
        def intersection (y1, x1, y2, x2, y3, x3):
            if x1 == x2: # Vertical line
                return y3, x1
            if y1 == y2: # Horizontal line
                return y1, x3

            scale = math.cos (math.radians (y3)) # Latitude correction
            y1, y2, y3 = y1 * scale, y2 * scale, y3 * scale

            angle2 = math.atan2 (x2 - x1, y2 - y1)
            angle3 = math.atan2 (x3 - x1, y3 - y1)
            angle312 = angle3 - angle2
            #print (angle312)
            dist12 = ((y2 - y1) ** 2 + (x2 - x1) ** 2) ** 0.5
            dist13 = ((y3 - y1) ** 2 + (x3 - x1) ** 2) ** 0.5
            dist14 = math.cos (angle312) * dist13
            x4 = x1 + (x2 - x1) * dist14 / dist12
            y4 = y1 + (y2 - y1) * dist14 / dist12

            #print ((y4 - y1) / (x4 - x1), (y2 - y1) / (x2 - x1))
            #assert (y4 - y1) / (x4 - x1) == (y2 - y1) / (x2 - x1) # Check if the point is on the line

            return y4 / scale, x4

            slope, inv_slope = (y2 - y1) / (x2 - x1), -(x2 - x1) / (y2 - y1)
            intercept, inv_intercept = y1 - slope * x1, y3 - inv_slope * x3
            x4 = (inv_intercept - intercept) / (slope - inv_slope)
            y4 = slope * x4 + intercept

            return y4 / scale, x4

        l1, l2, k = lattice_best [0].edge_m.l1, lattice_best [0].edge_m.l2, 0
        for i, j in zip (gpx.walk (True), lattice_best):
            """ #path_points = (lattice_best [0].edge_m.l1, ) + tuple (j.edge_m.l2 for j in lattice_best)
            #path_points = gpxpy.geo.Location (map_con.graph [j] [0] for j in path_points)
            i.latitude, i.longitude = min ((intersection (
                *map_con.graph [j.edge_m.l1] [0],
                *map_con.graph [j.edge_m.l2] [0],
                i.latitude, i.longitude
            ) for j in lattice_best), key = lambda k: gpxpy.geo.Location (*k).distance_2d (i))
            visualizer.add_marker (object (), *map_con.graph [j.edge_m.l1] [0])
            visualizer.add_marker (object (), *map_con.graph [j.edge_m.l2] [0])
            #visualizer.add_marker (object (), i.latitude, i.longitude, "Original")
            continue """
            """ if k <= j:
                print (lattice_best [k].edge_m.l1, l1)
                while k + 1 < len (lattice_best) and lattice_best [k].edge_m.l1 == l1:
                    print (lattice_best [k].edge_m.l1, l1)
                    k += 1
                print (j, k)
                l1, l2 = l2, lattice_best [k].edge_m.l1 """
            i.latitude, i.longitude = intersection (
                *map_con.graph [j.edge_m.l1] [0],
                *map_con.graph [j.edge_m.l2] [0],
                i.latitude, i.longitude
            )
            
    for k, v in metadata.items ():
        ext = etree.Element (k)
        ext.text = str (v)
        gpx.metadata_extensions.append (ext)
    for i, j in zip (gpx.walk (True), fields):
        for k, v in j.items ():
            ext = etree.Element (k)
            ext.text = v
            i.extensions.append (ext)

    with open (gpx_out, "w") as f:
        f.write (gpx.to_xml (version = "1.1"))
        print ("Saved data to", gpx_out)
    
    if visualizer:
        html_path = os.path.abspath (proj_path ("visualization.html"))
        fp = next (gpx.walk (True))
        visualizer.add_marker (object (), fp.latitude, fp.longitude, f"<b>Origin</b><br>Latitude: {fp.latitude}<br>Longitude: {fp.longitude}")
        for i in gpx.walk (True):
            lp = i
            visualizer.add_point (i.latitude, i.longitude)
        visualizer.add_marker (object (), lp.latitude, lp.longitude, f"<b>Destination</b><br>Latitude: {lp.latitude}<br>Longitude: {lp.longitude}")
        visualizer.write (html_path)
        print (f"Visit file://{html_path} in a browser to view the visualization.")

def script (args):
    import shlex
    main (parser.parse_args (shlex.split (args)))

if __name__ == "__main__":
    main (parser.parse_args ())