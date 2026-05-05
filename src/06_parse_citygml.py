"""
Phase 6 – CityGML-Parser (BayernAtlas LoD2)
Liest alle .gml-Dateien in data/raw/citygml/ und schreibt:
  - data/interim/georgsvorstadt_citygml.geojson   (Grundrisse + Höhen)
  - data/interim/georgsvorstadt_citygml_surfaces.json  (LoD2-3D-Flächen je gml_id)

Höhenlogik:
  Wandhöhe = NiedrigsteTraufeDesGebaeudes - HoeheGrund  (Traufe, für Box-Fallback)
  Fallback  = HoeheDach - HoeheGrund

Surfaces-JSON-Struktur je gml_id:
  { "cx_utm": float, "cy_utm": float, "h_grund": float,
    "ground": [[x,y,z],...], "walls": [[[x,y,z],...]], "roofs": [[[x,y,z],...]] }
"""

import sys, json
from pathlib import Path
import xml.etree.ElementTree as ET
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from configs.settings import CITYGML_DIR, DATA_INTERIM, CRS_SOURCE, CRS_WGS84, BBOX

import geopandas as gpd
from shapely.geometry import Polygon, box as shapely_box
from pyproj import Transformer

NS = {
    "bldg": "http://www.opengis.net/citygml/building/1.0",
    "gml":  "http://www.opengis.net/gml",
    "gen":  "http://www.opengis.net/citygml/generics/1.0",
}

ROOF_CODES = {
    "1000": "Flachdach",
    "2100": "Satteldach",
    "2200": "Walmdach",
    "2300": "Krüppelwalmdach",
    "2400": "Mansarddach",
    "3100": "Pultdach",
    "3200": "Versetztes Pultdach",
    "4000": "Zeltdach",
    "5000": "Kegeldach",
    "5100": "Kugelförmig",
    "6000": "Tonnendach",
    "9999": "Sonstiges",
}


def _str_attrs(building) -> dict:
    attrs = {}
    for el in building.findall("gen:stringAttribute", NS):
        name = el.get("name")
        val  = el.find("gen:value", NS)
        if name and val is not None and val.text:
            attrs[name] = val.text.strip()
    return attrs


def _poslist_to_pts3d(poslist_el) -> list[list[float]]:
    """Parst gml:posList in eine Liste von [x, y, z]-Tripeln."""
    if poslist_el is None or not poslist_el.text:
        return []
    nums = list(map(float, poslist_el.text.strip().split()))
    return [[nums[i], nums[i+1], nums[i+2]] for i in range(0, len(nums) - 2, 3)]


def _surface_polygons(building, surface_tag: str) -> list[list[list[float]]]:
    """Extrahiert alle 3D-Polygone für einen Flächentyp (z. B. RoofSurface)."""
    polygons = []
    for surf in building.findall(f".//bldg:{surface_tag}", NS):
        for poslist in surf.findall(".//gml:posList", NS):
            pts = _poslist_to_pts3d(poslist)
            if len(pts) >= 3:
                polygons.append(pts)
    return polygons


def _ground_polygon_2d(building):
    """Gibt das 2D-Shapely-Polygon der GroundSurface zurück (EPSG:25832)."""
    gs = building.find(".//bldg:GroundSurface", NS)
    if gs is None:
        return None
    poslist = gs.find(".//gml:posList", NS)
    pts = _poslist_to_pts3d(poslist)
    if len(pts) < 3:
        return None
    coords_2d = [(p[0], p[1]) for p in pts]
    try:
        poly = Polygon(coords_2d)
        return poly if poly.is_valid else poly.buffer(0)
    except Exception:
        return None


def _text(el):
    return el.text.strip() if el is not None and el.text else ""


