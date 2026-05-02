"""
Phase 2 – GIS-Vorverarbeitung
Loads building footprints from GeoJSON, reprojects, cleans geometry,
and derives height from OSM tags or LoD2 data.
Run after 01_fetch_data.py (or after manual QGIS export).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from configs.settings import (
    BUILDINGS_GEOJSON, DATA_INTERIM, CRS_WGS84,
    DEFAULT_STOREY_HEIGHT, DEFAULT_STOREYS,
)

import geopandas as gpd
import pandas as pd


def load_and_clean(path: Path) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs(CRS_WGS84)
    gdf = gdf.to_crs(CRS_WGS84)

    # Drop invalid or empty geometries
    gdf = gdf[gdf.geometry.is_valid & ~gdf.geometry.is_empty].copy()

    # Remove obvious duplicates by centroid proximity
    gdf["centroid"] = gdf.geometry.centroid
    gdf = gdf.drop_duplicates(subset=["centroid"]).drop(columns=["centroid"])

    return gdf.reset_index(drop=True)


def derive_height(row: pd.Series) -> float:
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
    return DEFAULT_STOREYS * DEFAULT_STOREY_HEIGHT


def preprocess(input_path: Path = BUILDINGS_GEOJSON) -> gpd.GeoDataFrame:
    print(f"Loading {input_path} …")
    gdf = load_and_clean(input_path)
    gdf["height_m"] = gdf.apply(derive_height, axis=1)
    print(f"  {len(gdf)} valid buildings after cleaning")
    print(f"  height range: {gdf['height_m'].min():.1f} – {gdf['height_m'].max():.1f} m")

    out = DATA_INTERIM / "georgsvorstadt_clean.geojson"
    gdf.to_file(out, driver="GeoJSON")
    print(f"  Saved -> {out}")
    return gdf


if __name__ == "__main__":
    preprocess()
