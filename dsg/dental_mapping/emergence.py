"""Prosthetic emergence transfer/derivation for CrownTarget.

PROSTHETIC_AXIS is authored prosthetic information. It is never synthesized from
PCA. Reference emergence assets are transferred through the exact CrownTarget
deformation and then, where applicable, reprojected to the final crown surface.
"""
from __future__ import annotations

import json
from typing import Any

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from .. import dental_assets, dental_asset_blender
from . import anatomic_fit, library


def _matrix(values) -> Matrix:
    return Matrix(tuple(tuple(float(values[r*4+c]) for c in range(4)) for r in range(4)))


def _replace_object(name: str):
    obj = bpy.data.objects.get(name)
    if obj is None:
        return
    data = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if data is not None and data.users == 0:
        if isinstance(data, bpy.types.Mesh):
            bpy.data.meshes.remove(data)
        elif isinstance(data, bpy.types.Curve):
            bpy.data.curves.remove(data)


def _create_empty(fdi: int, role: str, matrix_world: Matrix) -> bpy.types.Object:
    name = dental_assets.object_name(fdi, role)
    _replace_object(name)
    obj = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(obj)
    obj.empty_display_type = "ARROWS" if role == "PROSTHETIC_AXIS" else "SPHERE"
    obj.empty_display_size = 1.0 if role == "PROSTHETIC_AXIS" else 0.65
    obj.matrix_world = matrix_world
    dental_asset_blender.stamp_object(
        obj, fdi=fdi, role=role, source="DERIVED",
        coordinate_space="WORLD", rename=True,
    )
    return obj


def _create_mesh_asset(
    fdi: int,
    role: str,
    vertices,
    faces,
    matrix_world: Matrix,
) -> bpy.types.Object:
    name = dental_assets.object_name(fdi, role)
    _replace_object(name)
    mesh = bpy.data.meshes.new(f"{name}_DATA")
    mesh.from_pydata([tuple(float(v) for v in p) for p in vertices], [], [tuple(face) for face in faces])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.matrix_world = matrix_world
    dental_asset_blender.stamp_object(
        obj, fdi=fdi, role=role, source="DERIVED",
        coordinate_space="WORLD", rename=True,
    )
    return obj


def _warp_world(crown: bpy.types.Object, crown_local: Vector) -> Vector:
    warped = anatomic_fit.warp_crown_local_point(crown, crown_local)
    return crown.matrix_world @ warped


def _warped_axis_matrix(crown: bpy.types.Object, axis_rel: Matrix) -> Matrix:
    """Warp origin + basis probes, prioritizing authored Z as prosthetic axis."""
    o_local = axis_rel.translation.copy()
    x_dir = Vector((axis_rel[0][0], axis_rel[1][0], axis_rel[2][0]))
    z_dir = Vector((axis_rel[0][2], axis_rel[1][2], axis_rel[2][2]))
    if x_dir.length <= 1e-8 or z_dir.length <= 1e-8:
        raise RuntimeError("Degenerate authored ProstheticAxis")
    x_dir.normalize()
    z_dir.normalize()
    o = _warp_world(crown, o_local)
    x_probe = _warp_world(crown, o_local + x_dir)
    z_probe = _warp_world(crown, o_local + z_dir)
    z = z_probe - o
    if z.length <= 1e-8:
        raise RuntimeError("Crown deformation collapsed ProstheticAxis")
    z.normalize()
    x = x_probe - o
    x = x - z * x.dot(z)
    if x.length <= 1e-8:
        # Deterministic fallback orthogonal to Z, never a PCA axis.
        seed = Vector((1.0, 0.0, 0.0)) if abs(z.x) < 0.9 else Vector((0.0, 1.0, 0.0))
        x = seed - z * seed.dot(z)
    x.normalize()
    y = z.cross(x)
    if y.length <= 1e-8:
        raise RuntimeError("Cannot build right-handed ProstheticAxis frame")
    y.normalize()
    x = y.cross(z).normalized()
    return Matrix((
        (x.x, y.x, z.x, o.x),
        (x.y, y.y, z.y, o.y),
        (x.z, y.z, z.z, o.z),
        (0.0, 0.0, 0.0, 1.0),
    ))


