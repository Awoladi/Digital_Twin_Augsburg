# Digital Twin Augsburg – Georgsvorstadt

Automatisierter GIS→IFC-Workflow für das Quartier Georgsvorstadt (Augsburg, ca. 12 ha, ~2.140 Gebäude).
Open-Data-Quellen (BayernAtlas LoD2, ALKIS, OSM) werden vollautomatisch zu einem IFC 4 Digital Twin mit semantischen PropertySets und energetischen Kennwerten verarbeitet.

**Testquartier:** 48.363° N, 10.898° O · Blockrandbebauung 1880–1930 · Nutzung WA/MI/MK

---

## Entwicklungs-Timeline

### 2026-06-10 – Maximale Open-Data-Ausschöpfung (finale Abgabe)

**Neue Datenquellen vollständig integriert (alles öffentlich zugänglich, keine Registrierung):**
- **PVGIS 5.3 SARAH-3 (EU JRC):** Solarpotenzial für alle 2.139 Gebäude — `Pset_SolarPotential` mit PV-Ertrag, Solarthermie, Globalstrahlung; Quartierspotenzial **35.820 MWh/a PV**
- **Wikidata SPARQL:** 296 Gebäude mit QIDs → Baujahr, Architekt, Architekturstil, Denkmalstatus aus strukturierten Daten; **5 neue Baujahre** ergänzt
- **OSM Extended Tags (30+ Attribute):** Adressen (1.325 Gebäude, 62%), BLfD-Denkmalnummern (73 Gebäude), Dachform (939), Farbe/Material/Architekt (237)
- **`Pset_Adresse`:** Straße, Hausnummer, PLZ, Stadt aus OSM `addr:*`-Tags
- **`Pset_Denkmalschutz`:** BLfD-Referenz, Schutzumfang für alle 73 Baudenkmäler
- **`Pset_Gebaeudebeschreibung`:** Fassadenfarbe, Material, Architekturstil, Architekt
- **Dachform-Abdeckung:** 96% aller Gebäude (OSM `roof:shape` Fallback für 178 Gebäude ohne CityGML-Dachtyp)
- **Neue Pipeline-Phasen:** `07_enrich_solar.py` (PVGIS) + `08_enrich_wikidata.py` (Wikidata SPARQL)

### 2026-06-10 – Energetische Kennwerte, Versiegelungsgrad & Typologie
- **`04_enrich_semantics.py` vollständig überarbeitet:**
  - **TABULA-Energiewerte** (IWU Darmstadt, Ist-Zustand): `SpecificHeatDemand`, `CO2Intensity`, `EnergyConsumptionHeating`, `CO2EmissionsTotal` — alle 2.140 Gebäude mit echten Werten (statt Platzhaltern)
  - **Versiegelungsgrad je Gebäude** (`SealingRatio`) aus ALKIS-Nutzungsart (BauNVO-Richtwerte): WA=0.65 · MI=0.80 · Gewerbe=0.90 · Sondergebiet=0.75 statt globalem Fixwert 0.72
  - **TABULA-Mapping korrigiert**: deckt jetzt alle echten ALKIS-`nutzart`-Werte ab (`Wohnbaufläche` → MFH_1918_DE, `Fläche gemischter Nutzung` → MFH_1960_DE, etc.)
  - **Quartiersbilanz**: 325,6 GWh/a Heizwärmebedarf · 76.740 t CO2/a
- **`05_evaluate.py` erweitert**: Typologieverteilung, Energiebilanz-Zusammenfassung im Qualitätsbericht
- Alle Kommentare, Docstrings und Ausgaben auf Deutsch; Dachtyp-Codes in Klartextnamen übersetzt

