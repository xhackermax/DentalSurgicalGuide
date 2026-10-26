"""Blender adapter for the canonical DSG dental asset contract.

This module is the only place that translates the pure dental-assets contract
into Blender custom properties, object names and mesh attributes.  Clinical
modules should work by FDI/role through these helpers instead of parsing names.
"""
from __future__ import annotations

import json
import math
from typing import Any, Iterable, Mapping

import bpy
from mathutils import Matrix

from . import dental_assets

MAPPING_METADATA_KEY = "DSG_mapping_metadata_json"
MAPPING_STATE_KEY = "DSG_mapping_state"
MAPPING_CONFIDENCE_KEY = "DSG_mapping_global_confidence"
REGISTRATION_RMS_KEY = "DSG_registration_rms_mm"


def _known_role(role: str) -> str:
    role_name = str(role or "").upper().strip()
    if role_name not in dental_assets.role_names():
        raise dental_assets.DentalAssetContractError(f"Unknown dental asset role: {role!r}")
    return role_name


def stamp_object(
    obj: bpy.types.Object,
    *,
    fdi: int,
    role: str,
    source: str,
    coordinate_space: str,
    landmark: str | None = None,
    revision: str = "1",
    rename: bool = True,
) -> bpy.types.Object:
    """Stamp one Blender object with the canonical dental-family identity."""
    if obj is None:
        raise ValueError("Cannot stamp a null Blender object")
    fdi = dental_assets.normalize_fdi(fdi, include_primary=True)
    role_name = _known_role(role)
    source_name = str(source or "").upper().strip()
    space = str(coordinate_space or "").upper().strip()
    if source_name not in dental_assets.source_names():
        raise dental_assets.DentalAssetContractError(f"Unknown asset source: {source}")
    if space not in dental_assets.coordinate_spaces():
        raise dental_assets.DentalAssetContractError(f"Unknown coordinate space: {coordinate_space}")
    landmark_name = dental_assets.normalize_landmark_name(landmark) if landmark is not None else None
    name = dental_assets.object_name(fdi, role_name, landmark=landmark_name)
    aid = dental_assets.asset_id(fdi, role_name, landmark=landmark_name)

    if rename:
        existing = bpy.data.objects.get(name)
        if existing is not None and existing is not obj:
            raise dental_assets.DentalAssetContractError(f"Canonical dental asset name already in use: {name}")

    keys = dental_assets.property_keys()
    values: dict[str, Any] = {
        keys["schema"]: dental_assets.schema(),
        keys["contract_version"]: dental_assets.contract_version(),
        keys["contract_hash"]: dental_assets.contract_sha256(),
        keys["family_id"]: dental_assets.family_id(fdi),
        keys["asset_id"]: aid,
        keys["asset_role"]: role_name,
        keys["asset_source"]: source_name,
        keys["asset_revision"]: str(revision),
        keys["fdi"]: fdi,
        keys["tooth_class"]: dental_assets.tooth_class_from_fdi(fdi),
        keys["arch"]: dental_assets.arch_from_fdi(fdi),
        keys["side"]: dental_assets.side_from_fdi(fdi),
        keys["coordinate_space"]: space,
        keys["units"]: "millimetres",
        keys["frame_standard"]: "DSG_TOOTH_LOCAL_V1",
    }
    if landmark_name is not None:
        values[keys["landmark_name"]] = landmark_name

    for key, value in values.items():
        obj[str(key)] = value

    if rename:
        obj.name = name
        data = getattr(obj, "data", None)
        if data is not None:
            data.name = f"{name}_DATA"
    return obj


def object_role(obj: bpy.types.Object | None) -> str:
    if obj is None:
        return ""
    return str(obj.get(dental_assets.property_keys()["asset_role"], "") or "").upper()


def object_family_id(obj: bpy.types.Object | None) -> str:
    if obj is None:
        return ""
    return str(obj.get(dental_assets.property_keys()["family_id"], "") or "")


def object_fdi(obj: bpy.types.Object | None) -> int:
    if obj is None:
        return 0
    key = dental_assets.property_keys()["fdi"]
    try:
        fdi = int(obj.get(key, obj.get("DSG_fdi_number", 0)) or 0)
    except (TypeError, ValueError):
        return 0
    return fdi if dental_assets.valid_fdi(fdi, include_primary=True) else 0


def object_coordinate_space(obj: bpy.types.Object | None) -> str:
    if obj is None:
        return ""
    return str(obj.get(dental_assets.property_keys()["coordinate_space"], "") or "").upper()


