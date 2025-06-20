# Built-in modules:
import os, bisect, json, csv, argparse, pickle, subprocess, re, hashlib, time, threading
from zoneinfo import ZoneInfo

from tpov_functions import *

global _stop_fields # {source: ([display fields], [field keys])}
_stop_fields = {
    "GTFS": (
        ["Name", "Latitude", "Longitude", "Depart", "ID"],
        ["stop_name", "stop_lat", "stop_lon", "departure_time", "stop_id"]
    ),
    "OSM": (
        ["Name", "Latitude", "Longitude", "Role", "ID"],
        ["stop_name", "stop_lat", "stop_lon", "role", "stop_id"]
    ),
    "12306": (
        ["Name", "Latitude", "Longitude", "Depart", "Telecode / ID"],
        ["stop_name", "stop_lat", "stop_lon", "startTime", "stop_id"]
    ),
    "__default__": (
        ["Name", "Latitude", "Longitude", "ID"],
        ["stop_name", "stop_lat", "stop_lon", "stop_id"]
    )
}

global core_tags # Core tags (consistent across all data sources)
core_tags = {
    "Global": ("__sourcetype__", "route_id", "route_long_name", "agency_name", "__stops__"),
    "Stop": ("stop_id", "stop_name", "stop_lat", "stop_lon", "__transfer__")
}