### 2026-05-04 – BayernAtlas LoD2 & ALKIS integriert
- **`06_parse_citygml.py` (neu):** Parst LoD2-GML-Kacheln des BayernAtlas, extrahiert amtliche Gebäudehöhen (`NiedrigsteTraufe − HoeheGrund`), Grundrisse und Dachtypen; Clip auf Georgsvorstadt-BBox in metrischem CRS; **2.104 Gebäude mit offiziellen Höhen**
- **`02_preprocess_gis.py` erweitert:** Dreistufige Höhenpriorität — CityGML (87%) → OSM-Tag (8%) → Default-Fallback (5%); Nearest-Join mit max. 30 m Toleranz in EPSG:25832
- **`04_enrich_semantics.py` erweitert:** Spatial Join mit ALKIS `Nutzung.shp` → alle 2.140 Gebäude erhalten amtliche Nutzungsklasse (`nutzart`); `Pset_Georgsvorstadt` um `HeightSource`, `GmlID`, `RoofType` erweitert
- Fix `IndexError` bei fehlendem `IfcOwnerHistory` (ifcopenshell API erstellt keine mehr)

### 2026-05-04 – Bugfixes, Qualitätsbericht & Notebook
- Fix doppelter IFC-Dateiname: Phase 3 → `georgsvorstadt_base.ifc`, Phase 4 → `georgsvorstadt_LOD200.ifc`
- Fix `GrossFloorArea`: GeoDataFrame auf EPSG:25832 projiziert vor `.area`
- `05_evaluate.py` ausgebaut: Höhenverteilung, Fallback-Zähler, ASCII-Fortschrittsbalken
- `notebooks/01_explore_georgsvorstadt.ipynb` erstellt und ausgeführt

### 2026-05-02 – Pipeline debuggt & erstmals durchgelaufen
- **Phase 1:** Overpass-API HTTP 406 gefixt (fehlender `User-Agent`); 2.140 OSM-Gebäude geladen
- **Phase 3:** IFC-Hierarchie korrigiert — Geometrie von `IfcBuilding` auf `IfcBuildingElementProxy` verschoben; BlenderBIM rendert jetzt korrekt
- IFC-Modell in BlenderBIM verifiziert

### 2026-05-02 – Projektstart & Grundstruktur
- 5-Phasen-Workflow konzipiert, Verzeichnisstruktur angelegt, alle Skripte erstellt
- Repository auf GitHub veröffentlicht

---

## Workflow (8 Phasen)

```
BayernAtlas LoD2   ALKIS Nutzung   OpenStreetMap   PVGIS (EU JRC)   Wikidata SPARQL
      │                  │                │                │                 │
      ▼                  │                ▼                │                 │
[6] 06_parse_citygml.py  │    [1] 01_fetch_data.py         │                 │
      │                  │                │                │                 │
      └──────────────────┼────────────────┘                │                 │
                         ▼                                 │                 │
               [2] 02_preprocess_gis.py                    │                 │
                   Höhen: CityGML > OSM-Tag > Default      │                 │
                   Dachform: CityGML + OSM-Fallback (96%)  │                 │
                         │                                 │                 │
                         ▼                                 │                 │
               [3] 03_generate_ifc.py                      │                 │
                   IfcProject > IfcSite > IfcBuilding      │                 │
                   LoD2 FacetedBrep (87%) + Box (13%)      │                 │
                         │                                 │                 │
                         ▼                                 │                 │
               [4] 04_enrich_semantics.py                  │                 │
                   Pset_BuildingCommon · EnergyConsumption  │                 │
                   Pset_Georgsvorstadt · Pset_Adresse       │                 │
                   Pset_Denkmalschutz · Pset_Gebaeudebeschr.│                 │
                         │                                 │                 │
                    ┌────┴────┐                            │                 │
                    ▼         ▼                            ▼                 ▼
          [7] 07_enrich_solar.py              [8] 08_enrich_wikidata.py
              Pset_SolarPotential                 Pset_WikidataInfo
              (PVGIS SARAH-3, alle 2139)          (296 Gebäude mit QID)
                    └────┬────┘
                         ▼
               [5] 05_evaluate.py
                   Qualitätsbericht (8 Psets)
```

