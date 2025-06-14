# Built-in modules:
import subprocess, struct, pickle, os, sys, math, json, argparse, shutil

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
        self.tags [w.id].setdefault ("highway", "unknown") # Default highway type
        if w.tags.get ("oneway") != "-1":
            for i, j in zip (tuple (w.nodes), tuple (w.nodes) [1 : ]):
                self.map_con.add_edge (i.ref, j.ref)
                self.tags [struct.pack ("<Q", i.ref) + struct.pack ("<Q", j.ref)] = w.id # two 64-bit keys
        if w.tags.get ("oneway") != "yes":
            for i, j in zip (tuple (w.nodes) [1 : ], tuple (w.nodes)):
                self.map_con.add_edge (i.ref, j.ref)
                self.tags [struct.pack ("<Q", i.ref) + struct.pack ("<Q", j.ref)] = w.id
        self.way_cnt.update ()

class startWayHandler (osmium.SimpleHandler):
    class WayFound (Exception):
        pass
    def __init__ (self, way_id, stats = {}):
        super (startWayHandler, self).__init__ ()
        self.way_id = way_id
        self.way_cnt = tqdm (total = int (stats.get ("ways", 0)), desc = "Finding start way", mininterval = 0.5)
        self.nodes = None
    def way (self, w):
        if w.id == self.way_id:
            self.nodes = tuple ((i.ref for i in w.nodes))
            self.way_cnt.close ()
            raise self.WayFound ()
        self.way_cnt.update ()

# Visualize each intersection and action (e.g. process_divided) in a HTML file with a map background
class HTMLVisualizer:
    def __init__ (self, lat, lon, template = None):
        if template is None:
            raise ValueError ("Template file not provided.")
        elif not os.path.exists (proj_path (template)):
            raise FileNotFoundError (f"Could not find {template}")
        with open (proj_path (template), "r") as f:
            self.template = f.read ()
        self.lat, self.lon = lat, lon
        self.markers = set (), {}
        self.points = []
        self.replacements = {
            r"%lat": lambda: str (self.lat),
            r"%lon": lambda: str (self.lon),
            r"%markers": lambda: str (list (self.markers.values ())),
            r"%points": lambda: str (self.points)
        }
    def add_marker (self, uid, lat, lon, text = ""):
        if uid in self.markers:
            self.markers [uid] ["text"] += f"<br><br>{text}"
        else:
            self.markers [uid] = {"lat": lat, "lon": lon, "text": text}
    def add_point (self, lat, lon):
        self.points.append ([lat, lon])
    def write (self, path = os.path.abspath (proj_path ("visualization.html"))):
        page = self.template
        for i, j in self.replacements.items ():
            page = page.replace (i, j ())
        with open (path, "w") as f:
            f.write (page)
        print (f"Visit file://{path} in a browser to view the visualization.")

# Saves intersection and actions (e.g. process_divided) to a GPX file
class GPXVisualizer:
    def __init__ (self, lat, lon, template = None): # lat, lon, template are not used
        self.markers = {}
        self.gpx = gpxpy.gpx.GPX ()
        track = gpxpy.gpx.GPXTrack ()
        self.gpx.tracks.append (track)
        self.segment = gpxpy.gpx.GPXTrackSegment ()
        track.segments.append (self.segment)
    def add_marker (self, uid, lat, lon, text = ""):
        if uid in self.markers:
            self.markers [uid].description += f"<br><br>{text}"
        else:
            self.markers [uid] = gpxpy.gpx.GPXWaypoint (lat, lon, description = text)
    def add_point (self, lat, lon):
        self.segment.points.append (gpxpy.gpx.GPXTrackPoint (lat, lon))
    def write (self, path = os.path.abspath (proj_path ("visualization.gpx"))):
        for i in self.markers.values ():
            self.gpx.waypoints.append (i)
        with open (path, "w") as f:
            f.write (self.gpx.to_xml ())
        print (f"Load {path} in a GPX viewer to view the visualization.")

