"""
Phase 5 – Bewertung & Dokumentation
Prüft die Vollständigkeit des angereicherten IFC-Modells und gibt einen
Qualitätsbericht mit Höhenverteilung und Attribut-Füllraten aus.
"""

import sys, time, statistics
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from configs.settings import DATA_OUTPUT, DATA_INTERIM, DEFAULT_STOREYS, DEFAULT_STOREY_HEIGHT

import ifcopenshell
import ifcopenshell.util.element as ifc_util

REQUIRED_PSETS = {
    "Pset_BuildingCommon":    ["NumberOfStoreys", "YearOfConstruction", "OccupancyType", "GrossFloorArea"],
    "Pset_EnergyConsumption": ["SpecificHeatDemand", "CO2Intensity", "EnergyConsumptionHeating"],
    "Pset_Georgsvorstadt":    ["BuildingTypology", "SealingRatio", "CadastralID"],
}

DEFAULT_HEIGHT = DEFAULT_STOREYS * DEFAULT_STOREY_HEIGHT  # 9,6 m


def _bar(ratio: float, width: int = 20) -> str:
    filled = round(ratio * width)
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def evaluate(ifc_path: Path) -> None:
    t0        = time.time()
    f         = ifcopenshell.open(str(ifc_path))
    buildings = f.by_type("IfcBuilding")
    total     = len(buildings)

    print(f"\n{'='*55}")
    print(f"  IFC-Qualitaetsbericht: {ifc_path.name}")
    print(f"{'='*55}")
    print(f"  IfcBuilding-Entitaeten : {total}")

    # ------------------------------------------------------------------
    # Höhenverteilung über IfcBuildingElementProxy-Ausdehnungen
    # ------------------------------------------------------------------
    heights = []
    for proxy in f.by_type("IfcBuildingElementProxy"):
        try:
            solid = proxy.Representation.Representations[0].Items[0]
            h = float(solid.Depth)
            heights.append(h)
        except Exception:
            continue

    if heights:
        default_count = sum(1 for h in heights if abs(h - DEFAULT_HEIGHT) < 0.01)
        print(f"\n  Höhenverteilung ({len(heights)} Proxies):")
        print(f"    min      : {min(heights):.1f} m")
        print(f"    max      : {max(heights):.1f} m")
        print(f"    Mittel   : {statistics.mean(heights):.1f} m")
        print(f"    Median   : {statistics.median(heights):.1f} m")
        print(f"    Fallback : {default_count} ({default_count/len(heights)*100:.0f}%) "
              f"Standard {DEFAULT_HEIGHT} m  <- kein OSM-Höhen-Tag")

    # ------------------------------------------------------------------
    # PropertySet-Abdeckung
    # ------------------------------------------------------------------
    pset_hits = {pset: 0 for pset in REQUIRED_PSETS}
    attr_hits = {}

    for bldg in buildings:
        psets = ifc_util.get_psets(bldg)
        for pset_name, attrs in REQUIRED_PSETS.items():
            if pset_name in psets:
                pset_hits[pset_name] += 1
                for attr in attrs:
                    key = f"{pset_name}.{attr}"
                    val = psets[pset_name].get(attr, "")
                    if val and str(val) not in ("n/a", "unbekannt", ""):
                        attr_hits[key] = attr_hits.get(key, 0) + 1

    print(f"\n  PropertySet-Abdeckung:")
    for pset_name, count in pset_hits.items():
        ratio = count / total if total else 0
        print(f"    {pset_name:<30} {_bar(ratio)} {count}/{total} ({ratio*100:.0f}%)")

    print(f"\n  Attribut-Füllrate (ohne n/a / unbekannt):")
    for pset_name, attrs in REQUIRED_PSETS.items():
        for attr in attrs:
            key   = f"{pset_name}.{attr}"
            count = attr_hits.get(key, 0)
            ratio = count / total if total else 0
            print(f"    {key:<48} {count:>4}/{total} ({ratio*100:.0f}%)")

    # ------------------------------------------------------------------
    # Energie- und Typologie-Zusammenfassung
    # ------------------------------------------------------------------
    typology_counts: dict[str, int] = {}
    heat_total_gwh = 0.0
    co2_total_t    = 0.0

    for bldg in buildings:
        psets = ifc_util.get_psets(bldg)
        ep = psets.get("Pset_EnergyConsumption", {})
        gp = psets.get("Pset_Georgsvorstadt", {})

        try:
            heat_total_gwh += float(ep.get("EnergyConsumptionHeating", 0)) / 1e6
        except (ValueError, TypeError):
            pass
        try:
            co2_total_t += float(ep.get("CO2EmissionsTotal", 0)) / 1e3
        except (ValueError, TypeError):
            pass

        typ = str(gp.get("BuildingTypology", "unbekannt"))
        typology_counts[typ] = typology_counts.get(typ, 0) + 1

    print(f"\n  Gebäudetypologien (TABULA):")
    for typ, cnt in sorted(typology_counts.items(), key=lambda x: -x[1]):
        ratio = cnt / total if total else 0
        print(f"    {typ:<20} {_bar(ratio)} {cnt:>4} ({ratio*100:.0f}%)")

    print(f"\n  Energiebilanz Quartier (TABULA, Ist-Zustand):")
    print(f"    Heizwaermebedarf gesamt : {heat_total_gwh:.1f} GWh/a")
    print(f"    CO2-Emissionen gesamt   : {co2_total_t:.0f} t CO2/a")
    if total:
        print(f"    CO2 je Gebaeude (Mittel): {co2_total_t*1000/total:.0f} kg CO2/a")

    # ------------------------------------------------------------------
    # Bekannte Lücken
    # ------------------------------------------------------------------
    print(f"\n  Bekannte Luecken:")
    print(f"    - Fenster, Tueren, Innenraeume (erfordert LoD3+)")
    print(f"    - YearOfConstruction: nur OSM-start_date-Tag genutzt")
    print(f"    - Energiewerte: TABULA-Benchmarks (Ist-Zustand), kein Messdatenabgleich")

    elapsed = time.time() - t0
    print(f"\n  Verarbeitet in {elapsed:.2f}s")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    candidates = sorted((DATA_OUTPUT / "ifc").glob("*_LOD200*.ifc"))
    if not candidates:
        print("Keine LOD200-IFC-Datei gefunden. Phasen 1-4 zuerst ausführen.")
        sys.exit(1)
    evaluate(candidates[-1])