| Phase | Skript | Output |
|-------|--------|--------|
| 1 | `src/01_fetch_data.py` | `data/raw/osm/georgsvorstadt_osm_raw.json` |
| 2 | `src/02_preprocess_gis.py` | `data/interim/georgsvorstadt_clean.geojson` |
| 3 | `src/03_generate_ifc.py` | `data/output/ifc/georgsvorstadt_base.ifc` |
| 4 | `src/04_enrich_semantics.py` | `data/output/ifc/georgsvorstadt_LOD200.ifc` |
| 5 | `src/05_evaluate.py` | Qualitätsbericht auf stdout |
| 6 | `src/06_parse_citygml.py` | `data/interim/georgsvorstadt_citygml.geojson` |
| 7 | `src/07_enrich_solar.py` | `georgsvorstadt_LOD200.ifc` + `Pset_SolarPotential` |
| 8 | `src/08_enrich_wikidata.py` | `georgsvorstadt_LOD200.ifc` + `Pset_WikidataInfo` |

> Phase 6 vor Phase 2 ausführen. Phasen 7+8 nach Phase 4 für alle Open-Data-Quellen.

---

## Aktueller Datenstand

| Datenquelle | Status | Gebäude | Anteil |
|-------------|--------|---------|--------|
| BayernAtlas LoD2 (amtlich, Höhen + Geometrie) | integriert | 1.870 | **87%** |
| OSM-Tags (`height` / `levels`) | integriert | 171 | 8% |
| Default-Fallback (9,6 m) | – | 98 | 5% |
| ALKIS Nutzungsklasse | integriert | 2.139 / 2.139 | **100%** |
| OSM Adressen (`addr:*`) | integriert | 1.333 | **62%** |
| PVGIS Solarpotenzial (EU JRC SARAH-3) | integriert | 2.139 | **100%** |
| OSM Dachform (`roof:shape`) | integriert | 939 als Fallback | 44% OSM + 87% CityGML = **96%** gesamt |
| OSM Denkmalschutz (BLfD via `ref:BLfD`) | integriert | 73 | 3% |
| Wikidata SPARQL (Baujahr, Architekt, Stil) | integriert | 296 | 14% |
| OSM Farbe / Material / Architektur | integriert | 237 | 11% |

### Energetische Kennwerte (TABULA, Ist-Zustand unsaniert)

| Typologie | Gebäude | Anteil | Heizwärmebedarf | CO2-Intensität |
|-----------|---------|--------|-----------------|----------------|
| MFH_1918_DE (Gründerzeit) | 951 | 44% | 220 kWh/(m²·a) | 52 kg CO2/(m²·a) |
| MFH_1960_DE (Nachkrieg/Mischnutzung) | 723 | 34% | 160 kWh/(m²·a) | 38 kg CO2/(m²·a) |
| NWG_1970_DE (Gewerbe/öffentlich) | 466 | 22% | 120 kWh/(m²·a) | 28 kg CO2/(m²·a) |
| **Quartier gesamt** | **2.140** | – | **325,6 GWh/a** | **76.740 t CO2/a** |

> Quelle: TABULA-Webtool, IWU Darmstadt – webtool.building-typology.eu · Ist-Zustand (unsaniert)

### Versiegelungsgrad je ALKIS-Nutzungsart (BauNVO-Richtwerte)

| ALKIS-Nutzungsart | Gebäude | SealingRatio |
|-------------------|---------|--------------|
| Wohnbaufläche | 951 | 0,65 |
| Fläche gemischter Nutzung | 719 | 0,80 |
| Industrie-/Gewerbefläche | 224 | 0,90 |
| Fläche besonderer funktionaler Prägung | 180 | 0,75 |
| Sonstige (Verkehr, Sport, Friedhof) | 66 | 0,30–0,95 |

---

## Installation

```bash
pip install -r requirements.txt
```

> `ifcopenshell` alternativ via conda:
> ```bash
> conda install -c ifcopenshell ifcopenshell
> ```