def match_gpx (
    gpx_path,
    map_path,
    start_id,
    matcher_cls = SimpleMatcher, # Matcher class
    use_rtree = False, # Whether to use rtree in InMemMap (slow)
    exit_filter = lambda way: True, # Filter for intersection exits
    default_name = "Unnamed Road", # Default name for unnamed roads
    forward_angle = 45, # Angle threshold for forward direction
    follow_link = "Link -> %n", # Replace %n with link destination name, False to disable
    process_divided = None, # Divided road processing parameters
    hw_priority = {}, # Priority for highway types, default is 0
    matcher_params = {}, # Matcher parameters
    visualize = False): # Visualization parameters

    with open (gpx_path, "r") as f:
        gpx = gpxpy.parse (f)
        points = tuple (gpx.walk (True))
    if visualize:
        bounds = gpx.get_bounds ()
        visualizer = visualizers [visualize ["visualizer"]] (bounds.min_latitude + (bounds.max_latitude - bounds.min_latitude) / 2,
                                                             bounds.min_longitude + (bounds.max_longitude - bounds.min_longitude) / 2,
                                                             visualize.get ("template"))

    # Add a dict of information about a node into a marker
    def add_marker (node, info, title = "Marker"):
        if visualize:
            nonlocal visualizer, map_con
            template = "<b>{title}</b><br>Node ID: {node}<br>Latitude: {lat}<br>Longitude: {lon}<br>{info}"
            lat, lon = map_con.graph [node] [0]
            info = "<br>".join (f"{k}: {v}" for k, v in info.items ())
            visualizer.add_marker (node, lat, lon, template.format (title = title, node = node, lat = lat, lon = lon, info = info))

    # Get number of ways and nodes in the map
    def map_stats ():
        stats = subprocess.run (["osmconvert", map_path, "--out-statistics"], capture_output = True)
        stats.check_returncode ()
        return {i.split (": ") [0]: i.split (": ") [1] for i in stats.stdout.decode ().split ("\n") if i}

    if not os.path.exists (map_path):
        raise FileNotFoundError ("Could not find map file.")
    
    # Test for processed file (.filtered.o5m)
    if os.path.exists (os.path.splitext (map_path) [0] + ".filtered.o5m"):
        map_path = os.path.splitext (map_path) [0] + ".filtered.o5m"

    if start_id:
        handler = startWayHandler (int (start_id), map_stats ())
        try:
            handler.apply_file (map_path)
        except startWayHandler.WayFound:
            pass
        if handler.nodes is None:
            raise ValueError (f"Start way {start_id} not found in map file.")

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
        stats = map_stats ()
        handler = lmmHandler (InMemMap (map_path, use_latlon = True, index_edges = True, use_rtree = use_rtree), stats)
        handler.apply_file (map_path)
        map_con, tags = handler.map_con, handler.tags
        del handler # Free memory
        with open (map_path + ".pkl", "wb") as f:
            pickle.dump ((map_con.serialize (), tags), f)
        print (f"Saved pickle to {map_path}.pkl")

    print (f"Running {matcher_cls.__name__}...")
    if start_id:
        start_con = map_con.serialize ()
        start_graph = {}
        for i in handler.nodes: # Hack to only keep start way nodes
            start_graph [i] = (
                start_con ["graph"] [i] [0],
                [j for j in start_con ["graph"] [i] [1] if j in handler.nodes] # Remove neighbours not on the start way
            )
        start_con ["graph"] = start_graph
        start_con = InMemMap.deserialize (start_con)
        matcher = matcher_cls (start_con, **matcher_params)
        _, lastidx = matcher.match ([(i.latitude, i.longitude, i.time) for i in points], tqdm = tqdm)
        print (f"Matched {lastidx} points on start way {start_id}")
        start_con.graph = map_con.graph # Restore original graph
    else:
        matcher = matcher_cls (map_con, **matcher_params)

    _, lastidx = matcher.match([(i.latitude, i.longitude, i.time) for i in points], tqdm = tqdm)
    if lastidx < len (points) - 1:
        if not lastidx: # No points matched - likely due to origin being too far from a road
            raise SystemExit ("No points matched. Try increasing max_dist_init in the matcher parameters or setting a start way.")
        last_l1, last_l2 = matcher.lattice_best [lastidx].edge_m.l1, matcher.lattice_best [lastidx].edge_m.l2
        if input (
            f"Not all points were matched. Last matched {last_l1} -> {last_l2} at ({map_con.graph [last_l1] [0] [1]}, {map_con.graph [last_l1] [0] [0]})."
            "\nThis may be fixed by increasing max_dist and/or max_dist_init in the matcher parameters."
            "\nIn certain cases truncating the beginning of the GPX file may help, which can be done with this command:"
            f"\n{sys.executable} {proj_path ('tpov_truncate.py')} {gpx_path} -t {iso_time (points [lastidx + 1].time)} {iso_time (points [-1].time)}"
            "\nContinue processing (Y/n)? ").lower () != "y":
            raise SystemExit ("Processing cancelled.")
        add_marker (last_l1, {"Last Matched Way": f"{last_l1} -> {last_l2}"}, "Last Matched Node")

    for i, j in zip (matcher.lattice_best, matcher.lattice_best [1 : ]):
        if not (i.edge_m.l1 == j.edge_m.l1 and i.edge_m.l2 == j.edge_m.l2) and i.edge_m.l2 != j.edge_m.l1:
            raise NotImplementedError (f"Path discontinuity at ({i.edge_m.l1}, {i.edge_m.l2}) -> ({j.edge_m.l1}, {j.edge_m.l2})")

    exit_name = tags [tags [struct.pack ("<Q", matcher.lattice_best [0].edge_m.l1) +
                            struct.pack ("<Q", matcher.lattice_best [0].edge_m.l2)]].get ("name", default_name)
    last_name = exit_name
    # [gpx index, intersection node, current name, left name, forward name, right name, exit direction]
    directions = [(0, matcher.lattice_best [0].edge_m.l1, exit_name, "", "", "", "")]

    def node_heading (node2, node1):
        nonlocal map_con
        return math.degrees (math.atan2 (map_con.graph [node2] [0] [1] - map_con.graph [node1] [0] [1],
                                         map_con.graph [node2] [0] [0] - map_con.graph [node1] [0] [0]))
    def node_distance (node2, node1):
        nonlocal map_con
        return gpxpy.geo.Location (map_con.graph [node2] [0] [1], map_con.graph [node2] [0] [0]).distance_2d (
               gpxpy.geo.Location (map_con.graph [node1] [0] [1], map_con.graph [node1] [0] [0]))

    # Find loops (either U-turns or matching errors)
    curr_index = 0
    curr_edge = (matcher.lattice_best [0].edge_m.l1, matcher.lattice_best [0].edge_m.l2)
    # [(edge, start point, end point), ...] end point is exclusive
    edges = []
    for i in range (len (matcher.lattice_best)):
        edge = (matcher.lattice_best [i].edge_m.l1, matcher.lattice_best [i].edge_m.l2)
        if edge != curr_edge:
            edges.append ((curr_edge, curr_index, i))
            curr_edge, curr_index = edge, i
    edges.append ((curr_edge, curr_index, len (matcher.lattice_best))) # Add last edge

    # [[start point, end point, start node, end node, length in m, road name(s)], ...]
    loops = []
    for j, i in enumerate (edges [ : -1]):
        length, length_m, names = 0, 0, []
        while set (edges [j - length] [0]) == set (edges [j + length + 1] [0]) and j - length >= 0 and j + length + 1 < len (edges):
            nodes = edges [j - length] [0] # two nodes of the edge
            length_m += node_distance (*nodes)
            names.append (tags [tags [struct.pack ("<Q", nodes [0]) + struct.pack ("<Q", nodes [1])]].get ("name", default_name))
            length += 1
        length -= 1 # Remove last iteration
        if length >= 0:
            loops.append ((
                edges [j - length] [1],
                edges [j + length + 1] [2],
                edges [j - length] [0] [0],
                edges [j] [0] [1],
                format (length_m, ".4f"),
                ", ".join (dict.fromkeys (names)), # Remove duplicates
                edges [j] [2], # Middle point of the loop
            ))

    if loops:
        choicetable (
            ["Start Point", "End Point", "Start Node", "End Node", "Length", "Road Name(s)"],
            [i [ : 6] for i in loops]
        )
        print ("Select any loops to remove if they are matching errors and not U-turns.")
        remove = list (choice (loops, "(Press Enter if you don't understand): "))
        for i in remove:
            if i [0] == 0:
                midpoint = i [0] # Fill all edges from the back
            elif i [1] == len (matcher.lattice_best):
                midpoint = i [1] # Fill all edges from the front
            else:
                midpoint = i [6] # Fill half from the front and half from the back
            for j in range (i [0], midpoint):
                matcher.lattice_best [j] = matcher.lattice_best [i [0] - 1]
            for j in range (midpoint, i [1]):
                matcher.lattice_best [j] = matcher.lattice_best [i [1]]

    def divided_process (case, dest, orig, *, orig_id = None, orig_angle = None, lattice_index = None):
        # Return true if action should be taken (e.g. ignore exit, add exit), false otherwise
        nonlocal directions, map_con, tags, process_divided, matcher, default_name, add_marker
        if case not in process_divided ["enabled_cases"]:
            return False

        if case == 1: # Case 1: Ignore short spur which leads to the opposite side of the divided road
            if orig_id is None or orig_angle is None:
                raise ValueError ("process_divided: orig_id and orig_angle must be provided for case 1")

            dist = node_distance (dest, orig)
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
                if len (exits) != 1: # Not a spur which just leads to the opposite side
                    break

                orig, dest = dest, exits [0] # Move to next node
                name = tags [tags [struct.pack ("<Q", orig) + struct.pack ("<Q", dest)]].get ("name", default_name)
                visited.append (orig)
                angle = (node_heading (dest, orig) - orig_angle) % 360
                angle_diff = abs (180 - angle)
                if angle_diff <= process_divided ["angle"]:
                    if not process_divided ["same_name"] or tags [orig_id].get ("name", default_name) == name:
                        print (f"process_divided (1): Ignoring {', '.join (names)} {visited [0]} -> {orig} with angle {angle_diff:.4f} and length {dist:.4f}")
                        add_marker (visited [0], {"Name(s)": ", ".join (names), "Angle": angle_diff, "Length": dist}, "process_divided (1)")
                        return True

                dist += node_distance (dest, orig)
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

            orig_angle = node_heading (prev, prev2)
            angle = (node_heading (dest, orig) - orig_angle) % 360
            angle_diff = abs (180 - angle)
            if angle_diff > process_divided ["angle"]:
                return False

            # If straight-line distance is larger than threshold, no need to check individual segments
            rough_dist = node_distance (orig, prev)
            if rough_dist > process_divided ["length"]:
                return False
            dist, last_node = 0, prev
            for i in matcher.lattice_best [directions [-1] [0] : ]:
                if i.edge_m.l2 != last_node:
                    dist += node_distance (i.edge_m.l2, last_node)
                    if dist > process_divided ["length"]:
                        return False
                    last_node = i.edge_m.l2
                if i.edge_m.l2 == orig:
                    print (f"process_divided (2): Ignoring {dest_name} {orig} -> {dest} with angle {angle_diff:.4f} and length {dist:.4f}")
                    add_marker (orig, {"Name": dest_name, "Angle": angle_diff, "Length": dist}, "process_divided (2)")
                    return True
            print ("process_divided (2): Distance calculation reached the end of the path. Please report this error.")
            return False # Should not reach here

        elif case == 3: # Case 3: Add exit to [directions] for a far turn (e.g. left in right-hand traffic) onto a divided road
            dest_angle = node_heading (dest, orig)
            dest_name = tags [tags [struct.pack ("<Q", orig) + struct.pack ("<Q", dest)]].get ("name", default_name)
            prev = directions [-1] [1] # Previous intersection node
            prev2 = matcher.lattice_best [directions [-1] [0] - 1].edge_m.l1 # Previous road
            prev_l2 = matcher.lattice_best [directions [-1] [0]].edge_m.l2 # Next node of previous intersection

            if len ({prev2, prev, orig, dest}) != 4: # Skip if any node is repeated (e.g. backtracking of a two-way road)
                return False

            orig_angle = node_heading (prev_l2, prev)
            if abs (dest_angle - orig_angle) < process_divided ["angle"]: # Usually caused by backtracking of a two-way road becoming divided
                return False

            prev_angle = (node_heading (prev, prev2) - orig_angle) % 360
            prev_angle = 180 - abs (180 - prev_angle)
            if prev_angle > process_divided ["angle"]:
                return False # Side road bend too sharp, usually caused by backtracking of a two-way road (may need to adjust angle threshold)

            # If straight-line distance is larger than threshold, no need to check individual segments
            rough_dist = node_distance (orig, prev)
            if rough_dist > process_divided ["length"]:
                return False # Too far to be a divided road

            dist, last_node = 0, prev
            for i in matcher.lattice_best [directions [-1] [0] : ]:
                if i.edge_m.l2 != last_node:
                    dist += node_distance (i.edge_m.l2, last_node)
                    if dist > process_divided ["length"]:
                        return False
                    last_node = i.edge_m.l2
                if i.edge_m.l2 == orig:
                    break

            for i in map_con.graph [prev] [1]:
                if i in (orig, prev2, prev_l2):
                    continue # Skip matched roads
                prev_name = tags [tags [struct.pack ("<Q", prev) + struct.pack ("<Q", i)]].get ("name", default_name)
                if process_divided ["same_name"] and prev_name != dest_name:
                    continue

                angle = (node_heading (prev, i) - dest_angle) % 360
                angle = 180 - abs (180 - angle)
                if angle > process_divided ["angle"]:
                    continue
                print (f"process_divided (3): Adding {prev_name} {prev} -> {i} with angles {prev_angle:4f}, {angle:.4f} and length {dist:.4f}")
                add_marker (orig, {"Name": prev_name, "Prev_Angle": prev_angle, "Angle": angle, "Length": dist}, "process_divided (3)")
                return prev_name
            return False

        elif case == 4: # Case 4: Ignore "intersection" when a divided road merges back into a two-way road
            if lattice_index is None:
                raise ValueError ("process_divided: lattice_index must be provided for case 4")

            path_dest = matcher.lattice_best [lattice_index + 1].edge_m.l2 # Next path node after orig
            if path_dest not in map_con.graph [orig] [1] or orig not in map_con.graph [path_dest] [1]:
                return False # orig -> path_dest not a two-way road

            prev = matcher.lattice_best [lattice_index].edge_m.l1 # Previous path node (may be not an intersection)
            dest_name = tags [tags [struct.pack ("<Q", orig) + struct.pack ("<Q", dest)]].get ("name", default_name)
            orig_name = tags [tags [struct.pack ("<Q", prev) + struct.pack ("<Q", orig)]].get ("name", default_name)
            path_name = tags [tags [struct.pack ("<Q", orig) + struct.pack ("<Q", path_dest)]].get ("name", default_name)
            if process_divided ["same_name"] and (orig_name != dest_name or orig_name != path_name): # Two sides of the divided road have different names
                return False

            exits = []
            for i in map_con.graph [dest] [1]:
                if i == orig:
                    return False # dest is a two-way road
                way = tags [tags [struct.pack ("<Q", dest) + struct.pack ("<Q", i)]]
                if not process_divided ["apply_filter"] or exit_filter (way):
                    exits.append (i)
            if len (exits) > 1: # dest -> dest2 not a one-way road with no intersections 
                return False
            dest2 = exits [0] # Next path node after dest (may be not an intersection)

            for i in matcher.lattice_best [lattice_index : : -1]:
                if i.edge_m.l2 == prev:
                    break
            prev2 = i.edge_m.l1 # Second previous path node
            if prev2 == orig: # U-turn at prev
                return False
            
            exits = []
            for i in map_con.graph [prev] [1]:
                if i == prev2:
                    return False # prev is a two-way road
                way = tags [tags [struct.pack ("<Q", prev) + struct.pack ("<Q", i)]]
                if not process_divided ["apply_filter"] or exit_filter (way):
                    exits.append (i)
            if len (exits) > 1: # prev -> orig not a one-way road with no intersections
                return False
            elif exits != [orig]: # Should not reach here
                print (f"process_divided (4): Only exit from prev {prev} is not orig {orig}. Please report this error.")
                return False

            prev_angle = node_heading (prev, prev2)
            dest_angle = (node_heading (dest2, dest) - prev_angle) % 360
            angle_diff = abs (180 - dest_angle) # Angle difference between two sides of the divided road
            if angle_diff > process_divided ["angle"]: # TODO: choose a more appropriate angle threshold
                pass # return False

            dist = node_distance (prev, dest)
            dist2 = node_distance (prev2, dest2)
            if dist > process_divided ["length"] and dist2 > process_divided ["length"]:
                # Sample two node distances, not a divided road if both are too far
                # May need a more sophisticated method to determine divided road (e.g. linear algebra)
                return False 

            print (f"process_divided (4): Ignoring {dest_name} {orig} -> {dest} with angle {angle_diff:.4f} and distance {dist:.4f} {dist2:.4f}")
            add_marker (orig, {"Name": dest_name, "Angle": angle_diff, "Distance": dist, "Distance2": dist2}, "process_divided (4)")
            return True

        raise NotImplementedError (f"Divided road processing for case {case} not implemented.")
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
            orig_angle = node_heading (orig, matcher.lattice_best [j].edge_m.l1)
            orig_id = tags [struct.pack ("<Q", matcher.lattice_best [j].edge_m.l1) + struct.pack ("<Q", orig)]
            exits, min_angle, min_index = [], None, 0

            for dest in map_con.graph [orig] [1]:
                way = tags [tags [struct.pack ("<Q", orig) + struct.pack ("<Q", dest)]]
                if dest == matcher.lattice_best [j].edge_m.l1:
                    if dest != i.edge_m.l2:
                        continue # Skip previous road
                    add_marker (orig, {}, "Warning: Loop detected")
                elif not (exit_filter (way) or dest == i.edge_m.l2):
                    continue # Use filter to exclude certain exits not leading to the next road
                elif process_divided and dest != i.edge_m.l2:
                    if divided_process (1, dest, orig, orig_id = orig_id, orig_angle = orig_angle):
                        continue
                    elif divided_process (2, dest, orig):
                        continue
                    elif divided_process (4, dest, orig, lattice_index = j):
                        continue

                angle = (node_heading (dest, orig) - orig_angle) % 360
                if angle > 180:
                    angle -= 360 # Normalize angle to (-180, 180]
                if dest == i.edge_m.l2:
                    exit_angle = angle # Save exit angle for next segment
                    exit_name = way.get ("name", default_name)
                    if not follow_link is False:
                        followed_name = link_follow (j + 1, way)
                if orig_id == tags [struct.pack ("<Q", orig) + struct.pack ("<Q", dest)]:
                    min_angle = angle # The same road is always treated as forward
                exits.append ((angle, way))
                last_dest = dest

            if len (exits) == 0:
                print (f"Warning: No exits found at node {orig}")
                continue # Skip if no exits
            elif len (exits) == 1:
                dirs = None
                if last_name != exit_name: # Road name change
                    dirs = (j + 1, orig, exit_name, "", "", "", "")
                    last_name = exit_name
                name = divided_process (3, last_dest, orig)
                if process_divided and name:
                    if exits [0] [0] > forward_angle: # T-junction right
                        dirs = (j + 1, orig, last_name, "", "", name, "right")
                        exit_dir = "right"
                    elif exits [0] [0] < -forward_angle: # T-junction left
                        dirs = (j + 1, orig, last_name, name, "", "", "left")
                        exit_dir = "left"
                    else:
                        name = False # No need to indicate straight exit
                if dirs:
                    directions.append (dirs)
                    if name: # Indicate process_divided (3) result
                        add_marker (orig, {"Current": last_name, "Left": dirs [3], "Forward": dirs [4], "Right": dirs [5], "Exit": exit_dir}, "Intersection")
                continue
            last_name = exit_name
            if not follow_link is False:
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
            
            if i == j + 1: # Single point between stops
                fields [j] ["tpov.stop_bar"] = "0" # No stop bar
            elif params ["bar_reverse"]:
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

    with open (gpx_path, "r") as f:
        gpx = gpxpy.parse (f)
        points = tuple (gpx.walk (True))

    indices = [
        min (range (len (points)),
        key = lambda x: points [x].distance_2d (gpxpy.geo.Location (float (i ["stop_lat"]), float (i ["stop_lon"])))) 
        for i in stop_data ["__stops__"]]

    if indices != sorted (indices):
        if indices == sorted (indices, reverse = True):
            raise SystemExit ("NaiveStopMatcher: NaiveStopMatcher failed to match stops. You likely extracted stop data for the other direction of travel.")
        raise SystemExit ("NaiveStopMatcher failed to match stops. Try using a different stop matcher.")
    print (f"NaiveStopMatcher: Matched {len (indices)} stops successfully.")
    return indices

