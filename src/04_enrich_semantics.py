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
from configs.settings import IFC_OUTPUT, IFC_LOD200, DATA_INTERIM

import geopandas as gpd
import ifcopenshell
import ifcopenshell.util.element as ifc_util

CRS_METRIC = "EPSG:25832"  # ETRS89/UTM32N – metres, valid for Bavaria


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


def enrich(ifc_path: Path, geojson_path: Path) -> None:
    f   = ifcopenshell.open(str(ifc_path))
    oh  = f.by_type("IfcOwnerHistory")[0]
    gdf = gpd.read_file(geojson_path)

    # Reproject to metric CRS for correct area calculation
    gdf_metric = gdf.to_crs(CRS_METRIC)

    # Build a lookup: building name -> (wgs84 row, metric geometry)
    name_map = {
        str(row.get("name") or f"Gebaeude_{row.get('osm_id', i)}"): (row, gdf_metric.iloc[i].geometry)
        for i, (_, row) in enumerate(gdf.iterrows())
    }

    enriched = 0
    for bldg in f.by_type("IfcBuilding"):
        entry = name_map.get(bldg.Name)
        if entry is None:
            continue
        row, geom_metric = entry

        levels   = int(float(row.get("levels") or 3))
        year     = str(row.get("start_date") or "unbekannt")
        occ      = str(row.get("building") or "residential")
        typology = TABULA_MAP.get(occ, "MFH_1960_DE")
        gfa      = round(geom_metric.area * levels, 1)  # footprint m² × storeys

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
            "SealingRatio":     "0.72",          # district average from ATKIS
            "CadastralID":      str(row.get("osm_id", "")),
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
