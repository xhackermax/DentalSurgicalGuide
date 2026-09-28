"""Frangible walls and perforation marks on a real sleeve (Blender 5.2).

A sleeve tube for implant B is built, its irrigation outlets are cut with the
production cutters, and then the production seal / mark builders are applied
exactly as the STL export does.
"""
from __future__ import annotations

import json

import pytest

from irrigation_scene import B, build_linked_network, cylinder

pytestmark = pytest.mark.requires_bpy


@pytest.fixture(scope="module", params=["C", "DIRECT"])
def network(request):
    g, props, teardown = build_linked_network(request.param)
    yield g, props, request.param
    teardown()


def _first_hit_depth(obj, outlet):
    """Distance from the bore surface to the first solid along the outlet normal."""
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()
    mw = obj.matrix_world
    tree = BVHTree.FromPolygons([mw @ v.co for v in mesh.vertices], [tuple(p.vertices) for p in mesh.polygons])
    eval_obj.to_mesh_clear()
    normal = Vector(outlet["normal"]).normalized()
    origin = Vector(outlet["point"]) - normal * 0.5
    _loc, _n, _i, dist = tree.ray_cast(origin, normal, 10.0)
    return float("inf") if dist is None else dist - 0.5   # None: the channel runs out of the part


def _sleeve_with_cut_outlets(g, props, implant, mode, guide_plate=False):
    import bpy
    inner_r, outer_r, _ = g._sleeve_radii_from_props(props)
    mx = g.get_sleeve_matrix_world(props, implant)
    scene = bpy.context.scene
    tube = cylinder(scene, f"T_Sleeve_{mode}", outer_r, props.sleeve_height, (0, 0, 0), segments=96)
    tube.matrix_world = mx
    bore = cylinder(scene, f"T_Bore_{mode}", inner_r, props.sleeve_height + 2, (0, 0, 0), segments=96)
    bore.matrix_world = mx
    ok, message = g.apply_difference_exact_checked(bpy.context, tube, bore, "T_bore")
    assert ok, message
    bpy.data.objects.remove(bore, do_unlink=True)
    if guide_plate:
        # A 3 mm plate beside the sleeve, flush with its occlusal end: room for the digit.
        occ = g._occlusal_direction(props, implant).normalized()
        center = g.get_sleeve_center_world(props, implant)
        plate = cylinder(scene, "T_Plate", 6.0, 3.0, (0, 0, 0), segments=64)
        plate.location = center + g.Vector((outer_r + 5.0, 0.0, 0.0)) + occ * (props.sleeve_height * 0.5 - 1.5)
        bpy.context.view_layer.update()
        ok, _solver = g.apply_boolean_union_exact(bpy.context, tube, plate, mod_name="T_plate")
        assert ok
    entry = g._irrigation_entry_for_implant(props, implant)
    if mode == "C":
        c_props, _ = g._irrigation_entry_effective_props(props, entry)
        cutter = g.build_irrigation_c_only_cutter(
            bpy.context, entry["points"], c_props, implant_obj=implant, name="T_Cut", extra_radius=0.045)
    else:
        # DIRECT: the shared Y-network lumen enters every sleeve bore.
        entries = g.load_irrigation_path_entries(props)
        source = [e for e in entries if not e["link"]][0]
        cutter = g.build_irrigation_y_network_lumen_cutter(
            bpy.context, source, [e for e in entries if e["link"]], props, name="T_Cut")
    ok, message = g.apply_difference_exact_checked(bpy.context, tube, cutter, "T_channel", robust_retry=True)
    assert ok, message
    return tube


def test_membrane_closes_every_outlet_behind_a_visible_pocket(network):
    import bpy
    g, props, mode = network
    expected_outlets = 2 if mode == "C" else 1
    implant = bpy.data.objects[B]
    tube = _sleeve_with_cut_outlets(g, props, implant, mode)
    try:
        outlets, error = g.frangible_outlets(props, implant)
        assert len(outlets) == expected_outlets, error
        depth = g.frangible_seal_design().pocket_depth_mm
        for outlet in outlets:
            assert _first_hit_depth(tube, outlet) > depth + 0.3      # channel open before sealing
        seal, message = g.build_frangible_irrigation_seal_object(bpy.context, props, implant, name="T_Seal")
        assert seal is not None, message
        ok, _solver = g.apply_boolean_union_exact(bpy.context, tube, seal, mod_name="T_union")
        assert ok
        for outlet in outlets:
            assert _first_hit_depth(tube, outlet) == pytest.approx(depth, abs=0.01)   # closed at 0.30 mm
    finally:
        bpy.data.objects.remove(tube, do_unlink=True)