def gpx_snap (gpx, map_con, lattice_best, distance):
    # This is a simple function which snaps GPX points to the nearest point on the matched path.
    # It tries to snap a point to its matched path segment, and `distance` segments ahead and behind.
    # It chooses the segment which results in the smallest distance between the original and snapped points.
    # References: https://stackoverflow.com/a/6853926, gpxpy.geo.Location.distance

    # TODO: fix sporadic snapping errors where the path suddenly jumps to a different road and back

    def intersection (point, y1, x1, y2, x2): # Returns matched point and distance from original point
        y, x = point.latitude, point.longitude
        scale = math.cos (math.radians (y2)) # Latitude correction (assume spherical Earth)
        y, y1, y2 = y * scale, y1 * scale, y2 * scale

        a, b, c, d = x - x1, y - y1, x2 - x1, y2 - y1
        dot, len_sq = a * c + b * d, c * c + d * d
        if len_sq == 0: # Zero-length segment
            param = -1 # Use (x1, y1) as closest point
        else:
            param = dot / len_sq

        if param < 0: # Closest point in segment is (x1, y1)
            xx, yy = x1, y1 / scale
        elif param > 1: # Closest point in segment is (x2, y2)
            xx, yy = x2, y2 / scale
        else: # Closest point is on the segment
            xx, yy = x1 + param * c, (y1 + param * d) / scale
        
        return yy, xx, gpxpy.geo.Location (yy, xx).distance_2d (point)

    segments, k = [lattice_best [0].edge_m], 1
    seg_equal = lambda i, j: i.l1 == j.l1 and i.l2 == j.l2
    def inc_k ():
        nonlocal k, segments, lattice_best
        if k >= len (lattice_best):
            return True
        if not seg_equal (lattice_best [k].edge_m, segments [-1]):
            segments.append (lattice_best [k].edge_m)
        k += 1
        return False

    while len (segments) < distance + 1:
        if inc_k ():
            return # Matched path is too short to snap

    for i, j in zip (gpx.walk (True), (i.edge_m for i in lattice_best)):
        while not seg_equal (segments [- distance - 1], j):
            if inc_k ():
                break
        while len (segments) > distance * 2 + 1:
            segments.pop (0)
        
        snaps = tuple (intersection (i, *map_con.graph [k.l1] [0], *map_con.graph [k.l2] [0]) for k in segments)
        i.latitude, i.longitude, _ = min (snaps, key = lambda x: x [2])

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
visualizers = {
    "HTMLVisualizer": HTMLVisualizer,
    "GPXVisualizer": GPXVisualizer
}

