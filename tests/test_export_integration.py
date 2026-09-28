"""End-to-end export tests in real Blender (bpy wheel or Blender --python).

The clinical workflow gate (`_require_workflow_stage`) is bypassed here on
purpose: these tests cover the export pipeline and its quality gate, not the
stage machine.
"""
from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.requires_bpy


@pytest.fixture(scope="module")
def dsg_addon():
    import bpy
    import addon_utils
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mod = addon_utils.enable("dsg", default_set=True)
    assert mod is not None
    import importlib
    guide = importlib.import_module("dsg.guide_module")
    original = guide._require_workflow_stage
    guide._require_workflow_stage = lambda *a, **k: True
    yield guide
    guide._require_workflow_stage = original
    addon_utils.disable("dsg", default_set=True)


def _make_guide(guide_module, *, extra_box=None, open_mesh=False):
    import bmesh
    import bpy
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    mesh = bpy.data.meshes.new("guide_mesh")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=10.0)
    if extra_box is not None:
        ret = bmesh.ops.create_cube(bm, size=extra_box)
        bmesh.ops.translate(bm, verts=ret["verts"], vec=(40.0, 0.0, 0.0))
    if open_mesh:
        bm.faces.ensure_lookup_table()
        bm.faces.remove(bm.faces[0])
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(guide_module.GUIDE_NAME, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def test_closed_guide_exports_exact_file_and_report(dsg_addon, tmp_path):
    import bpy
    _make_guide(dsg_addon)
    target = tmp_path / "DSG_Guide_case.stl"
    assert bpy.ops.dsg.export_guide_stl(filepath=str(target)) == {"FINISHED"}
    assert target.is_file()
    report = json.loads((tmp_path / "DSG_Guide_case.dsg-report.json").read_text("utf-8"))
    assert report["output"]["stl_file"] == target.name
    names = {c["name"]: c["status"] for c in report["quality"]["checks"]}
    assert names["closed_solid"] == "PASS"
    assert names["wall_thickness"] == "PASS"
    assert report["geometry"]["volume_mm3"] == pytest.approx(1000.0, rel=1e-3)
    # the scene guide is untouched (transactional export)
    assert dsg_addon.GUIDE_NAME in bpy.data.objects
    assert "DSG_ExportGuide_Work" not in bpy.data.objects


def test_large_detached_piece_cancels_export(dsg_addon, tmp_path):
    import bpy
    _make_guide(dsg_addon, extra_box=5.0)          # 125 mm³ detached "sleeve"
    target = tmp_path / "g.stl"
    with pytest.raises(RuntimeError):              # CANCELLED raises in bpy.ops from Python
        bpy.ops.dsg.export_guide_stl(filepath=str(target))
    assert not target.exists()
    assert len(bpy.data.objects[dsg_addon.GUIDE_NAME].data.polygons) == 12  # scene guide untouched


def test_confirmed_island_removal_exports(dsg_addon, tmp_path):
    import bpy
    _make_guide(dsg_addon, extra_box=5.0)
    target = tmp_path / "g.stl"
    assert bpy.ops.dsg.export_guide_stl(filepath=str(target), confirm_island_removal=True) == {"FINISHED"}
    assert target.is_file()


def test_open_mesh_blocks_export(dsg_addon, tmp_path):
    import bpy
    _make_guide(dsg_addon, open_mesh=True)
    target = tmp_path / "g.stl"
    with pytest.raises(RuntimeError):
        bpy.ops.dsg.export_guide_stl(filepath=str(target))
    assert not target.exists()


def _cube(name, size, loc):
    import bmesh
    import bpy
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=size)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = loc
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.update()
    return obj


def test_bvh_clearance_distance_and_intersection(dsg_addon):
    from dsg.guide_export.blender_adapter import object_clearance_mm
    implant = _cube("implant", 2.0, (0.0, 0.0, 0.0))
    canal = _cube("canal", 2.0, (4.5, 0.0, 0.0))          # faces 2.5 mm apart
    dist, hits, method = object_clearance_mm(implant, canal)
    assert not hits and dist == pytest.approx(2.5, abs=1e-4) and "UPPER_BOUND" in method
    canal.location.x = 1.5
    import bpy
    bpy.context.view_layer.update()
    dist, hits, _ = object_clearance_mm(implant, canal)
    assert hits and dist == 0.0


def test_bvh_ray_caster_matches_numpy_reference(dsg_addon):
    import numpy as np
    from dsg.guide_export import mesh_checks as mc
    from dsg.guide_export.blender_adapter import BVHRayCaster, mesh_arrays
    v, t = mesh_arrays(_cube("slab", 3.0, (0.0, 0.0, 0.0)))
    a = mc.wall_thickness_report(v, t, BVHRayCaster(v, t))
    b = mc.wall_thickness_report(v, t, mc.NumpyRayCaster(v, t))
    assert a.metrics["min_mm"] == pytest.approx(b.metrics["min_mm"], abs=1e-4) == pytest.approx(3.0, abs=1e-3)


def test_mcp_bridge_token_is_never_saved_in_blend(dsg_addon, tmp_path):
    import importlib
    import bpy
    roadmap = importlib.import_module("dsg.roadmap_module")
    props = bpy.context.scene.dsg_roadmap_props
    props.bridge_port = 18999
    ok, message = roadmap.start_bridge(bpy.context)
    assert ok, message
    try:
        token = roadmap._BRIDGE_TOKEN
        assert len(token) >= 24 and not hasattr(props, "bridge_token")
        blend = tmp_path / "case.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(blend), copy=True, compress=False)
        assert token.encode() not in blend.read_bytes()
    finally:
        roadmap.stop_bridge(bpy.context)
    assert roadmap._BRIDGE_TOKEN == ""


def test_externalized_templates_decode_to_expected_meshes(dsg_addon):
    g = dsg_addon
    for decode, verts_const, faces_const in (
            (g._decode_implant_template, "IMPLANT_TEMPLATE_VERTS", "IMPLANT_TEMPLATE_FACES"),
            (g._decode_drill_visual_template, "DRILL_TEMPLATE_VERTS", "DRILL_TEMPLATE_FACES"),
            (g._decode_microscrew_visual_template, None, None)):
        data = decode()
        assert data is not None
        if verts_const:
            verts, faces = data[0], data[1]
            assert len(verts) == getattr(g, verts_const) and len(faces) == getattr(g, faces_const)