## Ausführung

```bash
python src/06_parse_citygml.py     # BayernAtlas LoD2 parsen (einmalig)
python src/01_fetch_data.py        # OSM-Daten holen (30+ Tags)
python src/02_preprocess_gis.py    # GIS bereinigen + Höhen + Dachform
python src/03_generate_ifc.py      # IFC-Geometrie erzeugen
python src/04_enrich_semantics.py  # Semantik (ALKIS, Adresse, Denkmal, ...)
python src/07_enrich_solar.py      # Solarpotenzial via PVGIS (EU JRC)
python src/08_enrich_wikidata.py   # Wikidata-Metadaten (Baujahr, Architekt, ...)
python src/05_evaluate.py          # Qualitätsbericht (8 Psets)
```

---

## IFC-Modell anschauen

Die aktuelle IFC-Datei ist `data/output/ifc/georgsvorstadt_LOD200.ifc`.

- **BlenderBIM** (empfohlen): `File → Open IFC Project` → `georgsvorstadt_LOD200.ifc`
- **FZKViewer** (KIT): IFC-Datei reinziehen, keine Konfiguration nötig
- **Online**: Autodesk Viewer (viewer.autodesk.com)

---

## Datenquellen

| Quelle | Inhalt | Format | Bezug | Status |
|--------|--------|--------|-------|--------|
| OpenStreetMap | Grundrisse, Höhen, Adressen, Dachform, BLfD, Wikidata (30+ Tags) | GeoJSON (Overpass API) | automatisch via `01_fetch_data.py` | ✓ aktiv |
| BayernAtlas (LDBV) | LoD2 Gebäudemodelle, amtl. Höhen, Dachtypen | CityGML | ldbv.bayern.de/3d_gebaeude | ✓ integriert |
| ALKIS Bayern | Nutzungsklassifikation (Flurstücke) | SHP | GDI-Bayern Portal | ✓ integriert |
| TABULA (IWU Darmstadt) | Gebäudetypologien, Energiekennwerte | Lookup-Tabelle | webtool.building-typology.eu | ✓ integriert |
| PVGIS 5.3 SARAH-3 (EU JRC) | Solarpotenzial, Globalstrahlung | REST-API | re.jrc.ec.europa.eu | ✓ integriert |
| Wikidata SPARQL | Baujahr, Architekt, Architekturstil, Denkmalstatus | SPARQL (CC0) | query.wikidata.org | ✓ integriert (296 Gebäude) |
| Bayerischer Energieatlas | Gemessener Energiebedarf je Quartier | CSV/WMS | energieatlas.bayern.de | offen – Messdatenabgleich |

Rohdaten gehören nach `data/raw/citygml/` (BayernAtlas) bzw. `data/raw/alkis/` (ALKIS) — nicht versioniert.

---

## IFC-Klassenmodell

| IFC-Klasse / Pset | Attribute | Datenquelle | Abdeckung |
|-------------------|-----------|-------------|-----------|
| IfcProject | GlobalId, Name, UnitsInContext | – | 100% |
| IfcSite | RefLatitude, RefLongitude | OSM | 100% |
| IfcBuilding | Name, ObjectPlacement | OSM | 100% |
| IfcBuildingStorey | Elevation, Name | LoD2 / OSM | 100% |
| IfcBuildingElementProxy | LoD2 FacetedBrep / LoD100 Box | CityGML / OSM | 100% |
| Pset_BuildingCommon | NumberOfStoreys, YearOfConstruction, OccupancyType, GrossFloorArea | ALKIS / OSM / Wikidata | **100%** |
| Pset_EnergyConsumption | SpecificHeatDemand, CO2Intensity, EnergyConsumptionHeating, CO2EmissionsTotal, EnergyTypology | TABULA IWU Darmstadt | **100%** |
| Pset_Georgsvorstadt | BuildingTypology, SealingRatio, CadastralID, GmlID, HeightSource, RoofType | ALKIS / CityGML / TABULA | **100%** |
| Pset_SolarPotential | SolarIrradiation_kWh_m2a, RoofArea_m2, PV_Yield_kWh_a, SolarThermal_kWh_a | PVGIS 5.3 EU JRC | **100%** |
| Pset_Adresse | Strasse, Hausnummer, Postleitzahl, Stadt | OSM addr:* | **62%** (1.333) |
| Pset_WikidataInfo | WikidataID, Baujahr_Wikidata, Architekt, Architekturstil, Denkmalschutz | Wikidata SPARQL | **14%** (296) |
| Pset_Denkmalschutz | BLfD_Referenz, Schutzumfang, IstDenkmalgeschuetzt | BLfD via OSM ref:BLfD | **3%** (73) |
| Pset_Gebaeudebeschreibung | Fassadenfarbe, Fassadenmaterial, Architekturstil, Architekt, Dachfarbe | OSM building:colour, material | **11%** (237) |

