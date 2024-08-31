# Built-in modules:
import os, bisect, json, csv, argparse, pickle, subprocess, re
from urllib.parse import urlparse

from tpov_functions import *

global _stop_fields # Fields to be displayed for each data source
_stop_fields = {
    "GTFS": (
        ["Name", "Latitude", "Longitude", "Depart", "ID"],
        ["stop_name", "stop_lat", "stop_lon", "departure_time", "stop_id"]
    ),
    "OSM": (
        ["Name", "Latitude", "Longitude", "Role", "ID"],
        ["stop_name", "stop_lat", "stop_lon", "role", "stop_id"]
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

def from_gtfs (gtfs_dir = None, transfer = True):
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
            sort = subprocess.run (f"cat -u stop_times.txt | tail -n +2 | sort -n -t , -k {ti},{ti} -k {ss},{ss}", shell = True, stdout = f)

        lines = subprocess.run (["wc", "-l", "stop_times_sorted.txt"], capture_output = True)
        lines.check_returncode ()
        lines = int (lines.stdout.decode ().split () [0])
        line_cnt = tqdm (total = lines, desc = "Indexing stop_times", mininterval = 0.5)
        ti -= 1 # Convert to 0-based index
        with open ("stop_times_sorted.txt") as f: # May be able to be optimized using csv module
            f.readline () # Skip header
            indices, last_id, fileptr, si = {}, None, f.tell (), header.index ("stop_id")
            line, transfers = f.readline (), {}
            while line:
                line_cnt.update ()
                line = line.strip ().split (",") # CSV format
                if line [ti] != last_id: # New trip_id
                    indices [line [ti]] = fileptr
                    last_id = line [ti]
                transfers.setdefault (line [si], set ()).add (trip_names [line [ti]]) # Map route_short_name to stop
                fileptr = f.tell () # Save file pointer at beginning of line
                line = f.readline ()
            line_cnt.close ()
        
            with open ("stop_times_sorted.txt.pkl", "wb") as f:
                pickle.dump ((indices, transfers), f)

    print ("Reading stop information...")
    with open ("stop_times_sorted.txt.pkl", "rb") as f:
        indices, transfers = pickle.load (f)
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

    start_time = input ("Enter the time the vehicle left the first stop in HH(:mm)(:ss) format: ")
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
    for i in trips_display:
        for j in i ["__stops__"]:
            j.update (stops [j ["stop_id"]])
    # Final format of trips_display:
    # [{fields from trips.txt, "__stops__": [{fields from stop_times.txt + fields from stops.txt}, ...]}, ...]

    os.chdir (orig) # Restore original working directory

    choicetable (
        ["Headsign", "From", "To", "Depart", "Arrive", "Trip ID"],
        ([
            i ["trip_headsign"] if "trip_headsign" in i else f"{route ['route_short_name']} {route ['route_long_name']}",
            i ["__stops__"] [0] ["stop_name"],
            i ["__stops__"] [-1] ["stop_name"],
            i ["__stops__"] [0] ["departure_time"],
            i ["__stops__"] [-1] ["departure_time"],
            i ["trip_id"]
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

    def get_transfer (_trip):
        for i in _trip ["__stops__"]:
            transfer = transfers [i ["stop_id"]]
            transfer.discard (_trip ["route_short_name"]) # Exclude the current route
            transfer.discard (_trip ["route_long_name"])
            i ["__transfer__"] = sorted (transfer)

    return trip, get_transfer if transfer else lambda x: None # Return a dummy function if transfer is disabled

def from_osm (rel_id, transfer = True, osm_out = "meta", opql_url = "http://overpass-api.de/api/interpreter"):
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
    })
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

    def get_transfer (_trip):
        for i in _trip ["__stops__"]:
            # Transfer lines with no "ref" or the same as route_short_name are excluded
            i ["__transfer__"] = sorted (i ["__transfer__"].difference ({None, _trip ["route_short_name"]}))

    return trip, get_transfer if transfer else lambda x: None # Return a dummy function if transfer is disabled

def from_tianditu (api_key, transfer = True):
    # Third-party modules:
    import requests as req
    from tqdm import tqdm

    if transfer:
        print ("Transfer information not supported for Tianditu API, which may be unavailable as a whole in the future.\n"
               "Please consider using other data sources or use -t to disable transfer information in the meantime.")
        raise SystemExit
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

def from_baidu (seckey = None, transfer = True):
    # Third-party modules:
    import requests as req
    from tqdm import tqdm
    from coord_convert.transform import bd2wgs
    from bd09convertor import convertMC2LL as mc2ll

    if not seckey:
        print ("No seckey provided. Some information may be missing.")
    key = lambda url: url + f"&seckey={seckey}" if seckey and seckey.lower () != "none" else url # Append seckey if provided
    headers = {
        "Host": "map.baidu.com",
        "Referer": "https://map.baidu.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    }

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
                break
            print ("No results found. Try entering the route name in full.")
        else:
            raise ConnectionError (f"Error querying Baidu Maps API: {trip.status_code} {trip.reason}")
    
    choicetable (
        ["Name", "ID"],
        ([i ["name"], i ["uid"]] for i in trips)
    )
    line = next (choice (trips, "Select one route: ", 1, 1))

    trip = req.get (key (f"https://map.baidu.com/?qt=bsl&c={c}&uid={line ['uid']}"), headers = headers)
    if trip.status_code == 200:
        trip = trip.json ()
        if not ("content" in trip and len (trip ["content"])):
            raise ValueError ("No stop information found. Try providing a seckey.")
        trip = trip ["content"] [0]
    else:
        raise ConnectionError (f"Error querying Baidu Maps API: {trip.status_code} {trip.reason}")
    
    trip.pop ("geo") # Remove geometry data
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
        stop.pop ("traffic_info") # May contain time-specific information
        if not transfer:
            stop.pop ("subways", None) # Subway transfer information
        geo = stop.pop ("geo").rstrip (";").split ("|") [-1].split (",") # BD-09MC format
        lon, lat = bd2wgs (*mc2ll (float (geo [0]), float (geo [1]))) # 请遵循相关法律法规
        stop.update ({
            "stop_lat": lat,
            "stop_lon": lon
        })
        trip ["__stops__"].append (stop)
    
    def get_transfer (_trip):
        for i in tqdm (_trip ["__stops__"], desc = "Querying transfer information"):
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
                i ["__transfer__"].extend (j ["addr"] for j in stop ["blinfo"] if j ["uid"] != _trip ["route_id"])
                i ["__close_transfer__"] = i ["__transfer__"].copy ()
                if "other_stations" in stop: # 其他同名站台线路
                    for j in stop ["other_stations"]:
                        i ["__close_transfer__"].extend (k for k in j ["addr"].split (";") if k != _trip ["route_short_name"])
                
                i ["__transfer__"] = tuple (dict.fromkeys (i ["__transfer__"])) # Remove duplicates while preserving order
                i ["__close_transfer__"] = tuple (dict.fromkeys (i ["__close_transfer__"]))
    
    return trip, get_transfer if transfer else lambda x: None

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
    "BAIDU": from_baidu
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
__transfer__        Stop        List of transfers at the stop

Non-core tags may vary and are specific to each data source.
"""
)
parser.add_argument ("source", help = "Data source to extract from")
parser.add_argument ("parameter", help = "Parameter to pass to the data source")
parser.add_argument ("output", help = "Output filepath to write extracted data to")
parser.add_argument ("-c", "--core-only", action = "store_true", help = "Only save core tags (see below for details)")
parser.add_argument ("-t", "--no-transfer", action = "store_false", help = "Exclude the __transfer__ tag")

def main (args):
    try:
        source = sources [args.source.upper ()]
    except KeyError:
        print (f"Data source '{args.source}' not supported. Run with -h for help.")
        raise SystemExit

    trip, get_transfer = source (args.parameter, transfer = args.no_transfer)
    sel_stops (trip, open (args.output, "w"), args.core_only, get_transfer)

def script (args):
    import shlex
    main (parser.parse_args (shlex.split (args)))

if __name__ == "__main__":
    main (parser.parse_args ())