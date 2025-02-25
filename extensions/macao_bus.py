# This file contains functions used by other programs. It should not be run directly.

# Built-in modules:
from zipfile import ZipFile

# Third-party modules:
import shapefile, xlrd

__tpov_ext__ = {
    "name": "Macao Bus Network",
    "for": "tpov_extract",
    "desc": "Extract Macao bus route information from the government's Open Data website",
    "params": {}
}

def from_macao_bus (shape_dir = None, transfer = True, shape = False):
    if not shape_dir:
        raise ValueError ("Shape directory cannot be empty.")
    zip_file = ZipFile (shape_dir)

    get_file = lambda path: zip_file.open ((i for i in zip_file.namelist () if path in i).__next__ ())
    pole = shapefile.Reader (shp = get_file ("BUS_POLE.shp"), dbf = get_file ("BUS_POLE.dbf"), shx = get_file ("BUS_POLE.shx"))
    network = shapefile.Reader (shp = get_file ("ROUTE_NETWORK.shp"), dbf = get_file ("ROUTE_NETWORK.dbf"), shx = get_file ("ROUTE_NETWORK.shx"))
    route = xlrd.open_workbook (file_contents = get_file ("BUS_ROUTE_SEQ.xls").read ())

# from_macao_bus ("/tmp/ExportShapeFile.zip", shape = True)