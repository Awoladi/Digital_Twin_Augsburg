# Digital Twin Augsburg – Georgsvorstadt

Automatisierter GIS→IFC-Workflow für das Quartier Georgsvorstadt (Augsburg, ca. 12 ha, ~380 Gebäude).
Open-Data-Quellen (BayernAtlas LoD2, ALKIS, OSM) → IFC 4 mit semantischen PropertySets.

## Workflow (5 Phasen)

| Phase | Skript | Beschreibung |
|-------|--------|-------------|
| 1 | `src/01_fetch_data.py` | OSM-Gebäude via Overpass API laden |
| 2 | `src/02_preprocess_gis.py` | Geometrien bereinigen, Höhen ableiten |
| 3 | `src/03_generate_ifc.py` | IFC 4 erzeugen (LOD 100) |
| 4 | `src/04_enrich_semantics.py` | PropertySets ergänzen (LOD 200+) |
| 5 | `src/05_evaluate.py` | Vollständigkeitsbericht |

## Installation

```bash
pip install -r requirements.txt
```

> **Hinweis:** `ifcopenshell` am einfachsten via conda installieren:
> ```bash
> conda install -c ifcopenshell ifcopenshell
> ```

## Ausführung

```bash
python src/01_fetch_data.py        # OSM-Daten holen
python src/02_preprocess_gis.py    # GIS bereinigen
python src/03_generate_ifc.py      # IFC generieren
python src/04_enrich_semantics.py  # Semantik ergänzen
python src/05_evaluate.py          # Bericht
```

## Manuelle Datenquellen

| Quelle | Format | Bezug |
|--------|--------|-------|
| BayernAtlas LoD2 | CityGML | https://www.ldbv.bayern.de/produkte/3dgeo/3d_gebaeude.html |
| ALKIS Bayern | NAS/GML | GDI-Bayern WFS-Portal |
| Bayerischer Energieatlas | CSV/WMS | https://www.energieatlas.bayern.de |

LoD2-Kacheln → nach `data/raw/citygml/`, ALKIS-Export → `data/raw/alkis/`.

## Projektstruktur

```
Digital_Twin_Augsburg/
├── configs/settings.py       # BBox, CRS, Pfade
├── src/
│   ├── 01_fetch_data.py
│   ├── 02_preprocess_gis.py
│   ├── 03_generate_ifc.py
│   ├── 04_enrich_semantics.py
│   └── 05_evaluate.py
├── data/
│   ├── raw/                  # Rohdaten (nicht versioniert)
│   │   ├── citygml/
│   │   ├── alkis/
│   │   └── osm/
│   ├── interim/              # QGIS-Exporte, bereinigtes GeoJSON
│   └── output/ifc/           # Endprodukt: .ifc-Dateien
├── notebooks/                # Explorative Auswertungen
└── requirements.txt
```

## Testquartier

- **Koordinaten:** 48.363° N, 10.898° O
- **Fläche:** ca. 12 ha
- **Baualter:** 1880–1930, Teile 1950er/60er
- **Ziel-LOD:** LOD 100 → LOD 200 → semantisch erweiterter IFC Digital Twin

## Technologien

- Python · GeoPandas · IfcOpenShell · Shapely
- QGIS (manuelle GIS-Schritte)
- BlenderBIM (Qualitätskontrolle)