def _snap_mesh_asset_to_crown(
    asset: bpy.types.Object,
    crown: bpy.types.Object,
    *,
    max_distance_mm: float = 1.5,
) -> dict[str, Any]:
    tree = BVHTree.FromObject(crown, bpy.context.evaluated_depsgraph_get(), deform=True, cage=False)
    if tree is None:
        raise RuntimeError("Could not build CrownTarget BVH for emergence projection")
    inv = asset.matrix_world.inverted_safe()
    moved = 0
    unresolved = 0
    max_move = 0.0
    for vertex in asset.data.vertices:
        world_before = asset.matrix_world @ vertex.co
        hit = tree.find_nearest(world_before, max_distance_mm)
        if hit is None or hit[0] is None:
            unresolved += 1
            continue
        world_after = hit[0]
        move = float((world_after - world_before).length)
        max_move = max(max_move, move)
        vertex.co = inv @ world_after
        moved += 1
    asset.data.update()
    return {"moved_vertices": moved, "unresolved_vertices": unresolved, "max_reprojection_mm": max_move}


def derive_emergence_assets(
    fdi: int,
    crown_target: bpy.types.Object,
) -> dict[str, Any]:
    fdi = dental_assets.normalize_fdi(fdi, include_primary=False)
    dental_asset_blender.validate_object_contract(
        crown_target, expected_fdi=fdi, expected_role="CROWN_TARGET"
    )
    snapshot = library.read_family_reference_snapshot(fdi, anchor_role="CROWN_TEMPLATE")

    required = ("EMERGENCE_REGION", "EMERGENCE_CENTER", "PROSTHETIC_AXIS")
    refs = {}
    for role in required:
        name = dental_assets.object_name(fdi, role)
        snap = snapshot.objects.get(name)
        if snap is None:
            raise dental_assets.DentalAssetContractError(
                f"FDI {fdi}: canonical library lacks {role}; prosthetic emergence cannot be invented"
            )
        refs[role] = snap

    center_ref = refs["EMERGENCE_CENTER"]
    center_world = _warp_world(crown_target, Vector(center_ref.location_relative_to_anchor))
    center_obj = _create_empty(fdi, "EMERGENCE_CENTER", Matrix.Translation(center_world))

    axis_ref = refs["PROSTHETIC_AXIS"]
    axis_obj = _create_empty(
        fdi, "PROSTHETIC_AXIS",
        _warped_axis_matrix(crown_target, _matrix(axis_ref.matrix_relative_to_anchor)),
    )

    region_ref = refs["EMERGENCE_REGION"]
    if region_ref.object_type != "MESH" or not region_ref.mesh_vertices:
        raise dental_assets.DentalAssetContractError(
            f"FDI {fdi}: EMERGENCE_REGION must be an authored mesh region"
        )
    region_vertices = [
        anatomic_fit.warp_crown_local_point(crown_target, Vector(v))
        for v in region_ref.mesh_vertices
    ]
    region_obj = _create_mesh_asset(
        fdi, "EMERGENCE_REGION",
        region_vertices, region_ref.mesh_faces, crown_target.matrix_world
    )
    region_projection = _snap_mesh_asset_to_crown(region_obj, crown_target)

    cervical_obj = None
    cervical_projection = None
    cervical_ref = snapshot.objects.get(dental_assets.object_name(fdi, "CERVICAL_PROFILE"))
    if cervical_ref is not None and cervical_ref.object_type == "MESH" and cervical_ref.mesh_vertices:
        cervical_vertices = [
            anatomic_fit.warp_crown_local_point(crown_target, Vector(v))
            for v in cervical_ref.mesh_vertices
        ]
        cervical_obj = _create_mesh_asset(
            fdi, "CERVICAL_PROFILE",
            cervical_vertices, cervical_ref.mesh_faces, crown_target.matrix_world
        )
        cervical_projection = _snap_mesh_asset_to_crown(cervical_obj, crown_target)

    report = {
        "schema": "dsg.emergence.v1",
        "fdi": fdi,
        "source": "CROWN_TEMPLATE_TRANSFER",
        "region": region_obj.name,
        "center": center_obj.name,
        "prosthetic_axis": axis_obj.name,
        "cervical_profile": cervical_obj.name if cervical_obj else None,
        "region_projection": region_projection,
        "cervical_projection": cervical_projection,
        "pca_used": False,
    }
    crown_target["DSG_emergence_json"] = json.dumps(report, sort_keys=True, separators=(",", ":"))
    return report


def get_emergence_region(fdi: int):
    return dental_asset_blender.find_one(fdi, "EMERGENCE_REGION")


def get_prosthetic_axis(fdi: int):
    return dental_asset_blender.find_one(fdi, "PROSTHETIC_AXIS")
