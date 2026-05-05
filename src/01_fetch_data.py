"""
Phase 1 – Datenbeschaffung
Lädt OSM-Gebäudegrundrisse für die Georgsvorstadt über die Overpass API.
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
                "osm_id":     el["id"],
                "name":       tags.get("name", ""),
                "building":   tags.get("building", "yes"),
                "levels":     tags.get("building:levels", ""),
                "height":     tags.get("height", ""),
                "start_date": tags.get("start_date", ""),
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

    print(f"  {len(gj['features'])} Gebäude gespeichert -> {BUILDINGS_GEOJSON}")
