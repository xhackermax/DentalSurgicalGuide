"""Shared Blender scene for irrigation integration tests (needs real bpy)."""
from __future__ import annotations

A, B, C = "DSG_Implant_01", "DSG_Implant_02", "DSG_Implant_03"


def cylinder(scene, name, radius, depth, location, segments=32):
    import bmesh
    import bpy
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segments, radius1=radius, radius2=radius, depth=depth)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    scene.collection.objects.link(obj)
    return obj


def build_linked_network(mode="C"):
    """Three implants in a row, main channel from A past B and C, B and C linked."""
    import importlib

    import bpy
    import addon_utils
    from mathutils import Vector

    bpy.ops.wm.read_factory_settings(use_empty=True)
    assert addon_utils.enable("dsg", default_set=True) is not None
    g = importlib.import_module("dsg.guide_module")
    original = g._require_workflow_stage
    g._require_workflow_stage = lambda *a, **k: True

    scene = bpy.context.scene
    props = scene.dsg_props
    implants = [cylinder(scene, name, 2.0, 10.0, (x, 0.0, 0.0))
                for name, x in ((A, 0.0), (B, 12.0), (C, 24.0))]
    props.guide_obj = cylinder(scene, g.GUIDE_NAME, 30.0, 3.0, (12.0, 0.0, 12.0))
    props.implant_obj = implants[0]
    props.irr_sleeve_channel_mode = mode
    bpy.context.view_layer.update()

    center = g.get_sleeve_center_world(props, implants[0])
    _inner, outer_r, _wall = g._sleeve_radii_from_props(props)
    z = center.z
    points = [center + Vector((0, 1, 0)) * outer_r, center + Vector((0, 6, 0)),
              Vector((12, 7, z)), Vector((24, 7, z)), Vector((36, 7, z)), Vector((42, 7, z + 4))]
    ok, message = g.build_irrigation_preview_from_points(bpy.context, props, points, implant=implants[0])
    assert ok, message
    assert bpy.ops.dsg.confirm_irrigation_preview() == {"FINISHED"}
    assert bpy.ops.dsg.link_selected_irrigation(implant_names=f"{C},{B}") == {"FINISHED"}

    def teardown():
        g._require_workflow_stage = original
        addon_utils.disable("dsg", default_set=True)

    return g, props, teardown