def parse_file(path: Path) -> tuple[list[dict], dict]:
    """Gibt (records_for_gdf, surfaces_dict) zurück."""
    tree    = ET.parse(path)
    root    = tree.getroot()
    records = []
    surfaces = {}

    for bldg in root.findall(".//bldg:Building", NS):
        gml_id = bldg.get("{http://www.opengis.net/gml}id", "")
        attrs  = _str_attrs(bldg)
        poly   = _ground_polygon_2d(bldg)
        if poly is None:
            continue

        try:
            h_dach   = float(attrs.get("HoeheDach", 0))
            h_grund  = float(attrs.get("HoeheGrund", 0))
            h_traufe = float(attrs.get("NiedrigsteTraufeDesGebaeudes", 0))
        except ValueError:
            continue

        wall_height = (h_traufe - h_grund) if h_traufe > h_grund else (h_dach - h_grund)
        if wall_height <= 0:
            continue

        # Schwerpunkt der Grundfläche
        cx_utm = poly.centroid.x
        cy_utm = poly.centroid.y

        # Alle LoD2-Flächen extrahieren
        ground_pts = _surface_polygons(bldg, "GroundSurface")
        wall_pts   = _surface_polygons(bldg, "WallSurface")
        roof_pts   = _surface_polygons(bldg, "RoofSurface")

        if wall_pts or roof_pts:
            surfaces[gml_id] = {
                "cx_utm":  cx_utm,
                "cy_utm":  cy_utm,
                "h_grund": h_grund,
                "ground":  ground_pts,
                "walls":   wall_pts,
                "roofs":   roof_pts,
            }

        records.append({
            "gml_id":    gml_id,
            "height_m":  round(wall_height, 2),
            "h_dach":    round(h_dach, 3),
            "h_grund":   round(h_grund, 3),
            "roof_type": ROOF_CODES.get(_text(bldg.find("bldg:roofType", NS)), _text(bldg.find("bldg:roofType", NS)) or "unbekannt"),
            "function":  _text(bldg.find("bldg:function", NS)),
            "created":   _text(bldg.find("creationDate", NS)),
            "geometry":  poly,
        })

    return records, surfaces


def parse_all(citygml_dir: Path = CITYGML_DIR) -> tuple[gpd.GeoDataFrame, dict]:
    gml_files = sorted(citygml_dir.glob("*.gml"))
    if not gml_files:
        raise FileNotFoundError(f"No .gml files found in {citygml_dir}")

    all_records  = []
    all_surfaces = {}
    for f in gml_files:
        print(f"  Parsing {f.name} ...", end=" ")
        recs, surfs = parse_file(f)
        print(f"{len(recs)} buildings, {len(surfs)} with LoD2 surfaces")
        all_records.extend(recs)
        all_surfaces.update(surfs)

    gdf = gpd.GeoDataFrame(all_records, crs=CRS_SOURCE)

    # Auf Georgsvorstadt-BBox in metrischem CRS zuschneiden
    transformer = Transformer.from_crs(CRS_WGS84, CRS_SOURCE, always_xy=True)
    x_min, y_min = transformer.transform(BBOX["min_lon"], BBOX["min_lat"])
    x_max, y_max = transformer.transform(BBOX["max_lon"], BBOX["max_lat"])
    bbox_poly    = shapely_box(x_min, y_min, x_max, y_max)
    mask         = gdf.geometry.centroid.within(bbox_poly)
    gdf_clip     = gdf[mask].to_crs(CRS_WGS84).reset_index(drop=True)

    # Nur Flächen der zugeschnittenen Gebäude behalten
    kept_ids     = set(gdf_clip["gml_id"])
    surfs_clip   = {k: v for k, v in all_surfaces.items() if k in kept_ids}

    print(f"  Auf BBox zugeschnitten: {len(gdf_clip)} Gebäude, {len(surfs_clip)} mit LoD2-Flächen")
    return gdf_clip, surfs_clip


if __name__ == "__main__":
    print("Parse CityGML-Dateien ...")
    gdf, surfaces = parse_all()

    geojson_out = DATA_INTERIM / "georgsvorstadt_citygml.geojson"
    gdf.to_file(geojson_out, driver="GeoJSON")
    print(f"GeoJSON gespeichert -> {geojson_out}")

    surfaces_out = DATA_INTERIM / "georgsvorstadt_citygml_surfaces.json"
    with open(surfaces_out, "w", encoding="utf-8") as fh:
        json.dump(surfaces, fh, ensure_ascii=False)
    print(f"Flächen gespeichert -> {surfaces_out}  ({len(surfaces)} Gebäude)")

    print(f"\nHöhenstatistik:")
    print(f"  min    : {gdf['height_m'].min():.1f} m")
    print(f"  max    : {gdf['height_m'].max():.1f} m")
    print(f"  Mittel : {gdf['height_m'].mean():.1f} m")
    print(f"  Median : {gdf['height_m'].median():.1f} m")