def from_gtfs (gtfs_dir = None, transfer = True, shape = False):
    # Third-party modules:
    from tqdm import tqdm

    if not gtfs_dir:
        raise ValueError ("GTFS directory cannot be empty.")
    orig = os.getcwd () # Save original working directory
    os.chdir (gtfs_dir)

    with open ("agency.txt") as f:
        agency = tuple (csv.DictReader (f))
        if len (agency) > 1:
            choicetable (
                ["Name", "URL"],
                ([i ["agency_name"], i ["agency_url"]] for i in agency)
            )
            agency = next (choice (agency, "Select one transit agency: ", 1, 1))
        else:
            agency = agency [0]
    
    route_name = input ("Enter the route short_name or long_name: ").lower ()
    if not route_name:
        raise ValueError ("Route name cannot be empty.")

    print ("Searching for route...")
    route, route_names = None, {}
    with open ("routes.txt") as f:
        for i in csv.DictReader (f):
            if route_name in (i ["route_short_name"].lower (), i ["route_long_name"].lower ()) and ("agency_id" not in i or i ["agency_id"] == agency ["agency_id"]):
                route = i
            route_names [i ["route_id"]] = i ["route_short_name"] if i ["route_short_name"] else i ["route_long_name"]
    if not route:
        raise ValueError (f"Route '{route_name}' not found.")

    print ("Searching for trips...")
    trip_names = {}
    with open ("trips.txt") as f:
        trip_ids = []
        for i in csv.DictReader (f):
            if i ["route_id"] == route ["route_id"]:
                trip_ids.append (i)
            trip_names [i ["trip_id"]] = route_names [i ["route_id"]]
    del route_names # Free up memory

    print (f"{len (trip_ids)} trips found.")
    if not os.path.exists ("stop_times_sorted.txt.pkl"): # Index stop_times for faster lookup
        with open ("stop_times.txt") as f:
            header = iter (csv.reader (f)).__next__ ()
            ti, ss = header.index ("trip_id") + 1, header.index ("stop_sequence") + 1
        
        with open ("stop_times_sorted.txt", "w") as f:
            writer = csv.writer (f)
            writer.writerow (header)
        # Reopen file as subprocess seem to reset the file pointer
        with open ("stop_times_sorted.txt", "a") as f:
            print ("Sorting stop_times (this may take a while)...")
            sort = subprocess.run (f"LC_ALL=C cat -u stop_times.txt | tail -n +2 | sort -t , -k {ti},{ti} -k {ss},{ss}n", shell = True, stdout = f)

        lines = subprocess.run (["wc", "-l", "stop_times_sorted.txt"], capture_output = True)
        lines.check_returncode ()
        lines = int (lines.stdout.decode ().split () [0])
        line_cnt = tqdm (total = lines, desc = "Indexing stop_times", mininterval = 0.5)
        ti -= 1 # Convert to 0-based index
        with open ("stop_times_sorted.txt") as f: # May be able to be optimized using csv module
            f.readline () # Skip header
            indices, last_id, fileptr, si = {}, None, f.tell (), header.index ("stop_id")
            line, transfers = f.readline (), {}
            h, linehash, dups, num_trips = hashlib.md5 (), set (), 0, 0
            while line:
                line_cnt.update ()
                line = line.strip ().split (",") # CSV format
                if line [ti] != last_id: # New trip_id
                    h = h.hexdigest ()
                    if h in linehash:
                        dups += 1
                    else:
                        indices [line [ti]] = fileptr
                        linehash.add (h)
                    h = hashlib.md5 ()
                    last_id = line [ti]
                    num_trips += 1

                h.update (",".join (i for j, i in enumerate (line) if j != ti and j != ss).encode ()) # Only check useful fields for duplicates
                transfers.setdefault (line [si], set ()).add (trip_names [line [ti]]) # Map route_short_name to stop
                fileptr = f.tell () # Save file pointer at beginning of line
                line = f.readline ()
            line_cnt.close ()

            with open ("stop_times_sorted.txt.pkl", "wb") as f:
                pickle.dump ((indices, transfers), f)
            print (f"Sorted and indexed {num_trips} trips, {len (indices)} unique, {dups} duplicates.")

    print ("Reading stop information...")
    with open ("stop_times_sorted.txt.pkl", "rb") as f:
        indices, transfers = pickle.load (f)
    dup = len (trip_ids)
    trip_ids = [i for i in trip_ids if i ["trip_id"] in indices] # Remove duplicates
    print (f"Removed {dup - len (trip_ids)} duplicate trips, {len (trip_ids)} remaining.")

    with open ("stop_times_sorted.txt") as f:
        header = iter (csv.reader (f)).__next__ ()
        for i in trip_ids:
            f.seek (indices [i ["trip_id"]]) # Seek to file pointer of trip_id
            line = csv.DictReader (f, fieldnames = header)
            for j in line:
                if j ["trip_id"] != i ["trip_id"]:
                    break
                # Convert departure_time from H:mm:ss to HH:mm:ss if necessary
                j ["departure_time"] = ("0" + j ["departure_time"].strip ()) [-8 : ]
                i.setdefault ("__stops__", []).append (j)

    start_time = input ("Enter the time the vehicle left the first stop in HH(:mm)(:ss) format, or a path to the recording video: ")
    if os.path.exists (start_time):
        start, _ = video_time (start_time, True) # Return datetime object
        start_time = start.astimezone (ZoneInfo (agency ["agency_timezone"])).strftime ("%H:%M:%S")
        print (f"Extracted start time from video: {start_time}")

    # Sort by departure_time of first stop
    trip_ids.sort (key = lambda x: x ["__stops__"] [0] ["departure_time"])

    num_trips = int (input (f"Enter the number of trips to display: "))
    trip = bisect.bisect_left (trip_ids, start_time, key = lambda x: x ["__stops__"] [0] ["departure_time"])
    if trip + num_trips // 2 >= len (trip_ids):
        trips_display = trip_ids [-num_trips : ]
    elif trip < (num_trips + 1) // 2:
        trips_display = trip_ids [ : num_trips]
    else:
        trips_display = trip_ids [trip - (num_trips + 1) // 2 : trip + num_trips // 2]

    stops = {} # set (j ["stop_id"] for i in trips_display for j in i ["__stops__"])
    print ("Searching for stop information...")
    for i in trips_display:
        for j in i ["__stops__"]:
            stops [j ["stop_id"]] = None
    with open ("stops.txt") as f:
        for i in csv.DictReader (f):
            if i ["stop_id"] in stops:
                stops [i ["stop_id"]] = i

    linehash = {}
    for i in trips_display:
        h = hashlib.md5 ()
        for j in i ["__stops__"]:
            j.update (stops [j ["stop_id"]])
            h.update (j ["stop_id"].encode ())
        linehash [i ["trip_id"]] = h.hexdigest ()

    # Final format of trips_display:
    # [{fields from trips.txt, "__stops__": [{fields from stop_times.txt + fields from stops.txt}, ...]}, ...]

    choicetable (
        ["Headsign", "From", "To", "Depart", "Arrive", "Trip ID", "Stops Hash"],
        ([
            i ["trip_headsign"] if "trip_headsign" in i else f"{route ['route_short_name']} {route ['route_long_name']}",
            i ["__stops__"] [0] ["stop_name"],
            i ["__stops__"] [-1] ["stop_name"],
            i ["__stops__"] [0] ["departure_time"],
            i ["__stops__"] [-1] ["departure_time"],
            i ["trip_id"],
            linehash [i ["trip_id"]]
        ] for i in trips_display)
    )
    trip = next (choice (trips_display, "Select one trip: ", 1, 1))

    trip.update (route)
    trip.update (agency)
    trip ["__sourcetype__"] = "GTFS"
    # As only one of route_short_name or route_long_name is required, fill in the other if empty
    if not trip ["route_short_name"]:
        trip ["route_short_name"] = trip ["route_long_name"]
    elif not trip ["route_long_name"]:
        trip ["route_long_name"] = trip ["route_short_name"]

    if shape:
        shape = []
        with open ("shapes.txt") as f:
            for i in csv.DictReader (f):
                if i ["shape_id"] == trip ["shape_id"]:
                    shape.append (([float (i ["shape_pt_lon"]), float (i ["shape_pt_lat"])], int (i ["shape_pt_sequence"])))
        trip ["__shape__"] = [i [0] for i in sorted (shape, key = lambda x: x [1])] # Sort by sequence

    os.chdir (orig) # Restore original working directory

    def get_transfer (_trip):
        for i in _trip ["__stops__"]:
            transfer = transfers [i ["stop_id"]]
            transfer.discard (_trip ["route_short_name"]) # Exclude the current route
            transfer.discard (_trip ["route_long_name"])
            i ["__transfer__"] = sorted (transfer)

    return trip, get_transfer if transfer else lambda x: None # Return a dummy function if transfer is disabled

def from_osm (rel_id, transfer = True, shape = False, osm_out = "meta", opql_url = "http://overpass-api.de/api/interpreter"):
    # Third-party modules:
    import requests as req

    if transfer:
        opql_req = f'[out:json];rel({rel_id});out {osm_out};node(r);foreach{{out {osm_out};rel(bn)[route~"^(bus|trolleybus|minibus|share_taxi|train|light_rail|subway|tram|monorail|ferry|funicular)$"];out tags;}};'
    else:
        opql_req = f'[out:json];rel({rel_id});out {osm_out};node(r);out {osm_out};'

    line_data = req.get (opql_url, data = opql_req)
    if line_data.status_code == 200:
        line_data = line_data.json () ["elements"]
    else:
        raise ConnectionError (f"Error querying Overpass API: {line_data.status_code} {line_data.reason}")
    if not line_data:
        raise ValueError ("No results found.")
    trip = line_data [0].copy ()
    trip.pop ("members")
    trip.update (trip.pop ("tags"))
    # Rename some keys to match GTFS format
    trip = renamedict (trip, {
        "name": "route_long_name",
        "ref": "route_short_name",
        "id": "route_id",
        "operator": "agency_name"
    }, "Unknown") # Use default value as OSM data may not have all fields
    trip.update ({
        "__sourcetype__": "OSM",
        "__stops__": [i for i in line_data [0] ["members"] if i ["type"] == "node"]
    })

    stops, count, node_id = {}, 1, None
    while count < len (line_data):
        i = line_data [count]
        if i ["type"] == "node":
            i.update (i.pop ("tags"))
            # Rename some keys to match GTFS format
            stops.update ({i ["id"]: renamedict (i, {
                "lat": "stop_lat",
                "lon": "stop_lon",
                "name": "stop_name",
                "id": "stop_id",
            })})
            transfer = stops [i ["id"]].setdefault ("__transfer__", set ())
        elif i ["type"] == "relation":
            transfer.add (i ["tags"].get ("ref"))
        count += 1
    for i in trip ["__stops__"]:
        i.update (stops [i ["ref"]])

    if shape:
        opql_req = f'[out:json];rel({rel_id});out skel;way(r);foreach{{out geom;}};'
        shape_data = req.get (opql_url, data = opql_req)
        if shape_data.status_code == 200:
            shape_data = shape_data.json () ["elements"]
        else:
            raise ConnectionError (f"Error querying Overpass API: {shape_data.status_code} {shape_data.reason}")
        relation = shape_data.pop (0) ["members"]

        shape_data = {i ["id"]: i for i in shape_data}
        for v in shape_data.values (): # Convert geometry to [lon, lat] format
            v ["geometry"] = [[j ["lon"], j ["lat"]] for j in v ["geometry"].copy ()]
        ways = [shape_data [i ["ref"]] for i in relation if i ["type"] == "way" and i.get ("role", "") == ""] # TODO: Handle roles

        """
            currF - First node of the current way
            currL - Last node of the current way
            nextF - First node of the next way
            nextL - Last node of the next way
            last_correct - Whether the direction of travel is known
        """
        shape, i, last_node = [], {}, None
        def extend_geom (direction):
            nonlocal shape, i, last_node
            if direction == "forward":
                shape.extend (i ["geometry"])
                last_node = i ["nodes"] [-1]
            elif direction == "reverse":
                shape.extend (reversed (i ["geometry"]))
                last_node = i ["nodes"] [0]
            
        last_correct = False
        if len (ways) == 0:
            print ("Error: No ways found in the relation.")
            raise SystemExit
        elif len (ways) == 1: # Single way, need user to specify direction
            i = ways [0]
            oneway = i ["tags"].get ("oneway")
            if oneway == "yes":
                extend_geom ("forward")
            elif oneway == "-1":
                extend_geom ("reverse")
            else:
                print (f"Way {i ['id']} has an ambiguous direction. Would you like to")
                choice = input (f"Add it in (F)orward or (R)erverse direction, or skip processing shape data (any other key)? ").lower ()
                if choice == "f":
                    extend_geom ("forward")
                elif choice == "r":
                    extend_geom ("reverse")
                else:
                    shape = []
            ways = None # Skip loop below

        for i, j in (zip (ways, ways [1 : ] + [ways [0]]) if ways else []): # Iterate len (ways) times
            oneway = i ["tags"].get ("oneway")
            currF, currL = i ["nodes"] [0], i ["nodes"] [-1]
            nextF, nextL = j ["nodes"] [0], j ["nodes"] [-1]
            if currF == currL:
                if oneway == "yes":
                    extend_geom ("forward")
                elif oneway == "-1":
                    extend_geom ("reverse")
                else:
                    print (f"Way {i ['id']} is a closed loop. Would you like to")
                    choice = input (f"Add it in (F)orward or (R)erverse direction, or skip processing shape data (any other key)? ").lower ()
                    if choice == "f":
                        extend_geom ("forward")
                    elif choice == "r":
                        extend_geom ("reverse")
                    else:
                        shape = []
                        break # Skip processing shape data
                print (f"Warning: Way {i ['id']} is a closed loop.")
                last_correct = True # Direction given by the first way
                continue

            elif not last_correct:
                nodes = {"currF": currF, "currL": currL, "nextF": nextF, "nextL": nextL}
                dups = set ((k for k, v in nodes.items () if list (nodes.values ()).count (v) > 1))
                if len (dups) == 0:
                    print (f"Error: Consecutive ways {i ['id']} and {j ['id']} do not connect.")
                    raise SystemExit
                elif len (dups) > 2:
                    if oneway == "yes":
                        extend_geom ("forward")
                    elif oneway == "-1":
                        extend_geom ("reverse")
                    else:
                        print (f"Error: Ways {i ['id']} and {j ['id']} form an ambiguous loop.")
                        raise SystemExit
                    print (f"Warning: Ways {i ['id']} and {j ['id']} form a loop.")
                    last_correct = True
                    continue
                else:
                    if dups in ({"currL", "nextF"}, {"currL", "nextL"}): # First way is correctly oriented
                        extend_geom ("forward")
                    elif dups in ({"currF", "nextF"}, {"currF", "nextL"}): # First way is reversed
                        extend_geom ("reverse")
                    else:
                        print (f"Invalid duplicate set: {dups}\nPlease report this issue.")
                        raise SystemExit
                    last_correct = True
                    continue
            
            if currF == last_node:
                extend_geom ("forward")
            elif currL == last_node:
                extend_geom ("reverse")
            else:
                print (f"Error: Way {i ['id']} does not connect with its previous way.")
                raise SystemExit
        trip ["__shape__"] = shape

    def get_transfer (_trip):
        for i in _trip ["__stops__"]:
            # Transfer lines with no "ref" or the same as route_short_name are excluded
            i ["__transfer__"] = sorted (i ["__transfer__"].difference ({None, _trip ["route_short_name"]}))

    return trip, get_transfer if transfer else lambda x: None # Return a dummy function if transfer is disabled

def from_tianditu (api_key, transfer = True, shape = False):
    if transfer:
        print ("Transfer information not supported for Tianditu API, which may be unavailable as a whole in the future.\n"
               "Please consider using other data sources or use -t to disable transfer information in the meantime.")
        raise SystemExit
    elif shape:
        raise NotImplementedError ("Support for Tianditu is deprecated and may be removed in the future.")

    # Third-party modules:
    import requests as req
    from tqdm import tqdm

    while True:
        keyword = input ("Enter the route name: ")
        if not keyword:
            raise ValueError ("Route name cannot be empty.")
        specify = input ("Enter the city or district in Chinese: ")
        if not specify:
            raise ValueError ("City or district cannot be empty.")

        trip = req.get (f'https://api.tianditu.gov.cn/v2/search?postStr={{"keyWord":"{keyword}","level":"18","mapBound":"-180,-90,180,90","queryType":"1","count":"100","start":"0","show":"2","specify":"{specify}"}}&type=query&tk={api_key}')
        if trip.status_code == 200:
            if "lineData" in trip.json ():
                break
            print ("No results found. Try entering the route name in full.")
        else:
            raise ConnectionError (f"Error querying Tianditu API: {trip.status_code} {trip.reason}")

    choicetable (
        ["Name", "Stops", "ID"],
        ([i ["name"], i ["stationNum"], i ["uuid"]] for i in trip.json () ["lineData"])
    )
    line = next (choice (trip.json () ["lineData"], "Select one route: ", 1, 1))

    trip = req.get (f'https://api.tianditu.gov.cn/transit?type=busline&postStr={{"uuid":"{line ["uuid"]}"}}&tk={api_key}')
    if trip.status_code == 200:
        trip = trip.json ()
    else:
        raise ConnectionError (f"Error querying Tianditu API: {trip.status_code} {trip.reason}")
    trip.pop ("linepoint")
    trip.update ({
        "__sourcetype__": "TIANDITU",
        "__stops__": []
    })
    trip = renamedict (trip, {
        "linename": "route_long_name",
        "byuuid": "route_id",
        "company": "agency_name"
    })

    for i in trip.pop ("station"):
        trip ["__stops__"].append ({
            "stop_name": i ["name"],
            "stop_lat": i ["lonlat"].split (",") [1],
            "stop_lon": i ["lonlat"].split (",") [0],
            "stop_id": i ["uuid"]
        })

    def get_transfer (_trip):
        for i in tqdm (_trip ["__stops__"], desc = "Querying transfer information"):
            stop = req.get (f'https://api.tianditu.gov.cn/transit?type=busline&postStr={{"uuid":"{i ["stop_id"]}"}}&tk={api_key}')
            if stop.status_code == 200:
                i ["__transfer__"] = tuple (j ["name"] for j in stop.json () ["linedata"])
            else:
                raise ConnectionError (f"Error querying Tianditu API: {stop.status_code} {stop.reason}")

    return trip, get_transfer if transfer else lambda x: None # Return a dummy function if transfer is disabled

def from_baidu (seckey = None, transfer = True, shape = False):
    # Third-party modules:
    import requests as req
    from tqdm import tqdm
    from coord_convert.transform import bd2wgs
    from bd09convertor import convertMC2LL as mc2ll

    key = lambda url: url + f"&seckey={seckey}" if seckey and seckey.lower () != "none" else url # Append seckey if provided
    headers = {
        "Host": "map.baidu.com",
        "Referer": "https://map.baidu.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    }
    strip_geo = lambda geo: geo.rstrip (";").split ("|") [-1].split (",")

    trips = None
    if not seckey:
        print ("No seckey provided. Some information may be missing.")
    elif re.search (r"^tpov-[0-9a-f]{24}-", seckey) is None:
        while True:
            wd = input ("Enter the route name: ")
            if not wd:
                raise ValueError ("Route name cannot be empty.")
            c = input ("Enter the city or district in Chinese: ")
            if not c:
                raise ValueError ("City or district cannot be empty.")

            trips = req.get (key (f"https://maps.baidu.com/?qt=s&wd={wd}&c={c}"), headers = headers)
            if trips.status_code == 200:
                trips = trips.json ()
                if "content" in trips and len (trips ["content"]) and "cla" in trips ["content"] [0]:
                    trips = [i for i in trips ["content"] if i ["cla"] and i ["cla"] [0] [0] == 903] # 公交线路tag
                    if len (trips):
                        break
                print ("No results found. Try entering the route name in full.")
            else:
                raise ConnectionError (f"Error querying Baidu Maps API: {trips.status_code} {trips.reason}")
        
        choicetable (
            ["Name", "ID"],
            ([i ["name"], i ["uid"]] for i in trips)
        )
        line = next (choice (trips, "Select one route: ", 1, 1))
    else:
        seckey = seckey.removeprefix ("tpov-")
        line = {"uid": seckey.split ("-") [0]} # Line ID is provided
        c = seckey.split ("-") [1] # City is provided
        if len (seckey.split ("-")) > 2:
            key = lambda url: url + f"&seckey={seckey.split ('-', 2) [2]}" # Append seckey if provided

    trip, re_fetched = None, False
    while not trip:
        trip = req.get (key (f"https://map.baidu.com/?qt=bsl&c={c}&uid={line ['uid']}"), headers = headers)
        if trip.status_code == 200:
            trip = trip.json ()
            if not ("content" in trip and len (trip ["content"])):
                raise ValueError ("No stop information found. Try providing a seckey.")
            trip = trip ["content"] [0]
        else:
            raise ConnectionError (f"Error querying Baidu Maps API: {trip.status_code} {trip.reason}")
        
        if re_fetched or trips: # Only need to query when line is provided via seckey
            break
        elif not trip ["pair_line"]:
            print ("Info - Line only has one direction.")
            break

        choicetable (
            ["Name", "Direction", "ID"],
            (
                [trip ["name"], trip ["line_direction"], trip ["uid"]],
                [trip ["pair_line"] ["name"], trip ["pair_line"] ["direction"], trip ["pair_line"] ["uid"]]
            )
        )
        trip, line = next (choice ((
            (trip, line), # If user selects the current direction, no need to query again
            (None, {"uid": trip ["pair_line"] ["uid"]}) # If user selects the opposite direction, query again
        ), "Select one direction: ", 1, 1))
        re_fetched = True

    line_geo = strip_geo (trip.pop ("geo")) # Line geometry
    
    trip.update ({
    "__sourcetype__": "BAIDU",
    "__stops__": []
    })
    trip = renamedict (trip, {
        "name": "route_long_name",
        "raw_name": "route_short_name",
        "uid": "route_id",
        "company": "agency_name"
    })
    for i in trip.pop ("stations"):
        stop = renamedict (i, {
            "name": "stop_name",
            "uid": "stop_id"
        })
        stop.pop ("traffic_info", None) # May contain time-specific information
        if not transfer:
            stop.pop ("subways", None) # Subway transfer information
        geo = strip_geo (stop.pop ("geo")) # BD-09MC format
        lon, lat = bd2wgs (*mc2ll (float (geo [0]), float (geo [1]))) # 请遵循相关法律法规
        stop.update ({
            "stop_lat": lat,
            "stop_lon": lon
        })
        trip ["__stops__"].append (stop)

    if shape:
        shape = []
        for lon, lat in zip (line_geo [ : : 2], line_geo [1 : : 2]):
            shape.append (bd2wgs (*mc2ll (float (lon), float (lat)))) # 请遵循相关法律法规
        trip ["__shape__"] = shape
    
    def get_transfer (_trip):
        transfers, close_transfers, threadpool = {}, {}, []
        def stop_transfer (i):
            nonlocal transfers, close_transfers
            i ["__transfer__"], i ["__close_transfer__"] = [], []
            if "subways" in i and len (i ["subways"]):
                exp = re.compile ("<[^>]*>") # Strip HTML tag
                i ["__transfer__"].extend (exp.sub ("", j ["name"]) for j in i ["subways"])
                i.pop ("subways")

            stop = req.get (key (f"https://map.baidu.com/?qt=inf&c={c}&uid={i ['stop_id']}"), headers = headers)
            if stop.status_code == 200:
                stop = stop.json ()
            else:
                raise ConnectionError (f"Error querying Baidu Maps API: {stop.status_code} {stop.reason}")
            if "content" in stop and "blinfo" in stop ["content"]:
                stop = stop ["content"]
                i ["__transfer__"].extend (j ["addr"].replace ("地铁", "") for j in stop ["blinfo"] if j ["uid"] != _trip ["route_id"])
                i ["__close_transfer__"] = i ["__transfer__"].copy ()
                if "other_stations" in stop: # 其他同名站台线路
                    for j in stop ["other_stations"]:
                        i ["__close_transfer__"].extend (k.replace ("地铁", "") for k in j ["addr"].split (";") if k != _trip ["route_short_name"])
                
                transfers [i ["stop_id"]] = tuple (dict.fromkeys (i ["__transfer__"])) # Remove duplicates while preserving order
                close_transfers [i ["stop_id"]] = tuple (dict.fromkeys (i ["__close_transfer__"]))
            else:
                print (f"Warning - No transfer information found for {i ['stop_name']}, ID: {i ['stop_id']}. Try providing a seckey.")
                transfers [i ["stop_id"]], close_transfers [i ["stop_id"]] = (), ()

        for i in _trip ["__stops__"]:
            threadpool.append (threading.Thread (target = stop_transfer, args = (i, )))
            threadpool [-1].start ()
        with tqdm (total = len (threadpool), desc = "Querying transfer information") as pbar:
            while True:
                count = len (threadpool)
                threadpool = [t for t in threadpool if t.is_alive ()]
                pbar.update (count - len (threadpool))
                if not threadpool:
                    break
                time.sleep (0.1)

        for i in _trip ["__stops__"]:
            i ["__transfer__"] = transfers [i ["stop_id"]]
            i ["__close_transfer__"] = close_transfers [i ["stop_id"]]
    
    return trip, get_transfer if transfer else lambda x: None

def from_12306 (_ = None, transfer = True, shape = False):
    # Third-party modules:
    import requests as req
    from coord_convert.transform import gcj2wgs

    """
    headers = {
        "Connection": "keep-alive",
        "Host": "mobile.12306.cn",
        "Referer": "https://servicewechat.com/wxa51f55ab3b2655b9/128/page-frame.html",
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_7_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.55(0x18003729) NetType/WIFI Language/en"
    }
    """
    headers = {}
    

    while True:
        trainCode = input ("Enter the train number (e.g. G1234): ").upper () # Train number is capitalized
        if not trainCode:
            raise ValueError ("Train number cannot be empty.")
        startDay = input ("Enter the date of travel in YYYYMMDD format (e.g. 20210930): ")
        if not startDay:
            raise ValueError ("Date of travel cannot be empty.")

        trip = req.post (f"https://mobile.12306.cn/wxxcx/wechat/main/travelServiceQrcodeTrainInfo?trainCode={trainCode}&startDay={startDay}&startTime=&endDay=&endTime=", headers = headers)
        if trip.status_code == 200:
            trip = trip.json ()
            if "data" in trip and "trainDetail" in trip ["data"] and "stopTime" in trip ["data"] ["trainDetail"]:
                trip = trip ["data"]
                break
            print ("No results found. Verify that the train number and date are correct.")
        else:
            raise ConnectionError (f"Error querying 12306 API: {trip.status_code} {trip.reason}")

    trip.update ({
        "__sourcetype__": "12306",
        "__stops__": []
    })
    trip.update (trip.pop ("trainDetail"))
    trip.pop ("timestamp") # Request timestamp
    trip = renamedict (trip, {
        "stationTrainCodeAll": "route_long_name",
        "trainCode": "route_short_name",
        "trainNo": "route_id"
    })
    trip ["agency_name"] = "中国铁路" + trip ["stopTime"] [0] ["jiaolu_corporation_code"] # e.g. 中国铁路沈阳客运段
    for i in trip.pop ("stopTime"):
        stop = renamedict (i, {
            "stationName": "stop_name",
            "stationTelecode": "stop_id",
        })
        if ("lon" not in i or "lat" not in i):
            if input (f'{stop ["stop_name"]} station has no coordinate data. Continue processing and skip this station (Y/n)? ').lower () != "y":
                raise SystemExit ("Processing cancelled.")
            continue

        lon, lat = gcj2wgs (float (i ["lon"]), float (i ["lat"])) # 请遵循相关法律法规
        stop.update ({
            "stop_lat": lat,
            "stop_lon": lon
        })
        for j in ("arriveTime", "startTime"):
            if j in stop:
                stop [j] = f"{stop [j] [ : 2]}:{stop [j] [2 : ]}:00" # HH:mm:ss format
        trip ["__stops__"].append (stop)

    if shape:
        shape_data = req.post (f"https://mobile.12306.cn/wxxcx/wechat/main/getTrainMapLine?version=v2&trainNo={trip ['route_id']}", headers = headers)
        if shape_data.status_code == 200:
            shape_data = shape_data.json () ["data"]
        else:
            raise ConnectionError (f"Error querying Overpass API: {shape_data.status_code} {shape_data.reason}")

        if type (shape_data) is not dict or shape_data == {}:
            if input ("Shape data is not available for this train. Continue processing without shape data (Y/n)? ").lower () != "y":
                raise SystemExit ("Processing cancelled.")
        shape = []
        shape_data = list (shape_data.values ())
        shape_data.sort (key = lambda x: x ["index"])
        for i in shape_data:
            if i ["line"] [0] in shape:
                i ["line"].pop (0) # Duplicate start and end point of adjacent segments
            for [lon, lat] in i ["line"]:
                shape.append (gcj2wgs (float (lon), float (lat))) # 请遵循相关法律法规
        trip ["__shape__"] = shape

    def get_transfer (_trip):
        pass # NotImplementedError

    return trip, get_transfer if transfer else lambda x: None

def from_macau (shape_dir = None, transfer = True, shape = False):
    # Built-in modules:
    from zipfile import ZipFile

    # Third-party modules:
    import shapefile, xlrd
    from pyproj import Proj, Transformer

    if not shape_dir:
        raise ValueError ("Shape directory cannot be empty.")
    zip_file = ZipFile (shape_dir)

    get_file = lambda path: zip_file.open ((i for i in zip_file.namelist () if path in i).__next__ ())
    pole = shapefile.Reader (shp = get_file ("BUS_POLE.shp"), dbf = get_file ("BUS_POLE.dbf"), shx = get_file ("BUS_POLE.shx"))
    network = shapefile.Reader (shp = get_file ("ROUTE_NETWORK.shp"), dbf = get_file ("ROUTE_NETWORK.dbf"), shx = get_file ("ROUTE_NETWORK.shx"))
    route_seq = xlrd.open_workbook (file_contents = get_file ("BUS_ROUTE_SEQ.xls").read ()).sheet_by_index (0)
    to_wgs = Transformer.from_proj (Proj ("EPSG:8433"), Proj ("EPSG:4326"), always_xy = True).transform

    keys = route_seq.row_values (0)
    routes = route_seq.col_values (keys.index ("ROUTE_NO"), 1) # Route numbers
    points = {}
    for i in pole.shapeRecords ():
        wgs_point = to_wgs (*i.shape.points [0])
        data = { # Coordinates
            "stop_lon": wgs_point [0],
            "stop_lat": wgs_point [1]
        }
        data.update (i.record.as_dict ()) # Attributes]
        data = renamedict (data, {
            "POLE_ID": "stop_id",
            "NAME": "stop_name"
        })
        if transfer:
            data ["__transfer__"] = data.pop ("ROUTE_NOS").split (",")
        points [data ["stop_id"]] = data

    while True:
        route_no = input ("Enter the route number: ").upper ()
        if not route_no:
            raise ValueError ("Route number cannot be empty.")
        elif route_no not in routes:
            print ("Route number not found. Please try again.")
        else:
            break

    directions, shape_segs, route_ids, trip = {}, {}, {}, {}
    for j, i in enumerate (route_seq.col_values (0)):
        if i != route_no:
            continue
        row_dict = {k: v for k, v in zip (keys, route_seq.row_values (j))} # Map keys to values

        if row_dict ["POLE_ID"] == "" and row_dict ["NETWORK_ID"] != "": # Shape segment
            shape_segs.setdefault (row_dict ["ROUTE_ID"], []).append ((int (row_dict ["SEQ"]), int (row_dict ["NETWORK_ID"])))
        elif row_dict ["NETWORK_ID"] == "" and row_dict ["POLE_ID"] != "": # Stop
            if not trip:
                trip = {
                    "__sourcetype__": "MACAU",
                    "route_long_name": row_dict ["NAME"],
                    "route_short_name": row_dict ["ROUTE_NO"],
                    "agency_name": row_dict ["COMPANY_NAME"],
                    "__stops__": []
                }
                trip.update (dict ([(k, row_dict [k]) for k in (
                    "COMPANY_NAME_POR", "COMPANY_NAME_EN",
                    "NAME_POR", "NAME_EN",
                    "REMARKS", "REMARKS_POR", "REMARKS_EN"
                )]))
            directions.setdefault (row_dict ["DIRECTION"], []).append ((int (row_dict ["SEQ"]), int (row_dict ["POLE_ID"])))
            route_ids [row_dict ["DIRECTION"]] = row_dict ["ROUTE_ID"]
        else:
            raise ValueError ("Exactly one of NETWORK_ID and POLE_ID must be present.")

    # (direction, stop_id0, stop_id1, ...)
    directions = tuple (((k, ) + tuple (i [1] for i in sorted (v, key = lambda x: x [0]))) for k, v in directions.items ())
    if len (directions) != 1:
        choicetable (
            ["Direction", "From", "To", "Trip ID"],
            ([
                i [0],
                points [i [1]] ["stop_name"],
                points [i [-1]] ["stop_name"],
                route_ids [i [0]]
            ] for i in directions)
        )
        direction = next (choice (directions, "Select one direction: ", 1, 1))
    else:
        print ("Info - Line only has one direction.")
        direction = directions [0]

    shape_segs = tuple (i [1] for i in sorted (shape_segs [route_ids [direction [0]]], key = lambda x: x [0]))
    trip.update ({
        "route_id": route_ids [direction [0]],
        "DIRECTION": direction [0],
        "__stops__": [points [i] for i in direction [1 : ]]
    })

    if shape:
        shape = [[] for _ in shape_segs]
        for i in network.shapeRecords ():
            if i.record ["NETWORK_ID"] in shape_segs:
                shape [shape_segs.index (i.record ["NETWORK_ID"])].extend (to_wgs (*j) for j in i.shape.points)
        trip ["__shape__"] = [i for j in shape for i in j] # Flatten

    return trip, lambda x: None # Transfer already included in the data

def sel_stops (trip, json_out = None, core_only = False, get_transfer = lambda x: None):
    fields = _stop_fields.get (trip ["__sourcetype__"].upper (), _stop_fields ["__default__"])
    choicetable (
        fields [0],
        ([i [j] for j in fields [1]] for i in trip ["__stops__"])
    )
    trip ["__stops__"] = list (choice (trip ["__stops__"], "Select at least two stops to include: ", 2))
    get_transfer (trip) # Set transfer information in place

    if core_only: # Strip non-core tags
        for i in tuple (trip.keys ()):
            if i not in core_tags ["Global"]:
                trip.pop (i)
        for i in trip ["__stops__"]:
            for j in tuple (i.keys ()):
                if j not in core_tags ["Stop"]:
                    i.pop (j)

    if json_out:
        try:
            with json_out:
                json.dump (trip, json_out, indent = 4, ensure_ascii = False)
            print (f"Selected stop data written to {json_out.name}")
        except Exception as e:
            print ("Error writing JSON data:", e)

    print (f"Global tags: {', '.join (trip.keys ())}")
    print (f"Stop-specific tags: {', '.join (set (str (j) for i in trip ['__stops__'] for j in i.keys ()))}")

    return trip

global sources # Data sources and their respective functions
sources = {
    "GTFS": from_gtfs,
    "OSM": from_osm,
    "TIANDITU": from_tianditu,
    "BAIDU": from_baidu,
    "12306": from_12306,
    "MACAU": from_macau
}

parser = argparse.ArgumentParser (
    description = "Extract route and stop data from transit data sources",
    formatter_class = argparse.RawDescriptionHelpFormatter,
    epilog = """\
Currently supported data sources and required parameters:
Source      Parameter       Example
GTFS        GTFS directory  /path/to/gtfs (unzipped)
OSM         Relation ID     1234567
BAIDU       Seckey          a1b2c3... ('none' to exclude)
12306       None            N/A
MACAU       ShapeFile       /path/to/shape.zip

Core tags are consistent across all data sources:
(note that identifiers are only unique within the data source)
Tag                 Type        Description
__sourcetype__      Global      Data source type (e.g. GTFS)
route_id            Global      Unique identifier for the route
route_long_name     Global      Full name of the route
agency_name         Global      Name of the transit agency
__stops__           Global      List of stops on the route
stop_id             Stop        Unique identifier for the stop
stop_name           Stop        Name of the stop
stop_lat            Stop        Latitude of the stop
stop_lon            Stop        Longitude of the stop

The following core tags can be excluded based on flags:
__transfer__        Stop        List of transfers at the stop
__shape__           Global      Route shape coordinate list

Non-core tags may vary and are specific to each data source.
"""
)
parser.add_argument ("source", help = "Data source to extract from")
parser.add_argument ("parameter", help = "Parameter to pass to the data source")
parser.add_argument ("output", help = "Output filepath to write extracted data to")
parser.add_argument ("-c", "--core-only", action = "store_true", help = "Only save core tags (see below for details)")
parser.add_argument ("-t", "--no-transfer", action = "store_false", help = "Exclude the __transfer__ tag")
parser.add_argument ("-s", "--no-shape", action = "store_false", help = "Exclude the __shape__ tag")

def main (args):
    try:
        source = sources [args.source.upper ()]
    except KeyError:
        print (f"Data source '{args.source}' not supported. Run with -h for help.")
        raise SystemExit

    trip, get_transfer = source (args.parameter, transfer = args.no_transfer, shape = args.no_shape)
    sel_stops (trip, open (args.output, "w"), args.core_only, get_transfer)

def script (args):
    import shlex
    main (parser.parse_args (shlex.split (args)))

if __name__ == "__main__":
    main (parser.parse_args ())