parser = argparse.ArgumentParser (
    description = "Process intersection and stop data using OSM",
    formatter_class = argparse.ArgumentDefaultsHelpFormatter,
    epilog = "See https://tpov.readthedocs.io/ for the latest documentation."
)
parser.add_argument ("params", help = "Path to JSON parameter file")
parser.add_argument ("gpx", help = "Path to .gpx track file")
parser.add_argument ("--map", metavar = "file", help = "Path to .o5m map file")
parser.add_argument ("--stop", metavar = "JSON", help = "Path to stop data")
parser.add_argument ("--start", metavar = "ID", help = "Start node or way of the track")

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
    hw_priority = params ["hw_priority"]
    matcher_params = params ["matcher_params"]
    display_params = params ["display_params"]
    display = displays [display_params ["display"]]
    visualize = params ["visu_params"]

    if args.map:
        dirs, lattice_best, map_con, visualizer = match_gpx (
            gpx_path = args.gpx,
            map_path = args.map,
            start_id = args.start,
            matcher_cls = map_matcher,
            use_rtree = use_rtree,
            exit_filter = exit_filter,
            default_name = default_name,
            forward_angle = forward_angle,
            follow_link = follow_link,
            process_divided = process_divided,
            hw_priority = hw_priority,
            matcher_params = matcher_params,
            visualize = visualize)
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
    if (not snap_gpx is False) and args.map: # Snap GPX points to the matched path
        gpx_snap (gpx, map_con, lattice_best, snap_gpx)
            
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
        fp = next (gpx.walk (True))
        visualizer.add_marker (object (), fp.latitude, fp.longitude, f"<b>Origin</b><br>Latitude: {fp.latitude}<br>Longitude: {fp.longitude}")
        for i in gpx.walk (True):
            lp = i
            visualizer.add_point (i.latitude, i.longitude)
        visualizer.add_marker (object (), lp.latitude, lp.longitude, f"<b>Destination</b><br>Latitude: {lp.latitude}<br>Longitude: {lp.longitude}")
        visualizer.write ()

def script (args):
    import shlex
    main (parser.parse_args (shlex.split (args)))

if __name__ == "__main__":
    main (parser.parse_args ())