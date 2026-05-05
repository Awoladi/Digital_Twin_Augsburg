"""
Phase 3 – IFC-Generierung (LOD 100 / LOD 200)

Gebäude mit CityGML-LoD2-Flächen: IfcFacetedBrep (echte Dachgeometrie).
Reine OSM-Gebäude: IfcExtrudedAreaSolid (flache Box, LOD-100-Fallback).

Hierarchie:
  IfcProject > IfcSite > IfcBuilding > IfcBuildingStorey > IfcBuildingElementProxy
"""

import sys, math, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from configs.settings import DATA_INTERIM, IFC_OUTPUT, PROJECT_NAME, SITE_NAME, BBOX, CRS_SOURCE, CRS_WGS84

import geopandas as gpd
import ifcopenshell
import ifcopenshell.api as ifc_api
from shapely.geometry import mapping
from pyproj import Transformer

SURFACES_JSON = DATA_INTERIM / "georgsvorstadt_citygml_surfaces.json"


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------

def _make_to_local(ref_lon, ref_lat):
    """Gibt eine Funktion zurück, die WGS84-Lon/Lat in standortlokale Meter umrechnet."""
    def to_local(lon, lat):
        x = (lon - ref_lon) * math.cos(math.radians(ref_lat)) * 111_320
        y = (lat - ref_lat) * 111_320
        return float(x), float(y)
    return to_local


def _utm_centroid_to_local(cx_utm, cy_utm, ref_lon, ref_lat):
    """Konvertiert UTM32N-Schwerpunkt in standortlokale IFC-Meter."""
    t = Transformer.from_crs(CRS_SOURCE, CRS_WGS84, always_xy=True)
    lon, lat = t.transform(cx_utm, cy_utm)
    to_local = _make_to_local(ref_lon, ref_lat)
    return to_local(lon, lat)


def _placement(f, x=0.0, y=0.0, z=0.0, relative_to=None):
    loc = f.createIfcCartesianPoint([x, y, z])
    ax  = f.createIfcAxis2Placement3D(
        loc,
        f.createIfcDirection([0.0, 0.0, 1.0]),
        f.createIfcDirection([1.0, 0.0, 0.0]),
    )
    return f.createIfcLocalPlacement(relative_to, ax)


def _dms(decimal):
    deg  = int(decimal)
    rem  = abs(decimal - deg) * 60
    mins = int(rem)
    secs = int((rem - mins) * 60)
    return (deg, mins, secs, 0)


# ---------------------------------------------------------------------------
# Geometry builders
# ---------------------------------------------------------------------------

def _extruded_solid(f, body_ctx, coords_wgs84, height):
    """LOD-100-Fallback: extrudierte Box aus WGS84-Grundrissring."""
    # Grundriss bereits in lokalen Koordinaten (relativ zum Gebäudeschwerpunkt)
    pts_2d = [f.createIfcCartesianPoint([float(x), float(y)]) for x, y in coords_wgs84]
    pts_2d.append(pts_2d[0])
    polyline = f.createIfcPolyline(pts_2d)
    profile  = f.createIfcArbitraryClosedProfileDef("AREA", None, polyline)
    solid_ax = f.createIfcAxis2Placement3D(
        f.createIfcCartesianPoint([0.0, 0.0, 0.0]),
        f.createIfcDirection([0.0, 0.0, 1.0]),
        f.createIfcDirection([1.0, 0.0, 0.0]),
    )
    solid = f.createIfcExtrudedAreaSolid(
        profile, solid_ax, f.createIfcDirection([0.0, 0.0, 1.0]), height
    )
    shape = f.createIfcShapeRepresentation(body_ctx, "Body", "SweptSolid", [solid])
    return f.createIfcProductDefinitionShape(None, None, [shape])


