"""
Phase 3 – IFC-Generierung (LOD 100)
Reads cleaned GeoJSON and produces an IFC 4 file with one IfcBuilding
per footprint, extruded to the derived height.
"""

import sys, math, uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from configs.settings import DATA_INTERIM, IFC_OUTPUT, PROJECT_NAME, SITE_NAME, BBOX

import geopandas as gpd
import ifcopenshell
import ifcopenshell.api as api
from shapely.geometry import mapping


# ---------------------------------------------------------------------------
# IFC helper utilities
# ---------------------------------------------------------------------------

def _create_ifc_model() -> ifcopenshell.file:
    f = ifcopenshell.file(schema="IFC4")
    return f


def _add_owner_history(f: ifcopenshell.file):
    person = f.createIfcPerson(FamilyName="Unknown")
    org    = f.createIfcOrganization(Name="Digital Twin Augsburg")
    p_and_o = f.createIfcPersonAndOrganization(ThePerson=person, TheOrganization=org)
    app    = f.createIfcApplication(ApplicationDeveloper=org,
                                    Version="0.1",
                                    ApplicationFullName="DT-Augsburg",
                                    ApplicationIdentifier="DT-AUG")
    return f.createIfcOwnerHistory(
        OwningUser=p_and_o, OwningApplication=app,
        ChangeAction="ADDED", CreationDate=0,
    )


def _point(f, x, y, z=0.0):
    return f.createIfcCartesianPoint([float(x), float(y), float(z)])


def _axis2placement3d(f, origin=(0, 0, 0)):
    return f.createIfcAxis2Placement3D(
        Location=_point(f, *origin),
        Axis=f.createIfcDirection([0.0, 0.0, 1.0]),
        RefDirection=f.createIfcDirection([1.0, 0.0, 0.0]),
    )


def _local_placement(f, origin=(0, 0, 0), relative_to=None):
    return f.createIfcLocalPlacement(
        PlacementRelTo=relative_to,
        RelativePlacement=_axis2placement3d(f, origin),
    )


def _footprint_to_ifc_solid(f, coords_wgs84: list, ref_lon: float, ref_lat: float, height: float):
    """Convert lon/lat polygon to a flat IFC extruded solid in metres."""
    def to_local(lon, lat):
        x = (lon - ref_lon) * math.cos(math.radians(ref_lat)) * 111_320
        y = (lat - ref_lat) * 111_320
        return x, y

    pts_2d = [f.createIfcCartesianPoint(list(to_local(lon, lat)))
              for lon, lat in coords_wgs84[:-1]]   # drop closing point

    polyline   = f.createIfcPolyline(pts_2d + [pts_2d[0]])
    profile    = f.createIfcArbitraryClosedProfileDef("AREA", None, polyline)
    direction  = f.createIfcDirection([0.0, 0.0, 1.0])
    placement  = _axis2placement3d(f)
    return f.createIfcExtrudedAreaSolid(profile, placement, direction, float(height))


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_ifc(geojson_path: Path, output_path: Path) -> None:
    gdf = gpd.read_file(geojson_path)
    f   = _create_ifc_model()
    oh  = _add_owner_history(f)

    units = f.createIfcUnitAssignment([
        f.createIfcSIUnit(None, "LENGTHUNIT", None, "METRE"),
        f.createIfcSIUnit(None, "AREAUNIT",   None, "SQUARE_METRE"),
        f.createIfcSIUnit(None, "VOLUMEUNIT", None, "CUBIC_METRE"),
    ])

    ctx = f.createIfcGeometricRepresentationContext(
        None, "Model", 3, 1e-5,
        _axis2placement3d(f),
        f.createIfcDirection([1.0, 0.0]),
    )

    project = f.createIfcProject(
        ifcopenshell.guid.new(), oh,
        Name=PROJECT_NAME,
        UnitsInContext=units,
        RepresentationContexts=[ctx],
    )

    ref_lat = (BBOX["min_lat"] + BBOX["max_lat"]) / 2
    ref_lon = (BBOX["min_lon"] + BBOX["max_lon"]) / 2

    site_pl = _local_placement(f)
    site = f.createIfcSite(
        ifcopenshell.guid.new(), oh,
        Name=SITE_NAME,
        CompositionType="ELEMENT",
        ObjectPlacement=site_pl,
        RefLatitude=_dms(ref_lat),
        RefLongitude=_dms(ref_lon),
    )
    f.createIfcRelAggregates(ifcopenshell.guid.new(), oh, None, None, project, [site])

    buildings = []
    skipped   = 0
    for _, row in gdf.iterrows():
        try:
            geom   = row.geometry
            coords = list(mapping(geom)["coordinates"][0])
            height = float(row.get("height_m", 9.6))

            solid  = _footprint_to_ifc_solid(f, coords, ref_lon, ref_lat, height)
            shape  = f.createIfcShapeRepresentation(ctx, "Body", "SweptSolid", [solid])
            prod_repr = f.createIfcProductDefinitionShape(None, None, [shape])

            bldg_pl = _local_placement(f, relative_to=site_pl)
            bldg = f.createIfcBuilding(
                ifcopenshell.guid.new(), oh,
                Name=str(row.get("name") or f"Gebaeude_{row.get('osm_id', _)}"),
                CompositionType="ELEMENT",
                ObjectPlacement=bldg_pl,
                Representation=prod_repr,
            )
            buildings.append(bldg)
        except Exception as exc:
            skipped += 1
            continue

    f.createIfcRelAggregates(ifcopenshell.guid.new(), oh, None, None, site, buildings)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    f.write(str(output_path))
    print(f"IFC written → {output_path}")
    print(f"  {len(buildings)} buildings | {skipped} skipped")


def _dms(decimal: float):
    deg = int(decimal)
    rem = abs(decimal - deg) * 60
    mins = int(rem)
    secs = int((rem - mins) * 60)
    return (deg, mins, secs, 0)


if __name__ == "__main__":
    clean = DATA_INTERIM / "georgsvorstadt_clean.geojson"
    if not clean.exists():
        print("Run 02_preprocess_gis.py first.")
        sys.exit(1)
    build_ifc(clean, IFC_OUTPUT)