def is_family_object(
    obj: bpy.types.Object | None,
    *,
    fdi: int | None = None,
    role: str | None = None,
) -> bool:
    if obj is None:
        return False
    actual_fdi = object_fdi(obj)
    if actual_fdi == 0:
        return False
    if fdi is not None and actual_fdi != dental_assets.normalize_fdi(fdi, include_primary=True):
        return False
    if role is not None and object_role(obj) != str(role).upper():
        return False
    schema_key = dental_assets.property_keys()["schema"]
    return str(obj.get(schema_key, "") or "") == dental_assets.schema()


def validate_object_contract(
    obj: bpy.types.Object,
    *,
    expected_fdi: int | None = None,
    expected_role: str | None = None,
    require_canonical_name: bool = True,
    migrate_additive_v1: bool = True,
) -> dict[str, Any]:
    """Fail-fast validation of one persisted dental asset.

    Additive v1 scene metadata from DSG 9.0 may be restamped to the current
    contract hash. External payloads do not use this migration path.
    """
    if obj is None:
        raise dental_assets.DentalAssetContractError("Dental asset object is missing")
    keys = dental_assets.property_keys()
    if str(obj.get(keys["schema"], "") or "") != dental_assets.schema():
        raise dental_assets.DentalAssetContractError(f"{obj.name}: asset schema mismatch")
    try:
        version = int(obj.get(keys["contract_version"], 0))
    except (TypeError, ValueError) as exc:
        raise dental_assets.DentalAssetContractError(f"{obj.name}: invalid contract version") from exc
    if version != dental_assets.contract_version():
        raise dental_assets.DentalAssetContractError(f"{obj.name}: dental contract version mismatch")

    fdi = object_fdi(obj)
    if not fdi:
        raise dental_assets.DentalAssetContractError(f"{obj.name}: invalid/missing FDI")
    if expected_fdi is not None and fdi != dental_assets.normalize_fdi(expected_fdi, include_primary=True):
        raise dental_assets.DentalAssetContractError(f"{obj.name}: FDI mismatch")

    role = object_role(obj)
    _known_role(role)
    if expected_role is not None and role != _known_role(expected_role):
        raise dental_assets.DentalAssetContractError(f"{obj.name}: role {role} != {expected_role}")

    if str(obj.get(keys["family_id"], "") or "") != dental_assets.family_id(fdi):
        raise dental_assets.DentalAssetContractError(f"{obj.name}: family_id mismatch")
    landmark = None
    if role == "LANDMARK":
        landmark = dental_assets.normalize_landmark_name(obj.get(keys["landmark_name"], ""))
    expected_name = dental_assets.object_name(fdi, role, landmark=landmark)
    expected_aid = dental_assets.asset_id(fdi, role, landmark=landmark)
    if str(obj.get(keys["asset_id"], "") or "") != expected_aid:
        raise dental_assets.DentalAssetContractError(f"{obj.name}: asset_id mismatch")
    if require_canonical_name and obj.name != expected_name:
        raise dental_assets.DentalAssetContractError(f"{obj.name}: canonical name must be {expected_name}")

    expected_derived = {
        keys["tooth_class"]: dental_assets.tooth_class_from_fdi(fdi),
        keys["arch"]: dental_assets.arch_from_fdi(fdi),
        keys["side"]: dental_assets.side_from_fdi(fdi),
    }
    for key, expected in expected_derived.items():
        if str(obj.get(key, "") or "") != expected:
            raise dental_assets.DentalAssetContractError(f"{obj.name}: derived property {key} must be {expected}")

    space = object_coordinate_space(obj)
    if space not in dental_assets.coordinate_spaces():
        raise dental_assets.DentalAssetContractError(f"{obj.name}: invalid coordinate space {space!r}")

    source = str(obj.get(keys["asset_source"], "") or "").upper()
    if source not in dental_assets.source_names():
        raise dental_assets.DentalAssetContractError(f"{obj.name}: invalid asset source {source!r}")

    supplied_hash = str(obj.get(keys["contract_hash"], "") or "").lower()
    current_hash = dental_assets.contract_sha256().lower()
    migrated = False
    if supplied_hash != current_hash:
        if not (migrate_additive_v1 and supplied_hash in dental_assets.accepted_previous_hashes()):
            raise dental_assets.DentalAssetContractError(f"{obj.name}: dental contract hash mismatch")
        # Safe additive migration: identity/naming/derived semantics were already
        # validated above. No geometry or clinical identity is changed.
        obj[keys["contract_hash"]] = current_hash
        obj[keys["units"]] = "millimetres"
        obj[keys["frame_standard"]] = "DSG_TOOTH_LOCAL_V1"
        migrated = True

    units = str(obj.get(keys["units"], "") or "")
    frame_standard = str(obj.get(keys["frame_standard"], "") or "")
    if not units and migrate_additive_v1:
        obj[keys["units"]] = "millimetres"
        units = "millimetres"
        migrated = True
    if not frame_standard and migrate_additive_v1:
        obj[keys["frame_standard"]] = "DSG_TOOTH_LOCAL_V1"
        frame_standard = "DSG_TOOTH_LOCAL_V1"
        migrated = True
    if units != "millimetres":
        raise dental_assets.DentalAssetContractError(f"{obj.name}: units must be millimetres")
    if frame_standard != "DSG_TOOTH_LOCAL_V1":
        raise dental_assets.DentalAssetContractError(
            f"{obj.name}: frame standard must be DSG_TOOTH_LOCAL_V1"
        )

    return {
        "name": obj.name,
        "fdi": fdi,
        "family_id": dental_assets.family_id(fdi),
        "role": role,
        "coordinate_space": space,
        "source": source,
        "migrated_additive_v1": migrated,
    }

