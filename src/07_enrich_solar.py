"""
Phase 7 – Solarpotenzial (PVGIS, EU JRC)
Berechnet das jährliche Solarpotenzial für jedes Gebäude im IFC-Modell und
schreibt es als Pset_SolarPotential in eine neue IFC-Datei.

Methode:
  1. PVGIS SARAH-3 API einmalig für den Quartiersmittelpunkt aufrufen
     -> Globale Horizontalstrahlung H_h [kWh/(m²·a)] aus 'outputs.totals.fixed.H(h)'
  2. Dachflächenfaktor je Dachform (Neigungsfaktor ≥1.0 für geneigte Dächer)
  3. PV-Ertragspotenzial je Gebäude = H_h × Faktor × Grundfläche × η × PR
     (η=0.20 monokristallin, PR=0.80 Performance Ratio – praxisüblich)
  4. Solarthermie-Warmwasserpotenzial = H_h × 0.45 × Grundfläche × 0.25
     (45% solare Deckung, 25% der Dachfläche für Kollektoren)

Quelle: PVGIS 5.3 REST API – re.jrc.ec.europa.eu/pvg_tools/en/tools.html
        (öffentlich zugänglich, keine Authentifizierung nötig)
"""

import sys, json, time, urllib.request, urllib.parse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from configs.settings import IFC_LOD200, DATA_INTERIM, CRS_SOURCE, CRS_WGS84, BBOX

import geopandas as gpd
import ifcopenshell
import ifcopenshell.util.element as ifc_util

# ---------------------------------------------------------------------------
# PVGIS-Parameter
# ---------------------------------------------------------------------------
PVGIS_URL    = "https://re.jrc.ec.europa.eu/api/v5_3/PVcalc"
PV_ETA       = 0.20   # Modulwirkungsgrad monokristallin [–]
PV_PR        = 0.80   # Performance Ratio (Wechselrichter, Leitungsverluste) [–]
SOLTH_SHARE  = 0.25   # Anteil Dachfläche für Solarthermie [–]
SOLTH_ETA    = 0.45   # Solare Deckungsrate Warmwasser [–]

IFC_SOLAR    = IFC_LOD200.parent / "georgsvorstadt_solar.ifc"

# ---------------------------------------------------------------------------
# Dachflächenfaktor je Dachform (berücksichtigt Neigung und Himmelsrichtung)
# Wert > 1.0: geneigte Dachfläche > Grundfläche
# Wert = 1.0: Flachdach oder unbekannt
# ---------------------------------------------------------------------------
ROOF_AREA_FACTOR = {
    "Satteldach":       1.25,   # Neigung ~30°, zwei Seiten
    "Walmdach":         1.30,
    "Mansarddach":      1.35,
    "Pultdach":         1.15,
    "Versetztes Pultdach": 1.20,
    "Zeltdach":         1.20,
    "Krüppelwalmdach":  1.28,
    "Flachdach":        1.00,
    "Kegeldach":        1.30,
    "Tonnendach":       1.20,
    "Kuppeldach":       1.40,
    "Sonstiges":        1.10,
}


def _guid():
    return ifcopenshell.guid.new()


