"""Blender EOFF authoring adapter."""
from __future__ import annotations

from pathlib import Path

import bpy

from .. import dental_assets, dental_asset_blender
from .eoff_core import parse_eoff


def import_eoff(
    path: str | Path,
    *,
    object_name: str,
    collection: bpy.types.Collection | None = None,
) -> bpy.types.Object:
    data = parse_eoff(path)
    mesh = bpy.data.meshes.new(f"{object_name}_DATA")
    mesh.from_pydata(data["vertices"], [], data["faces"])
    mesh.update()
    labels = data["vertex_feature_labels"]
    if labels is not None:
        names = dental_assets.mesh_attribute_names()
        original = names.get("eoff_vertex_feature_original", "VERTEX_FEATURE_LABELS")
        canonical = names.get("vertex_feature_label", "DSG_vertex_feature_label")
        dental_asset_blender.ensure_point_int_attribute(mesh, labels, name=original)
        dental_asset_blender.ensure_point_int_attribute(mesh, labels, name=canonical)
    obj = bpy.data.objects.new(object_name, mesh)
    (collection or bpy.context.scene.collection).objects.link(obj)
    obj["DSG_import_format"] = data["header"]
    obj["DSG_eoff_feature_labels_present"] = bool(labels is not None)
    return obj
