"""
Phase 1 – Datenbeschaffung
Lädt OSM-Gebäudegrundrisse für die Georgsvorstadt über die Overpass API.
Extrahiert alle relevanten Tags: Adressen, Dachdetails, Denkmalschutz (BLfD),
Wikidata-Verknüpfungen, Farben, Materialien, Architekt.
BayernAtlas (LoD2) und ALKIS müssen manuell heruntergeladen werden – siehe README.
"""

import json
import urllib.request
import urllib.parse
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from configs.settings import BBOX, OSM_DIR, BUILDINGS_GEOJSON

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

OVERPASS_QUERY = f"""
[out:json][timeout:60];
(
  way["building"]
    ({BBOX['min_lat']},{BBOX['min_lon']},{BBOX['max_lat']},{BBOX['max_lon']});
  relation["building"]
    ({BBOX['min_lat']},{BBOX['min_lon']},{BBOX['max_lat']},{BBOX['max_lon']});
);
out body;
>;
out skel qt;
"""


def fetch_osm_buildings() -> dict:
    data = urllib.parse.urlencode({"data": OVERPASS_QUERY}).encode()
    req  = urllib.request.Request(OVERPASS_URL, data=data, headers={
        "User-Agent":   "DigitalTwinAugsburg/0.1",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept":       "application/json",
    })
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read())


def osm_to_geojson(osm: dict) -> dict:
    nodes = {n["id"]: (n["lon"], n["lat"]) for n in osm["elements"] if n["type"] == "node"}
    features = []
    for el in osm["elements"]:
        if el["type"] != "way" or "nodes" not in el:
            continue
        coords = [nodes[nid] for nid in el["nodes"] if nid in nodes]
        if len(coords) < 4:
            continue
        tags = el.get("tags", {})
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [coords]},
            "properties": {
                # --- Basis ---
                "osm_id":     el["id"],
                "name":       tags.get("name", ""),
                "building":   tags.get("building", "yes"),
                "levels":     tags.get("building:levels", ""),
                "height":     tags.get("height", ""),
                "start_date": tags.get("start_date", ""),
                # --- Adresse (OSM addr:* Tags – 62% der Gebäude) ---
                "addr_street":      tags.get("addr:street", ""),
                "addr_housenumber": tags.get("addr:housenumber", ""),
                "addr_postcode":    tags.get("addr:postcode", ""),
                "addr_city":        tags.get("addr:city", ""),
                # --- Dachdetails (OSM – ergänzt CityGML) ---
                "osm_roof_shape":       tags.get("roof:shape", ""),
                "osm_roof_colour":      tags.get("roof:colour", ""),
                "osm_roof_material":    tags.get("roof:material", ""),
                "osm_roof_levels":      tags.get("roof:levels", ""),
                "osm_roof_orientation": tags.get("roof:orientation", ""),
                "osm_roof_direction":   tags.get("roof:direction", ""),
                "osm_roof_height":      tags.get("roof:height", ""),
                # --- Gebäudedetails ---
                "building_colour":       tags.get("building:colour", ""),
                "building_material":     tags.get("building:material", ""),
                "building_architecture": tags.get("building:architecture", ""),
                # --- Denkmalschutz (BLfD – Bayerisches Landesamt für Denkmalpflege) ---
                "heritage":          tags.get("heritage", ""),
                "heritage_operator": tags.get("heritage:operator", ""),
                "ref_blfd":          tags.get("ref:BLfD", ""),
                "blfd_criteria":     tags.get("BLfD:criteria", ""),
                # --- Verknüpfungen zu externen Datenbanken ---
                "wikidata":  tags.get("wikidata", ""),
                "wikipedia": tags.get("wikipedia", ""),
                "architect": tags.get("architect", ""),
                # --- Nutzungsdetails ---
                "amenity":  tags.get("amenity", ""),
                "historic": tags.get("historic", ""),
                "tourism":  tags.get("tourism", ""),
                "religion": tags.get("religion", ""),
                "operator": tags.get("operator", ""),
            },
        })
    return {"type": "FeatureCollection", "features": features}


if __name__ == "__main__":
    print("Lade OSM-Gebäude für die Georgsvorstadt …")
    osm  = fetch_osm_buildings()
    gj   = osm_to_geojson(osm)

    OSM_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = OSM_DIR / "georgsvorstadt_osm_raw.json"
    raw_path.write_text(json.dumps(osm, ensure_ascii=False, indent=2), encoding="utf-8")

    BUILDINGS_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    BUILDINGS_GEOJSON.write_text(json.dumps(gj, ensure_ascii=False, indent=2), encoding="utf-8")

    # Statistik
    addr  = sum(1 for f in gj["features"] if f["properties"].get("addr_street"))
    denkm = sum(1 for f in gj["features"] if f["properties"].get("ref_blfd"))
    wiki  = sum(1 for f in gj["features"] if f["properties"].get("wikidata"))
    roof  = sum(1 for f in gj["features"] if f["properties"].get("osm_roof_shape"))
    total = len(gj["features"])
    print(f"  {total} Gebäude gespeichert -> {BUILDINGS_GEOJSON}")
    print(f"  Adressen          : {addr}/{total} ({addr/total*100:.0f}%)")
    print(f"  Denkmalschutz     : {denkm}/{total} ({denkm/total*100:.0f}%)")
    print(f"  Wikidata-Links    : {wiki}/{total} ({wiki/total*100:.0f}%)")
    print(f"  Dachform (OSM)    : {roof}/{total} ({roof/total*100:.0f}%)")