def find_family_members(fdi: int, *, role: str | None = None, scene=None) -> list[bpy.types.Object]:
    fdi = dental_assets.normalize_fdi(fdi, include_primary=True)
    scene = scene or getattr(bpy.context, "scene", None)
    result = []
    for obj in bpy.data.objects:
        if not is_family_object(obj, fdi=fdi, role=role):
            continue
        if scene is not None and scene.objects.get(obj.name) is not obj:
            continue
        result.append(obj)
    result.sort(key=lambda item: (object_role(item), item.name))
    return result


def find_one(fdi: int, role: str, *, scene=None):
    matches = find_family_members(fdi, role=role, scene=scene)
    return matches[-1] if matches else None


def migrate_legacy_tooth_object(obj: bpy.types.Object, *, source: str = "CBCT_TOTALSEGMENTATOR") -> bool:
    """Stamp an existing pre-contract DSG tooth without renaming it."""
    if obj is None or getattr(obj, "type", "") != "MESH":
        return False
    try:
        fdi = int(obj.get("DSG_fdi_number", 0) or 0)
    except (TypeError, ValueError):
        return False
    if not dental_assets.valid_fdi(fdi, include_primary=True):
        return False
    stamp_object(
        obj,
        fdi=fdi,
        role="TOOTH",
        source=source,
        coordinate_space=str(obj.get("DSG_coordinate_space", "CBCT_DSG_ROOT") or "CBCT_DSG_ROOT"),
        rename=False,
    )
    return True


def stamp_landmark_confidence(obj: bpy.types.Object, confidence: float) -> None:
    value = float(confidence)
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError("landmark confidence must be finite and in 0..1")
    obj[dental_assets.property_keys()["landmark_confidence"]] = value



def migrate_legacy_landmark_object(
    obj: bpy.types.Object,
    *,
    fdi: int | None = None,
    source: str = "USER",
    coordinate_space: str = "WORLD",
) -> bool:
    """Explicit import/scene migration for the two published legacy aliases."""
    if obj is None:
        return False
    raw_name = str(obj.get("DSG_landmark_name", "") or "")
    if not raw_name and "__" in obj.name:
        raw_name = obj.name.rsplit("__", 1)[-1]
    try:
        canonical = dental_assets.normalize_import_landmark_name(raw_name)
    except dental_assets.DentalAssetContractError:
        return False
    if canonical == str(raw_name).upper():
        return False
    resolved_fdi = int(fdi or object_fdi(obj) or 0)
    if not dental_assets.valid_fdi(resolved_fdi, include_primary=True):
        return False
    target_name = dental_assets.object_name(resolved_fdi, "LANDMARK", landmark=canonical)
    existing = bpy.data.objects.get(target_name)
    if existing is not None and existing is not obj:
        raise dental_assets.DentalAssetContractError(
            f"Cannot migrate {obj.name}: canonical landmark already exists as {target_name}"
        )
    stamp_object(
        obj,
        fdi=resolved_fdi,
        role="LANDMARK",
        landmark=canonical,
        source=source,
        coordinate_space=coordinate_space,
        rename=True,
    )
    return True

def ensure_landmark_collection(parent_collection=None):
    name = "DSG_Dental_Landmarks"
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
    parent_collection = parent_collection or getattr(getattr(bpy.context, "scene", None), "collection", None)
    if parent_collection is not None and parent_collection.children.get(collection.name) is None:
        parent_collection.children.link(collection)
    return collection


