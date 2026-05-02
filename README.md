# Digital Twin Augsburg – Georgsvorstadt

Automatisierter GIS→IFC-Workflow für das Quartier Georgsvorstadt (Augsburg, ca. 12 ha, ~380 Gebäude).
Open-Data-Quellen (BayernAtlas LoD2, ALKIS, OSM) werden vollautomatisch zu einem IFC 4 Digital Twin mit semantischen PropertySets verarbeitet.

**Testquartier:** 48.363° N, 10.898° O · Blockrandbebauung 1880–1930 · Nutzung WA/MI/MK

---

## Entwicklungs-Timeline

### 2026-05-02 – Projektstart & Grundstruktur
- Projektkonzept definiert: 5-Phasen-Workflow GIS → IFC auf Basis von Open Data
- Verzeichnisstruktur angelegt (`src/`, `data/raw/`, `data/interim/`, `data/output/ifc/`)
- Alle fünf Pipeline-Skripte erstellt (Phasen 1–5)
- `configs/settings.py` mit BBox Georgsvorstadt, CRS und Pfaden
- Repository auf GitHub veröffentlicht

### 2026-05-02 – Pipeline debuggt & erstmals durchgelaufen
- **Phase 1 (`01_fetch_data.py`):** Overpass-API-Request repariert (fehlender `User-Agent`-Header → HTTP 406); Unicode-Ausgabe für Windows-Konsole gefixt
- **Phase 2 (`02_preprocess_gis.py`):** 2 140 Gebäude aus OSM geladen, bereinigt, Höhen aus `height`- und `building:levels`-Tags abgeleitet
- **Phase 3 (`03_generate_ifc.py`):** IFC-Hierarchie korrigiert — Geometrie lag auf `IfcBuilding` (von BlenderBIM nicht gerendert); umgestellt auf `IfcBuildingElementProxy` als Geometrieträger; ifcopenshell-API-Signatur auf `products=[...]` angepasst; **2 140 Gebäude erfolgreich als 3D-Körper exportiert**
- IFC-Modell in BlenderBIM geöffnet und 3D-Geometrie verifiziert

---

## Workflow (5 Phasen)

```
OSM / BayernAtlas / ALKIS
        │
        ▼
[1] 01_fetch_data.py        Gebäudegrundrisse via Overpass API (OSM)
        │
        ▼
[2] 02_preprocess_gis.py    Geometrien bereinigen, Höhen ableiten
        │
        ▼
[3] 03_generate_ifc.py      IFC 4 generieren (LOD 100)
        │                   IfcProject > IfcSite > IfcBuilding >
        │                   IfcBuildingStorey > IfcBuildingElementProxy
        ▼
[4] 04_enrich_semantics.py  PropertySets ergänzen (LOD 200+)
        │                   Pset_BuildingCommon, Pset_EnergyConsumption,
        │                   Pset_Georgsvorstadt (custom)
        ▼
[5] 05_evaluate.py          Vollständigkeitsbericht
```

| Phase | Skript | Output |
|-------|--------|--------|
| 1 | `src/01_fetch_data.py` | `data/raw/osm/georgsvorstadt_osm_raw.json` |
| 2 | `src/02_preprocess_gis.py` | `data/interim/georgsvorstadt_clean.geojson` |
| 3 | `src/03_generate_ifc.py` | `data/output/ifc/georgsvorstadt_LOD200.ifc` |
| 4 | `src/04_enrich_semantics.py` | `data/output/ifc/georgsvorstadt_LOD200_LOD200.ifc` |
| 5 | `src/05_evaluate.py` | Bericht auf stdout |

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
# Vollständigen Python-Pfad nutzen (Windows) oder in venv/conda aktivieren:
python src/01_fetch_data.py        # OSM-Daten holen
python src/02_preprocess_gis.py    # GIS bereinigen
python src/03_generate_ifc.py      # IFC generieren
python src/04_enrich_semantics.py  # Semantik ergänzen
python src/05_evaluate.py          # Bericht
```

---

## IFC-Modell anschauen

- **BlenderBIM** (empfohlen): `File → Open IFC Project` → `data/output/ifc/georgsvorstadt_LOD200.ifc`
- **FZKViewer** (KIT): IFC-Datei reinziehen, keine Konfiguration nötig
- **Online**: Autodesk Viewer (viewer.autodesk.com)

---

## Datenquellen

| Quelle | Inhalt | Format | Bezug |
|--------|--------|--------|-------|
| OpenStreetMap | Gebäudegrundrisse, Höhentags | GeoJSON (Overpass API) | automatisch via `01_fetch_data.py` |
| BayernAtlas (LDBV) | LoD1/LoD2 Gebäudemodelle | CityGML | https://www.ldbv.bayern.de/produkte/3dgeo/3d_gebaeude.html |
| ALKIS Bayern | Flurstücke, Gebäudegrundrisse | NAS/GML | GDI-Bayern WFS-Portal |
| Bayerischer Energieatlas | Energiebedarf je Quartier | CSV/WMS | https://www.energieatlas.bayern.de |
| TABULA | Gebäudetypologien, U-Werte | CSV | https://webtool.building-typology.eu |

Manuell heruntergeladene Daten gehören nach `data/raw/citygml/` (BayernAtlas) bzw. `data/raw/alkis/` (ALKIS).

---

## IFC-Klassenmodell

| IFC-Klasse / Pset | Attribute | Datenquelle | LOD |
|-------------------|-----------|-------------|-----|
| IfcProject | GlobalId, Name, UnitsInContext | – | 100 |
| IfcSite | RefLatitude, RefLongitude | OSM | 100 |
| IfcBuilding | Name, ObjectPlacement | OSM | 100 |
| IfcBuildingStorey | Elevation, Name | LoD2 / OSM | 100 |
| IfcBuildingElementProxy | Geometry (ExtrudedAreaSolid) | OSM / LoD2 | 100 |
| Pset_BuildingCommon | NumberOfStoreys, YearOfConstruction, OccupancyType | ALKIS / OSM | 200+ |
| Pset_EnergyConsumption | EnergyConsumptionHeating, CO2Intensity | Energieatlas Bayern | Semantik |
| Pset_Georgsvorstadt | BuildingTypology, SealingRatio, CadastralID | ATKIS / ALKIS / TABULA | Semantik |

---

## Projektstruktur

```
Digital_Twin_Augsburg/
├── configs/
│   └── settings.py           # BBox, CRS, alle Pfade
├── src/
│   ├── 01_fetch_data.py
│   ├── 02_preprocess_gis.py
│   ├── 03_generate_ifc.py
│   ├── 04_enrich_semantics.py
│   └── 05_evaluate.py
├── data/
│   ├── raw/                  # Rohdaten (nicht versioniert)
│   │   ├── citygml/          # BayernAtlas LoD2 (manuell)
│   │   ├── alkis/            # ALKIS WFS-Export (manuell)
│   │   └── osm/              # automatisch via Phase 1
│   ├── interim/              # bereinigtes GeoJSON
│   └── output/ifc/           # fertige .ifc-Dateien
├── notebooks/                # explorative Auswertungen
├── requirements.txt
└── README.md
```

---

## Technologien

- **Python** · GeoPandas · IfcOpenShell · Shapely
- **QGIS** (manuelle GIS-Schritte, CityGML-Import)
- **BlenderBIM** (Qualitätskontrolle, IFC-Visualisierung)