"""Headless Blender 5.2 smoke of installed DSG GenerativeFrame geometry + operators.

No clinical case/data, no STL export and no writes to the user scene.
The real module/Blender data path must work, not fake-bpy AST shims.
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import addon_utils
import bpy
import numpy as np


def main():
    assert bpy.app.version[:2] == (5, 2), bpy.app.version
    bpy.ops.wm.read_factory_settings(use_empty=True)
    assert addon_utils.enable("dsg", default_set=True) is not None, "DSG addon registration failed"

    from dsg import frame_structural
    from dsg.frame_boolean_section_core import measure_boolean_section
    from dsg.frame_boolean_path_core import profile_boolean_path
    from dsg.guide_export.blender_adapter import mesh_arrays

    expected = (
        "dsg.analyze_geodesic_frame_fem",
        "dsg.preview_geodesic_frame_fem",
        "dsg.estimate_geodesic_contact",
        "dsg.analyze_geodesic_groups",
        "dsg.inspect_final_boolean_section",
        "dsg.inspect_final_boolean_path",
    )
    for op_id in expected:
        category, identifier = op_id.split(".", 1)
        getattr(getattr(bpy.ops, category), identifier).get_rna_type()

    # Blender exposes registered operators via bpy.ops RNA, while bpy.types
    # need not export their Python implementation classes as module attrs.
    cls = bpy.ops.dsg.inspect_final_boolean_section.get_rna_type()
    assert cls.properties.get("section_axis") is not None
    assert cls.properties.get("nominal_diameter_mm") is not None
    cls_profile = bpy.ops.dsg.inspect_final_boolean_path.get_rna_type()
    assert cls_profile.properties.get("station_count") is not None

    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0, 0, 0))
    cube = bpy.context.active_object
    assert cube is not None and cube.type == "MESH"
    before = (len(cube.data.vertices), len(cube.data.polygons), tuple(cube.location))
    v, t = mesh_arrays(cube)
    assert len(t) == 12
    section = measure_boolean_section(v, t, [0, 0, 0], [1, 0, 0],
                                      probe_point_mm=[0, 0, 0])
    assert math.isclose(section.area_mm2, 4., abs_tol=1e-7)
    assert math.isclose(section.principal_inertia_min_mm4, 4/3, abs_tol=1e-7)
    measured = profile_boolean_path(
        v, t, [[-0.75, 0, 0], [0.75, 0, 0]],
        sample_count=5, nominal_radii_mm=[1, 1])
    assert measured.probe_count == 5
    assert math.isclose(measured.area_min_mm2, 4., abs_tol=1e-7)
    assert not measured.mechanical_fem_validated
    after = (len(cube.data.vertices), len(cube.data.polygons), tuple(cube.location))
    assert after == before, "Read-only section analyses mutated Blender mesh"

    # Exercise the REAL Blender registered operator, not just its RNA/pure
    # kernel. The cube is a synthetic final-guide fixture, never patient data.
    from dsg import guide_module
    cube = guide_module.register_dsg_object(
        cube, guide_module.ROLE_GUIDE, guide_module.GUIDE_NAME)
    bpy.context.scene.dsg_props.guide_obj = cube
    cube["DSG_final_cut_completed"] = True
    bpy.context.scene.cursor.location = (0, 0, 0)
    result = bpy.ops.dsg.inspect_final_boolean_section(
        section_axis=(1, 0, 0), nominal_diameter_mm=2.0)
    assert result == {'FINISHED'}, f"Real section operator failed: {result}"

    # The second operator reads a deliberately separate interior POLY trace
    # and writes only de-identified technical JSON to Blender clipboard.
    trace_data = bpy.data.curves.new("Synthetic interior frame trace", "CURVE")
    trace_data.dimensions = "3D"
    poly = trace_data.splines.new("POLY")
    poly.points.add(1)
    poly.points[0].co = (-0.75, 0.0, 0.0, 1)
    poly.points[1].co = (0.75, 0.0, 0.0, 1)
    trace = bpy.data.objects.new("DSG_Synthetic_Interior_Trace", trace_data)
    bpy.context.scene.collection.objects.link(trace)
    bpy.ops.object.select_all(action="DESELECT")
    trace.select_set(True)
    bpy.context.view_layer.objects.active = trace
    result = bpy.ops.dsg.inspect_final_boolean_path(
        station_count=5, nominal_diameter_mm=2.0)
    assert result == {'FINISHED'}, f"Real Boolean path operator failed: {result}"
    import json
    report = json.loads(bpy.context.window_manager.clipboard)
    assert report["station_count"] == 5
    assert math.isclose(report["area_min_mm2"], 4.0, abs_tol=1e-6)
    assert not report["post_boolean_fem_validated"]
    assert (len(cube.data.vertices),len(cube.data.polygons),tuple(cube.location)) == before

    addon_utils.disable("dsg", default_set=True)
    print("GENERATIVE FRAME BLENDER 5.2 SMOKE PASS: RNA + actual registered"
          " operators + evaluated mesh + 5 measured sections")


if __name__ == "__main__":
    main()