---

## Projektstruktur

```
Digital_Twin_Augsburg/
├── configs/
│   └── settings.py              # BBox, CRS, alle Pfade
├── src/
│   ├── 01_fetch_data.py         # OSM via Overpass API (30+ Tags)
│   ├── 02_preprocess_gis.py     # Bereinigung + Höhen + Dachform-Fallback
│   ├── 03_generate_ifc.py       # IFC 4 Geometrie (LoD2 FacetedBrep / LoD100 Box)
│   ├── 04_enrich_semantics.py   # Pset_BuildingCommon + Energy + Adresse + Denkmal
│   ├── 05_evaluate.py           # Qualitätsbericht (8 Psets)
│   ├── 06_parse_citygml.py      # BayernAtlas LoD2 Parser
│   ├── 07_enrich_solar.py       # Solarpotenzial via PVGIS EU JRC (alle 2139 Gebäude)
│   └── 08_enrich_wikidata.py    # Wikidata SPARQL (Baujahr, Architekt, Stil)
├── data/
│   ├── raw/                     # Rohdaten (nicht versioniert)
│   │   ├── citygml/             # BayernAtlas LoD2 .gml Kacheln
│   │   ├── alkis/               # ALKIS Nutzung.shp
│   │   └── osm/                 # automatisch via Phase 1
│   ├── interim/                 # bereinigtes GeoJSON, CityGML-GeoJSON
│   └── output/ifc/              # georgsvorstadt_base.ifc, georgsvorstadt_LOD200.ifc
├── notebooks/
│   └── 01_explore_georgsvorstadt.ipynb
├── requirements.txt
└── README.md
```

---

## Skalierbarkeit auf ganz Augsburg

Die Pipeline ist vollständig skalierbar — der Untersuchungsbereich ist über eine einzige Variable steuerbar:

```python
# configs/settings.py – BBOX anpassen für ganz Augsburg:
BBOX = {
    "min_lon": 10.820,  "min_lat": 48.310,
    "max_lon": 11.000,  "max_lat": 48.430,
}
```

Weitere CityGML-Kacheln des BayernAtlas (kostenlos über geodaten.bayern.de) in `data/raw/citygml/` ablegen — Phase 6 verarbeitet alle `.gml`-Dateien automatisch. Augsburg umfasst ca. 75.000 Gebäude; Rechenzeit schätzungsweise 10–15 Minuten.

**Offene Datenlücken:**
- **Flurstücksnummern** (CadastralID): aktuell OSM-IDs; amtliche Flurstückskennzeichen via ALKIS-Flurstück-WFS der Bayerischen Vermessungsverwaltung nachrüstbar
- **YearOfConstruction**: nur 3% der Gebäude haben OSM-`start_date`-Tags; Gebäudealter aus ALKIS-Gebäudeumriss-Daten (Basiskarte) erweiterbar
- **Energiemessdaten**: TABULA-Benchmarks sind Typologiemittelwerte; Abgleich mit Energieatlas Bayern für gemessene Verbräuche empfohlen

