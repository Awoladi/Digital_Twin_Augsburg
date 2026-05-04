"""
Phase 5 – Bewertung & Dokumentation
Checks completeness of the enriched IFC model and prints a quality report
including height distribution and attribute fill rates.
"""

import sys, time, statistics
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from configs.settings import DATA_OUTPUT, DATA_INTERIM, DEFAULT_STOREYS, DEFAULT_STOREY_HEIGHT

import ifcopenshell
import ifcopenshell.util.element as ifc_util

REQUIRED_PSETS = {
    "Pset_BuildingCommon": ["NumberOfStoreys", "YearOfConstruction", "OccupancyType", "GrossFloorArea"],
    "Pset_Georgsvorstadt": ["BuildingTypology", "CadastralID"],
}

DEFAULT_HEIGHT = DEFAULT_STOREYS * DEFAULT_STOREY_HEIGHT  # 9.6 m


def _bar(ratio: float, width: int = 20) -> str:
    filled = round(ratio * width)
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def evaluate(ifc_path: Path) -> None:
    t0        = time.time()
    f         = ifcopenshell.open(str(ifc_path))
    buildings = f.by_type("IfcBuilding")
    total     = len(buildings)

    print(f"\n{'='*55}")
    print(f"  IFC Quality Report: {ifc_path.name}")
    print(f"{'='*55}")
    print(f"  IfcBuilding entities : {total}")

    # ------------------------------------------------------------------
    # Height distribution via IfcBuildingElementProxy extents
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
        print(f"\n  Height distribution ({len(heights)} proxies):")
        print(f"    min     : {min(heights):.1f} m")
        print(f"    max     : {max(heights):.1f} m")
        print(f"    mean    : {statistics.mean(heights):.1f} m")
        print(f"    median  : {statistics.median(heights):.1f} m")
        print(f"    fallback: {default_count} ({default_count/len(heights)*100:.0f}%) "
              f"used default {DEFAULT_HEIGHT} m  <- no OSM height tag")

    # ------------------------------------------------------------------
    # PropertySet coverage
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

    print(f"\n  PropertySet coverage:")
    for pset_name, count in pset_hits.items():
        ratio = count / total if total else 0
        print(f"    {pset_name:<30} {_bar(ratio)} {count}/{total} ({ratio*100:.0f}%)")

    print(f"\n  Attribute fill rate (excl. n/a / unbekannt):")
    for pset_name, attrs in REQUIRED_PSETS.items():
        for attr in attrs:
            key   = f"{pset_name}.{attr}"
            count = attr_hits.get(key, 0)
            ratio = count / total if total else 0
            print(f"    {key:<48} {count:>4}/{total} ({ratio*100:.0f}%)")

    # ------------------------------------------------------------------
    # Known limitations
    # ------------------------------------------------------------------
    print(f"\n  Known gaps:")
    print(f"    - Roof geometry (LoD2 CityGML not yet integrated)")
    print(f"    - Windows, doors, interior spaces (requires LoD3+)")
    print(f"    - YearOfConstruction: only OSM start_date tag used")
    print(f"    - EnergyConsumption: placeholder, needs Energieatlas Bayern")

    elapsed = time.time() - t0
    print(f"\n  Processed in {elapsed:.2f}s")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    candidates = sorted((DATA_OUTPUT / "ifc").glob("*_LOD200*.ifc"))
    if not candidates:
        print("No LOD200 IFC file found. Run phases 1-4 first.")
        sys.exit(1)
    evaluate(candidates[-1])