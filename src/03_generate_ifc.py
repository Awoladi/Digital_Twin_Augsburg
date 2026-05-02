"""
Phase 3 – IFC-Generierung (LOD 100)
Reads cleaned GeoJSON and produces an IFC 4 file.

Hierarchy per building:
  IfcProject > IfcSite > IfcBuilding > IfcBuildingStorey > IfcBuildingElementProxy
Geometry lives on the proxy so BlenderBIM renders it correctly.
"""

import sys, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from configs.settings import DATA_INTERIM, IFC_OUTPUT, PROJECT_NAME, SITE_NAME, BBOX

import geopandas as gpd
import ifcopenshell
import ifcopenshell.api as ifc_api
from shapely.geometry import mapping


def _dms(decimal: float):
    deg  = int(decimal)
    rem  = abs(decimal - deg) * 60
    mins = int(rem)
    secs = int((rem - mins) * 60)
    return (deg, mins, secs, 0)


def _placement(f, x=0.0, y=0.0, z=0.0, relative_to=None):
    loc = f.createIfcCartesianPoint([x, y, z])
    ax  = f.createIfcAxis2Placement3D(
        loc,
        f.createIfcDirection([0.0, 0.0, 1.0]),
        f.createIfcDirection([1.0, 0.0, 0.0]),
    )
    return f.createIfcLocalPlacement(relative_to, ax)


def build_ifc(geojson_path: Path, output_path: Path) -> None:
    gdf = gpd.read_file(geojson_path)

    # ------------------------------------------------------------------
    # IFC model bootstrap
    # ------------------------------------------------------------------
    model = ifcopenshell.file(schema="IFC4")

    project = ifc_api.run("root.create_entity", model, ifc_class="IfcProject", name=PROJECT_NAME)
    ifc_api.run("unit.assign_unit", model)

    # Two-level context: Model > Body (required by BlenderBIM)
    model_ctx = ifc_api.run("context.add_context", model, context_type="Model")
    body_ctx  = ifc_api.run("context.add_context", model,
                            context_type="Model",
                            context_identifier="Body",
                            target_view="MODEL_VIEW",
                            parent=model_ctx)

    # ------------------------------------------------------------------
    # Site
    # ------------------------------------------------------------------
    ref_lat = (BBOX["min_lat"] + BBOX["max_lat"]) / 2
    ref_lon = (BBOX["min_lon"] + BBOX["max_lon"]) / 2

    site = ifc_api.run("root.create_entity", model, ifc_class="IfcSite", name=SITE_NAME)
    ifc_api.run("aggregate.assign_object", model, relating_object=project, products=[site])
    site.RefLatitude  = _dms(ref_lat)
    site.RefLongitude = _dms(ref_lon)
    site.ObjectPlacement = _placement(model)

    def to_local(lon, lat):
        x = (lon - ref_lon) * math.cos(math.radians(ref_lat)) * 111_320
        y = (lat - ref_lat) * 111_320
        return float(x), float(y)

    # ------------------------------------------------------------------
    # Buildings
    # ------------------------------------------------------------------
    built   = 0
    skipped = 0

    for i, (_, row) in enumerate(gdf.iterrows()):
        try:
            geom   = row.geometry
            coords = list(mapping(geom)["coordinates"][0])
            height = float(row.get("height_m") or 9.6)
            if height <= 0:
                height = 9.6
            name = str(row.get("name") or f"Gebaeude_{row.get('osm_id', i)}")

            # Local metre coordinates for the footprint ring
            local_xy = [to_local(lon, lat) for lon, lat in coords[:-1]]
            cx = sum(p[0] for p in local_xy) / len(local_xy)
            cy = sum(p[1] for p in local_xy) / len(local_xy)

            # ---- IfcBuilding (spatial container, no geometry) --------
            building = ifc_api.run("root.create_entity", model, ifc_class="IfcBuilding", name=name)
            ifc_api.run("aggregate.assign_object", model, relating_object=site, products=[building])
            building.ObjectPlacement = _placement(model, cx, cy, 0.0, site.ObjectPlacement)

            # ---- IfcBuildingStorey -----------------------------------
            storey = ifc_api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="EG")
            ifc_api.run("aggregate.assign_object", model, relating_object=building, products=[storey])
            storey.ObjectPlacement = _placement(model, 0.0, 0.0, 0.0, building.ObjectPlacement)

            # ---- IfcBuildingElementProxy (carries the geometry) ------
            proxy = ifc_api.run("root.create_entity", model,
                                ifc_class="IfcBuildingElementProxy", name=name)
            ifc_api.run("spatial.assign_container", model,
                        relating_structure=storey, products=[proxy])
            proxy.ObjectPlacement = _placement(model, 0.0, 0.0, 0.0, storey.ObjectPlacement)

            # ---- Footprint polygon (relative to building centroid) ---
            rel_xy = [(x - cx, y - cy) for x, y in local_xy]
            pts_2d = [model.createIfcCartesianPoint([x, y]) for x, y in rel_xy]
            pts_2d.append(pts_2d[0])          # close the loop
            polyline = model.createIfcPolyline(pts_2d)
            profile  = model.createIfcArbitraryClosedProfileDef("AREA", None, polyline)

            # ---- Extruded solid -------------------------------------
            solid_ax = model.createIfcAxis2Placement3D(
                model.createIfcCartesianPoint([0.0, 0.0, 0.0]),
                model.createIfcDirection([0.0, 0.0, 1.0]),
                model.createIfcDirection([1.0, 0.0, 0.0]),
            )
            solid = model.createIfcExtrudedAreaSolid(
                profile, solid_ax,
                model.createIfcDirection([0.0, 0.0, 1.0]),
                height,
            )

            shape_repr = model.createIfcShapeRepresentation(body_ctx, "Body", "SweptSolid", [solid])
            proxy.Representation = model.createIfcProductDefinitionShape(None, None, [shape_repr])

            built += 1

        except Exception as exc:
            skipped += 1
            continue

    output_path.parent.mkdir(parents=True, exist_ok=True)
    model.write(str(output_path))
    print(f"IFC written -> {output_path}")
    print(f"  {built} buildings | {skipped} skipped")


if __name__ == "__main__":
    clean = DATA_INTERIM / "georgsvorstadt_clean.geojson"
    if not clean.exists():
        print("Run 02_preprocess_gis.py first.")
        sys.exit(1)
    build_ifc(clean, IFC_OUTPUT)