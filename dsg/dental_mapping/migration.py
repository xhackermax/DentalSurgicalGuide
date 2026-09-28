"""Explicit, idempotent migration of legacy dental mapping scene artifacts.

No coordinate-axis guess is performed. Legacy ToothFrames are rebuilt from
canonical semantic landmarks so +X/+Y/+Z follow DSG_TOOTH_LOCAL_V1 by
construction.
"""
from __future__ import annotations

import re
from typing import Any

import bpy

from .. import dental_assets, dental_asset_blender
from . import derived_geometry

_FRAME_RE = re.compile(r"^DSG_ToothFrame_FDI_(\d{2})(?:\.\d+)?$")


def _landmarks_for_fdi(fdi: int):
    keys = dental_assets.property_keys()
    items = []
    for obj in bpy.data.objects:
        if not dental_asset_blender.is_family_object(obj, fdi=fdi, role="LANDMARK"):
            continue
        name = str(obj.get(keys["landmark_name"], "") or "")
        try:
            name = dental_assets.normalize_import_landmark_name(name)
        except dental_assets.DentalAssetContractError:
            continue
        p = obj.matrix_world.translation
        items.append({
            "name": name,
            "xyz": [float(p.x), float(p.y), float(p.z)],
            "confidence": float(obj.get(keys["landmark_confidence"], 0.0) or 0.0),
        })
    return items


def rebuild_legacy_tooth_frame(fdi: int, frame_obj: bpy.types.Object) -> bool:
    fdi = dental_assets.normalize_fdi(fdi, include_primary=False)
    standard = str(frame_obj.get("DSG_tooth_frame_standard", "") or "")
    # Current DSG 9.0 contract already used the definitive convention. Only
    # explicit unknown/legacy frames are rebuilt; absence on accepted v9.0
    # additive metadata is handled by dental_asset_blender migration.
    if standard == "DSG_TOOTH_LOCAL_V1":
        return False
    landmarks = _landmarks_for_fdi(fdi)
    present = {item["name"] for item in landmarks}
    missing = [name for name in dental_assets.required_landmarks(fdi) if name not in present]
    if missing:
        raise dental_assets.DentalAssetContractError(
            f"Cannot migrate legacy ToothFrame FDI {fdi}; missing canonical landmarks: "
            + ", ".join(missing)
        )
    matrix = derived_geometry.derive_tooth_frame_matrix(landmarks)
    frame_obj.matrix_world = matrix
    dental_asset_blender.stamp_object(
        frame_obj,
        fdi=fdi,
        role="TOOTH_FRAME",
        source="DERIVED",
        coordinate_space="WORLD",
        rename=True,
    )
    frame_obj["DSG_frame_migration"] = "REBUILT_FROM_CANONICAL_LANDMARKS"
    return True


def migrate_scene_compatibility(scene=None) -> dict[str, Any]:
    scene = scene or getattr(bpy.context, "scene", None)
    base = dental_asset_blender.migrate_scene_assets(scene)
    rebuilt_frames = 0
    objects = list(scene.objects) if scene is not None else list(bpy.data.objects)
    for obj in objects:
        match = _FRAME_RE.match(obj.name)
        if not match:
            continue
        fdi = int(match.group(1))
        # Pre-contract legacy frames have no canonical role metadata.
        if dental_asset_blender.is_family_object(obj, fdi=fdi, role="TOOTH_FRAME"):
            continue
        try:
            if rebuild_legacy_tooth_frame(fdi, obj):
                rebuilt_frames += 1
        except dental_assets.DentalAssetContractError:
            # Fail the specific mapping operation later; scene loading itself
            # degrades gracefully so unrelated guide work remains accessible.
            obj["DSG_frame_migration_required"] = True
    return {**base, "rebuilt_legacy_frames": rebuilt_frames}
