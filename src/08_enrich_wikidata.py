"""
Phase 8 – Wikidata-Anreicherung
Ruft für alle Gebäude mit bekannter Wikidata-ID strukturierte Metadaten ab:
  - Baujahr (P571 inception / P1619 date of official opening)
  - Architekt (P84 architect -> Label)
  - Architekturstil (P149 architectural style -> Label)
  - Offizieller Name (P1448 official name)
  - Denkmalstatus (P1435 heritage designation -> Label)
  - Anzahl Stockwerke (P1101 floors above ground)

Gibt diese Daten als Pset_WikidataInfo in eine neue IFC-Datei.

Quelle: Wikidata SPARQL Endpoint – query.wikidata.org
        (öffentlich, keine Authentifizierung nötig, CC0-Lizenz)
"""

import sys, json, time, urllib.request, urllib.parse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from configs.settings import IFC_LOD200, DATA_INTERIM

import geopandas as gpd
import ifcopenshell

SPARQL_URL   = "https://query.wikidata.org/sparql"
IFC_WIKIDATA = IFC_LOD200.parent / "georgsvorstadt_wikidata.ifc"

SPARQL_QUERY = """
SELECT ?item ?itemLabel
       (SAMPLE(?baujahr)        AS ?baujahr)
       (SAMPLE(?architektLabel) AS ?architekt)
       (SAMPLE(?stilLabel)      AS ?stil)
       (SAMPLE(?offName)        AS ?offiziellerName)
       (SAMPLE(?denkmalLabel)   AS ?denkmal)
       (SAMPLE(?stockwerke)     AS ?stockwerke)
WHERE {{
  VALUES ?item {{ {values} }}
  OPTIONAL {{ ?item wdt:P571  ?baujahr.  }}
  OPTIONAL {{ ?item wdt:P1619 ?baujahr.  }}
  OPTIONAL {{ ?item wdt:P84   ?architekt_.
              ?architekt_ rdfs:label ?architektLabel. FILTER(LANG(?architektLabel)="de") }}
  OPTIONAL {{ ?item wdt:P149  ?stil_.
              ?stil_ rdfs:label ?stilLabel.            FILTER(LANG(?stilLabel)="de")    }}
  OPTIONAL {{ ?item wdt:P1448 ?offName.               FILTER(LANG(?offName)="de")       }}
  OPTIONAL {{ ?item wdt:P1435 ?denkmal_.
              ?denkmal_ rdfs:label ?denkmalLabel.      FILTER(LANG(?denkmalLabel)="de") }}
  OPTIONAL {{ ?item wdt:P1101 ?stockwerke.             }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "de,en". }}
}}
GROUP BY ?item ?itemLabel
"""

BATCH_SIZE = 50   # SPARQL VALUES-Klausel pro Anfrage


def _guid():
    return ifcopenshell.guid.new()


