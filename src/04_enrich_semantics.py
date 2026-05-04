"""
Phase 4 – Semantische Erweiterung (LOD 200+)
Adds IfcPropertySets to each IfcBuilding in an existing IFC file:
  - Pset_BuildingCommon  (NumberOfStoreys, YearOfConstruction, OccupancyType)
  - Pset_EnergyConsumption (placeholder – fill from Energieatlas Bayern)
  - Pset_Georgsvorstadt  (custom: SealingRatio, BuildingTypology, CadastralID)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from configs.settings import IFC_OUTPUT, IFC_LOD200, DATA_INTERIM, CRS_SOURCE, CRS_WGS84

import geopandas as gpd
import pandas as pd
import ifcopenshell
import ifcopenshell.util.element as ifc_util

CRS_METRIC = CRS_SOURCE  # EPSG:25832 – ETRS89/UTM32N, metres, valid for Bavaria
ALKIS_SHP  = DATA_INTERIM.parent / "raw" / "alkis" / "Nutzung.shp"


TABULA_MAP = {
    "residential": "MFH_1918_DE",
    "apartments":  "MFH_1918_DE",
    "house":       "EFH_1918_DE",
    "detached":    "EFH_1918_DE",
    "commercial":  "NWG_1970_DE",
    "retail":      "NWG_1970_DE",
    "yes":         "MFH_1960_DE",   # unknown type - default
}


def _guid():
    return ifcopenshell.guid.new()


def _add_pset(f: ifcopenshell.file, oh, building, name: str, props: dict):
    pset = f.createIfcPropertySet(
        _guid(), oh, name, None,
        [f.createIfcPropertySingleValue(
            k, None,
            f.createIfcLabel(str(v)) if isinstance(v, str)
            else f.createIfcInteger(int(v)) if isinstance(v, int)
            else f.createIfcReal(float(v)),
            None,
        ) for k, v in props.items()],
    )
    f.createIfcRelDefinesByProperties(
        _guid(), oh, None, None, [building], pset,
    )


def _load_alkis_lookup(gdf_metric: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Spatial join: each building centroid → ALKIS Nutzungsklasse."""
    if not ALKIS_SHP.exists():
        return None
    alkis = gpd.read_file(ALKIS_SHP)[["nutzart", "bez", "geometry"]]
    # alkis is already EPSG:25832
    centroids = gdf_metric.copy()
    centroids.geometry = centroids.geometry.centroid
    joined = gpd.sjoin(centroids[["geometry"]], alkis, how="left", predicate="within")
    return joined[["nutzart", "bez"]].reset_index(drop=True)


def enrich(ifc_path: Path, geojson_path: Path) -> None:
    f   = ifcopenshell.open(str(ifc_path))
    oh  = f.by_type("IfcOwnerHistory")[0]
    gdf = gpd.read_file(geojson_path)

    # Reproject to metric CRS for area and spatial join
    gdf_metric = gdf.to_crs(CRS_METRIC)

    # ALKIS land use per building (optional)
    alkis_join = _load_alkis_lookup(gdf_metric)
    if alkis_join is not None:
        print(f"  ALKIS spatial join: {alkis_join['nutzart'].notna().sum()}/{len(gdf)} matched")

    # Build lookup: building name -> (wgs84 row, metric geometry, alkis row)
    name_map = {}
    for i, (_, row) in enumerate(gdf.iterrows()):
        key = str(row.get("name") or f"Gebaeude_{row.get('osm_id', i)}")
        alkis_row = alkis_join.iloc[i] if alkis_join is not None else None
        name_map[key] = (row, gdf_metric.iloc[i].geometry, alkis_row)

    enriched = 0
    for bldg in f.by_type("IfcBuilding"):
        entry = name_map.get(bldg.Name)
        if entry is None:
            continue
        row, geom_metric, alkis_row = entry

        levels   = int(float(row.get("levels") or 3))
        year     = str(row.get("start_date") or "unbekannt")
        gfa      = round(geom_metric.area * levels, 1)

        # OccupancyType: ALKIS beats OSM building tag
        if alkis_row is not None and pd.notna(alkis_row.get("nutzart")):
            occ = str(alkis_row["nutzart"])
        else:
            occ = str(row.get("building") or "residential")
        typology = TABULA_MAP.get(occ, "MFH_1960_DE")

        # Height source from preprocess
        h_source  = str(row.get("height_source", "default"))
        roof_type = str(row.get("roof_type") or "unbekannt")
        gml_id    = str(row.get("gml_id") or "")

        _add_pset(f, oh, bldg, "Pset_BuildingCommon", {
            "NumberOfStoreys":    levels,
            "YearOfConstruction": year,
            "OccupancyType":      occ,
            "GrossFloorArea":     gfa,
        })
        _add_pset(f, oh, bldg, "Pset_EnergyConsumption", {
            "EnergyConsumptionHeating": "n/a",  # fill from Energieatlas Bayern
            "CO2Intensity":             "n/a",
        })
        _add_pset(f, oh, bldg, "Pset_Georgsvorstadt", {
            "BuildingTypology": typology,
            "SealingRatio":     "0.72",
            "CadastralID":      str(row.get("osm_id", "")),
            "GmlID":            gml_id,
            "HeightSource":     h_source,
            "RoofType":         roof_type,
        })
        enriched += 1

    IFC_LOD200.parent.mkdir(parents=True, exist_ok=True)
    f.write(str(IFC_LOD200))
    print(f"Enriched {enriched} buildings -> {IFC_LOD200}")


if __name__ == "__main__":
    clean = DATA_INTERIM / "georgsvorstadt_clean.geojson"
    if not IFC_OUTPUT.exists():
        print("Run 03_generate_ifc.py first.")
        sys.exit(1)
    enrich(IFC_OUTPUT, clean)
