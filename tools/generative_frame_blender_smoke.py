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

    cls = bpy.types.DSG_OT_InspectFinalBooleanSection
    assert cls.bl_rna.properties.get("section_axis") is not None
    assert cls.bl_rna.properties.get("nominal_diameter_mm") is not None
    cls_profile = bpy.types.DSG_OT_InspectFinalBooleanPath
    assert cls_profile.bl_rna.properties.get("station_count") is not None

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

    addon_utils.disable("dsg", default_set=True)
    print("GENERATIVE FRAME BLENDER 5.2 SMOKE PASS: RNA + evaluated mesh + 5 real sections")


if __name__ == "__main__":
    main()