def _set_world_position_preserving_parent(obj: bpy.types.Object, xyz: Iterable[float], parent=None) -> None:
    coords = tuple(float(v) for v in xyz)
    if len(coords) != 3 or any(not math.isfinite(v) for v in coords):
        raise ValueError("Landmark xyz must contain three finite numbers")
    obj.parent = None
    obj.matrix_world.translation = coords
    if parent is not None:
        parent_inv = parent.matrix_world.inverted_safe()
        obj.parent = parent
        obj.matrix_parent_inverse = parent_inv
        # matrix_parent_inverse keeps the already assigned world transform stable.


def store_mapping_metadata(obj: bpy.types.Object, metadata: Mapping[str, Any]) -> None:
    clean = dental_assets.validate_mapping_metadata(metadata)
    obj[MAPPING_METADATA_KEY] = json.dumps(clean, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    quality = clean.get("quality") or {}
    registration = clean.get("registration") or {}
    state = str(quality.get("state", "REVIEW") or "REVIEW").upper()
    if state not in dental_assets.mapping_quality_states():
        raise dental_assets.DentalAssetContractError(f"Invalid mapping state: {state}")
    obj[MAPPING_STATE_KEY] = state
    if "global_confidence" in quality:
        obj[MAPPING_CONFIDENCE_KEY] = float(quality["global_confidence"])
    if "rms_mm" in registration:
        obj[REGISTRATION_RMS_KEY] = float(registration["rms_mm"])


def read_mapping_metadata(obj: bpy.types.Object | None) -> dict[str, Any]:
    if obj is None:
        return {}
    raw = str(obj.get(MAPPING_METADATA_KEY, "") or "")
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise dental_assets.DentalAssetContractError(f"{obj.name}: invalid mapping metadata JSON") from exc
    return dental_assets.validate_mapping_metadata(value)


def apply_recognition_payload(
    payload,
    *,
    parent: bpy.types.Object | None = None,
    collection: bpy.types.Collection | None = None,
    replace_existing: bool = True,
) -> list[bpy.types.Object]:
    """Materialize canonical landmark empties from a recognition payload.

    The payload's coordinates are interpreted in the declared DSG case-space.
    DSG case spaces are scene-space after the corresponding CBCT/IOS alignment;
    parent assignment preserves world coordinates instead of silently converting
    them to parent-local values.
    """
    clean = dental_assets.validate_recognition_payload(payload, require_complete=False)
    fdi = int(clean["fdi"])
    collection = collection or ensure_landmark_collection()
    created: list[bpy.types.Object] = []
    metrics = dict((clean.get("metadata") or {}).get("landmark_metrics") or {})

    for item in clean["landmarks"]:
        landmark = str(item["name"])
        name = dental_assets.object_name(fdi, "LANDMARK", landmark=landmark)
        obj = bpy.data.objects.get(name)
        if obj is not None and not replace_existing:
            raise dental_assets.DentalAssetContractError(f"Landmark object already exists: {name}")
        if obj is None:
            obj = bpy.data.objects.new(name, None)
            collection.objects.link(obj)
        elif collection.objects.get(obj.name) is None:
            collection.objects.link(obj)

        obj.empty_display_type = "SPHERE"
        obj.empty_display_size = 0.6
        _set_world_position_preserving_parent(obj, item["xyz"], parent=parent)
        stamp_object(
            obj,
            fdi=fdi,
            role="LANDMARK",
            landmark=landmark,
            source=str(clean["source"]),
            coordinate_space=str(clean["coordinate_space"]),
            rename=True,
        )
        stamp_landmark_confidence(obj, float(item.get("confidence", 1.0)))
        if landmark in metrics:
            obj["DSG_landmark_metrics_json"] = json.dumps(
                metrics[landmark], ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
        created.append(obj)

    if parent is not None:
        store_mapping_metadata(parent, clean.get("metadata") or {})
    return created


def ensure_point_int_attribute(
    mesh: bpy.types.Mesh,
    values: Iterable[int],
    *,
    name: str | None = None,
) -> bpy.types.Attribute:
    """Create/update the canonical POINT/INT attribute used for EOFF labels."""
    if mesh is None:
        raise ValueError("Mesh is required")
    attr_name = name or dental_assets.mesh_attribute_names().get("vertex_feature_label", "DSG_vertex_feature_label")
    vals = [int(v) for v in values]
    if len(vals) != len(mesh.vertices):
        raise ValueError(f"{attr_name}: expected {len(mesh.vertices)} values, got {len(vals)}")
    attr = mesh.attributes.get(attr_name)
    if attr is not None and (attr.domain != "POINT" or attr.data_type != "INT"):
        mesh.attributes.remove(attr)
        attr = None
    if attr is None:
        attr = mesh.attributes.new(name=attr_name, type="INT", domain="POINT")
    for item, value in zip(attr.data, vals):
        item.value = int(value)
    return attr


def read_point_int_attribute(mesh: bpy.types.Mesh, *, name: str | None = None) -> list[int]:
    if mesh is None:
        return []
    attr_name = name or dental_assets.mesh_attribute_names().get("vertex_feature_label", "DSG_vertex_feature_label")
    attr = mesh.attributes.get(attr_name)
    if attr is None:
        return []
    if attr.domain != "POINT" or attr.data_type != "INT":
        raise dental_assets.DentalAssetContractError(
            f"{mesh.name}: {attr_name} must be POINT/INT, got {attr.domain}/{attr.data_type}"
        )
    return [int(item.value) for item in attr.data]


def validate_tooth_frame_object(frame: bpy.types.Object, *, fdi: int | None = None) -> dict[str, Any]:
    info = validate_object_contract(frame, expected_fdi=fdi, expected_role="TOOTH_FRAME")
    matrix = Matrix(frame.matrix_world)
    det = float(matrix.to_3x3().determinant())
    if not math.isfinite(det) or det <= 1.0e-8:
        raise dental_assets.DentalAssetContractError(f"{frame.name}: ToothFrame is not right-handed")
    info["determinant"] = det
    return info




def validate_scene_uniqueness(scene=None) -> dict[str, int]:
    """Reject duplicate canonical asset IDs even if Blender auto-added .001 names."""
    scene = scene or getattr(bpy.context, "scene", None)
    objects = list(scene.objects) if scene is not None else list(bpy.data.objects)
    keys = dental_assets.property_keys()
    seen: dict[str, bpy.types.Object] = {}
    checked = 0
    for obj in objects:
        if not is_family_object(obj):
            continue
        checked += 1
        aid = str(obj.get(keys["asset_id"], "") or "")
        if not aid:
            raise dental_assets.DentalAssetContractError(f"{obj.name}: missing asset_id")
        previous = seen.get(aid)
        if previous is not None and previous is not obj:
            raise dental_assets.DentalAssetContractError(
                f"Duplicate canonical dental asset_id {aid}: {previous.name} / {obj.name}"
            )
        seen[aid] = obj
    return {"checked": checked, "unique_asset_ids": len(seen)}

def migrate_scene_assets(scene=None) -> dict[str, int]:
    """Idempotent additive migration for saved DSG 9.x scenes."""
    scene = scene or getattr(bpy.context, "scene", None)
    migrated = {"tooth": 0, "landmark_alias": 0, "contract_metadata": 0}
    objects = list(scene.objects) if scene is not None else list(bpy.data.objects)
    for obj in objects:
        # Pre-contract teeth keep their canonical scene names and clinical props.
        if obj.name.startswith("DSG_Tooth_FDI_") and not is_family_object(obj):
            if migrate_legacy_tooth_object(obj):
                migrated["tooth"] += 1
                continue
        # Explicit old landmark aliases only.
        if "__CENTRAL_GROOVE_CENTER" in obj.name or "__DISTAL_CUSP_OPTIONAL" in obj.name:
            if migrate_legacy_landmark_object(obj):
                migrated["landmark_alias"] += 1
                continue
        # Additive contract v1 metadata/hash migration. Validation performs the
        # restamp only after identity and canonical semantics are confirmed.
        if is_family_object(obj):
            try:
                info = validate_object_contract(
                    obj, require_canonical_name=False, migrate_additive_v1=True
                )
            except dental_assets.DentalAssetContractError:
                continue
            if info.get("migrated_additive_v1"):
                migrated["contract_metadata"] += 1
    return migrated

def family_snapshot(fdi: int, *, scene=None) -> dict[str, Any]:
    """CQS query: immutable-ish JSON-safe view of one loaded dental family."""
    fdi = dental_assets.normalize_fdi(fdi, include_primary=True)
    members = []
    for obj in find_family_members(fdi, scene=scene):
        info = validate_object_contract(obj, expected_fdi=fdi, require_canonical_name=False)
        info["canonical_name"] = dental_assets.object_name(
            fdi, info["role"],
            landmark=obj.get(dental_assets.property_keys()["landmark_name"]) if info["role"] == "LANDMARK" else None,
        )
        members.append(info)
    return {"family": dental_assets.family_descriptor(fdi), "members": members}
