"""
Phase 5 – Bewertung & Dokumentation
Checks completeness of the enriched IFC model and prints a report.
"""

import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from configs.settings import DATA_OUTPUT

import ifcopenshell
import ifcopenshell.util.element as ifc_util

REQUIRED_PSETS = {
    "Pset_BuildingCommon":  ["NumberOfStoreys", "YearOfConstruction", "OccupancyType"],
    "Pset_Georgsvorstadt":  ["BuildingTypology", "CadastralID"],
}


def evaluate(ifc_path: Path) -> None:
    t0 = time.time()
    f  = ifcopenshell.open(str(ifc_path))
    buildings = f.by_type("IfcBuilding")
    total = len(buildings)
    print(f"\n=== IFC Quality Report: {ifc_path.name} ===")
    print(f"Total IfcBuilding entities : {total}")

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

    print("\nPropertySet coverage:")
    for pset_name, count in pset_hits.items():
        pct = count / total * 100 if total else 0
        print(f"  {pset_name:<30} {count:>4}/{total}  ({pct:.0f}%)")

    print("\nAttribute fill rate (excluding n/a and 'unbekannt'):")
    for pset_name, attrs in REQUIRED_PSETS.items():
        for attr in attrs:
            key   = f"{pset_name}.{attr}"
            count = attr_hits.get(key, 0)
            pct   = count / total * 100 if total else 0
            print(f"  {key:<45} {count:>4}/{total}  ({pct:.0f}%)")

    elapsed = time.time() - t0
    print(f"\nProcessed in {elapsed:.2f}s")
    print("Known gaps: roof geometry, windows, doors, interior spaces")


if __name__ == "__main__":
    candidates = sorted((DATA_OUTPUT / "ifc").glob("*_LOD200.ifc"))
    if not candidates:
        print("No LOD200 IFC file found. Run phases 1–4 first.")
        sys.exit(1)
    evaluate(candidates[-1])