def _faceted_brep(f, body_ctx, surf_data):
    """LoD2: IfcFacetedBrep aus CityGML-Boden-, Wand- und Dachflächen."""
    cx   = surf_data["cx_utm"]
    cy   = surf_data["cy_utm"]
    h0   = surf_data["h_grund"]

    all_polys = (
        surf_data.get("ground", []) +
        surf_data.get("walls",  []) +
        surf_data.get("roofs",  [])
    )

    faces = []
    for poly in all_polys:
        pts = poly[:-1] if len(poly) > 3 and poly[0] == poly[-1] else poly
        if len(pts) < 3:
            continue
        ifc_pts = [
            f.createIfcCartesianPoint([p[0] - cx, p[1] - cy, p[2] - h0])
            for p in pts
        ]
        loop  = f.createIfcPolyLoop(ifc_pts)
        bound = f.createIfcFaceOuterBound(loop, True)
        faces.append(f.createIfcFace([bound]))

    if not faces:
        return None

    shell = f.createIfcClosedShell(faces)
    brep  = f.createIfcFacetedBrep(shell)
    shape = f.createIfcShapeRepresentation(body_ctx, "Body", "Brep", [brep])
    return f.createIfcProductDefinitionShape(None, None, [shape])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_ifc(geojson_path: Path, output_path: Path) -> None:
    gdf = gpd.read_file(geojson_path)

    # CityGML-Flächen laden, falls vorhanden
    surfaces_map = {}
    if SURFACES_JSON.exists():
        with open(SURFACES_JSON, encoding="utf-8") as fh:
            surfaces_map = json.load(fh)
        print(f"  {len(surfaces_map)} LoD2-Flächensätze geladen")
    else:
        print("  Kein Flächen-JSON gefunden – LOD-100-Box für alle Gebäude")

    model = ifcopenshell.file(schema="IFC4")
    project = ifc_api.run("root.create_entity", model, ifc_class="IfcProject", name=PROJECT_NAME)
    ifc_api.run("unit.assign_unit", model)

    model_ctx = ifc_api.run("context.add_context", model, context_type="Model")
    body_ctx  = ifc_api.run("context.add_context", model,
                            context_type="Model",
                            context_identifier="Body",
                            target_view="MODEL_VIEW",
                            parent=model_ctx)

    ref_lat   = (BBOX["min_lat"] + BBOX["max_lat"]) / 2
    ref_lon   = (BBOX["min_lon"] + BBOX["max_lon"]) / 2
    to_local  = _make_to_local(ref_lon, ref_lat)

    site = ifc_api.run("root.create_entity", model, ifc_class="IfcSite", name=SITE_NAME)
    ifc_api.run("aggregate.assign_object", model, relating_object=project, products=[site])
    site.RefLatitude  = _dms(ref_lat)
    site.RefLongitude = _dms(ref_lon)
    site.ObjectPlacement = _placement(model)

    built_brep = built_box = skipped = 0

    for i, (_, row) in enumerate(gdf.iterrows()):
        try:
            geom    = row.geometry
            coords  = list(mapping(geom)["coordinates"][0])
            height  = float(row.get("height_m") or 9.6)
            if height <= 0:
                height = 9.6
            name    = str(row.get("name") or f"Gebaeude_{row.get('osm_id', i)}")
            gml_id  = str(row.get("gml_id") or "")

            surf_data = surfaces_map.get(gml_id)

            # Gebäudeschwerpunkt in IFC-Standortkoordinaten
            if surf_data:
                bx, by = _utm_centroid_to_local(
                    surf_data["cx_utm"], surf_data["cy_utm"], ref_lon, ref_lat
                )
            else:
                local_xy = [to_local(lon, lat) for lon, lat in coords[:-1]]
                bx = sum(p[0] for p in local_xy) / len(local_xy)
                by = sum(p[1] for p in local_xy) / len(local_xy)

            # Räumliche Hierarchie
            building = ifc_api.run("root.create_entity", model, ifc_class="IfcBuilding", name=name)
            ifc_api.run("aggregate.assign_object", model, relating_object=site, products=[building])
            building.ObjectPlacement = _placement(model, bx, by, 0.0, site.ObjectPlacement)

            storey = ifc_api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="EG")
            ifc_api.run("aggregate.assign_object", model, relating_object=building, products=[storey])
            storey.ObjectPlacement = _placement(model, 0.0, 0.0, 0.0, building.ObjectPlacement)

            proxy = ifc_api.run("root.create_entity", model, ifc_class="IfcBuildingElementProxy", name=name)
            ifc_api.run("spatial.assign_container", model, relating_structure=storey, products=[proxy])
            proxy.ObjectPlacement = _placement(model, 0.0, 0.0, 0.0, storey.ObjectPlacement)

            # Geometrie
            if surf_data:
                repr_ = _faceted_brep(model, body_ctx, surf_data)
                if repr_:
                    proxy.Representation = repr_
                    built_brep += 1
                    continue

            # Fallback: extrudierte Box
            local_xy = [to_local(lon, lat) for lon, lat in coords[:-1]]
            bx2 = sum(p[0] for p in local_xy) / len(local_xy)
            by2 = sum(p[1] for p in local_xy) / len(local_xy)
            rel_xy = [(x - bx2, y - by2) for x, y in local_xy]
            proxy.Representation = _extruded_solid(model, body_ctx, rel_xy, height)
            built_box += 1

        except Exception:
            skipped += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    model.write(str(output_path))
    print(f"IFC geschrieben -> {output_path}")
    print(f"  LoD2 FacetedBrep : {built_brep}")
    print(f"  LOD100 Box       : {built_box}")
    print(f"  Übersprungen     : {skipped}")


if __name__ == "__main__":
    clean = DATA_INTERIM / "georgsvorstadt_clean.geojson"
    if not clean.exists():
        print("Zuerst 02_preprocess_gis.py ausführen.")
        sys.exit(1)
    build_ifc(clean, IFC_OUTPUT)