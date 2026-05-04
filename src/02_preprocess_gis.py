"""
Phase 2 – GIS-Vorverarbeitung
Loads OSM building footprints, cleans geometry, and enriches heights:
  1. OSM height / levels tags (parsed directly)
  2. CityGML LoD2 spatial join (if georgsvorstadt_citygml.geojson exists)
  3. Default fallback (DEFAULT_STOREYS * DEFAULT_STOREY_HEIGHT)

Run after 01_fetch_data.py and (optionally) 06_parse_citygml.py.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from configs.settings import (
    BUILDINGS_GEOJSON, DATA_INTERIM, CRS_WGS84, CRS_SOURCE,
    DEFAULT_STOREY_HEIGHT, DEFAULT_STOREYS,
)

import geopandas as gpd
import pandas as pd


CITYGML_GEOJSON = DATA_INTERIM / "georgsvorstadt_citygml.geojson"


def load_and_clean(path: Path) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs(CRS_WGS84)
    gdf = gdf.to_crs(CRS_WGS84)
    gdf = gdf[gdf.geometry.is_valid & ~gdf.geometry.is_empty].copy()

    # Remove duplicates in metric CRS (centroid-based)
    gdf_m = gdf.to_crs(CRS_SOURCE)
    gdf["_cx"] = gdf_m.geometry.centroid.x.round(1)
    gdf["_cy"] = gdf_m.geometry.centroid.y.round(1)
    gdf = gdf.drop_duplicates(subset=["_cx", "_cy"]).drop(columns=["_cx", "_cy"])

    return gdf.reset_index(drop=True)


def _osm_height(row: pd.Series) -> float | None:
    if pd.notna(row.get("height")) and str(row["height"]).strip():
        try:
            return float(str(row["height"]).replace("m", "").strip())
        except ValueError:
            pass
    if pd.notna(row.get("levels")) and str(row["levels"]).strip():
        try:
            return float(row["levels"]) * DEFAULT_STOREY_HEIGHT
        except ValueError:
            pass
    return None


def merge_citygml_heights(osm: gpd.GeoDataFrame, citygml_path: Path) -> gpd.GeoDataFrame:
    """Spatial join: assign nearest CityGML height to each OSM building."""
    cgml = gpd.read_file(citygml_path)[["height_m", "gml_id", "roof_type", "geometry"]]
    cgml = cgml.to_crs(CRS_WGS84)

    # Nearest join in metric CRS (each OSM building → closest CityGML centroid)
    osm_m  = osm.to_crs(CRS_SOURCE).copy()
    osm_m.geometry  = osm_m.geometry.centroid
    cgml_m = cgml.to_crs(CRS_SOURCE).copy()
    cgml_m.geometry = cgml_m.geometry.centroid

    joined = gpd.sjoin_nearest(
        osm_m,
        cgml_m[["height_m", "gml_id", "roof_type", "geometry"]],
        how="left",
        max_distance=30,          # only accept matches within 30 m
        distance_col="_dist_m",
    )
    osm["height_citygml"] = joined["height_m"].values
    osm["gml_id"]         = joined["gml_id"].values
    osm["roof_type"]      = joined["roof_type"].values
    return osm


def preprocess(input_path: Path = BUILDINGS_GEOJSON) -> gpd.GeoDataFrame:
    print(f"Loading {input_path} ...")
    gdf = load_and_clean(input_path)

    # Step 1: OSM height from tags
    gdf["height_osm"] = gdf.apply(_osm_height, axis=1)

    # Step 2: CityGML heights (if available)
    if CITYGML_GEOJSON.exists():
        print(f"  Merging CityGML heights from {CITYGML_GEOJSON.name} ...")
        gdf = merge_citygml_heights(gdf, CITYGML_GEOJSON)
        has_cgml = gdf["height_citygml"].notna().sum()
        print(f"  CityGML match: {has_cgml}/{len(gdf)} buildings")
    else:
        gdf["height_citygml"] = None
        gdf["gml_id"]         = None
        gdf["roof_type"]      = None
        print("  No CityGML data found – run 06_parse_citygml.py for official heights.")

    # Step 3: height_m priority: CityGML > OSM tag > default
    default = DEFAULT_STOREYS * DEFAULT_STOREY_HEIGHT
    gdf["height_m"] = (
        gdf["height_citygml"]
        .combine_first(gdf["height_osm"])
        .fillna(default)
    )
    gdf["height_source"] = "default"
    gdf.loc[gdf["height_osm"].notna(),     "height_source"] = "osm_tag"
    gdf.loc[gdf["height_citygml"].notna(), "height_source"] = "citygml"

    # Stats
    src_counts = gdf["height_source"].value_counts()
    print(f"  {len(gdf)} buildings | heights from:")
    for src, cnt in src_counts.items():
        print(f"    {src:<12}: {cnt:>5}  ({cnt/len(gdf)*100:.0f}%)")
    print(f"  height range: {gdf['height_m'].min():.1f} – {gdf['height_m'].max():.1f} m")

    out = DATA_INTERIM / "georgsvorstadt_clean.geojson"
    gdf.to_file(out, driver="GeoJSON")
    print(f"  Saved -> {out}")
    return gdf


if __name__ == "__main__":
    preprocess()