def test_membrane_never_enters_the_drill_bore(network):
    import bpy
    import numpy as np
    g, props, _mode = network
    implant = bpy.data.objects[B]
    seal, message = g.build_frangible_irrigation_seal_object(bpy.context, props, implant, name="T_Seal_bore")
    try:
        assert seal is not None, message
        inner_r, _outer_r, _ = g._sleeve_radii_from_props(props)
        mx = g.get_sleeve_matrix_world(props, implant)
        inv = mx.inverted()
        local = np.array([tuple(inv @ (seal.matrix_world @ v.co)) for v in seal.data.vertices])
        radial = np.hypot(local[:, 0], local[:, 1])
        assert radial.min() >= inner_r + 0.25       # ≥ pocket depth minus the membrane curvature
        assert seal["DSG_seal_center_thickness_mm"] == pytest.approx(0.10)
        assert seal["DSG_seal_rim_thickness_mm"] == pytest.approx(0.25)
        assert seal["DSG_irrigation_open_order"] == 2
    finally:
        bpy.data.objects.remove(seal, do_unlink=True)


def test_marks_are_cut_and_the_export_triangulation_is_manifold(network):
    import bpy
    from dsg.guide_export import blender_adapter, mesh_checks
    g, props, mode = network
    implant = bpy.data.objects[B]
    tube = _sleeve_with_cut_outlets(g, props, implant, mode, guide_plate=True)
    try:
        seal, _m = g.build_frangible_irrigation_seal_object(bpy.context, props, implant, name="T_Seal2")
        assert g.apply_boolean_union_exact(bpy.context, tube, seal, mod_name="T_u2")[0]
        volume_before = mesh_checks.signed_volume_mm3(*blender_adapter.mesh_arrays(tube))
        cutters, notes = g.build_frangible_mark_cutters(bpy.context, props, implant, tube)
        kinds = sorted(c["DSG_frangible_mark"] for c in cutters)
        assert kinds == ["COUNTERSINK", "ORDER_DIGIT"], notes
        for cutter in cutters:
            ok, message = g.apply_difference_exact_checked(bpy.context, tube, cutter, "T_mark", robust_retry=True)
            assert ok, message
            bpy.data.objects.remove(cutter, do_unlink=True)
        volume_after = mesh_checks.signed_volume_mm3(*blender_adapter.mesh_arrays(tube))
        assert volume_after < volume_before - 0.05          # countersinks + digit removed material
        outlets, _ = g.frangible_outlets(props, implant)
        for outlet in outlets:                                # membrane untouched by the marks
            assert _first_hit_depth(tube, outlet) == pytest.approx(g.frangible_seal_design().pocket_depth_mm, abs=0.01)
        blender_adapter.triangulate_for_stl(tube)
        v, t = blender_adapter.mesh_arrays(tube)
        assert mesh_checks.manifold_report(v, t).status in ("PASS", "WARN")
    finally:
        bpy.data.objects.remove(tube, do_unlink=True)


def test_preview_operator_shows_and_clears(network):
    import bpy
    g, props, _mode = network
    assert bpy.ops.dsg.preview_frangible_marks() == {"FINISHED"}
    shown = [o for o in bpy.data.objects if o.name.startswith(g.FRANGIBLE_PREVIEW_PREFIX)]
    assert any("_Wall" in o.name for o in shown) and any("Countersink" in o.name for o in shown)
    assert bpy.ops.dsg.preview_frangible_marks(clear=True) == {"FINISHED"}
    assert not [o for o in bpy.data.objects if o.name.startswith(g.FRANGIBLE_PREVIEW_PREFIX)]


def test_every_sleeve_of_the_network_is_reached_by_its_channel(network):
    """Regression: in DIRECT mode Link channels started inside the ACTIVE sleeve."""
    import bpy
    import numpy as np
    g, props, mode = network
    entries = g.load_irrigation_path_entries(props)
    inner_r, outer_r, _ = g._sleeve_radii_from_props(props)
    for entry in entries:
        implant = bpy.data.objects[entry["implant_name"]]
        props_e, _ = g._irrigation_entry_effective_props(props, entry)
        first = g.smooth_irrigation_centerline_controls(entry["points"], props_e)[0]
        center = g.get_sleeve_center_world(props, implant)
        axis = g.get_sleeve_axis_world(props, implant)
        rel = first - center
        radial = (rel - axis * rel.dot(axis)).length
        assert radial < outer_r, (entry["implant_name"], radial)
