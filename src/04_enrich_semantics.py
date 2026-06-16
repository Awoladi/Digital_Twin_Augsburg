"""
Phase 4 – Semantische Erweiterung (LOD 200+)
Fügt jedem IfcBuilding in einer bestehenden IFC-Datei PropertySets hinzu:
  - Pset_BuildingCommon       (NumberOfStoreys, YearOfConstruction, OccupancyType, GrossFloorArea)
  - Pset_EnergyConsumption    (Heizwärmebedarf und CO2-Intensität aus TABULA-Typologien)
  - Pset_Georgsvorstadt       (BuildingTypology, SealingRatio je ALKIS-Nutzungsart, GmlID, …)
  - Pset_Adresse              (Straße, Hausnummer, PLZ, Stadt – aus OSM addr:* Tags)
  - Pset_Denkmalschutz        (BLfD-Referenz, Schutzumfang – für 73 Denkmäler in OSM)
  - Pset_Gebaeudebeschreibung (Farbe, Material, Architekturstil, Architekt – aus OSM-Tags)

Baujahr-Priorität: Wikidata (08_enrich_wikidata.py) > OSM start_date > ALKIS-Baujahr
Energiequelle:     TABULA-Webtool – IWU Darmstadt (webtool.building-typology.eu)
Versiegelungsgrad: BauNVO-Richtwerte (GRZ) je ALKIS-Nutzungsart
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from configs.settings import IFC_OUTPUT, IFC_LOD200, DATA_INTERIM, CRS_SOURCE, CRS_WGS84

import geopandas as gpd
import pandas as pd
import ifcopenshell
import ifcopenshell.util.element as ifc_util

CRS_METRIC = CRS_SOURCE  # EPSG:25832 – ETRS89/UTM32N, Meter, gültig für Bayern
ALKIS_SHP  = DATA_INTERIM.parent / "raw" / "alkis" / "Nutzung.shp"


# ---------------------------------------------------------------------------
# ALKIS nutzart → TABULA-Gebäudetypologie
# Deckt alle tatsächlich im Datensatz vorkommenden ALKIS-Werte ab (Phase 2 Analyse).
# ---------------------------------------------------------------------------
ALKIS_TO_TYPOLOGY = {
    # ALKIS-Nutzungsarten (aus Georgsvorstadt-Daten)
    "Wohnbaufläche":                              "MFH_1918_DE",
    "Fläche gemischter Nutzung":                  "MFH_1960_DE",
    "Industrie- und Gewerbefläche":               "NWG_1970_DE",
    "Fläche besonderer funktionaler Prägung":     "NWG_1970_DE",
    "Straßenverkehr":                             "NWG_1970_DE",
    "Bahnverkehr":                                "NWG_1970_DE",
    "Sport-, Freizeit- und Erholungsfläche":      "NWG_1970_DE",
    "Friedhof":                                   "NWG_1970_DE",
    # OSM-Fallbacks (wenn kein ALKIS-Treffer)
    "residential":  "MFH_1918_DE",
    "apartments":   "MFH_1918_DE",
    "house":        "EFH_1918_DE",
    "detached":     "EFH_1918_DE",
    "commercial":   "NWG_1970_DE",
    "retail":       "NWG_1970_DE",
    "yes":          "MFH_1960_DE",
}

# ---------------------------------------------------------------------------
# TABULA-Energiekennwerte (Ist-Zustand, unsaniert)
# Quelle: TABULA-Webtool, IWU Darmstadt – webtool.building-typology.eu
#   heat_kwh_m2 : Heizwärmebedarf [kWh/(m²·a)]
#   co2_kg_m2   : CO2-Emissionen   [kg CO2/(m²·a)]  (Faktor Gas: 0.202 kg/kWh, η=0.85)
# ---------------------------------------------------------------------------
TABULA_ENERGY = {
    "MFH_1918_DE": {"heat_kwh_m2": 220, "co2_kg_m2": 52},   # Gründerzeit-MFH
    "MFH_1960_DE": {"heat_kwh_m2": 160, "co2_kg_m2": 38},   # Nachkriegs-MFH
    "EFH_1918_DE": {"heat_kwh_m2": 250, "co2_kg_m2": 59},   # Gründerzeit-EFH
    "NWG_1970_DE": {"heat_kwh_m2": 120, "co2_kg_m2": 28},   # Gewerbe/Sonstiges
}

# ---------------------------------------------------------------------------
# Versiegelungsgrad (Grundflächenzahl GRZ) je ALKIS-Nutzungsart
# Quelle: BauNVO §17 Richtwerte, ergänzt durch Literaturwerte
# ---------------------------------------------------------------------------
ALKIS_SEALING = {
    "Wohnbaufläche":                              0.65,
    "Fläche gemischter Nutzung":                  0.80,
    "Industrie- und Gewerbefläche":               0.90,
    "Fläche besonderer funktionaler Prägung":     0.75,
    "Straßenverkehr":                             0.95,
    "Bahnverkehr":                                0.90,
    "Sport-, Freizeit- und Erholungsfläche":      0.40,
    "Friedhof":                                   0.30,
}
DEFAULT_SEALING = 0.72


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
    """Spatial-Join: jedem Gebäudeschwerpunkt die ALKIS-Nutzungsklasse zuweisen."""
    if not ALKIS_SHP.exists():
        return None
    alkis = gpd.read_file(ALKIS_SHP)[["nutzart", "bez", "geometry"]]
    # ALKIS liegt bereits in EPSG:25832 vor
    centroids = gdf_metric.copy()
    centroids.geometry = centroids.geometry.centroid
    joined = gpd.sjoin(centroids[["geometry"]], alkis, how="left", predicate="within")
    return joined[["nutzart", "bez"]].reset_index(drop=True)


def enrich(ifc_path: Path, geojson_path: Path) -> None:
    f   = ifcopenshell.open(str(ifc_path))
    oh_list = f.by_type("IfcOwnerHistory")
    oh = oh_list[0] if oh_list else None
    gdf = gpd.read_file(geojson_path)

    # In metrisches CRS reprojizieren für Flächenberechnung und Spatial-Join
    gdf_metric = gdf.to_crs(CRS_METRIC)

    # ALKIS-Nutzung je Gebäude (optional)
    alkis_join = _load_alkis_lookup(gdf_metric)
    if alkis_join is not None:
        print(f"  ALKIS-Spatial-Join: {alkis_join['nutzart'].notna().sum()}/{len(gdf)} gematcht")

    # Lookup aufbauen: Gebäudename -> (WGS84-Zeile, metrische Geometrie, ALKIS-Zeile)
    name_map = {}
    for i, (_, row) in enumerate(gdf.iterrows()):
        key = str(row.get("name") or f"Gebaeude_{row.get('osm_id', i)}")
        alkis_row = alkis_join.iloc[i] if alkis_join is not None else None
        name_map[key] = (row, gdf_metric.iloc[i].geometry, alkis_row)

    enriched = 0
    total_heat_kwh = 0.0
    typology_counts: dict[str, int] = {}

    for bldg in f.by_type("IfcBuilding"):
        entry = name_map.get(bldg.Name)
        if entry is None:
            continue
        row, geom_metric, alkis_row = entry

        levels = int(float(row.get("levels") or 3))
        year   = str(row.get("start_date") or "unbekannt")
        gfa    = round(geom_metric.area * levels, 1)

        # OccupancyType: ALKIS hat Vorrang vor OSM-building-Tag
        if alkis_row is not None and pd.notna(alkis_row.get("nutzart")):
            occ = str(alkis_row["nutzart"])
        else:
            occ = str(row.get("building") or "residential")

        # Gebäudetypologie: ALKIS-Nutzungsart → TABULA-Klasse
        typology = ALKIS_TO_TYPOLOGY.get(occ, "MFH_1960_DE")
        typology_counts[typology] = typology_counts.get(typology, 0) + 1

        # Energiekennwerte aus TABULA-Benchmarks (Ist-Zustand, unsaniert)
        energy     = TABULA_ENERGY.get(typology, TABULA_ENERGY["MFH_1960_DE"])
        heat_total = round(energy["heat_kwh_m2"] * gfa, 0)   # kWh/a gesamt
        co2_total  = round(energy["co2_kg_m2"]   * gfa, 0)   # kg CO2/a gesamt
        total_heat_kwh += heat_total

        # Versiegelungsgrad je ALKIS-Nutzungsart
        sealing = ALKIS_SEALING.get(occ, DEFAULT_SEALING)

        # Metadaten aus Vorphasen
        h_source  = str(row.get("height_source", "default"))
        roof_type = str(row.get("roof_type") or "unbekannt")
        gml_id    = str(row.get("gml_id") or "")

        # Baujahr: Wikidata (08) > OSM start_date
        year_osm = str(row.get("start_date") or "").strip()
        year_wd  = str(row.get("wd_baujahr") or "").strip()
        year     = year_wd or year_osm or "unbekannt"

        _add_pset(f, oh, bldg, "Pset_BuildingCommon", {
            "NumberOfStoreys":    levels,
            "YearOfConstruction": year,
            "OccupancyType":      occ,
            "GrossFloorArea":     gfa,
        })
        _add_pset(f, oh, bldg, "Pset_EnergyConsumption", {
            "SpecificHeatDemand":       energy["heat_kwh_m2"],
            "CO2Intensity":             energy["co2_kg_m2"],
            "EnergyConsumptionHeating": heat_total,
            "CO2EmissionsTotal":        co2_total,
            "EnergyDataSource":         "TABULA-Webtool IWU Darmstadt (Ist-Zustand unsaniert)",
            "EnergyTypology":           typology,
        })
        _add_pset(f, oh, bldg, "Pset_Georgsvorstadt", {
            "BuildingTypology": typology,
            "SealingRatio":     sealing,
            "CadastralID":      str(row.get("osm_id", "")),
            "GmlID":            gml_id,
            "HeightSource":     h_source,
            "RoofType":         roof_type,
        })

        # Pset_Adresse – aus OSM addr:* Tags (62% der Gebäude)
        street = str(row.get("addr_street",      "") or "").strip()
        hsnr   = str(row.get("addr_housenumber", "") or "").strip()
        plz    = str(row.get("addr_postcode",    "") or "").strip()
        city   = str(row.get("addr_city",        "") or "").strip()
        if any([street, hsnr, plz, city]):
            _add_pset(f, oh, bldg, "Pset_Adresse", {
                "Strasse":       street,
                "Hausnummer":    hsnr,
                "Postleitzahl":  plz,
                "Stadt":         city,
            })

        # Pset_Denkmalschutz – BLfD-Daten aus OSM (73 Gebäude)
        ref_blfd = str(row.get("ref_blfd",      "") or "").strip()
        blfd_kr  = str(row.get("blfd_criteria", "") or "").strip()
        heritage = str(row.get("heritage",      "") or "").strip()
        if any([ref_blfd, blfd_kr, heritage]):
            _add_pset(f, oh, bldg, "Pset_Denkmalschutz", {
                "IstDenkmalgeschuetzt": "ja",
                "BLfD_Referenz":        ref_blfd,
                "Schutzumfang":         blfd_kr,
                "Denkmalstufe":         heritage,
                "Denkmalbehoerde":      str(row.get("heritage_operator", "") or "").strip(),
            })

        # Pset_Gebaeudebeschreibung – visuelle + historische Metadaten aus OSM/Wikidata
        colour   = str(row.get("building_colour",       "") or "").strip()
        material = str(row.get("building_material",     "") or "").strip()
        archstil = str(row.get("building_architecture", "") or "").strip()
        architkt = str(row.get("architect",             "") or "").strip()
        wd_arch  = str(row.get("wd_architekt",          "") or "").strip()
        wd_stil  = str(row.get("wd_stil",               "") or "").strip()
        roof_col = str(row.get("osm_roof_colour",       "") or "").strip()
        roof_mat = str(row.get("osm_roof_material",     "") or "").strip()
        if any([colour, material, archstil, architkt, wd_arch, wd_stil, roof_col, roof_mat]):
            _add_pset(f, oh, bldg, "Pset_Gebaeudebeschreibung", {
                "Fassadenfarbe":    colour,
                "Fassadenmaterial": material,
                "Architekturstil":  wd_stil or archstil,
                "Architekt":        wd_arch or architkt,
                "Dachfarbe":        roof_col,
                "Dachmaterial":     roof_mat,
            })

        enriched += 1

    IFC_LOD200.parent.mkdir(parents=True, exist_ok=True)
    f.write(str(IFC_LOD200))
    print(f"{enriched} Gebäude semantisch erweitert -> {IFC_LOD200}")
    print(f"\n  Gebäudetypologien:")
    for typ, cnt in sorted(typology_counts.items(), key=lambda x: -x[1]):
        print(f"    {typ:<20}: {cnt:>5} Gebäude")
    print(f"\n  Gesamter Heizwärmebedarf (Quartier): {total_heat_kwh/1e6:.1f} GWh/a")


if __name__ == "__main__":
    # Wikidata-angereicherte GeoJSON bevorzugen (08_enrich_wikidata.py), falls vorhanden
    wikidata_geojson = DATA_INTERIM / "georgsvorstadt_clean_wikidata.geojson"
    clean            = DATA_INTERIM / "georgsvorstadt_clean.geojson"
    geojson_path     = wikidata_geojson if wikidata_geojson.exists() else clean
    if geojson_path == wikidata_geojson:
        print("  Wikidata-angereicherte GeoJSON wird verwendet.")
    if not IFC_OUTPUT.exists():
        print("Zuerst 03_generate_ifc.py ausführen.")
        sys.exit(1)
    enrich(IFC_OUTPUT, geojson_path)
