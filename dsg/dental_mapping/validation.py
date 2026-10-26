"""Fail-fast semantic and quality validation for dental mapping."""
from __future__ import annotations

from dataclasses import dataclass, asdict
import math
from typing import Any, Iterable, Mapping

from mathutils import Matrix, Vector

from .. import dental_assets


@dataclass(slots=True)
class MappingQuality:
    state: str
    complete: bool
    global_confidence: float
    registration_rms_mm: float
    missing_required: list[str]
    semantic_errors: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _landmark_map(landmarks: Iterable[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    result = {}
    for item in landmarks:
        name = dental_assets.normalize_landmark_name(item.get("name"))
        if name in result:
            raise dental_assets.DentalAssetContractError(f"Duplicate mapped landmark: {name}")
        result[name] = item
    return result


def quality_from_mapping(
    fdi: int,
    landmarks: Iterable[Mapping[str, Any]],
    *,
    registration_rms_mm: float,
    registration_state: str,
    semantic_errors: Iterable[str] = (),
) -> MappingQuality:
    fdi = dental_assets.normalize_fdi(fdi, include_primary=False)
    items = _landmark_map(landmarks)
    missing = [name for name in dental_assets.required_landmarks(fdi) if name not in items]
    confidences = [float(item.get("confidence", 0.0)) for item in items.values()]
    if any((not math.isfinite(v) or not 0.0 <= v <= 1.0) for v in confidences):
        raise dental_assets.DentalAssetContractError("Mapped landmark confidence must be finite and in 0..1")
    global_conf = sum(confidences) / len(confidences) if confidences else 0.0
    errors = [str(v) for v in semantic_errors if str(v)]
    state = str(registration_state or "REVIEW").upper()
    if state not in dental_assets.mapping_quality_states():
        state = "REVIEW"
    if missing:
        state = "LOW_CONFIDENCE" if state != "INVALID" else state
    if errors:
        state = "REVIEW" if state == "VALID" else state
    if global_conf < 0.35 and state != "INVALID":
        state = "LOW_CONFIDENCE"
    return MappingQuality(
        state=state,
        complete=not missing,
        global_confidence=float(global_conf),
        registration_rms_mm=float(registration_rms_mm),
        missing_required=missing,
        semantic_errors=errors,
    )


def validate_frame_semantics(
    frame_matrix_world: Matrix,
    landmarks: Iterable[Mapping[str, Any]],
) -> list[str]:
    """Check semantic ordering in DSG_TOOTH_LOCAL_V1 without silently flipping axes."""
    inv = frame_matrix_world.inverted_safe()
    items = _landmark_map(landmarks)
    local = {
        name: inv @ Vector(tuple(float(v) for v in item["xyz"]))
        for name, item in items.items()
    }
    errors = []
    pairs = (
        ("MESIAL_CONTACT", "DISTAL_CONTACT", 0, "mesial must be +X of distal"),
        ("FACIAL_EQUATOR", "LINGUAL_EQUATOR", 1, "facial must be +Y of lingual"),
    )
    for positive, negative, axis, message in pairs:
        if positive in local and negative in local:
            if float(local[positive][axis] - local[negative][axis]) <= 0.05:
                errors.append(message)
    cervical = [local[name].z for name in (
        "FACIAL_CERVICAL", "LINGUAL_CERVICAL", "MESIAL_CERVICAL", "DISTAL_CERVICAL"
    ) if name in local]
    coronal_names = [
        name for name in (
            "MESIOINCISAL", "DISTOINCISAL", "CUSP_TIP", "BUCCAL_CUSP_TIP",
            "LINGUAL_PALATAL_CUSP_TIP", "CENTRAL_FOSSA", "MB_CUSP", "DB_CUSP",
            "MP_CUSP", "DP_CUSP", "ML_CUSP", "DL_CUSP"
        ) if name in local
    ]
    if cervical and coronal_names:
        cervical_z = sum(cervical) / len(cervical)
        coronal_z = sum(local[name].z for name in coronal_names) / len(coronal_names)
        if coronal_z <= cervical_z:
            errors.append("coronal/occlusal landmarks must lie in +Z from cervical references")
    return errors