def fetch_pvgis(lat: float, lon: float, peak_power: float = 1.0) -> dict:
    """PVGIS SARAH-3 API aufrufen und Jahreswerte zurückgeben."""
    params = {
        "lat":        lat,
        "lon":        lon,
        "peakpower":  peak_power,
        "loss":       14,           # Systemverluste in %
        "pvtechchoice": "crystSi",
        "mountingplace": "free",
        "outputformat": "json",
        "browser":    0,
    }
    url  = PVGIS_URL + "?" + urllib.parse.urlencode(params)
    req  = urllib.request.Request(url, headers={"User-Agent": "DigitalTwinAugsburg/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def fetch_pvgis_data(lat: float, lon: float) -> tuple[float, float]:
    """
    PVGIS-Daten fuer den Standort abrufen.
    Gibt (E_y, H_i_y) zurueck:
      E_y    : jaehrl. Energieertrag je installiertem kWp [kWh/kWp/a] – inkl. aller Verluste
      H_i_y  : Globalstrahlung auf optimaler Neigungsflaeche [kWh/(m2*a)]
    """
    data  = fetch_pvgis(lat, lon, peak_power=1.0)
    fixed = data["outputs"]["totals"]["fixed"]
    e_y   = fixed["E_y"]
    h_i_y = fixed["H(i)_y"]
    print(f"  PVGIS: H(i)_y={h_i_y:.0f} kWh/(m2*a), E_y={e_y:.0f} kWh/kWp/a")
    return e_y, h_i_y


def _add_pset(f, oh, building, name: str, props: dict):
    pset = f.createIfcPropertySet(
        _guid(), oh, name, None,
        [f.createIfcPropertySingleValue(
            k, None,
            f.createIfcLabel(str(v)) if isinstance(v, str)
            else f.createIfcReal(float(v)),
            None,
        ) for k, v in props.items()],
    )
    f.createIfcRelDefinesByProperties(_guid(), oh, None, None, [building], pset)


def enrich_solar(ifc_path: Path, geojson_path: Path) -> None:
    # PVGIS einmalig für Quartiersmittelpunkt aufrufen
    lat_c = (BBOX["min_lat"] + BBOX["max_lat"]) / 2
    lon_c = (BBOX["min_lon"] + BBOX["max_lon"]) / 2
    print(f"  Rufe PVGIS fuer ({lat_c:.4f} N, {lon_c:.4f} E) ab ...")
    try:
        e_y, h_i_y = fetch_pvgis_data(lat_c, lon_c)
    except Exception as exc:
        print(f"  PVGIS-Fehler: {exc}  - nutze Fallback-Werte")
        e_y, h_i_y = 950.0, 1213.0   # DWD Klimareferenz Augsburg

    gdf = gpd.read_file(geojson_path).to_crs(CRS_SOURCE)
    f   = ifcopenshell.open(str(ifc_path))
    oh_list = f.by_type("IfcOwnerHistory")
    oh = oh_list[0] if oh_list else None

    name_map = {}
    for _, row in gdf.iterrows():
        key = str(row.get("name") or f"Gebaeude_{row.get('osm_id', '')}")
        name_map[key] = row

    enriched = 0
    pv_total_mwh = 0.0

    for bldg in f.by_type("IfcBuilding"):
        row = name_map.get(bldg.Name)
        if row is None:
            continue

        # Grundfläche in m²
        geom_metric = gdf.loc[gdf["osm_id"] == row.get("osm_id")].geometry
        if geom_metric.empty:
            footprint_m2 = 80.0   # Fallback
        else:
            footprint_m2 = float(geom_metric.iloc[0].area)

        # Dachflächenfaktor
        roof_type   = str(row.get("roof_type") or "Sonstiges")
        area_factor = ROOF_AREA_FACTOR.get(roof_type, 1.10)
        roof_area   = footprint_m2 * area_factor

        # Belichtungsfaktor: Anteil der Dachfläche, der für PV nutzbar ist
        # (Abzüge für Aufbauten, Verschattung, Ausrichtung)
        usable_share = 0.30   # konservativ 30%

        # PV-Ertragspotenzial (Methode: E_y * installierte kWp)
        # Installierbare Leistung: usable_share * roof_area * 0.2 kWp/m² (200 W/m²)
        peak_power_kwp = usable_share * roof_area * PV_ETA   # kWp (ETA als kWp/m²)
        pv_kwh_a       = e_y * peak_power_kwp                # kWh/a (netto, inkl. Verluste)

        # Solarthermie-Potenzial [kWh/a, thermisch]
        solth_kwh_a = h_i_y * SOLTH_SHARE * roof_area * SOLTH_ETA

        pv_total_mwh += pv_kwh_a / 1000

        _add_pset(f, oh, bldg, "Pset_SolarPotential", {
            "SolarIrradiation_kWh_m2a": round(h_i_y, 0),
            "RoofArea_m2":              round(roof_area, 1),
            "RoofAreaFactor":           area_factor,
            "PV_Yield_kWh_a":           round(pv_kwh_a, 0),
            "SolarThermal_kWh_a":       round(solth_kwh_a, 0),
            "PV_UsableShare":           usable_share,
            "DataSource":               "PVGIS 5.3 SARAH-3 (re.jrc.ec.europa.eu)",
        })
        enriched += 1

    # In LOD200-Hauptdatei schreiben (damit 05_evaluate.py Pset_SolarPotential sieht)
    IFC_SOLAR.parent.mkdir(parents=True, exist_ok=True)
    f.write(str(ifc_path))
    print(f"  {enriched} Gebaeude mit Solardaten erweitert -> {ifc_path}")
    print(f"  PV-Potenzial Quartier gesamt: {pv_total_mwh:.0f} MWh/a")


if __name__ == "__main__":
    clean = DATA_INTERIM / "georgsvorstadt_clean.geojson"
    if not IFC_LOD200.exists():
        print("Zuerst 04_enrich_semantics.py ausführen.")
        sys.exit(1)
    if not clean.exists():
        print("Zuerst 02_preprocess_gis.py ausführen.")
        sys.exit(1)
    enrich_solar(IFC_LOD200, clean)
