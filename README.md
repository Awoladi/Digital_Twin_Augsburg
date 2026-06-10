# Digital Twin Augsburg – Georgsvorstadt

Automatisierter GIS→IFC-Workflow für das Quartier Georgsvorstadt (Augsburg, ca. 12 ha, ~2.140 Gebäude).
Open-Data-Quellen (BayernAtlas LoD2, ALKIS, OSM) werden vollautomatisch zu einem IFC 4 Digital Twin mit semantischen PropertySets und energetischen Kennwerten verarbeitet.

**Testquartier:** 48.363° N, 10.898° O · Blockrandbebauung 1880–1930 · Nutzung WA/MI/MK

---

## Entwicklungs-Timeline

### 2026-06-10 – Energetische Kennwerte, Versiegelungsgrad & Typologie (finale Abgabe)
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

## Workflow (6 Phasen)

```
BayernAtlas LoD2   ALKIS Nutzung   OpenStreetMap
      │                  │                │
      ▼                  │                ▼
[6] 06_parse_citygml.py  │    [1] 01_fetch_data.py
      │                  │                │
      └──────────────────┼────────────────┘
                         ▼
               [2] 02_preprocess_gis.py
                   Höhen: CityGML > OSM-Tag > Default
                         │
                         ▼
               [3] 03_generate_ifc.py
                   IfcProject > IfcSite > IfcBuilding >
                   IfcBuildingStorey > IfcBuildingElementProxy
                         │
                         ▼
               [4] 04_enrich_semantics.py
                   Pset_BuildingCommon  (ALKIS Nutzungsklasse)
                   Pset_EnergyConsumption
                   Pset_Georgsvorstadt  (GmlID, HeightSource, RoofType)
                         │
                         ▼
               [5] 05_evaluate.py
                   Qualitätsbericht
```

| Phase | Skript | Output |
|-------|--------|--------|
| 1 | `src/01_fetch_data.py` | `data/raw/osm/georgsvorstadt_osm_raw.json` |
| 2 | `src/02_preprocess_gis.py` | `data/interim/georgsvorstadt_clean.geojson` |
| 3 | `src/03_generate_ifc.py` | `data/output/ifc/georgsvorstadt_base.ifc` |
| 4 | `src/04_enrich_semantics.py` | `data/output/ifc/georgsvorstadt_LOD200.ifc` |
| 5 | `src/05_evaluate.py` | Bericht auf stdout |
| 6 | `src/06_parse_citygml.py` | `data/interim/georgsvorstadt_citygml.geojson` |

> Phase 6 vor Phase 2 ausführen, damit die amtlichen Höhen eingemergt werden.

---

## Aktueller Datenstand

| Datenquelle | Status | Gebäude | Anteil |
|-------------|--------|---------|--------|
| BayernAtlas LoD2 (amtlich) | integriert | 1.871 gematcht | **87%** |
| OSM-Tags (`height` / `levels`) | integriert | 171 | 8% |
| Default-Fallback (9,6 m) | – | 98 | 5% |
| ALKIS Nutzungsklasse | integriert | 2.140 / 2.140 | **100%** |

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
python src/01_fetch_data.py        # OSM-Daten holen
python src/02_preprocess_gis.py    # GIS bereinigen + Höhen mergen
python src/03_generate_ifc.py      # IFC generieren
python src/04_enrich_semantics.py  # Semantik ergänzen (ALKIS + PropertySets)
python src/05_evaluate.py          # Qualitätsbericht
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
| OpenStreetMap | Gebäudegrundrisse, Höhentags | GeoJSON (Overpass API) | automatisch via `01_fetch_data.py` | ✓ aktiv |
| BayernAtlas (LDBV) | LoD2 Gebäudemodelle, amtl. Höhen | CityGML | https://www.ldbv.bayern.de/produkte/3dgeo/3d_gebaeude.html | ✓ integriert |
| ALKIS Bayern | Nutzungsklassifikation | SHP | GDI-Bayern Portal | ✓ integriert |
| TABULA (IWU Darmstadt) | Gebäudetypologien, Energiekennwerte | Lookup-Tabelle | https://webtool.building-typology.eu | ✓ integriert |
| Bayerischer Energieatlas | Gemessener Energiebedarf je Quartier | CSV/WMS | https://www.energieatlas.bayern.de | offen – als Messdatenabgleich |

Rohdaten gehören nach `data/raw/citygml/` (BayernAtlas) bzw. `data/raw/alkis/` (ALKIS) — nicht versioniert.

---

## IFC-Klassenmodell

| IFC-Klasse / Pset | Attribute | Datenquelle | LOD |
|-------------------|-----------|-------------|-----|
| IfcProject | GlobalId, Name, UnitsInContext | – | 100 |
| IfcSite | RefLatitude, RefLongitude | OSM | 100 |
| IfcBuilding | Name, ObjectPlacement | OSM | 100 |
| IfcBuildingStorey | Elevation, Name | LoD2 / OSM | 100 |
| IfcBuildingElementProxy | Geometry (ExtrudedAreaSolid) | CityGML / OSM | 100 |
| Pset_BuildingCommon | NumberOfStoreys, YearOfConstruction, OccupancyType, GrossFloorArea | ALKIS / OSM | 200+ |
| Pset_EnergyConsumption | SpecificHeatDemand [kWh/(m²·a)], CO2Intensity [kg/(m²·a)], EnergyConsumptionHeating [kWh/a], CO2EmissionsTotal [kg/a], EnergyTypology, EnergyDataSource | TABULA IWU Darmstadt | Semantik |
| Pset_Georgsvorstadt | BuildingTypology, SealingRatio, CadastralID, GmlID, HeightSource, RoofType | ALKIS / CityGML / TABULA | Semantik |

---

## Projektstruktur

```
Digital_Twin_Augsburg/
├── configs/
│   └── settings.py              # BBox, CRS, alle Pfade
├── src/
│   ├── 01_fetch_data.py         # OSM via Overpass API
│   ├── 02_preprocess_gis.py     # Bereinigung + Höhen-Merge
│   ├── 03_generate_ifc.py       # IFC 4 Geometrie (LOD 100)
│   ├── 04_enrich_semantics.py   # PropertySets + ALKIS-Join
│   ├── 05_evaluate.py           # Qualitätsbericht
│   └── 06_parse_citygml.py      # BayernAtlas LoD2 Parser
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