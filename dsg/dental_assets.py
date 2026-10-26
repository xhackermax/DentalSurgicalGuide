"""Canonical DSG dental asset family contract.

Pure-Python module shared by DSG clinical code and external dental-recognition
engines.  The JSON manifest under ``resources/dental_assets`` is the SSOT for
asset names, roles, landmark identifiers and the tooth-local coordinate frame.

No Blender imports are allowed here.
"""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping
import math

CONTRACT_FILENAME = "asset_contract_v1.json"
EXPECTED_SCHEMA = "dsg.dental_assets.v1"
RECOGNITION_SCHEMA = "dsg.dental_recognition.v1"
MAPPING_METADATA_SCHEMA = "dsg.dental_mapping.metadata.v1"

# Import-only aliases. Canonical output never uses these names.
LEGACY_LANDMARK_ALIASES = {
    "CENTRAL_GROOVE_CENTER": "CENTRAL_FOSSA",
    "DISTAL_CUSP_OPTIONAL": "DISTAL_CUSP",
}


class DentalAssetContractError(ValueError):
    """Raised when a dental asset or contract violates the shared schema."""


def _contract_path() -> Path:
    return Path(__file__).resolve().parent / "resources" / "dental_assets" / CONTRACT_FILENAME


@lru_cache(maxsize=1)
def _load_contract() -> dict[str, Any]:
    path = _contract_path()
    if not path.is_file():
        raise DentalAssetContractError(f"Missing DSG dental asset contract: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise DentalAssetContractError(f"Invalid DSG dental asset contract JSON: {exc}") from exc
    _validate_contract(data)
    return data


def contract() -> dict[str, Any]:
    """Return a defensive copy of the canonical contract."""
    return deepcopy(_load_contract())


def contract_path() -> str:
    return str(_contract_path())


def contract_version() -> int:
    return int(_load_contract()["contract_version"])


@lru_cache(maxsize=1)
def contract_sha256() -> str:
    return hashlib.sha256(_contract_path().read_bytes()).hexdigest()


def schema() -> str:
    return str(_load_contract()["schema"])


def property_keys() -> Mapping[str, str]:
    return dict(_load_contract()["property_keys"])


def role_names() -> tuple[str, ...]:
    return tuple(_load_contract()["roles"].keys())


def coordinate_spaces() -> tuple[str, ...]:
    return tuple(_load_contract()["coordinate_spaces"])


def source_names() -> tuple[str, ...]:
    return tuple(_load_contract()["sources"])


def coordinate_frame() -> dict[str, Any]:
    """Return the definitive DSG_TOOTH_LOCAL_V1 frame descriptor."""
    return dict(_load_contract()["coordinate_frame"])


def mesh_attribute_names() -> dict[str, str]:
    return dict(_load_contract().get("mesh_attributes", {}))


def derived_geometry_names() -> tuple[str, ...]:
    return tuple((_load_contract().get("derived_geometry") or {}).keys())


def mapping_quality_states() -> tuple[str, ...]:
    return tuple(_load_contract().get("mapping_quality_states", ("VALID", "REVIEW", "LOW_CONFIDENCE", "INVALID")))


def mapping_metadata_schema() -> str:
    return str(_load_contract().get("mapping_metadata_schema", MAPPING_METADATA_SCHEMA))


def accepted_previous_hashes() -> tuple[str, ...]:
    values = ((_load_contract().get("compatibility") or {}).get("accepted_previous_hashes") or ())
    return tuple(str(v).lower() for v in values)


def verify_contract_sidecar() -> bool:
    """Fail-fast verification for packaged JSON/sha256 copies."""
    sidecar = _contract_path().with_suffix(".sha256")
    if not sidecar.is_file():
        raise DentalAssetContractError(f"Missing DSG dental contract hash sidecar: {sidecar}")
    expected = sidecar.read_text(encoding="utf-8").strip().split()[0].lower()
    actual = contract_sha256().lower()
    if expected != actual:
        raise DentalAssetContractError(f"Dental asset contract sidecar mismatch: {expected} != {actual}")
    return True


def valid_fdi(value: Any, *, include_primary: bool = True) -> bool:
    try:
        fdi = int(value)
    except Exception:
        return False
    quadrant, position = divmod(fdi, 10)
    if quadrant in (1, 2, 3, 4) and 1 <= position <= 8:
        return True
    if include_primary and quadrant in (5, 6, 7, 8) and 1 <= position <= 5:
        return True
    return False


def normalize_fdi(value: Any, *, include_primary: bool = True) -> int:
    try:
        fdi = int(value)
    except Exception as exc:
        raise DentalAssetContractError(f"FDI is not an integer: {value!r}") from exc
    if not valid_fdi(fdi, include_primary=include_primary):
        suffix = " or primary 51-85" if include_primary else ""
        raise DentalAssetContractError(f"Invalid FDI {fdi}; expected permanent FDI 11-48{suffix}")
    return fdi


def arch_from_fdi(value: Any) -> str:
    try:
        q = int(value) // 10
    except Exception:
        return "UNKNOWN"
    if q in (1, 2, 5, 6):
        return "MAXILLA"
    if q in (3, 4, 7, 8):
        return "MANDIBLE"
    return "UNKNOWN"


def side_from_fdi(value: Any) -> str:
    try:
        q = int(value) // 10
    except Exception:
        return "UNKNOWN"
    if q in (1, 4, 5, 8):
        return "RIGHT"
    if q in (2, 3, 6, 7):
        return "LEFT"
    return "UNKNOWN"


def neighbor_fdis(value: Any) -> dict[str, int | None]:
    """Return nominal mesial/distal family neighbors from FDI identity only.

    This is topology of the dental arch, not an assertion that those teeth are
    present. Actual patient neighbors must be resolved against the scene/IOS.
    """
    fdi = normalize_fdi(value, include_primary=False)
    q, p = divmod(fdi, 10)
    if p == 1:
        opposite_midline = {1: 2, 2: 1, 3: 4, 4: 3}[q] * 10 + 1
        mesial = opposite_midline
    else:
        mesial = q * 10 + (p - 1)
    distal = q * 10 + (p + 1) if p < 8 else None
    return {"mesial": mesial, "distal": distal}


def tooth_class_from_fdi(value: Any) -> str:
    fdi = normalize_fdi(value, include_primary=True)
    quadrant, position = divmod(fdi, 10)
    table_name = "primary_tooth_class_by_position" if quadrant in (5, 6, 7, 8) else "tooth_class_by_position"
    return str(_load_contract()[table_name].get(str(position), "UNKNOWN"))


def family_id(value: Any) -> str:
    fdi = normalize_fdi(value, include_primary=True)
    return str(_load_contract()["family_pattern"]).format(fdi=fdi)


def _normalize_role(role: Any) -> str:
    role_name = str(role or "").upper().strip()
    if role_name not in _load_contract()["roles"]:
        raise DentalAssetContractError(
            f"Unknown DSG dental asset role {role!r}; expected one of {', '.join(role_names())}"
        )
    return role_name


def normalize_landmark_name(name: Any) -> str:
    """Normalize a canonical landmark name.

    Legacy aliases are deliberately rejected here so new objects/payloads never
    emit two dialects. Use :func:`normalize_import_landmark_name` only at a
    migration/import boundary.
    """
    landmark = str(name or "").strip().upper()
    if landmark not in _load_contract()["landmarks"]:
        raise DentalAssetContractError(f"Unknown DSG dental landmark: {name!r}")
    return landmark


def normalize_import_landmark_name(name: Any) -> str:
    landmark = str(name or "").strip().upper()
    aliases = dict((_load_contract().get("legacy_import_aliases") or {}).get("landmarks", {}))
    landmark = str(aliases.get(landmark, LEGACY_LANDMARK_ALIASES.get(landmark, landmark)))
    return normalize_landmark_name(landmark)


def asset_id(fdi: Any, role: Any, *, landmark: Any | None = None) -> str:
    fdi = normalize_fdi(fdi, include_primary=True)
    role_name = _normalize_role(role)
    base = str(_load_contract()["asset_id_pattern"]).format(fdi=fdi, role=role_name)
    if role_name == "LANDMARK":
        if landmark is None:
            raise DentalAssetContractError("LANDMARK asset_id requires landmark name")
        return f"{base}.{normalize_landmark_name(landmark)}"
    if landmark is not None:
        raise DentalAssetContractError(f"Role {role_name} does not accept a landmark name")
    return base




def object_prefix(role: Any) -> str:
    role_name = _normalize_role(role)
    pattern = str(_load_contract()["naming"].get(role_name, ""))
    token = "{fdi:02d}"
    if token not in pattern:
        raise DentalAssetContractError(f"Role {role_name} has no FDI naming token")
    return pattern.split(token, 1)[0]


def object_name(fdi: Any, role: Any, *, landmark: Any | None = None) -> str:
    fdi = normalize_fdi(fdi, include_primary=True)
    role_name = _normalize_role(role)
    pattern = str(_load_contract()["naming"].get(role_name, ""))
    if not pattern:
        raise DentalAssetContractError(f"No canonical object-name pattern for role {role_name}")
    if role_name == "LANDMARK":
        if landmark is None:
            raise DentalAssetContractError("LANDMARK object name requires landmark name")
        return pattern.format(fdi=fdi, landmark=normalize_landmark_name(landmark))
    if landmark is not None:
        raise DentalAssetContractError(f"Role {role_name} does not accept landmark")
    return pattern.format(fdi=fdi)


def required_landmarks(fdi: Any) -> tuple[str, ...]:
    """Required canonical landmark names for one tooth family.

    The contract intentionally distinguishes required names from optional
    anatomy.  For example ``DISTAL_CUSP`` is optional in mandibular molars.
    """
    fdi = normalize_fdi(fdi, include_primary=True)
    data = _load_contract()
    cls = tooth_class_from_fdi(fdi)
    groups = ["UNIVERSAL", cls]
    if cls == "MOLAR":
        groups.append("MAXILLARY_MOLAR" if arch_from_fdi(fdi) == "MAXILLA" else "MANDIBULAR_MOLAR")
    out: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for name in data["landmark_sets"].get(group, ()):
            name = normalize_landmark_name(name)
            if name not in seen:
                out.append(name)
                seen.add(name)
    return tuple(out)


def optional_landmarks(fdi: Any) -> tuple[str, ...]:
    fdi = normalize_fdi(fdi, include_primary=True)
    data = _load_contract()
    if tooth_class_from_fdi(fdi) == "MOLAR" and arch_from_fdi(fdi) == "MANDIBLE":
        return tuple(normalize_landmark_name(v) for v in data["landmark_sets"].get("MANDIBULAR_MOLAR_OPTIONAL", ()))
    return ()


def all_landmarks() -> tuple[str, ...]:
    return tuple(_load_contract()["landmarks"].keys())




def library_filename() -> str:
    return str(_load_contract()["library_layout"]["blend_filename"])


def library_path() -> str:
    return str(_contract_path().parent / library_filename())


def library_family_collection_name(fdi: Any) -> str:
    fdi = normalize_fdi(fdi, include_primary=True)
    return str(_load_contract()["library_layout"]["family_collection_pattern"]).format(fdi=fdi)


def initial_prosthetic_fdis() -> tuple[int, ...]:
    values = _load_contract()["initial_prosthetic_library"]["included_permanent_fdi"]
    return tuple(int(v) for v in values)


def deferred_prosthetic_fdis() -> tuple[int, ...]:
    values = _load_contract()["initial_prosthetic_library"]["deferred_permanent_fdi"]
    return tuple(int(v) for v in values)


def family_descriptor(fdi: Any) -> dict[str, Any]:
    fdi = normalize_fdi(fdi, include_primary=True)
    return {
        "schema": schema(),
        "contract_version": contract_version(),
        "contract_sha256": contract_sha256(),
        "numbering_system": "FDI_ISO_3950",
        "family_id": family_id(fdi),
        "fdi": fdi,
        "tooth_class": tooth_class_from_fdi(fdi),
        "arch": arch_from_fdi(fdi),
        "side": side_from_fdi(fdi),
        "coordinate_frame": coordinate_frame(),
        "library_collection": library_family_collection_name(fdi),
        "required_landmarks": list(required_landmarks(fdi)),
        "optional_landmarks": list(optional_landmarks(fdi)),
        "objects": {
            role: object_name(fdi, role)
            for role in role_names()
            if role != "LANDMARK"
        },
        "landmark_objects": {
            name: object_name(fdi, "LANDMARK", landmark=name)
            for name in (*required_landmarks(fdi), *optional_landmarks(fdi))
        },
    }


def validate_mapping_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """Validate optional recognition/mapping metadata without creating v2.

    v1 remains transport-compatible: registration/refinement audit information
    lives under metadata until it proves necessary as required top-level data.
    """
    if metadata is None:
        return {}
    if not isinstance(metadata, Mapping):
        raise DentalAssetContractError("Recognition metadata must be an object")
    clean = deepcopy(dict(metadata))
    registration = clean.get("registration")
    if registration is not None:
        if not isinstance(registration, Mapping):
            raise DentalAssetContractError("metadata.registration must be an object")
        if "rms_mm" in registration:
            rms = float(registration["rms_mm"])
            if not math.isfinite(rms) or rms < 0:
                raise DentalAssetContractError("registration.rms_mm must be finite and >= 0")
        if "transform_template_to_target" in registration:
            matrix = registration["transform_template_to_target"]
            if not isinstance(matrix, (list, tuple)) or len(matrix) != 16:
                raise DentalAssetContractError("registration transform must contain 16 numbers")
            for value in matrix:
                if not math.isfinite(float(value)):
                    raise DentalAssetContractError("registration transform contains non-finite value")
    quality = clean.get("quality")
    if quality is not None:
        if not isinstance(quality, Mapping):
            raise DentalAssetContractError("metadata.quality must be an object")
        if "global_confidence" in quality:
            value = float(quality["global_confidence"])
            if not 0.0 <= value <= 1.0:
                raise DentalAssetContractError("quality.global_confidence must be 0..1")
        if "state" in quality and str(quality["state"]).upper() not in mapping_quality_states():
            raise DentalAssetContractError("metadata.quality.state is not canonical")
    lm_metrics = clean.get("landmark_metrics")
    if lm_metrics is not None:
        if not isinstance(lm_metrics, Mapping):
            raise DentalAssetContractError("metadata.landmark_metrics must be an object")
        normalized = {}
        for raw_name, raw_metrics in lm_metrics.items():
            name = normalize_import_landmark_name(raw_name)
            if not isinstance(raw_metrics, Mapping):
                raise DentalAssetContractError(f"Metrics for {name} must be an object")
            metrics = dict(raw_metrics)
            for key in ("transfer_distance_mm", "surface_distance_mm", "registration_rms_mm"):
                if key in metrics:
                    value = float(metrics[key])
                    if not math.isfinite(value) or value < 0:
                        raise DentalAssetContractError(f"{name}.{key} must be finite and >=0")
                    metrics[key] = value
            components = metrics.get("confidence_components")
            if components is not None:
                if not isinstance(components, Mapping):
                    raise DentalAssetContractError(f"{name}.confidence_components must be an object")
                metrics["confidence_components"] = {str(k): float(v) for k, v in components.items()}
                for key, value in metrics["confidence_components"].items():
                    if not 0.0 <= value <= 1.0:
                        raise DentalAssetContractError(f"{name}.confidence_components.{key} must be 0..1")
            normalized[name] = metrics
        clean["landmark_metrics"] = normalized
    return clean


def canonical_recognition_payload(
    fdi: Any,
    *,
    source: str,
    coordinate_space: str,
    landmarks: Iterable[Mapping[str, Any]],
    confidence: float | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a strict payload accepted by DSG from an external recognition engine."""
    fdi = normalize_fdi(fdi, include_primary=True)
    source_name = str(source or "").upper()
    if source_name not in source_names():
        raise DentalAssetContractError(f"Unknown recognition source: {source}")
    space = str(coordinate_space or "").upper()
    if space not in coordinate_spaces():
        raise DentalAssetContractError(f"Unknown coordinate space: {coordinate_space}")
    clean_landmarks = []
    seen = set()
    for item in landmarks:
        name = normalize_landmark_name(item.get("name"))
        if name in seen:
            raise DentalAssetContractError(f"Duplicate landmark {name}")
        xyz = item.get("xyz")
        if not isinstance(xyz, (list, tuple)) or len(xyz) != 3:
            raise DentalAssetContractError(f"Landmark {name} requires xyz[3]")
        coords = [float(v) for v in xyz]
        lm_conf = float(item.get("confidence", 1.0))
        if not 0.0 <= lm_conf <= 1.0:
            raise DentalAssetContractError(f"Landmark {name} confidence must be 0..1")
        clean_landmarks.append({"name": name, "xyz": coords, "confidence": lm_conf})
        seen.add(name)
    payload = {
        "schema": RECOGNITION_SCHEMA,
        "asset_schema": schema(),
        "contract_version": contract_version(),
        "contract_sha256": contract_sha256(),
        "family_id": family_id(fdi),
        "fdi": fdi,
        "tooth_class": tooth_class_from_fdi(fdi),
        "arch": arch_from_fdi(fdi),
        "side": side_from_fdi(fdi),
        "source": source_name,
        "coordinate_space": space,
        "landmarks": clean_landmarks,
        "metadata": validate_mapping_metadata(metadata),
    }
    if confidence is not None:
        value = float(confidence)
        if not 0.0 <= value <= 1.0:
            raise DentalAssetContractError("Recognition confidence must be 0..1")
        payload["confidence"] = value
    return payload


def validate_recognition_payload(payload: Mapping[str, Any], *, require_complete: bool = False) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise DentalAssetContractError("Recognition payload must be an object")
    if str(payload.get("schema", "")) != RECOGNITION_SCHEMA:
        raise DentalAssetContractError(f"Recognition schema must be {RECOGNITION_SCHEMA}")
    if str(payload.get("asset_schema", "")) != schema():
        raise DentalAssetContractError(f"asset_schema must be {schema()}")
    try:
        supplied_version = int(payload.get("contract_version", 0))
    except Exception as exc:
        raise DentalAssetContractError("contract_version must be an integer") from exc
    if supplied_version != contract_version():
        raise DentalAssetContractError(
            f"Dental asset contract version mismatch: {supplied_version} != {contract_version()}"
        )
    supplied_hash = str(payload.get("contract_sha256", "") or "")
    if supplied_hash != contract_sha256():
        raise DentalAssetContractError("Dental asset contract hash mismatch")
    fdi = normalize_fdi(payload.get("fdi"), include_primary=True)
    expected_family = family_id(fdi)
    if str(payload.get("family_id", "")) != expected_family:
        raise DentalAssetContractError(f"family_id must be {expected_family}")
    rebuilt = canonical_recognition_payload(
        fdi,
        source=str(payload.get("source", "")),
        coordinate_space=str(payload.get("coordinate_space", "")),
        landmarks=payload.get("landmarks", ()),
        confidence=payload.get("confidence"),
        metadata=payload.get("metadata", {}),
    )
    if require_complete:
        present = {item["name"] for item in rebuilt["landmarks"]}
        missing = [name for name in required_landmarks(fdi) if name not in present]
        if missing:
            raise DentalAssetContractError(f"Missing required landmarks for FDI {fdi}: {', '.join(missing)}")
    return rebuilt


def _validate_contract(data: Mapping[str, Any]) -> None:
    if not isinstance(data, Mapping):
        raise DentalAssetContractError("Dental asset contract root must be an object")
    if data.get("schema") != EXPECTED_SCHEMA:
        raise DentalAssetContractError(f"Dental asset schema must be {EXPECTED_SCHEMA}")
    if int(data.get("contract_version", 0)) != 1:
        raise DentalAssetContractError("Unsupported dental asset contract version")
    frame = data.get("coordinate_frame")
    expected_frame = {
        "+X": "MESIAL", "-X": "DISTAL",
        "+Y": "FACIAL_BUCCAL", "-Y": "LINGUAL_PALATAL",
        "+Z": "CORONAL_OCCLUSAL_INCISAL", "-Z": "APICAL",
        "units": "millimetres",
    }
    if not isinstance(frame, Mapping):
        raise DentalAssetContractError("Dental coordinate_frame missing")
    for axis, expected in expected_frame.items():
        if str(frame.get(axis, "")) != expected:
            raise DentalAssetContractError(f"Invalid DSG_TOOTH_LOCAL_V1 {axis}: expected {expected}")
    if str(frame.get("name", "")) != "DSG_TOOTH_LOCAL_V1":
        raise DentalAssetContractError("coordinate_frame.name must be DSG_TOOTH_LOCAL_V1")
    roles = data.get("roles")
    naming = data.get("naming")
    landmarks = data.get("landmarks")
    sets = data.get("landmark_sets")
    if not isinstance(roles, Mapping) or not roles:
        raise DentalAssetContractError("Contract roles missing")
    if not isinstance(naming, Mapping):
        raise DentalAssetContractError("Contract naming missing")
    if set(roles) - set(naming):
        raise DentalAssetContractError("Every asset role requires a canonical naming pattern")
    if not isinstance(landmarks, Mapping) or not isinstance(sets, Mapping):
        raise DentalAssetContractError("Landmark registry/sets missing")
    known = set(landmarks)
    unknown = sorted({name for values in sets.values() for name in values if name not in known})
    if unknown:
        raise DentalAssetContractError(f"Landmark sets reference undefined names: {', '.join(unknown)}")
    keys = data.get("property_keys")
    required_keys = {
        "schema", "contract_version", "contract_hash", "family_id", "asset_id", "asset_role",
        "asset_source", "fdi", "tooth_class", "arch", "side", "coordinate_space",
        "units", "frame_standard",
    }
    if not isinstance(keys, Mapping) or required_keys - set(keys):
        raise DentalAssetContractError("Contract property_keys incomplete")


# Verify the packaged sidecar after module import lazily when contract is first used.
def assert_contract_integrity() -> None:
    _load_contract()
    verify_contract_sidecar()
