"""
Phase 2 – GIS-Vorverarbeitung
Lädt OSM-Gebäudegrundrisse, bereinigt die Geometrie und ergänzt Höhen:
  1. OSM-Höhen- / Stockwerk-Tags (direkt ausgelesen)
  2. CityGML-LoD2-Spatial-Join (falls georgsvorstadt_citygml.geojson vorhanden)
  3. Standard-Fallback (DEFAULT_STOREYS * DEFAULT_STOREY_HEIGHT)

Dachform-Fallback: OSM roof:shape → deutsches Kürzel, wenn CityGML keinen roof_type liefert.
Alle neuen OSM-Spalten (Adresse, Denkmal, Wikidata, …) werden durchgereicht.

Nach 01_fetch_data.py und (optional) 06_parse_citygml.py ausführen.
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

# OSM roof:shape → deutsche Dachformbezeichnung (als Fallback wenn CityGML kein roof_type hat)
OSM_ROOF_SHAPES = {
    "gabled":       "Satteldach",
    "flat":         "Flachdach",
    "hipped":       "Walmdach",
    "mansard":      "Mansarddach",
    "skillion":     "Pultdach",
    "pyramidal":    "Zeltdach",
    "half-hipped":  "Krüppelwalmdach",
    "side_hipped":  "Krüppelwalmdach",
    "saltbox":      "Pultdach",
    "gambrel":      "Mansarddach",
    "dome":         "Kuppeldach",
    "onion":        "Zwiebelturm",
    "round":        "Tonnendach",
    "conical":      "Kegeldach",
}


def load_and_clean(path: Path) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs(CRS_WGS84)
    gdf = gdf.to_crs(CRS_WGS84)
    gdf = gdf[gdf.geometry.is_valid & ~gdf.geometry.is_empty].copy()

    # Duplikate anhand metrischer Schwerpunkte entfernen
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
    """Spatial-Join: jedem OSM-Gebäude die nächste CityGML-Höhe zuweisen."""
    cgml = gpd.read_file(citygml_path)[["height_m", "gml_id", "roof_type", "geometry"]]
    cgml = cgml.to_crs(CRS_WGS84)

    # Nearest-Join in metrischem CRS (jedes OSM-Gebäude -> nächster CityGML-Schwerpunkt)
    osm_m  = osm.to_crs(CRS_SOURCE).copy()
    osm_m.geometry  = osm_m.geometry.centroid
    cgml_m = cgml.to_crs(CRS_SOURCE).copy()
    cgml_m.geometry = cgml_m.geometry.centroid

    joined = gpd.sjoin_nearest(
        osm_m,
        cgml_m[["height_m", "gml_id", "roof_type", "geometry"]],
        how="left",
        max_distance=30,          # nur Treffer innerhalb von 30 m akzeptieren
        distance_col="_dist_m",
    )
    osm["height_citygml"] = joined["height_m"].values
    osm["gml_id"]         = joined["gml_id"].values
    osm["roof_type"]      = joined["roof_type"].values
    return osm


def preprocess(input_path: Path = BUILDINGS_GEOJSON) -> gpd.GeoDataFrame:
    print(f"Lade {input_path} ...")
    gdf = load_and_clean(input_path)

    # Schritt 1: OSM-Höhe aus Tags
    gdf["height_osm"] = gdf.apply(_osm_height, axis=1)

    # Schritt 2: CityGML-Höhen (falls vorhanden)
    if CITYGML_GEOJSON.exists():
        print(f"  Merge CityGML-Höhen aus {CITYGML_GEOJSON.name} ...")
        gdf = merge_citygml_heights(gdf, CITYGML_GEOJSON)
        has_cgml = gdf["height_citygml"].notna().sum()
        print(f"  CityGML-Treffer: {has_cgml}/{len(gdf)} Gebäude")
    else:
        gdf["height_citygml"] = None
        gdf["gml_id"]         = None
        gdf["roof_type"]      = None
        print("  Keine CityGML-Daten gefunden – 06_parse_citygml.py für amtliche Höhen ausführen.")

    # Schritt 3: Höhenpriorität: CityGML > OSM-Tag > Standard-Fallback
    default = DEFAULT_STOREYS * DEFAULT_STOREY_HEIGHT
    MIN_HEIGHT = 2.5  # darunter -> wahrscheinlich Garage/Nebengebäude, Fallback verwenden
    gdf["height_m"] = (
        gdf["height_citygml"]
        .combine_first(gdf["height_osm"])
        .fillna(default)
    )
    low_mask = gdf["height_m"] < MIN_HEIGHT
    gdf.loc[low_mask, "height_m"] = default
    gdf.loc[low_mask, "height_source"] = "default"
    gdf["height_source"] = "default"
    gdf.loc[gdf["height_osm"].notna(),     "height_source"] = "osm_tag"
    gdf.loc[gdf["height_citygml"].notna(), "height_source"] = "citygml"

    # Schritt 4: OSM roof:shape als Fallback für roof_type (wenn CityGML keinen Wert liefert)
    if "osm_roof_shape" in gdf.columns:
        osm_roof_mask = (
            gdf["roof_type"].isna() | (gdf["roof_type"] == "") | (gdf["roof_type"] == "unbekannt")
        ) & gdf["osm_roof_shape"].notna() & (gdf["osm_roof_shape"] != "")
        gdf.loc[osm_roof_mask, "roof_type"] = (
            gdf.loc[osm_roof_mask, "osm_roof_shape"].map(OSM_ROOF_SHAPES).fillna("Sonstiges")
        )
        osm_roof_count = osm_roof_mask.sum()
        print(f"  Dachform-Fallback (OSM): {osm_roof_count} Gebäude ergänzt")

    # Statistik
    src_counts = gdf["height_source"].value_counts()
    print(f"  {len(gdf)} Gebäude | Höhen aus:")
    for src, cnt in src_counts.items():
        print(f"    {src:<12}: {cnt:>5}  ({cnt/len(gdf)*100:.0f}%)")
    print(f"  Höhenspanne: {gdf['height_m'].min():.1f} – {gdf['height_m'].max():.1f} m")

    # Dachform-Statistik
    if "roof_type" in gdf.columns:
        roof_filled = gdf["roof_type"].notna() & (gdf["roof_type"] != "") & (gdf["roof_type"] != "unbekannt")
        print(f"  Dachform bekannt: {roof_filled.sum()}/{len(gdf)} ({roof_filled.sum()/len(gdf)*100:.0f}%)")

    out = DATA_INTERIM / "georgsvorstadt_clean.geojson"
    gdf.to_file(out, driver="GeoJSON")
    print(f"  Gespeichert -> {out}")
    return gdf


if __name__ == "__main__":
    preprocess()