def sparql_query(qids: list[str]) -> list[dict]:
    """Wikidata SPARQL für eine Liste von QIDs aufrufen."""
    values = " ".join(f"wd:{qid}" for qid in qids)
    query  = SPARQL_QUERY.format(values=values)
    data   = urllib.parse.urlencode({"query": query, "format": "json"}).encode()
    req    = urllib.request.Request(
        SPARQL_URL, data=data,
        headers={
            "User-Agent":   "DigitalTwinAugsburg/0.1 (github.com/mwollert; maxim.wollert@example.com)",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept":       "application/sparql-results+json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read())
    return result["results"]["bindings"]


def fetch_all_wikidata(qids: list[str]) -> dict[str, dict]:
    """Alle QIDs in Batches abfragen; gibt dict QID->Metadaten zurück."""
    lookup: dict[str, dict] = {}
    for i in range(0, len(qids), BATCH_SIZE):
        batch = qids[i : i + BATCH_SIZE]
        print(f"  SPARQL Batch {i//BATCH_SIZE + 1}: {len(batch)} QIDs …")
        try:
            rows = sparql_query(batch)
            for row in rows:
                qid = row["item"]["value"].split("/")[-1]
                lookup[qid] = {
                    "name":        row.get("itemLabel",       {}).get("value", ""),
                    "baujahr":     row.get("baujahr",         {}).get("value", "")[:4],  # ISO-Datum -> Jahr
                    "architekt":   row.get("architekt",       {}).get("value", ""),
                    "stil":        row.get("stil",            {}).get("value", ""),
                    "offiz_name":  row.get("offiziellerName", {}).get("value", ""),
                    "denkmal":     row.get("denkmal",         {}).get("value", ""),
                    "stockwerke":  row.get("stockwerke",      {}).get("value", ""),
                }
        except Exception as exc:
            print(f"    Fehler bei Batch {i//BATCH_SIZE + 1}: {exc}")
        time.sleep(1.0)   # Rate-Limit respektieren (Wikidata: 5 req/s)
    return lookup


def _add_pset(f, oh, building, name: str, props: dict):
    non_empty = {k: v for k, v in props.items() if v and str(v).strip()}
    if not non_empty:
        return
    pset = f.createIfcPropertySet(
        _guid(), oh, name, None,
        [f.createIfcPropertySingleValue(
            k, None, f.createIfcLabel(str(v)), None,
        ) for k, v in non_empty.items()],
    )
    f.createIfcRelDefinesByProperties(_guid(), oh, None, None, [building], pset)


def enrich_wikidata(ifc_path: Path, geojson_path: Path) -> None:
    gdf = gpd.read_file(geojson_path)

    # Alle QIDs aus GeoJSON sammeln (Spalte "wikidata")
    wikidata_col = "wikidata" if "wikidata" in gdf.columns else None
    if wikidata_col is None:
        print("  Keine wikidata-Spalte in GeoJSON – 01_fetch_data.py neu ausführen.")
        return

    qid_map: dict[str, list[int]] = {}   # QID -> Liste von GeoJSON-Indizes
    for idx, row in gdf.iterrows():
        qid = str(row.get("wikidata") or "").strip()
        if qid.startswith("Q"):
            qid_map.setdefault(qid, []).append(idx)

    print(f"  {len(qid_map)} eindeutige Wikidata-QIDs für {sum(len(v) for v in qid_map.values())} Gebäude")
    if not qid_map:
        print("  Keine Wikidata-IDs gefunden – übersprungen.")
        return

    # Wikidata abfragen
    lookup = fetch_all_wikidata(list(qid_map.keys()))
    print(f"  {len(lookup)}/{len(qid_map)} QIDs erfolgreich abgefragt")

    # Metadaten in GeoJSON schreiben (für 04_enrich_semantics.py)
    gdf["wd_baujahr"]   = ""
    gdf["wd_architekt"] = ""
    gdf["wd_stil"]      = ""
    gdf["wd_denkmal"]   = ""
    gdf["wd_name"]      = ""

    for qid, idxs in qid_map.items():
        meta = lookup.get(qid)
        if not meta:
            continue
        for idx in idxs:
            gdf.at[idx, "wd_baujahr"]   = meta["baujahr"]
            gdf.at[idx, "wd_architekt"] = meta["architekt"]
            gdf.at[idx, "wd_stil"]      = meta["stil"]
            gdf.at[idx, "wd_denkmal"]   = meta["denkmal"]
            gdf.at[idx, "wd_name"]      = meta["offiz_name"] or meta["name"]

    # Angereicherte GeoJSON-Datei speichern
    enriched_geojson = geojson_path.parent / "georgsvorstadt_clean_wikidata.geojson"
    gdf.to_file(enriched_geojson, driver="GeoJSON")
    print(f"  Angereicherte GeoJSON -> {enriched_geojson}")

    # In IFC-Datei schreiben
    f   = ifcopenshell.open(str(ifc_path))
    oh_list = f.by_type("IfcOwnerHistory")
    oh = oh_list[0] if oh_list else None

    name_map = {}
    for _, row in gdf.iterrows():
        key = str(row.get("name") or f"Gebaeude_{row.get('osm_id', '')}")
        name_map[key] = row

    written = 0
    year_fixes = 0
    for bldg in f.by_type("IfcBuilding"):
        row = name_map.get(bldg.Name)
        if row is None:
            continue

        wd_year  = str(row.get("wd_baujahr",   "") or "").strip()
        wd_arch  = str(row.get("wd_architekt", "") or "").strip()
        wd_stil  = str(row.get("wd_stil",      "") or "").strip()
        wd_name  = str(row.get("wd_name",      "") or "").strip()
        wd_denkm = str(row.get("wd_denkmal",   "") or "").strip()

        if not any([wd_year, wd_arch, wd_stil, wd_name, wd_denkm]):
            continue

        _add_pset(f, oh, bldg, "Pset_WikidataInfo", {
            "WikidataID":         str(row.get("wikidata", "")),
            "Baujahr_Wikidata":   wd_year,
            "Architekt":          wd_arch,
            "Architekturstil":    wd_stil,
            "OffizielerName":     wd_name,
            "Denkmalschutz":      wd_denkm,
        })
        written += 1
        if wd_year:
            year_fixes += 1

    # In LOD200-Hauptdatei schreiben (damit 05_evaluate.py Pset_WikidataInfo sieht)
    f.write(str(ifc_path))
    print(f"  {written} Gebaeude mit Wikidata-Pset erweitert -> {ifc_path}")
    print(f"  Baujahr-Ergaenzungen: {year_fixes} (vorher nur OSM start_date)")


if __name__ == "__main__":
    clean = DATA_INTERIM / "georgsvorstadt_clean.geojson"
    if not IFC_LOD200.exists():
        print("Zuerst 04_enrich_semantics.py ausführen.")
        sys.exit(1)
    if not clean.exists():
        print("Zuerst 02_preprocess_gis.py ausführen.")
        sys.exit(1)
    enrich_wikidata(IFC_LOD200, clean)
