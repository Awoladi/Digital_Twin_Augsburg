"""
Phase 6 – CityGML-Parser (BayernAtlas LoD2)
Reads all .gml files in data/raw/citygml/, extracts building footprints
and official heights, writes data/interim/georgsvorstadt_citygml.geojson.

Height logic (preferred over OSM tags):
  wall_height = NiedrigsteTraufeDesGebaeudes - HoeheGrund  (eave, no roof)
  fallback    = HoeheDach - HoeheGrund                     (total incl. roof)
"""

import sys, json
from pathlib import Path
import xml.etree.ElementTree as ET
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from configs.settings import CITYGML_DIR, DATA_INTERIM, CRS_SOURCE, CRS_WGS84, BBOX

import geopandas as gpd
from shapely.geometry import Polygon

NS = {
    "bldg": "http://www.opengis.net/citygml/building/1.0",
    "gml":  "http://www.opengis.net/gml",
    "gen":  "http://www.opengis.net/citygml/generics/1.0",
}


def _str_attrs(building) -> dict:
    """Extract all gen:stringAttribute values as a flat dict."""
    attrs = {}
    for el in building.findall("gen:stringAttribute", NS):
        name = el.get("name")
        val  = el.find("gen:value", NS)
        if name and val is not None and val.text:
            attrs[name] = val.text.strip()
    return attrs


def _ground_polygon(building):
    """Return Shapely Polygon from the GroundSurface (2D, EPSG:25832)."""
    gs = building.find(".//bldg:GroundSurface", NS)
    if gs is None:
        return None
    poslist = gs.find(".//gml:posList", NS)
    if poslist is None or not poslist.text:
        return None
    nums   = list(map(float, poslist.text.strip().split()))
    coords = [(nums[i], nums[i + 1]) for i in range(0, len(nums), 3)]
    if len(coords) < 3:
        return None
    try:
        poly = Polygon(coords)
        return poly if poly.is_valid else poly.buffer(0)
    except Exception:
        return None


def parse_file(path: Path) -> list[dict]:
    tree     = ET.parse(path)
    root     = tree.getroot()
    records  = []

    for bldg in root.findall(".//bldg:Building", NS):
        gml_id = bldg.get("{http://www.opengis.net/gml}id", "")
        attrs  = _str_attrs(bldg)
        poly   = _ground_polygon(bldg)
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

        def _text(el): return el.text.strip() if el is not None and el.text else ""

        records.append({
            "gml_id":      gml_id,
            "height_m":    round(wall_height, 2),
            "h_dach":      round(h_dach, 3),
            "h_grund":     round(h_grund, 3),
            "roof_type":   _text(bldg.find("bldg:roofType", NS)),
            "function":    _text(bldg.find("bldg:function", NS)),
            "created":     _text(bldg.find("creationDate", NS)),
            "geometry":    poly,
        })

    return records


def parse_all(citygml_dir: Path = CITYGML_DIR) -> gpd.GeoDataFrame:
    gml_files = sorted(citygml_dir.glob("*.gml"))
    if not gml_files:
        raise FileNotFoundError(f"No .gml files found in {citygml_dir}")

    all_records = []
    for f in gml_files:
        print(f"  Parsing {f.name} …", end=" ")
        recs = parse_file(f)
        print(f"{len(recs)} buildings")
        all_records.extend(recs)

    gdf = gpd.GeoDataFrame(all_records, crs=CRS_SOURCE)

    # Clip to Georgsvorstadt bounding box (clip in metric CRS to avoid centroid warning)
    from shapely.geometry import box as shapely_box
    from pyproj import Transformer
    transformer = Transformer.from_crs(CRS_WGS84, CRS_SOURCE, always_xy=True)
    x_min, y_min = transformer.transform(BBOX["min_lon"], BBOX["min_lat"])
    x_max, y_max = transformer.transform(BBOX["max_lon"], BBOX["max_lat"])
    bbox_poly = shapely_box(x_min, y_min, x_max, y_max)
    gdf_clip  = gdf[gdf.geometry.centroid.within(bbox_poly)].copy()
    gdf_clip  = gdf_clip.to_crs(CRS_WGS84).reset_index(drop=True)

    print(f"  Clipped to Georgsvorstadt BBox: {len(gdf_clip)} buildings")
    return gdf_clip


if __name__ == "__main__":
    print("Parsing CityGML files …")
    gdf = parse_all()

    out = DATA_INTERIM / "georgsvorstadt_citygml.geojson"
    gdf.to_file(out, driver="GeoJSON")
    print(f"Saved -> {out}")
    print(f"\nHeight stats (official LoD2):")
    print(f"  min    : {gdf['height_m'].min():.1f} m")
    print(f"  max    : {gdf['height_m'].max():.1f} m")
    print(f"  mean   : {gdf['height_m'].mean():.1f} m")
    print(f"  median : {gdf['height_m'].median():.1f} m")