---

## Technologien

- **Python** · GeoPandas · IfcOpenShell · Shapely · PyProj
- **BlenderBIM** (IFC-Visualisierung & Qualitätskontrolle)
- **QGIS** (optional, für manuelle GIS-Schritte)

---

## Quellen & Literatur

### Wissenschaftliche Literatur

| Quelle | Verwendung im Projekt |
|--------|------------------------|
| Kritzinger, W.; Karner, M.; Traar, G.; Henjes, J.; Sihn, W. (2018): *Digital Twin in manufacturing: A categorical literature review and classification.* IFAC-PapersOnLine 51(11), S. 1016–1022. | Begriffliche Grundlage für die Einordnung des Projekts als **Digital Shadow** (automatisierter, einseitiger Datenfluss physisch → digital) statt Digital Twin (bidirektional, mit Rückkopplung); Basis der Vergleichskriterien auf Folie „Ist das ein Digital Twin?" |
| Loga, T.; Stein, B.; Diefenbach, N. (IWU Darmstadt): **TABULA/EPISCOPE Gebäudetypologie** – webtool.building-typology.eu | Energiekennwerte (Heizwärmebedarf, CO2-Intensität) je Gebäudetypologie, Ist-Zustand unsaniert |
| Huld, T.; Müller, R.; Gambardella, A. (2012): *A new solar radiation database for estimating PV performance in Europe and Africa.* Solar Energy 86(6), S. 1803–1815. | Methodische Grundlage des PVGIS-SARAH-Datensatzes (Satelliten-basierte Globalstrahlung) |
| BauNVO (Baunutzungsverordnung), Bundesministerium der Justiz | Richtwerte für Versiegelungsgrad (GRZ) je Nutzungsart (WA, MI, Gewerbe, Sondergebiet) |

### Daten- & API-Quellen

| Quelle | Inhalt | Format / Zugang | Betreiber |
|--------|--------|------------------|-----------|
| OpenStreetMap (Overpass API) | Grundrisse, Höhen, Adressen, Dachform, BLfD-Referenzen, Wikidata-Links (30+ Tags) | GeoJSON, REST | OSM-Foundation, CC-BY-SA |
| BayernAtlas / LDBV (Landesamt für Digitalisierung, Breitband und Vermessung) | LoD2-Gebäudemodelle, amtliche Höhen, Dachtypen | CityGML, ldbv.bayern.de/3d_gebaeude | Freistaat Bayern |
| ALKIS Bayern (GDI-Bayern) | Amtliche Nutzungsklassifikation (Flurstücke) | Shapefile, geodaten.bayern.de | Bayerische Vermessungsverwaltung |
| TABULA-Webtool (IWU Darmstadt) | Gebäudetypologien, Energiekennwerte | Lookup-Tabelle, webtool.building-typology.eu | Institut Wohnen und Umwelt |
| PVGIS 5.3 SARAH-3 (EU Joint Research Centre) | Solarpotenzial, Globalstrahlung, PV-Ertrag pro kWp | REST-API, re.jrc.ec.europa.eu | Europäische Kommission (JRC) |
| Wikidata (SPARQL-Endpoint) | Baujahr, Architekt, Architekturstil, Denkmalstatus | SPARQL, CC0, query.wikidata.org | Wikimedia Foundation |
| DWD-Klimareferenz Augsburg | Fallback-Solarertrag (950 kWh/kWp/a) bei PVGIS-API-Fehler | statischer Referenzwert | Deutscher Wetterdienst |
| Bayerischer Energieatlas | Gemessener Energiebedarf je Quartier (für Validierung vorgesehen, noch nicht integriert) | CSV/WMS, energieatlas.bayern.de | Bayerisches Wirtschaftsministerium |

Alle Datenquellen sind frei zugänglich (Open Data), ohne Registrierung oder Kosten nutzbar.