from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Georgsvorstadt bounding box (EPSG:4326)
BBOX = {
    "min_lon": 10.888,
    "min_lat": 48.358,
    "max_lon": 10.908,
    "max_lat": 48.368,
}

# Coordinate reference systems
CRS_SOURCE = "EPSG:25832"   # ETRS89 / UTM Zone 32N (BayernAtlas, ALKIS)
CRS_WGS84  = "EPSG:4326"

# Paths
DATA_RAW     = BASE_DIR / "data" / "raw"
DATA_INTERIM = BASE_DIR / "data" / "interim"
DATA_OUTPUT  = BASE_DIR / "data" / "output"

CITYGML_DIR  = DATA_RAW / "citygml"
ALKIS_DIR    = DATA_RAW / "alkis"
OSM_DIR      = DATA_RAW / "osm"

BUILDINGS_GEOJSON = DATA_INTERIM / "georgsvorstadt_gebaeude.geojson"
IFC_OUTPUT        = DATA_OUTPUT / "ifc" / "georgsvorstadt_LOD200.ifc"

# IFC defaults
DEFAULT_STOREY_HEIGHT = 3.2   # metres per floor when no height tag present
DEFAULT_STOREYS       = 3
PROJECT_NAME          = "Digital Twin Augsburg – Georgsvorstadt"
SITE_NAME             = "Georgsvorstadt"
