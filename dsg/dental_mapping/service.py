"""High-level DSG Dental Mapping API.

This is the facade consumed by clinical DSG modules, an external mapping engine,
and the future MCP bridge. Consumers work by FDI/role, never by parsing bpy
object names or reimplementing registration/landmark rules.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

import bpy
from mathutils import Matrix, Quaternion, Vector

from .. import dental_assets, dental_asset_blender
from . import (
    anatomic_fit,
    derived_geometry,
    emergence,
    landmark_refine,
    landmark_transfer,
    library,
    occlusal_fit,
    proximal_fit,
    registration,
    scoring,
    validation,
)


def get_dental_asset_contract() -> dict[str, Any]:
    dental_assets.assert_contract_integrity()
    return {
        "contract": dental_assets.contract(),
        "sha256": dental_assets.contract_sha256(),
        "path": dental_assets.contract_path(),
        "library_path": dental_assets.library_path(),
        "library_available": library.library_available(),
    }


def family_descriptor(fdi: int) -> dict[str, Any]:
    return dental_assets.family_descriptor(fdi)


def required_landmarks(fdi: int) -> tuple[str, ...]:
    return dental_assets.required_landmarks(fdi)


def load_tooth_template(fdi: int):
    return library.load_tooth_template(fdi)


def load_crown_template(fdi: int):
    return library.load_crown_template(fdi)


def _patient_tooth(fdi: int):
    obj = dental_asset_blender.find_one(fdi, "TOOTH")
    if obj is None:
        # Legacy scenes may not have been stamped yet.
        canonical = bpy.data.objects.get(dental_assets.object_name(fdi, "TOOTH"))
        if canonical is not None and dental_asset_blender.migrate_legacy_tooth_object(canonical):
            obj = canonical
    return obj


def _remove_ghost(obj: bpy.types.Object | None) -> None:
    if obj is None:
        return
    data = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if data is not None and getattr(data, "users", 1) == 0 and isinstance(data, bpy.types.Mesh):
        bpy.data.meshes.remove(data)


def map_patient_crown(
    fdi: int,
    patient_object: bpy.types.Object | None = None,
    *,
    registration_policy: registration.RegistrationPolicy | None = None,
    keep_ghost_on_success: bool = False,
) -> dict[str, Any]:
    """Canonical Gold Standard crown mapping pipeline: CROWN_TEMPLATE -> CROWN_GHOST -> TOOTH."""
    fdi = dental_assets.normalize_fdi(fdi, include_primary=False)
    dental_asset_blender.validate_scene_uniqueness()
    patient = patient_object or _patient_tooth(fdi)
    if patient is None:
        raise dental_assets.DentalAssetContractError(f"No patient TOOTH loaded for FDI {fdi}")
    actual = dental_asset_blender.object_fdi(patient)
    if actual == 0:
        if not dental_asset_blender.migrate_legacy_tooth_object(patient):
            raise dental_assets.DentalAssetContractError(f"{patient.name}: cannot resolve FDI family")
        actual = dental_asset_blender.object_fdi(patient)
    if actual != fdi:
        raise dental_assets.DentalAssetContractError(f"{patient.name}: FDI {actual} != requested {fdi}")

    gold = library.read_crown_gold_standard(fdi)
    if str(gold.get("approval_state", "")).upper() != "APPROVED":
        raise dental_assets.DentalAssetContractError(
            f"FDI {fdi}: CROWN_TEMPLATE Gold Standard is not APPROVED"
        )
    reference = library.read_family_reference_snapshot(fdi, anchor_role="CROWN_TEMPLATE")
    template = library.load_crown_template(fdi)
    reg = registration.register_crown_template_to_patient(
        template, patient, fdi=fdi, policy=registration_policy, keep_ghost=True
    )
    ghost = bpy.data.objects.get(str(reg.get("ghost_object", "") or ""))
    if ghost is None:
        raise RuntimeError("Registration completed without a usable CROWN_GHOST")

    if reg["state"] == "INVALID":
        patient["DSG_mapping_state"] = "INVALID"
        patient["DSG_registration_rms_mm"] = float(reg["rms_mm"])
        ghost.hide_viewport = False
        ghost.hide_render = True
        return {
            "ok": False, "state": "INVALID", "fdi": fdi, "registration": reg,
            "error": "CrownGhost registration RMS exceeds mapping policy; landmarks were not materialized",
        }

    transferred = landmark_transfer.transfer_landmarks(reference, ghost.matrix_world)
    mapped, landmark_metrics = landmark_refine.refine_landmarks(
        patient, transferred, registration_rms_mm=float(reg["rms_mm"]),
    )
    frame_matrix = None
    semantic_errors = []
    try:
        frame_matrix = derived_geometry.derive_tooth_frame_matrix(mapped)
        semantic_errors = validation.validate_frame_semantics(frame_matrix, mapped)
    except dental_assets.DentalAssetContractError as exc:
        semantic_errors = [str(exc)]

    quality = validation.quality_from_mapping(
        fdi, mapped, registration_rms_mm=float(reg["rms_mm"]),
        registration_state=str(reg["state"]), semantic_errors=semantic_errors,
    )
    metadata = {
        "schema": dental_assets.mapping_metadata_schema(),
        "mapping_scope": "CORONAL_GOLD_STANDARD",
        "gold_standard": {
            "schema": gold.get("schema"),
            "mapper_version": gold.get("mapper_version"),
            "asset_contract_sha256": gold.get("asset_contract_sha256"),
            "approval_state": gold.get("approval_state"),
            "authority": gold.get("authority"),
        },
        "registration": {
            "method": str(reg["method"]), "rms_mm": float(reg["rms_mm"]),
            "coarse_rms_mm": float(reg["coarse_rms_mm"]), "iterations": int(reg["iterations"]),
            "transform_template_to_target": list(reg["transform_template_to_target"]),
        },
        "quality": quality.as_dict(), "landmark_metrics": landmark_metrics,
    }
    payload = dental_assets.canonical_recognition_payload(
        fdi, source="DERIVED", coordinate_space="WORLD", landmarks=mapped,
        confidence=quality.global_confidence, metadata=metadata,
    )
    landmark_objects = dental_asset_blender.apply_recognition_payload(
        payload, parent=patient, replace_existing=True
    )
    for obj in landmark_objects:
        obj["DSG_authority"] = "INFERRED"
        obj["DSG_inference_source"] = "ARCHITECT_GOLD_STANDARD"

    frame_obj = None
    derived = None
    if frame_matrix is not None and not semantic_errors:
        frame_obj = derived_geometry.materialize_tooth_frame(fdi, mapped, coordinate_space="WORLD")
        frame_obj["DSG_authority"] = "DERIVED_FROM_GOLD_STANDARD"
        derived = derived_geometry.derive_geometry(fdi, mapped, frame_matrix=frame_matrix)
        derived_geometry.store_derived_geometry(patient, derived)

    dental_asset_blender.store_mapping_metadata(patient, metadata)
    patient["DSG_mapping_payload_json"] = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    patient["DSG_mapping_contract_sha256"] = dental_assets.contract_sha256()
    patient["DSG_mapping_reference_template"] = template.name
    patient["DSG_mapping_reference_role"] = "CROWN_TEMPLATE"
    patient["DSG_mapping_ghost_role"] = "CROWN_GHOST"
    patient["DSG_mapping_ghost_transform_json"] = json.dumps(list(reg["transform_template_to_target"]), separators=(",", ":"))

    if quality.state == "VALID":
        ghost.hide_viewport = True; ghost.hide_render = True
        if not keep_ghost_on_success:
            _remove_ghost(ghost); ghost_name = ""
        else:
            ghost_name = ghost.name
    else:
        ghost.hide_viewport = False; ghost.hide_render = True; ghost_name = ghost.name

    dental_asset_blender.validate_scene_uniqueness()
    return {
        "ok": quality.state != "INVALID", "state": quality.state, "fdi": fdi,
        "family_id": dental_assets.family_id(fdi), "registration": reg,
        "quality": quality.as_dict(), "landmarks": payload["landmarks"],
        "landmark_objects": [obj.name for obj in landmark_objects],
        "tooth_frame": frame_obj.name if frame_obj else None, "ghost": ghost_name,
        "derived_geometry": derived, "metadata": metadata,
    }


def map_patient_tooth(*args, **kwargs) -> dict[str, Any]:
    """Backward-compatible alias. In 9.1.1 coronal semantics use CROWN_GHOST."""
    result = map_patient_crown(*args, **kwargs)
    result["compatibility_alias"] = "map_patient_tooth->map_patient_crown"
    return result

def get_landmarks(fdi: int) -> list[dict[str, Any]]:
    fdi = dental_assets.normalize_fdi(fdi, include_primary=False)
    keys = dental_assets.property_keys()
    objects = dental_asset_blender.find_family_members(fdi, role="LANDMARK")
    order = {
        name: idx for idx, name in enumerate(
            (*dental_assets.required_landmarks(fdi), *dental_assets.optional_landmarks(fdi))
        )
    }
    result = []
    for obj in objects:
        name = dental_assets.normalize_landmark_name(obj.get(keys["landmark_name"], ""))
        metrics_raw = str(obj.get("DSG_landmark_metrics_json", "") or "")
        try:
            metrics = json.loads(metrics_raw) if metrics_raw else {}
        except json.JSONDecodeError:
            metrics = {"invalid_metadata": True}
        p = obj.matrix_world.translation
        result.append({
            "name": name,
            "xyz": [float(p.x), float(p.y), float(p.z)],
            "confidence": float(obj.get(keys["landmark_confidence"], 0.0) or 0.0),
            "metrics": metrics,
        })
    result.sort(key=lambda item: order.get(item["name"], 999))
    return result


def get_tooth_frame(fdi: int):
    fdi = dental_assets.normalize_fdi(fdi, include_primary=False)
    return dental_asset_blender.find_one(fdi, "TOOTH_FRAME")


def get_mapping_quality(fdi: int) -> dict[str, Any]:
    fdi = dental_assets.normalize_fdi(fdi, include_primary=False)
    tooth = _patient_tooth(fdi)
    if tooth is None:
        return {"state": "UNMAPPED", "fdi": fdi}
    metadata = dental_asset_blender.read_mapping_metadata(tooth)
    if not metadata:
        return {"state": "UNMAPPED", "fdi": fdi}
    return {
        "fdi": fdi,
        "state": str((metadata.get("quality") or {}).get("state", "REVIEW")),
        "quality": metadata.get("quality") or {},
        "registration": metadata.get("registration") or {},
    }


def select_crown_candidate(fdi: int, context: Mapping[str, Any] | None = None):
    """Current library contains one canonical CrownTemplate per FDI family."""
    fdi = dental_assets.normalize_fdi(fdi, include_primary=False)
    crown = library.load_crown_template(fdi)
    return {
        "fdi": fdi,
        "object": crown,
        "object_name": crown.name,
        "source": "LIBRARY",
        "candidate_count": 1,
        "selection_reason": "CANONICAL_FDI_TEMPLATE",
    }


def _frame_blend(a: bpy.types.Object, b: bpy.types.Object) -> Matrix:
    origin = (a.matrix_world.translation + b.matrix_world.translation) * 0.5
    qa = a.matrix_world.to_quaternion()
    qb = b.matrix_world.to_quaternion()
    if qa.dot(qb) < 0:
        qb = Quaternion((-qb.w, -qb.x, -qb.y, -qb.z))
    q = qa.slerp(qb, 0.5)
    return Matrix.LocRotScale(origin, q, Vector((1.0, 1.0, 1.0)))


def _landmark_position(fdi: int, name: str) -> Vector | None:
    canonical = dental_assets.object_name(fdi, "LANDMARK", landmark=name)
    obj = bpy.data.objects.get(canonical)
    return obj.matrix_world.translation.copy() if obj is not None else None


def _target_frame_for_missing_site(fdi: int) -> Matrix:
    existing = get_tooth_frame(fdi)
    if existing is not None:
        return existing.matrix_world.copy()
    neighbors = dental_assets.neighbor_fdis(fdi)
    mesial_fdi, distal_fdi = neighbors["mesial"], neighbors["distal"]
    if mesial_fdi is None or distal_fdi is None:
        raise dental_assets.DentalAssetContractError(
            f"FDI {fdi}: automatic site frame requires two mapped neighbors or an explicit ToothFrame"
        )
    # Central incisors straddle a midline where +X changes semantic direction.
    if fdi % 10 == 1:
        raise dental_assets.DentalAssetContractError(
            f"FDI {fdi}: midline site frame must be provided/confirmed explicitly"
        )
    ma = get_tooth_frame(mesial_fdi)
    da = get_tooth_frame(distal_fdi)
    if ma is None or da is None:
        raise dental_assets.DentalAssetContractError(
            f"FDI {fdi}: map both neighbor ToothFrames ({mesial_fdi}, {distal_fdi}) first"
        )
    return _frame_blend(ma, da)


def fit_crown_to_neighbors(fdi: int, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    fdi = dental_assets.normalize_fdi(fdi, include_primary=False)
    context = dict(context or {})
    neighbors = dental_assets.neighbor_fdis(fdi)
    mesial_fdi = context.get("mesial_fdi", neighbors["mesial"])
    distal_fdi = context.get("distal_fdi", neighbors["distal"])
    mesial_obj = _patient_tooth(mesial_fdi) if mesial_fdi else None
    distal_obj = _patient_tooth(distal_fdi) if distal_fdi else None

    target_frame = context.get("target_frame_matrix_world")
    if target_frame is None:
        target_frame = _target_frame_for_missing_site(fdi)
    elif not isinstance(target_frame, Matrix):
        values = list(target_frame)
        if len(values) != 16:
            raise ValueError("target_frame_matrix_world requires Matrix or 16 values")
        target_frame = Matrix(tuple(tuple(float(values[r*4+c]) for c in range(4)) for r in range(4)))

    neighbor_mesial_contact = _landmark_position(mesial_fdi, "DISTAL_CONTACT") if mesial_fdi else None
    neighbor_distal_contact = _landmark_position(distal_fdi, "MESIAL_CONTACT") if distal_fdi else None
    desired = dict(context.get("desired_dimensions") or {})
    if "md_mm" not in desired and neighbor_mesial_contact is not None and neighbor_distal_contact is not None:
        desired["md_mm"] = float((neighbor_distal_contact - neighbor_mesial_contact).length)

    candidate = select_crown_candidate(fdi, context)
    target, fit_report = anatomic_fit.create_crown_target(
        fdi, candidate["object"],
        target_frame_world=target_frame,
        desired_dimensions=desired,
    )

    reference = library.read_family_reference_snapshot(fdi, anchor_role="CROWN_TEMPLATE")
    target_landmarks = []
    target_landmark_metrics = {}
    for landmark_name in (*dental_assets.required_landmarks(fdi), *dental_assets.optional_landmarks(fdi)):
        snap = reference.objects.get(dental_assets.object_name(fdi, "LANDMARK", landmark=landmark_name))
        if snap is None:
            continue
        warped_local = anatomic_fit.warp_crown_local_point(target, Vector(snap.location_relative_to_anchor))
        world_point = target.matrix_world @ warped_local
        target_landmarks.append({
            "name": landmark_name,
            "xyz": [float(world_point.x), float(world_point.y), float(world_point.z)],
            "confidence": 1.0,
        })
        target_landmark_metrics[landmark_name] = {
            "origin": "CROWN_TEMPLATE_TRANSFER",
            "refinement_method": str(fit_report.get("status", "INITIAL_AFFINE")),
            "registration_rms_mm": 0.0,
            "transfer_distance_mm": 0.0,
            "surface_distance_mm": 0.0,
            "confidence_components": {"registration": 1.0, "surface": 1.0, "semantic": 1.0},
        }
    target_payload = dental_assets.canonical_recognition_payload(
        fdi,
        source="DERIVED",
        coordinate_space="WORLD",
        landmarks=target_landmarks,
        metadata={
            "schema": dental_assets.mapping_metadata_schema(),
            "quality": {
                "complete": all(name in {item["name"] for item in target_landmarks} for name in dental_assets.required_landmarks(fdi)),
                "global_confidence": 1.0,
                "state": "REVIEW" if fit_report.get("requires_review") else "VALID",
            },
            "landmark_metrics": target_landmark_metrics,
        },
    )
    dental_asset_blender.apply_recognition_payload(
        target_payload, parent=target, replace_existing=True
    )
    target["DSG_target_landmarks_payload_json"] = json.dumps(
        target_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )

    def target_point(landmark_name: str) -> Vector:
        snap = reference.objects[dental_assets.object_name(fdi, "LANDMARK", landmark=landmark_name)]
        warped_local = anatomic_fit.warp_crown_local_point(target, Vector(snap.location_relative_to_anchor))
        return target.matrix_world @ warped_local

    mesial_contact = target_point("MESIAL_CONTACT")
    distal_contact = target_point("DISTAL_CONTACT")
    frame_ref = reference.objects[dental_assets.object_name(fdi, "TOOTH_FRAME")]
    frame_rel = Matrix(tuple(
        tuple(float(frame_ref.matrix_relative_to_anchor[r*4+c]) for c in range(4))
        for r in range(4)
    ))
    target_frame_world = target.matrix_world @ frame_rel
    x_axis = Vector((target_frame_world[0][0], target_frame_world[1][0], target_frame_world[2][0]))
    proximal_report = proximal_fit.fit_translation(
        target,
        frame_x_world=x_axis,
        mesial_neighbor=mesial_obj,
        distal_neighbor=distal_obj,
        mesial_contact_world=mesial_contact,
        distal_contact_world=distal_contact,
    )
    target["DSG_proximal_fit_json"] = json.dumps(
        proximal_report, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    # Proximal translation moves the parented target landmarks. Rebuild the
    # canonical family ToothFrame from those active semantic landmarks.
    active_landmarks = get_landmarks(fdi)
    target_frame_obj = derived_geometry.materialize_tooth_frame(
        fdi, active_landmarks, coordinate_space="WORLD"
    )
    target_derived = derived_geometry.derive_geometry(
        fdi, active_landmarks, frame_matrix=target_frame_obj.matrix_world
    )
    derived_geometry.store_derived_geometry(target, target_derived)
    quality = get_mapping_quality(fdi)
    candidate_score = scoring.crown_candidate_score(
        deformation=fit_report,
        proximal=proximal_report,
        mapping_confidence=(quality.get("quality") or {}).get("global_confidence"),
    )
    return {
        "fdi": fdi,
        "crown_target": target.name,
        "anatomic_fit": fit_report,
        "proximal_fit": proximal_report,
        "tooth_frame": target_frame_obj.name,
        "derived_geometry": target_derived,
        "score": candidate_score,
        "neighbors": {"mesial": mesial_fdi, "distal": distal_fdi},
    }


def fit_occlusion(fdi: int, antagonist: bpy.types.Object) -> dict[str, Any]:
    fdi = dental_assets.normalize_fdi(fdi, include_primary=False)
    crown = dental_asset_blender.find_one(fdi, "CROWN_TARGET")
    if crown is None:
        raise dental_assets.DentalAssetContractError(f"FDI {fdi}: fit CrownTarget to neighbors first")
    report = occlusal_fit.fit_occlusion(crown, antagonist, fdi=fdi)
    # Emergence is derived after final occlusal geometry, per pipeline contract.
    report["emergence"] = emergence.derive_emergence_assets(fdi, crown)
    return report


def get_emergence_region(fdi: int):
    return emergence.get_emergence_region(fdi)


def get_prosthetic_axis(fdi: int):
    return emergence.get_prosthetic_axis(fdi)


def _matrix_json(obj: bpy.types.Object | None):
    if obj is None:
        return None
    return [float(obj.matrix_world[r][c]) for r in range(4) for c in range(4)]


def build_implant_planning_context(fdi: int) -> dict[str, Any]:
    """JSON-safe dental/prosthetic context. Surgical anatomy is supplied elsewhere."""
    fdi = dental_assets.normalize_fdi(fdi, include_primary=False)
    tooth = _patient_tooth(fdi)
    frame = get_tooth_frame(fdi)
    crown = dental_asset_blender.find_one(fdi, "CROWN_TARGET")
    region = get_emergence_region(fdi)
    axis = get_prosthetic_axis(fdi)
    neighbors = dental_assets.neighbor_fdis(fdi)
    present_neighbors = {}
    for side, neighbor_fdi in neighbors.items():
        present_neighbors[side] = {
            "fdi": neighbor_fdi,
            "present": bool(neighbor_fdi and _patient_tooth(neighbor_fdi)),
        }
    return {
        "schema": "dsg.implant_planning_context.v1",
        "asset_contract": {
            "schema": dental_assets.schema(),
            "version": dental_assets.contract_version(),
            "sha256": dental_assets.contract_sha256(),
        },
        "family": dental_assets.family_descriptor(fdi),
        "patient_tooth": tooth.name if tooth else None,
        "mapping_quality": get_mapping_quality(fdi),
        "landmarks": get_landmarks(fdi),
        "tooth_frame_matrix_world": _matrix_json(frame),
        "neighbors": present_neighbors,
        "crown_target": crown.name if crown else None,
        "emergence_region": region.name if region else None,
        "prosthetic_axis_matrix_world": _matrix_json(axis),
        "surgical_context_source": "DSG_CBCT_RUNTIME",
        "status": "READY_FOR_SURGICAL_CONTEXT" if crown and axis else "PROSTHETIC_CONTEXT_INCOMPLETE",
    }



def get_gold_standard(fdi: int) -> dict[str, Any]:
    return library.read_crown_gold_standard(fdi)


def analyze_implant_bone_support(
    fdi: int,
    implant_name: str | None = None,
    *,
    radial_offset_mm: float = 0.75,
    axial_samples: int = 18,
    angular_samples: int = 16,
    include_samples: bool = False,
) -> dict[str, Any]:
    from . import surgical_context
    return surgical_context.analyze_implant_bone_support(
        fdi=fdi, implant_name=implant_name, radial_offset_mm=radial_offset_mm,
        axial_samples=axial_samples, angular_samples=angular_samples, include_samples=include_samples,
    )


def analyze_implant_neighbor_clearance(fdi: int, implant_name: str | None = None, required_clearance_mm: float | None = None, verification_mode: str = "FAST") -> dict[str, Any]:
    from . import surgical_context
    return surgical_context.analyze_implant_neighbor_clearance(
        fdi=fdi, implant_name=implant_name, required_clearance_mm=required_clearance_mm,
        verification_mode=verification_mode)


def analyze_interdental_space(fdi: int, implant_name: str | None = None) -> dict[str, Any]:
    from . import surgical_context
    return surgical_context.analyze_interdental_space(fdi=fdi, implant_name=implant_name)


def analyze_implant_diameter_options(fdi: int, implant_name: str | None = None, *, diameters_mm=None, clearance_mm: float = 1.5, verification_mode: str = "FAST") -> dict[str, Any]:
    from . import surgical_context
    return surgical_context.analyze_implant_diameter_options(
        fdi=fdi, implant_name=implant_name, diameters_mm=diameters_mm, clearance_mm=clearance_mm,
        verification_mode=verification_mode)


def build_full_implant_context(fdi: int, implant_name: str | None = None) -> dict[str, Any]:
    from . import surgical_context
    base = build_implant_planning_context(fdi)
    return surgical_context.enrich_implant_context(base, fdi=fdi, implant_name=implant_name)


def prepare_implant_axis_from_prosthetic_context(fdi: int) -> dict[str, Any]:
    from . import surgical_context
    return surgical_context.prepare_implant_axis_from_prosthetic_context(fdi=fdi)


def evaluate_implant_candidate(fdi: int, implant_name: str | None = None, constraints: Mapping[str, Any] | None = None) -> dict[str, Any]:
    from . import surgical_context
    return surgical_context.evaluate_implant_candidate(
        fdi=fdi, implant_name=implant_name, constraints=dict(constraints or {})
    )


def apply_implant_bone_support_heatmap(
    fdi: int, implant_name: str | None = None, *, radial_offset_mm: float = 0.75,
    sampling_mode: str = "SURFACE_NORMAL_AVERAGE", ring_offsets_mm=(0.25, 0.50, 1.00),
    emission_strength: float = 0.25,
) -> dict[str, Any]:
    from . import surgical_context
    return surgical_context.apply_implant_bone_support_heatmap(
        fdi=fdi, implant_name=implant_name, radial_offset_mm=radial_offset_mm,
        sampling_mode=sampling_mode, ring_offsets_mm=ring_offsets_mm,
        emission_strength=emission_strength,
    )


def clear_implant_bone_support_heatmap(implant_name: str | None = None) -> dict[str, Any]:
    from . import surgical_context
    return surgical_context.clear_implant_bone_support_heatmap(implant_name=implant_name)
