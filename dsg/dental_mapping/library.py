"""Shared native .blend dental-library access and validation.

The .blend is the native editable master.  It is intentionally not mirrored into
private STL/OBJ copies. Runtime code either appends a persistent template object
or reads a temporary reference snapshot and immediately removes temporary data.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import bpy
from mathutils import Matrix

from .. import dental_assets, dental_asset_blender

RUNTIME_COLLECTION = "DSG_Dental_Library_Runtime"


@dataclass(slots=True)
class ReferenceObjectSnapshot:
    role: str
    name: str
    object_type: str
    matrix_relative_to_anchor: tuple[float, ...]
    location_relative_to_anchor: tuple[float, float, float]
    mesh_vertices: tuple[tuple[float, float, float], ...] = ()
    mesh_faces: tuple[tuple[int, ...], ...] = ()


@dataclass(slots=True)
class FamilyReferenceSnapshot:
    fdi: int
    anchor_role: str
    anchor_name: str
    objects: dict[str, ReferenceObjectSnapshot]


def library_path() -> Path:
    return Path(dental_assets.library_path())


def library_available() -> bool:
    return library_path().is_file()


def require_library() -> Path:
    path = library_path()
    if not path.is_file():
        raise FileNotFoundError(
            f"DSG dental library is not installed: {path}. "
            "Author/import the canonical dsg_dental_library.blend before mapping."
        )
    return path


def ensure_runtime_collection() -> bpy.types.Collection:
    coll = bpy.data.collections.get(RUNTIME_COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(RUNTIME_COLLECTION)
        bpy.context.scene.collection.children.link(coll)
    elif bpy.context.scene.collection.children.get(coll.name) is None:
        bpy.context.scene.collection.children.link(coll)
    return coll


def _library_catalog() -> tuple[set[str], set[str]]:
    path = require_library()
    with bpy.data.libraries.load(str(path), link=False) as (data_from, _data_to):
        return set(data_from.objects), set(data_from.collections)


def validate_library_catalog(*, fdis: Iterable[int] | None = None) -> dict[str, Any]:
    """Cheap structural validation without appending the whole .blend."""
    object_names, collection_names = _library_catalog()
    fdis = tuple(fdis or dental_assets.initial_prosthetic_fdis())
    missing: dict[int, list[str]] = {}
    optional_missing: dict[int, list[str]] = {}
    for raw_fdi in fdis:
        fdi = dental_assets.normalize_fdi(raw_fdi, include_primary=False)
        required = [
            dental_assets.object_name(fdi, "CROWN_TEMPLATE"),
            dental_assets.object_name(fdi, "TOOTH_FRAME"),
            *[
                dental_assets.object_name(fdi, "LANDMARK", landmark=name)
                for name in dental_assets.required_landmarks(fdi)
            ],
            dental_assets.object_name(fdi, "EMERGENCE_REGION"),
            dental_assets.object_name(fdi, "EMERGENCE_CENTER"),
            dental_assets.object_name(fdi, "PROSTHETIC_AXIS"),
        ]
        absent = [name for name in required if name not in object_names]
        family_collection = dental_assets.library_family_collection_name(fdi)
        if family_collection not in collection_names:
            absent.append(family_collection)
        if absent:
            missing[fdi] = absent
        tooth_template = dental_assets.object_name(fdi, "TOOTH_TEMPLATE")
        if tooth_template not in object_names:
            optional_missing.setdefault(fdi, []).append(tooth_template)
    return {
        "path": str(library_path()),
        "contract_sha256": dental_assets.contract_sha256(),
        "checked_fdi": list(fdis),
        "ok": not bool(missing),
        "missing": missing,
        "optional_missing": optional_missing,
        "tooth_template_policy": "OPTIONAL_CBCT_REFERENCE_NOT_REQUIRED_FOR_PROSTHETIC_MAPPING",
    }


def _append_objects(names: list[str]) -> list[bpy.types.Object]:
    """Append exact object datablocks and return the resulting references."""
    path = require_library()
    catalog, _ = _library_catalog()
    absent = [name for name in names if name not in catalog]
    if absent:
        raise dental_assets.DentalAssetContractError(
            "Dental library missing objects: " + ", ".join(absent)
        )
    with bpy.data.libraries.load(str(path), link=False) as (_from, data_to):
        data_to.objects = list(names)
    loaded = [obj for obj in data_to.objects if obj is not None]
    if len(loaded) != len(names):
        raise RuntimeError(f"Could not append all requested dental library objects ({len(loaded)}/{len(names)})")
    return loaded


def _remove_temporary_objects(objects: Iterable[bpy.types.Object]) -> None:
    for obj in list(objects):
        if obj is None:
            continue
        data = getattr(obj, "data", None)
        bpy.data.objects.remove(obj, do_unlink=True)
        if data is not None and getattr(data, "users", 1) == 0:
            if isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)
            elif isinstance(data, bpy.types.Curve):
                bpy.data.curves.remove(data)


def _matrix_tuple(matrix: Matrix) -> tuple[float, ...]:
    return tuple(float(matrix[r][c]) for r in range(4) for c in range(4))


def _mesh_snapshot(obj: bpy.types.Object, anchor_inv: Matrix) -> tuple[
    tuple[tuple[float, float, float], ...], tuple[tuple[int, ...], ...]
]:
    if obj.type != "MESH" or obj.data is None:
        return (), ()
    transform = anchor_inv @ obj.matrix_world
    vertices = tuple(tuple(float(v) for v in (transform @ vertex.co)) for vertex in obj.data.vertices)
    faces = tuple(tuple(int(i) for i in poly.vertices) for poly in obj.data.polygons)
    return vertices, faces


def read_family_reference_snapshot(
    fdi: int,
    *,
    anchor_role: str = "TOOTH_TEMPLATE",
    include_optional_landmarks: bool = True,
) -> FamilyReferenceSnapshot:
    """Read library semantics without leaving landmark/frame assets in the scene.

    This avoids the intentional runtime name collision between library landmarks
    and patient landmarks: both use the same canonical LANDMARK role/name because
    the contract models one semantic landmark per FDI family.
    """
    fdi = dental_assets.normalize_fdi(fdi, include_primary=False)
    anchor_role = str(anchor_role).upper()
    anchor_name = dental_assets.object_name(fdi, anchor_role)
    names = [anchor_name, dental_assets.object_name(fdi, "TOOTH_FRAME")]
    landmarks = list(dental_assets.required_landmarks(fdi))
    if include_optional_landmarks:
        landmarks.extend(dental_assets.optional_landmarks(fdi))
    names.extend(dental_assets.object_name(fdi, "LANDMARK", landmark=lm) for lm in landmarks)
    for role in ("EMERGENCE_REGION", "EMERGENCE_CENTER", "PROSTHETIC_AXIS", "CERVICAL_PROFILE"):
        name = dental_assets.object_name(fdi, role)
        # CERVICAL_PROFILE is optional. Avoid failing before knowing catalog.
        names.append(name)

    catalog, _ = _library_catalog()
    required_names = [
        anchor_name,
        dental_assets.object_name(fdi, "TOOTH_FRAME"),
        *[dental_assets.object_name(fdi, "LANDMARK", landmark=lm) for lm in dental_assets.required_landmarks(fdi)],
    ]
    missing = [name for name in required_names if name not in catalog]
    if missing:
        raise dental_assets.DentalAssetContractError(
            f"FDI {fdi} library reference incomplete: {', '.join(missing)}"
        )
    names = [name for name in names if name in catalog]

    loaded = _append_objects(names)
    try:
        by_requested = dict(zip(names, loaded))
        anchor = by_requested[anchor_name]
        # Library objects themselves must have been authored with the same contract.
        dental_asset_blender.validate_object_contract(
            anchor, expected_fdi=fdi, expected_role=anchor_role, require_canonical_name=False
        )
        anchor_inv = anchor.matrix_world.inverted_safe()
        snapshots: dict[str, ReferenceObjectSnapshot] = {}
        for requested_name, obj in by_requested.items():
            role = dental_asset_blender.object_role(obj)
            if role:
                info = dental_asset_blender.validate_object_contract(
                    obj, expected_fdi=fdi, expected_role=role, require_canonical_name=False
                )
                if info["source"] != "LIBRARY":
                    raise dental_assets.DentalAssetContractError(
                        f"{requested_name}: library asset source must be LIBRARY"
                    )
                if info["coordinate_space"] != "TEMPLATE_LOCAL":
                    raise dental_assets.DentalAssetContractError(
                        f"{requested_name}: library coordinate_space must be TEMPLATE_LOCAL"
                    )
                if role == "TOOTH_FRAME":
                    dental_asset_blender.validate_tooth_frame_object(obj, fdi=fdi)
            rel = anchor_inv @ obj.matrix_world
            verts, faces = _mesh_snapshot(obj, anchor_inv)
            snapshots[requested_name] = ReferenceObjectSnapshot(
                role=role,
                name=requested_name,
                object_type=obj.type,
                matrix_relative_to_anchor=_matrix_tuple(rel),
                location_relative_to_anchor=tuple(float(v) for v in rel.translation),
                mesh_vertices=verts,
                mesh_faces=faces,
            )
        return FamilyReferenceSnapshot(
            fdi=fdi,
            anchor_role=anchor_role,
            anchor_name=anchor_name,
            objects=snapshots,
        )
    finally:
        _remove_temporary_objects(loaded)


def load_role_template(fdi: int, role: str) -> bpy.types.Object:
    """Idempotently append one persistent library template by FDI/role."""
    fdi = dental_assets.normalize_fdi(fdi, include_primary=False)
    role = str(role).upper()
    if role not in {"TOOTH_TEMPLATE", "CROWN_TEMPLATE"}:
        raise ValueError("Only persistent TOOTH_TEMPLATE/CROWN_TEMPLATE assets are loaded directly")
    name = dental_assets.object_name(fdi, role)
    existing = bpy.data.objects.get(name)
    if existing is not None:
        dental_asset_blender.validate_object_contract(existing, expected_fdi=fdi, expected_role=role)
        return existing
    obj = _append_objects([name])[0]
    # Blender may rename on collision; collision was checked above, so enforce contract.
    if obj.name != name:
        _remove_temporary_objects([obj])
        raise dental_assets.DentalAssetContractError(
            f"Cannot load {name}: Blender renamed it to {obj.name}; resolve name collision first"
        )
    info = dental_asset_blender.validate_object_contract(obj, expected_fdi=fdi, expected_role=role)
    if info["source"] != "LIBRARY" or info["coordinate_space"] != "TEMPLATE_LOCAL":
        _remove_temporary_objects([obj])
        raise dental_assets.DentalAssetContractError(
            f"{name}: canonical library template must be source=LIBRARY and coordinate_space=TEMPLATE_LOCAL"
        )
    coll = ensure_runtime_collection()
    if coll.objects.get(obj.name) is None:
        coll.objects.link(obj)
    return obj


def load_tooth_template(fdi: int) -> bpy.types.Object:
    return load_role_template(fdi, "TOOTH_TEMPLATE")


def load_crown_template(fdi: int) -> bpy.types.Object:
    return load_role_template(fdi, "CROWN_TEMPLATE")



def read_crown_gold_standard(fdi: int) -> dict[str, Any]:
    """Read approved Gold Standard JSON from the canonical CROWN_TEMPLATE without scene pollution."""
    import json
    fdi = dental_assets.normalize_fdi(fdi, include_primary=False)
    name = dental_assets.object_name(fdi, "CROWN_TEMPLATE")
    loaded = _append_objects([name])
    try:
        crown = loaded[0]
        dental_asset_blender.validate_object_contract(
            crown, expected_fdi=fdi, expected_role="CROWN_TEMPLATE", require_canonical_name=False
        )
        raw = str(crown.get("DSG_gold_standard_json", "") or "")
        if not raw:
            return {
                "schema": "dsg.dental_gold_standard.v1",
                "fdi": fdi,
                "approval_state": str(crown.get("DSG_approval_state", "") or "UNSPECIFIED"),
                "available": False,
            }
        payload = json.loads(raw)
        payload["available"] = True
        return payload
    finally:
        _remove_temporary_objects(loaded)
