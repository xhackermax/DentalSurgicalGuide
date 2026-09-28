"""DSG dental semantics v2 — tabula-rasa tooth identity model.

Tooth identity comes from explicit UniversalLab CBCT labels. DSG never infers
FDI from IOS geometry. A marker-controlled 3-D watershed may be used only as a
post-inference *continuity reconciler*: UniversalLab labels are immutable identity
seeds and DentalSegmentator supplies grouped anatomical tooth support. This is
not geometric FDI guessing and cannot create a new dental identity.

Identity becomes clinically accepted only after review; IOS is alignment
geometry and never reassigns FDI. The module provides deterministic label
mapping, validation, topology/path reconciliation, compact geometry statistics
and the shared payload schema. It has no Blender imports.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Iterable
import math

from . import dental_assets

SCHEMA = "dsg.dental_semantics.v2"

# Universal numbering -> FDI permanent dentition.
UNIVERSAL_TO_FDI_PERMANENT: dict[int, int] = {
    1: 18, 2: 17, 3: 16, 4: 15, 5: 14, 6: 13, 7: 12, 8: 11,
    9: 21, 10: 22, 11: 23, 12: 24, 13: 25, 14: 26, 15: 27, 16: 28,
    17: 38, 18: 37, 19: 36, 20: 35, 21: 34, 22: 33, 23: 32, 24: 31,
    25: 41, 26: 42, 27: 43, 28: 44, 29: 45, 30: 46, 31: 47, 32: 48,
}

# Universal temporary teeth 33..52 -> FDI primary dentition.
UNIVERSAL_TO_FDI_PRIMARY: dict[int, int] = {
    33: 55, 34: 54, 35: 53, 36: 52, 37: 51,
    38: 61, 39: 62, 40: 63, 41: 64, 42: 65,
    43: 75, 44: 74, 45: 73, 46: 72, 47: 71,
    48: 81, 49: 82, 50: 83, 51: 84, 52: 85,
}

# Non-tooth structure IDs retained for import compatibility.
UNIVERSAL_LAB_STRUCTURES = {53: "MANDIBLE", 54: "MAXILLA", 55: "MANDIBULAR_CANAL"}
IOS_GUM_LABEL = 33

# UniversalLab left/right counterparts. This mapping is semantic model data, not
# geometry policy, so it belongs beside the Universal→FDI SSOT.
_UNIVERSAL_MIRROR_PAIR_LIST = (
    (1,16),(2,15),(3,14),(4,13),(5,12),(6,11),(7,10),(8,9),
    (17,32),(18,31),(19,30),(20,29),(21,28),(22,27),(23,26),(24,25),
    (33,42),(34,41),(35,40),(36,39),(37,38),
    (43,52),(44,51),(45,50),(46,49),(47,48),
)
UNIVERSAL_MIRROR_PAIRS: dict[int, int] = {
    value: counterpart
    for a, b in _UNIVERSAL_MIRROR_PAIR_LIST
    for value, counterpart in ((a, b), (b, a))
}


# Same side/tooth position in the opposite dental arch. Permanent Universal
# labels 1..32 are symmetric around 16.5; primary labels 33..52 around 42.5.
# This is semantic numbering data, not a geometric guess.
def universal_arch_counterpart(label: Any) -> int:
    try:
        label = int(label)
    except Exception:
        return 0
    if 1 <= label <= 32:
        return 33 - label
    if 33 <= label <= 52:
        return 85 - label
    return 0


def _expected_arch_from_universal(label: Any) -> str:
    fdi = universal_to_fdi(label, source="CBCT")
    return arch_from_fdi(fdi) if fdi else "UNKNOWN"



@dataclass(slots=True)
class ToothRecord:
    """One explicit semantic tooth label from an AI engine.

    Coordinates are DSG root-local millimetres unless the field name says
    ``world``.  No FDI number in this record is inferred from position.
    """

    fdi: int
    universal_label: int
    source: str
    centroid_local_xyz_mm: tuple[float, float, float]
    axis_local_xyz: tuple[float, float, float] | None = None
    axis_shape_confidence: float = 0.0
    volume_mm3: float = 0.0
    point_count: int = 0
    voxel_count: int = 0
    model_name: str = ""
    model_hash: str = ""
    engine_version: str = ""
    confidence_available: bool = False
    confidence: float | None = None
    review_state: str = "REVIEW"  # REVIEW | ACCEPTED | REJECTED
    diagnostics: dict[str, Any] | None = None

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


def valid_fdi(value: Any, *, include_primary: bool = True) -> bool:
    return dental_assets.valid_fdi(value, include_primary=include_primary)


# Compatibility spelling used by old tests/MCP helpers. It is validation only;
# the removed geometric FDI inference is not reintroduced.
def _valid_fdi(value: Any) -> bool:
    return valid_fdi(value, include_primary=False)


def universal_to_fdi(label: Any, *, source: str = "CBCT") -> int:
    """Deterministic mapping from an explicit Universal label to FDI.

    DSG Native MultiView IOS uses permanent labels 1..32 and label 33 for gingiva.
    Universal-style datasets may additionally use 33..52 for primary teeth and 53..55 for
    non-tooth structures.
    """
    try:
        label = int(label)
    except Exception:
        return 0
    if label in UNIVERSAL_TO_FDI_PERMANENT:
        return UNIVERSAL_TO_FDI_PERMANENT[label]
    if str(source).upper() == "CBCT" and label in UNIVERSAL_TO_FDI_PRIMARY:
        return UNIVERSAL_TO_FDI_PRIMARY[label]
    return 0


def fdi_to_universal(fdi: Any) -> int:
    try:
        fdi = int(fdi)
    except Exception:
        return 0
    for label, value in UNIVERSAL_TO_FDI_PERMANENT.items():
        if value == fdi:
            return label
    for label, value in UNIVERSAL_TO_FDI_PRIMARY.items():
        if value == fdi:
            return label
    return 0


def arch_from_fdi(fdi: Any) -> str:
    return dental_assets.arch_from_fdi(fdi)


def side_from_fdi(fdi: Any) -> str:
    return dental_assets.side_from_fdi(fdi)


def tooth_class_from_fdi(fdi: Any) -> str:
    try:
        return dental_assets.tooth_class_from_fdi(fdi)
    except Exception:
        return "UNKNOWN"


def _spacing(spacing_zyx):
    values = tuple(float(v) for v in spacing_zyx)
    if len(values) != 3 or any(not math.isfinite(v) or v <= 0 for v in values):
        raise ValueError("spacing_zyx must contain three positive values")
    return values


def _pca_axis_from_component(np, component, global_origin_zyx, spacing_zyx, full_shape_zyx,
                             *, max_samples=60000):
    """Physical PCA for an already-labelled tooth component.

    Retained as a geometry primitive and numeric regression target.  It does not
    segment, split, classify, or assign an FDI number.
    """
    points = np.argwhere(component)
    if points.shape[0] < 16:
        return None
    if points.shape[0] > int(max_samples):
        stride = max(1, int(math.ceil(points.shape[0] / float(max_samples))))
        points = points[::stride]
    origin = np.asarray(global_origin_zyx, dtype=np.float64)
    g = points.astype(np.float64, copy=False) + origin[None, :]
    sz, sy, sx = _spacing(spacing_zyx)
    full_z, full_y, full_x = (int(v) for v in full_shape_zyx)
    xyz = np.empty((g.shape[0], 3), dtype=np.float64)
    xyz[:, 0] = -((g[:, 2] - 0.5 * (full_x - 1)) * sx)
    xyz[:, 1] = ((g[:, 1] - 0.5 * (full_y - 1)) * sy)
    xyz[:, 2] = ((g[:, 0] - 0.5 * (full_z - 1)) * sz)
    return pca_axis_from_xyz(np, xyz)


def pca_axis_from_xyz(np, xyz, *, max_samples: int = 60000):
    xyz = np.asarray(xyz)
    if xyz.ndim != 2 or xyz.shape[1] != 3 or xyz.shape[0] < 16:
        return None
    if xyz.shape[0] > int(max_samples):
        stride = max(1, int(math.ceil(xyz.shape[0] / float(max_samples))))
        xyz = xyz[::stride]
    # Convert only the bounded PCA sample, not every marching-cubes vertex.
    xyz = np.asarray(xyz, dtype=np.float64)
    center = xyz.mean(axis=0)
    centered = xyz - center[None, :]
    covariance = centered.T @ centered / max(1, centered.shape[0] - 1)
    values, vectors = np.linalg.eigh(covariance)
    order = np.argsort(values)
    values = np.maximum(values[order], 0.0)
    principal = vectors[:, order[-1]]
    norm = float(np.linalg.norm(principal))
    if not math.isfinite(norm) or norm < 1.0e-9:
        return None
    principal = principal / norm
    projections = centered @ principal
    lo = float(np.quantile(projections, 0.12))
    hi = float(np.quantile(projections, 0.88))
    negative = xyz[projections <= lo]
    positive = xyz[projections >= hi]
    neg_center = negative.mean(axis=0) if negative.size else center - principal
    pos_center = positive.mean(axis=0) if positive.size else center + principal
    l1 = float(values[-1])
    l2 = float(values[-2]) if len(values) >= 2 else 0.0
    shape_conf = 0.0 if l1 <= 1.0e-9 else max(0.0, min(1.0, (l1 - l2) / l1))
    return {
        "axis": tuple(float(v) for v in principal),
        "centroid": tuple(float(v) for v in center),
        "positive": tuple(float(v) for v in pos_center),
        "negative": tuple(float(v) for v in neg_center),
        "shape_confidence": float(shape_conf),
        "eigenvalues": tuple(float(v) for v in values),
    }


def orient_axis_apical(axis: Iterable[float], fdi: int) -> tuple[float, float, float] | None:
    """Orient a tooth PCA line using only explicit FDI arch semantics.

    This resolves sign, not identity.  It is advisory and remains reviewable.
    """
    try:
        x, y, z = (float(v) for v in axis)
    except Exception:
        return None
    norm = math.sqrt(x*x + y*y + z*z)
    if not math.isfinite(norm) or norm < 1e-9:
        return None
    vec = (x/norm, y/norm, z/norm)
    arch = arch_from_fdi(fdi)
    desired_z = 1.0 if arch == "MAXILLA" else -1.0 if arch == "MANDIBLE" else 0.0
    if desired_z and vec[2] * desired_z < 0.0:
        vec = tuple(-v for v in vec)
    return tuple(float(v) for v in vec)



def _semantic_label_patient_centroids(np, labels, spacing_zyx, orientation_xyz,
                                      image_origin_patient, *, max_label=55):
    """Return physical DICOM-LPS centroids for semantic labels.

    Work is streamed in z blocks to avoid allocating one coordinate array for the
    entire CBCT. Returned coordinates are patient LPS millimetres, so head/volume
    rotation in Blender does not change superior/inferior classification.
    """
    arr = np.asarray(labels)
    counts = np.zeros(int(max_label) + 1, dtype=np.int64)
    sums = np.zeros((int(max_label) + 1, 3), dtype=np.float64)  # z,y,x voxels
    for z0 in range(0, int(arr.shape[0]), 16):
        block = arr[z0:min(arr.shape[0], z0 + 16)]
        mask = (block > 0) & (block <= int(max_label))
        if not mask.any():
            continue
        zz, yy, xx = np.nonzero(mask)
        vals = block[zz, yy, xx].astype(np.int64, copy=False)
        counts += np.bincount(vals, minlength=int(max_label) + 1)[:int(max_label) + 1]
        sums[:, 0] += np.bincount(vals, weights=(zz + z0), minlength=int(max_label) + 1)[:int(max_label) + 1]
        sums[:, 1] += np.bincount(vals, weights=yy, minlength=int(max_label) + 1)[:int(max_label) + 1]
        sums[:, 2] += np.bincount(vals, weights=xx, minlength=int(max_label) + 1)[:int(max_label) + 1]

    orientation = np.asarray(orientation_xyz, dtype=np.float64).reshape(3, 3)
    origin = np.asarray(image_origin_patient, dtype=np.float64).reshape(3)
    sz, sy, sx = _spacing(spacing_zyx)
    out = {}
    for label in range(1, int(max_label) + 1):
        if counts[label] <= 0:
            continue
        z, y, x = sums[label] / counts[label]
        local_xyz = np.asarray((x * sx, y * sy, z * sz), dtype=np.float64)
        patient = origin + orientation @ local_xyz
        out[label] = tuple(float(v) for v in patient)
    return out, counts


def correct_universal_arch_array(np, labels, spacing_zyx, orientation_xyz,
                                 image_origin_patient):
    """Validate UniversalLab maxilla/mandible identity without rewriting teeth.

    UniversalLab was trained with explicit upper/lower tooth identities.  The
    upstream BATCHDENTALSEG source therefore treats those learned labels as the
    identity authority and does not perform per-tooth arch relabelling.  DSG
    9.1.15 added centroid-based automatic arch remapping; that optimization can
    corrupt a learned instance when a label contains more than one component.

    This function now uses DICOM patient LPS only as a *validation gate*.  When
    jaw structures 53/54 are available, labels that lie on the opposite physical
    arch are reported for review and are never merged into another tooth.  When
    jaw structures are absent, the relative order of both labelled arches is
    validated.  A clear global inversion is reported, not silently rewritten;
    the existing explicit INTERCAMBIAR ARCOS action remains the safe correction.
    """
    arr = np.asarray(labels)
    if arr.ndim != 3:
        return {"checked": False, "corrected": False, "reason": "labelmap no 3D", "source": "NONE"}

    centroids, counts = _semantic_label_patient_centroids(
        np, arr, spacing_zyx, orientation_xyz, image_origin_patient, max_label=55
    )
    tooth_labels = [l for l in range(1, 53) if counts[l] > 0]
    if not tooth_labels:
        return {"checked": False, "corrected": False, "reason": "sin dientes", "source": "NONE"}

    jaw53 = centroids.get(53)
    jaw54 = centroids.get(54)
    if jaw53 is not None and jaw54 is not None:
        z53 = float(jaw53[2]); z54 = float(jaw54[2])
        upper_z = max(z53, z54)
        lower_z = min(z53, z54)
        separation = upper_z - lower_z
        if separation < 3.0:
            return {
                "checked": False, "corrected": False,
                "reason": "estructuras maxila/mandíbula sin separación suficiente",
                "source": "JAW_STRUCTURES_LPS", "jaw_separation_mm": float(separation),
            }
        mid = 0.5 * (upper_z + lower_z)
        band = max(1.5, min(5.0, 0.08 * separation))
        wrong = []
        uncertain = []
        for label in tooth_labels:
            pz = float(centroids[label][2])
            if abs(pz - mid) <= band:
                uncertain.append(int(label))
                continue
            observed = "MAXILLA" if pz > mid else "MANDIBLE"
            if _expected_arch_from_universal(label) != observed:
                wrong.append(int(label))
        ambiguous = sorted(set(wrong + uncertain))
        result = {
            "checked": not bool(ambiguous),
            "corrected": False,
            "changed_labels": [],
            "ambiguous_labels": ambiguous,
            "conflicting_labels": sorted(wrong),
            "source": "JAW_STRUCTURES_LPS",
            "mid_lps_z": float(mid),
            "jaw_separation_mm": float(separation),
            "uncertainty_band_mm": float(band),
            "structure_53_lps_z": z53,
            "structure_54_lps_z": z54,
            "policy": "VALIDATE_LEARNED_ARCH_NO_AUTO_REMAP",
        }
        if wrong:
            result["reason"] = (
                "UniversalLab y la posición física del arco discrepan; DSG conserva la etiqueta aprendida "
                "y exige revisión en vez de fusionar dientes"
            )
        elif uncertain:
            result["reason"] = "dientes dentro de la banda interarcada; revisión necesaria"
        else:
            result["reason"] = "orden maxila/mandíbula coherente"
        return result

    upper_z = [float(centroids[l][2]) for l in tooth_labels if _expected_arch_from_universal(l) == "MAXILLA"]
    lower_z = [float(centroids[l][2]) for l in tooth_labels if _expected_arch_from_universal(l) == "MANDIBLE"]
    if len(upper_z) < 2 or len(lower_z) < 2:
        return {
            "checked": False, "corrected": False,
            "reason": "sin estructuras 53/54 y solo un arco dental identificable",
            "source": "INSUFFICIENT_ARCH_EVIDENCE",
            "upper_label_count": len(upper_z), "lower_label_count": len(lower_z),
        }
    upper_med = float(np.median(np.asarray(upper_z, dtype=np.float64)))
    lower_med = float(np.median(np.asarray(lower_z, dtype=np.float64)))
    delta = upper_med - lower_med
    result = {
        "checked": bool(delta > 3.0),
        "corrected": False,
        "changed_labels": [],
        "ambiguous_labels": [] if delta > 3.0 else list(tooth_labels),
        "source": "DENTAL_ARCH_ORDER_LPS",
        "labelled_maxilla_median_lps_z": upper_med,
        "labelled_mandible_median_lps_z": lower_med,
        "separation_mm": abs(float(delta)),
        "policy": "VALIDATE_LEARNED_ARCH_NO_AUTO_REMAP",
    }
    if delta < -3.0:
        result["reason"] = "inversión global de arcos detectada; usar INTERCAMBIAR ARCOS tras revisión"
        result["suggested_global_swap"] = True
    elif abs(delta) <= 3.0:
        result["reason"] = "arcos dentarios demasiado próximos/ambiguos"
    else:
        result["reason"] = "orden maxila/mandíbula coherente"
    return result

def correct_universal_semantics_array(np, labels, spacing_zyx, orientation_xyz,
                                      image_origin_patient):
    """Run arch validation first, then DICOM-LPS laterality correction."""
    arch = correct_universal_arch_array(
        np, labels, spacing_zyx, orientation_xyz, image_origin_patient
    )
    side = correct_universal_mirroring_array(
        np, labels, spacing_zyx, orientation_xyz, image_origin_patient
    )
    return {"arch": arch, "laterality": side}


def correct_universal_mirroring_array(np, labels, spacing_zyx, orientation_xyz, image_origin_patient):
    """Correct UniversalLab laterality at voxel level, never by whole-label merge.

    This restores the essential behavior of the prior BATCHDENTALSEG
    ``onResolveMirroring`` implementation while keeping DSG's memory-bounded
    z-block processing and DICOM-LPS coordinates.  Only voxels physically on the
    wrong side of the central-incisor midline move to the predefined
    contralateral label.  A correct counterpart is therefore never swallowed by
    a centroid-based whole-label remap.
    """
    arr = np.asarray(labels)
    if arr.ndim != 3:
        return {"checked": False, "corrected": False, "reason": "labelmap no 3D"}

    centroids, counts = _semantic_label_patient_centroids(
        np, arr, spacing_zyx, orientation_xyz, image_origin_patient, max_label=55
    )
    patient_x = {label: float(value[0]) for label, value in centroids.items() if 1 <= int(label) <= 52}

    # Prefer the permanent central incisors, then primary centrals.  Two visible
    # central labels are enough to define the patient midline; unlike tooth order,
    # no missing identity is fabricated.
    central = []
    central_source = "NONE"
    for candidates, source in (((8, 9, 24, 25), "PERMANENT_CENTRALS"),
                               ((37, 38, 47, 48), "PRIMARY_CENTRALS")):
        values = [patient_x[v] for v in candidates if v in patient_x]
        if len(values) >= 2:
            central = values
            central_source = source
            break
    if len(central) < 2:
        return {"checked": False, "corrected": False, "reason": "centrales insuficientes"}

    mid = float(sum(central) / len(central))
    orientation = np.asarray(orientation_xyz, dtype=np.float64).reshape(3, 3)
    origin = np.asarray(image_origin_patient, dtype=np.float64).reshape(3)
    sz, sy, sx = _spacing(spacing_zyx)

    target = np.arange(256, dtype=np.uint8)
    side_code = np.zeros(256, dtype=np.int8)  # -1 RIGHT, +1 LEFT
    for label in range(1, 53):
        fdi = universal_to_fdi(label, source="CBCT")
        side = side_from_fdi(fdi)
        side_code[label] = 1 if side == "LEFT" else (-1 if side == "RIGHT" else 0)
        counterpart = UNIVERSAL_MIRROR_PAIRS.get(label)
        if counterpart is not None:
            target[label] = int(counterpart)

    # Avoid cutting central-incisor voxels that sit essentially on the plane.
    safety_band_mm = 0.5
    changed_counts = np.zeros(56, dtype=np.int64)
    for z0 in range(0, int(arr.shape[0]), 16):
        block = arr[z0:min(arr.shape[0], z0 + 16)]
        mask = (block > 0) & (block <= 52)
        if not mask.any():
            continue
        zz, yy, xx = np.nonzero(mask)
        vals = block[zz, yy, xx].astype(np.int64, copy=False)
        px = (
            float(origin[0])
            + float(orientation[0, 0]) * (xx.astype(np.float64) * sx)
            + float(orientation[0, 1]) * (yy.astype(np.float64) * sy)
            + float(orientation[0, 2]) * ((zz.astype(np.float64) + float(z0)) * sz)
        )
        codes = side_code[vals]
        # DICOM LPS: +X points to the patient's left.
        wrong = ((codes > 0) & (px < (mid - safety_band_mm))) | ((codes < 0) & (px > (mid + safety_band_mm)))
        if not wrong.any():
            continue
        wz = zz[wrong]; wy = yy[wrong]; wx = xx[wrong]
        source_vals = vals[wrong]
        dest_vals = target[source_vals]
        block[wz, wy, wx] = dest_vals.astype(block.dtype, copy=False)
        changed_counts += np.bincount(source_vals, minlength=56)[:56]

    changed_labels = [int(v) for v in np.flatnonzero(changed_counts) if 1 <= int(v) <= 52]
    return {
        "checked": True,
        "corrected": bool(changed_labels),
        "mid_lps_x": float(mid),
        "central_source": central_source,
        "safety_band_mm": float(safety_band_mm),
        "changed_labels": changed_labels,
        "changed_voxels_by_label": {str(v): int(changed_counts[v]) for v in changed_labels},
        "policy": "PRIOR_UNIVERSALLAB_VOXEL_SIDE_CORRECTION",
    }


def analyze_tooth_mask_components(np, mask, spacing_zyx, *, minimum_island_mm3=60.0,
                                  relative_significant_fraction=1.00):
    """Connected-component analysis for one learned tooth label.

    BATCHDENTALSEG carries a 60 mm³ small-island cleanup threshold. DSG 9.1.32
    uses that upstream absolute threshold as the default.  Relative thresholds
    remain available to tests/callers, but are not used to reject normal teeth.
    """
    from scipy import ndimage
    binary = np.asarray(mask, dtype=bool)
    structure = ndimage.generate_binary_structure(3, 2)
    cc, count = ndimage.label(binary, structure=structure)
    if int(count) <= 0:
        return cc, {
            "component_count": 0, "significant_component_count": 0,
            "largest_voxels": 0, "significant_ids": [], "sizes_voxels": [],
            "voxel_volume_mm3": float(math.prod(_spacing(spacing_zyx))),
        }
    sizes = np.bincount(cc.ravel()).astype(np.int64, copy=False)
    component_sizes = sizes[1:]
    largest = int(component_sizes.max(initial=0))
    voxel_volume = float(math.prod(_spacing(spacing_zyx)))
    absolute_voxels = int(math.ceil(float(minimum_island_mm3) / max(voxel_volume, 1e-12)))
    relative_voxels = int(math.ceil(max(1.0, largest * float(relative_significant_fraction))))
    threshold = max(24, min(absolute_voxels, relative_voxels))
    significant_ids = [int(i) for i in range(1, int(count) + 1) if int(sizes[i]) >= threshold]
    order = sorted(range(1, int(count) + 1), key=lambda i: int(sizes[i]), reverse=True)
    second = int(sizes[order[1]]) if len(order) > 1 else 0
    diagnostics = {
        "component_count": int(count),
        "significant_component_count": len(significant_ids),
        "significant_ids": significant_ids,
        "sizes_voxels": [int(sizes[i]) for i in order],
        "largest_component_id": int(order[0]) if order else 0,
        "largest_voxels": int(largest),
        "second_largest_voxels": int(second),
        "second_to_largest_ratio": float(second / largest) if largest else 0.0,
        "voxel_volume_mm3": voxel_volume,
        "minimum_island_mm3_reference": float(minimum_island_mm3),
        "significant_threshold_voxels": int(threshold),
        "significant_threshold_mm3": float(threshold * voxel_volume),
    }
    return cc, diagnostics


def validate_universal_labelmap_topology(np, labels, spacing_zyx, *, max_tooth_label=52):
    """Return learned tooth labels that contain >1 anatomically significant island."""
    from scipy import ndimage
    arr = np.asarray(labels)
    boxes = ndimage.find_objects(arr, max_label=int(max_tooth_label))
    invalid = []
    checked = 0
    fragmentation = 0.0
    details = []
    for label in range(1, int(max_tooth_label) + 1):
        bbox = boxes[label - 1] if label - 1 < len(boxes) else None
        if bbox is None:
            continue
        checked += 1
        mask = arr[bbox] == int(label)
        _cc, diag = analyze_tooth_mask_components(np, mask, spacing_zyx)
        fragmentation += float(diag.get("second_to_largest_ratio", 0.0))
        if int(diag.get("significant_component_count", 0)) > 1:
            fdi = universal_to_fdi(label, source="CBCT")
            invalid.append(int(label))
            details.append({
                "label": int(label), "fdi": int(fdi),
                "component_count": int(diag["component_count"]),
                "significant_component_count": int(diag["significant_component_count"]),
                "sizes_voxels": list(diag["sizes_voxels"][:6]),
                "second_to_largest_ratio": float(diag["second_to_largest_ratio"]),
            })
    return {
        "checked": True,
        "checked_tooth_labels": int(checked),
        "invalid_count": len(invalid),
        "invalid_labels": invalid,
        "invalid_fdi": [int(universal_to_fdi(v, source="CBCT")) for v in invalid],
        "fragmentation_score": float(fragmentation),
        "details": details,
        "pass": not invalid,
    }

def validate_semantic_records(records: Iterable[ToothRecord]) -> dict[str, Any]:
    """Structural/laterality/sequence gate without inventing missing teeth."""
    records = list(records)
    duplicates: list[int] = []
    seen: set[int] = set()
    invalid: list[int] = []
    for rec in records:
        fdi = int(rec.fdi)
        if not valid_fdi(fdi):
            invalid.append(fdi)
            continue
        if fdi in seen:
            duplicates.append(fdi)
        seen.add(fdi)

    permanent = sorted(f for f in seen if 10 < f < 50)
    # Sequence validation checks only ordering within each explicit quadrant;
    # absences are allowed and never guessed/fabricated.
    quadrant_positions: dict[int, list[int]] = {}
    for fdi in permanent:
        q, p = divmod(fdi, 10)
        quadrant_positions.setdefault(q, []).append(p)
    sequence_ok = all(len(set(vals)) == len(vals) and all(1 <= p <= 8 for p in vals)
                      for vals in quadrant_positions.values())
    return {
        "schema": SCHEMA,
        "record_count": len(records),
        "valid_count": len(seen),
        "invalid_fdi": sorted(set(invalid)),
        "duplicate_fdi": sorted(set(duplicates)),
        "sequence_ok": bool(sequence_ok),
        "pass": not invalid and not duplicates and sequence_ok,
    }


def mcp_payload(records: Iterable[ToothRecord], diagnostics: dict[str, Any] | None = None) -> dict[str, Any]:
    records = list(records)
    return {
        "schema": SCHEMA,
        "asset_schema": dental_assets.schema(),
        "asset_contract_version": dental_assets.contract_version(),
        "numbering_system": "FDI_ISO_3950",
        "identity_source": "explicit_reviewed_native_dental_labels",
        "teeth": [item.public_dict() for item in records],
        "diagnostics": dict(diagnostics or {}),
    }

# =============================================================================
# DSG 9.1.34 · COMPETITIVE TOOTH TERRITORY RECONCILIATION
# =============================================================================

def reconcile_universal_dentition_paths(
    np,
    labels,
    spacing_zyx,
    *,
    upper_support_mask=None,
    upper_support_origin=(0, 0, 0),
    lower_support_mask=None,
    lower_support_origin=(0, 0, 0),
):
    """Repair UniversalLab tooth instances by following each tooth through a
    second model's *grouped-tooth* support mask.

    This deliberately mirrors DSG's mandibular-canal strategy:

    * UniversalLab remains the identity source (Universal label -> FDI).
    * DentalSegmentator provides independent anatomical support (upper/lower
      teeth) but never invents an FDI number.
    * A robust *interior core* is selected for every learned Universal tooth
      label, so a thin proximal bridge between two teeth is broken before growth.
    * A native-resolution 3-D watershed follows the interior topology of the
      grouped tooth mask from all cores simultaneously.
    * A competitive nearest-core guard removes territory that is physically
      closer to a neighbouring tooth core, then keeps only the branch connected
      to the original core.  Two dental paths therefore meet at a boundary
      instead of fusing into one tooth.
    * Growth is accepted only when it remains a plausible corona-root
      continuation; excessive lateral capture falls back to the interior core
      and is flagged for review.

    The function mutates ``labels`` in place and returns audit diagnostics.  If
    the verifier is unavailable, the Universal labelmap is left untouched.
    """
    from scipy import ndimage
    try:
        from skimage.segmentation import watershed
    except Exception as exc:
        return {
            "checked": False,
            "corrected": False,
            "reason": f"watershed unavailable: {type(exc).__name__}: {exc}",
            "policy": "UNIVERSAL_IDENTITY_NO_GEOMETRIC_FDI_INFERENCE",
        }

    arr = np.asarray(labels)
    if arr.ndim != 3:
        return {"checked": False, "corrected": False, "reason": "labelmap no 3D"}
    spacing = np.asarray(_spacing(spacing_zyx), dtype=np.float64)

    def _labels_for_arch(arch_name):
        return [
            label for label in range(1, 53)
            if _expected_arch_from_universal(label) == arch_name
        ]

    def _clip_box(starts, stops):
        starts = [max(0, int(starts[i])) for i in range(3)]
        stops = [min(int(arr.shape[i]), int(stops[i])) for i in range(3)]
        if any(stops[i] <= starts[i] for i in range(3)):
            return None
        return tuple(starts), tuple(stops)

    def _component_data(binary, offset_zyx=(0, 0, 0)):
        structure = ndimage.generate_binary_structure(3, 2)
        cc, count = ndimage.label(binary, structure=structure)
        if int(count) <= 0:
            return cc, []
        sizes = np.bincount(cc.ravel()).astype(np.int64, copy=False)
        voxel_volume = float(np.prod(spacing))
        absolute = max(24, int(math.ceil(60.0 / max(voxel_volume, 1.0e-12))))
        largest = int(sizes[1:].max(initial=0))
        # Candidate seed islands: retain substantial alternatives so a wrongly
        # attached neighbouring fragment cannot automatically win just by size.
        threshold = max(24, min(absolute, max(24, int(math.ceil(largest * 0.18)))))
        ids = [i for i in range(1, int(count) + 1) if int(sizes[i]) >= threshold]
        if not ids and count:
            ids = [int(np.argmax(sizes[1:]) + 1)]
        out = []
        for comp_id in ids:
            coords = np.argwhere(cc == int(comp_id))
            if coords.size == 0:
                continue
            centroid = (coords.mean(axis=0, dtype=np.float64) + np.asarray(offset_zyx, dtype=np.float64)) * spacing
            out.append({
                "id": int(comp_id),
                "size": int(sizes[int(comp_id)]),
                "centroid_mm": centroid,
            })
        out.sort(key=lambda item: item["size"], reverse=True)
        return cc, out

    def _seed_core_data(binary, offset_zyx=(0, 0, 0)):
        """Return eroded interior cores for one learned tooth label.

        A UniversalLab label may contain two neighbouring teeth joined through a
        thin proximal bridge.  Using the full connected component as a watershed
        marker makes that error irreversible.  We therefore derive markers from
        the *interior* of the label, where a narrow inter-dental contact vanishes.
        The full grouped-tooth support is recovered later by competitive growth.
        """
        binary = np.asarray(binary, dtype=bool)
        if not binary.any():
            return None, []
        structure = ndimage.generate_binary_structure(3, 2)
        voxel_volume = float(np.prod(spacing))
        # 0.70 mm is wide enough to break most contact bridges while preserving
        # a crown/root core at ordinary CBCT spacings.  Fallbacks keep thin teeth.
        radii = (0.70, 0.55, 0.40, 0.25, 0.0)
        best_cc = None
        best_comps = []
        inside = ndimage.distance_transform_edt(
            binary, sampling=tuple(float(v) for v in spacing)
        )
        for radius_mm in radii:
            core = (inside >= float(radius_mm)) if radius_mm > 0.0 else binary
            cc, count = ndimage.label(core, structure=structure)
            if int(count) <= 0:
                continue
            sizes = np.bincount(cc.ravel()).astype(np.int64, copy=False)
            largest = int(sizes[1:].max(initial=0))
            # A real crown/root core must be more than microscopic noise, but we
            # deliberately retain substantial sibling cores because two teeth
            # joined by a contact often create two similarly sized interiors.
            absolute = max(12, int(math.ceil(8.0 / max(voxel_volume, 1.0e-12))))
            threshold = max(12, min(absolute, max(12, int(math.ceil(largest * 0.20)))))
            ids = [i for i in range(1, int(count) + 1) if int(sizes[i]) >= threshold]
            if not ids:
                ids = [int(np.argmax(sizes[1:]) + 1)]
            comps = []
            for comp_id in ids:
                coords = np.argwhere(cc == int(comp_id))
                if coords.size == 0:
                    continue
                centroid = (coords.mean(axis=0, dtype=np.float64) + np.asarray(offset_zyx, dtype=np.float64)) * spacing
                comps.append({
                    "id": int(comp_id),
                    "size": int(sizes[int(comp_id)]),
                    "centroid_mm": centroid,
                    "core_radius_mm": float(radius_mm),
                })
            comps.sort(key=lambda item: item["size"], reverse=True)
            if comps:
                best_cc = cc
                best_comps = comps
                # Prefer an actually eroded marker.  radius==0 is only fallback.
                break
        del inside
        return best_cc, best_comps

    def _competitive_seed_guard(label, seed, territory, markers, *, tolerance_mm=0.30, bbox=None):
        """Prevent one reconstructed tooth from swallowing a neighbouring tooth.

        Watershed follows topology inside the grouped tooth mask, but if a contact
        bridge is broad it may still assign too much of a neighbour to one basin.
        Within a local ROI we compare physical distance to this tooth's core versus
        all other learned tooth cores.  Voxels clearly closer to another core are
        removed, then only the component still connected to this seed is retained.
        This is a boundary guard, not an FDI inference: identities still come only
        from UniversalLab markers.
        """
        territory = np.asarray(territory, dtype=bool)
        seed = np.asarray(seed, dtype=bool)
        if bbox is not None:
            lo = np.asarray([int(bbox[i].start) for i in range(3)], dtype=np.int64)
            hi = np.asarray([int(bbox[i].stop) for i in range(3)], dtype=np.int64)
        else:
            # Fallback only. Normal 9.2.15 flow precomputes all watershed boxes
            # once, avoiding a full-volume argwhere scan for every tooth.
            coords = np.argwhere(territory | seed)
            if coords.size == 0:
                return territory, {"checked": False, "removed_voxels": 0}
            lo = coords.min(axis=0)
            hi = coords.max(axis=0) + 1
        # Include neighbouring cores even if the provisional territory stopped
        # just before them.  Six millimetres comfortably spans a proximal contact.
        halo = np.asarray([
            max(1, int(math.ceil(6.0 / max(float(spacing[i]), 1.0e-6))))
            for i in range(3)
        ], dtype=np.int64)
        lo = np.maximum(0, lo - halo)
        hi = np.minimum(np.asarray(territory.shape, dtype=np.int64), hi + halo)
        sl = tuple(slice(int(lo[i]), int(hi[i])) for i in range(3))
        own = seed[sl]
        local_markers = markers[sl]
        foreign = (local_markers > 0) & (local_markers != int(label))
        if not foreign.any():
            return territory, {"checked": True, "removed_voxels": 0, "foreign_seed_present": False}

        sampling = tuple(float(v) for v in spacing)
        own_dist = ndimage.distance_transform_edt(~own, sampling=sampling)
        foreign_dist = ndimage.distance_transform_edt(~foreign, sampling=sampling)
        # A small tolerance avoids shaving a genuine root merely because two
        # seed surfaces are sub-voxel equidistant.  Since this only intersects
        # an already mutually-exclusive watershed territory, it cannot overlap
        # another final tooth.
        tolerance_mm = float(max(0.0, tolerance_mm))
        owner_ok = own_dist <= (foreign_dist + tolerance_mm)
        local = territory[sl] & owner_ok
        local |= own
        del own_dist, foreign_dist, owner_ok

        structure = ndimage.generate_binary_structure(3, 2)
        cc, count = ndimage.label(local, structure=structure)
        if int(count) > 0:
            seed_ids = np.unique(cc[own])
            seed_ids = seed_ids[seed_ids > 0]
            if seed_ids.size:
                local = np.isin(cc, seed_ids)
            else:
                local = own.copy()
        out = np.zeros_like(territory, dtype=bool)
        out[sl] = local
        out |= seed
        removed = int(np.count_nonzero(territory & ~out))
        return out, {
            "checked": True,
            "removed_voxels": removed,
            "foreign_seed_present": True,
            "tolerance_mm": float(tolerance_mm),
        }

    def _sample_coords(binary, max_points=40000):
        coords = np.argwhere(binary)
        if coords.shape[0] > int(max_points):
            step = max(1, int(math.ceil(coords.shape[0] / float(max_points))))
            coords = coords[::step]
        return coords.astype(np.float64, copy=False) * spacing[None, :]

    def _corridor_metrics(seed, territory):
        seed_pts = _sample_coords(seed)
        terr_pts = _sample_coords(territory)
        if seed_pts.shape[0] < 16 or terr_pts.shape[0] < 16:
            return {"usable": False}
        center = seed_pts.mean(axis=0)
        centered = seed_pts - center[None, :]
        cov = centered.T @ centered / max(1, centered.shape[0] - 1)
        values, vectors = np.linalg.eigh(cov)
        axis = vectors[:, int(np.argmax(values))]
        norm = float(np.linalg.norm(axis))
        if not math.isfinite(norm) or norm < 1.0e-9:
            return {"usable": False}
        axis = axis / norm

        def _measure(points):
            delta = points - center[None, :]
            axial = delta @ axis
            radial_vec = delta - axial[:, None] * axis[None, :]
            radial = np.sqrt(np.sum(radial_vec * radial_vec, axis=1))
            return {
                "axial_lo": float(np.quantile(axial, 0.02)),
                "axial_hi": float(np.quantile(axial, 0.98)),
                "radial95": float(np.quantile(radial, 0.95)),
                "centroid": points.mean(axis=0),
            }

        sm = _measure(seed_pts)
        tm = _measure(terr_pts)
        seed_span = max(0.1, sm["axial_hi"] - sm["axial_lo"])
        terr_span = max(0.1, tm["axial_hi"] - tm["axial_lo"])
        lateral_limit = max(sm["radial95"] + 1.75, sm["radial95"] * 1.45 + 0.50)
        axial_extra = max(0.0, terr_span - seed_span)
        shift = float(np.linalg.norm(tm["centroid"] - sm["centroid"]))
        return {
            "usable": True,
            "seed_radial95_mm": float(sm["radial95"]),
            "territory_radial95_mm": float(tm["radial95"]),
            "lateral_limit_mm": float(lateral_limit),
            "seed_axial_span_mm": float(seed_span),
            "territory_axial_span_mm": float(terr_span),
            "axial_extra_mm": float(axial_extra),
            "centroid_shift_mm": float(shift),
            "lateral_ok": bool(tm["radial95"] <= lateral_limit),
            # Longitudinal recovery may be substantial (missing root portion),
            # but a whole extra tooth-length is not accepted silently.
            "axial_ok": bool(axial_extra <= 10.0),
            "shift_ok": bool(shift <= 5.0),
        }

    def _process_arch(arch_name, support_mask, support_origin):
        if support_mask is None:
            return {
                "arch": arch_name, "checked": False, "corrected": False,
                "reason": "DentalSegmentator grouped-tooth support unavailable",
            }
        support_mask = np.asarray(support_mask, dtype=bool)
        if support_mask.ndim != 3 or not support_mask.any():
            return {
                "arch": arch_name, "checked": False, "corrected": False,
                "reason": "empty grouped-tooth support",
            }
        arch_labels = _labels_for_arch(arch_name)
        arch_set = set(arch_labels)
        present = [int(v) for v in np.unique(arr) if int(v) in arch_set]
        if not present:
            return {
                "arch": arch_name, "checked": True, "corrected": False,
                "reason": "no UniversalLab tooth seeds in arch", "seed_count": 0,
            }

        boxes = ndimage.find_objects(arr, max_label=55)
        starts = [int(support_origin[i]) for i in range(3)]
        stops = [starts[i] + int(support_mask.shape[i]) for i in range(3)]
        for label in present:
            bbox = boxes[label - 1] if label - 1 < len(boxes) else None
            if bbox is None:
                continue
            for axis in range(3):
                starts[axis] = min(starts[axis], int(bbox[axis].start))
                stops[axis] = max(stops[axis], int(bbox[axis].stop))
        # Small halo lets the path terminate naturally at the periodontal edge.
        halo = [max(1, int(math.ceil(1.0 / max(float(spacing[i]), 1.0e-6)))) for i in range(3)]
        starts = [starts[i] - halo[i] for i in range(3)]
        stops = [stops[i] + halo[i] for i in range(3)]
        clipped = _clip_box(starts, stops)
        if clipped is None:
            return {"arch": arch_name, "checked": False, "corrected": False, "reason": "invalid ROI"}
        starts, stops = clipped
        roi = tuple(slice(starts[i], stops[i]) for i in range(3))
        raw = arr[roi]

        support = np.zeros(raw.shape, dtype=bool)
        so = [int(v) for v in support_origin]
        ss = [so[i] + int(support_mask.shape[i]) for i in range(3)]
        ov0 = [max(starts[i], so[i]) for i in range(3)]
        ov1 = [min(stops[i], ss[i]) for i in range(3)]
        if all(ov1[i] > ov0[i] for i in range(3)):
            dst = tuple(slice(ov0[i] - starts[i], ov1[i] - starts[i]) for i in range(3))
            src = tuple(slice(ov0[i] - so[i], ov1[i] - so[i]) for i in range(3))
            support[dst] = support_mask[src]

        raw_arch = np.isin(raw, np.asarray(arch_labels, dtype=raw.dtype))
        candidate = support | raw_arch
        # The mandibular canal is never allowed to become tooth support even if
        # a verifier boundary is imperfect.
        candidate &= (raw != 55)
        if not candidate.any():
            return {"arch": arch_name, "checked": False, "corrected": False, "reason": "empty candidate"}

        # Analyse all candidate components first.  For a fragmented learned label,
        # choose the island that best continues the *sequence of neighbouring
        # learned teeth*, not blindly the largest island.
        # Build *interior* seed cores rather than using the full learned label.
        # This is the crucial anti-join step: if two teeth are connected by a
        # thin proximal bridge, erosion breaks that bridge before path growth.
        comp_by_label = {}
        largest_centroid = {}
        raw_voxels_by_label = {}
        # 9.2.15 PERFORMANCE: never run one full-arch EDT per tooth. UniversalLab
        # already gives a bounding box for every identity, so deep-core analysis is
        # performed only inside that compact local box. This preserves the exact
        # 9.1.34 competitive-marker semantics while removing the O(N_teeth * FOV)
        # bottleneck and the many full-volume int32 component arrays it created.
        for label in present:
            bbox_global = boxes[label - 1] if label - 1 < len(boxes) else None
            if bbox_global is None:
                continue
            local_starts = [max(0, int(bbox_global[i].start) - int(starts[i]) - 1) for i in range(3)]
            local_stops = [min(int(raw.shape[i]), int(bbox_global[i].stop) - int(starts[i]) + 1) for i in range(3)]
            if any(local_stops[i] <= local_starts[i] for i in range(3)):
                continue
            local_sl = tuple(slice(local_starts[i], local_stops[i]) for i in range(3))
            block = np.asarray(raw[local_sl] == int(label), dtype=bool)
            raw_voxels_by_label[label] = int(block.sum())
            cc, comps = _seed_core_data(block, offset_zyx=tuple(local_starts))
            if cc is None or not comps:
                # Last-resort compatibility with very thin/small predictions.
                cc, comps = _component_data(block, offset_zyx=tuple(local_starts))
            if not comps:
                continue
            # Store only the compact component volume + its local ROI. Keeping a
            # full arch cc array for 20-32 teeth could consume gigabytes.
            comp_by_label[label] = (cc, comps, local_sl)
            largest_centroid[label] = comps[0]["centroid_mm"]

        ordered = [label for label in arch_labels if label in comp_by_label]
        selected = {}
        selection_notes = {}
        # Two passes let an interior tooth use already improved neighbour choices
        # instead of permanently trusting the neighbours' largest raw fragment.
        selected_centroid = dict(largest_centroid)
        for _selection_pass in range(2):
            for idx, label in enumerate(ordered):
                cc, comps, local_sl = comp_by_label[label]
                chosen = comps[0]
                note = {
                    "method": "LARGEST_INTERIOR_CORE",
                    "candidate_components": len(comps),
                    "core_radius_mm": float(chosen.get("core_radius_mm", 0.0)),
                }
                if len(comps) > 1:
                    prev_label = ordered[idx - 1] if idx > 0 else None
                    next_label = ordered[idx + 1] if idx + 1 < len(ordered) else None
                    refs = []
                    if prev_label is not None:
                        refs.append(selected_centroid.get(prev_label))
                    if next_label is not None:
                        refs.append(selected_centroid.get(next_label))
                    refs = [r for r in refs if r is not None]
                    if len(refs) >= 2:
                        scored = []
                        for comp in comps:
                            distances = [float(np.linalg.norm(comp["centroid_mm"] - ref)) for ref in refs]
                            score = max(distances) + 0.35 * sum(distances) + 0.70 * abs(distances[0] - distances[1])
                            size_bonus = -0.10 * math.log1p(max(1, comp["size"]))
                            scored.append((score + size_bonus, comp, distances))
                        scored.sort(key=lambda item: item[0])
                        chosen = scored[0][1]
                        note = {
                            "method": "INTERIOR_CORE_NEIGHBOUR_PATH_BALANCE",
                            "candidate_components": len(comps),
                            "neighbour_distances_mm": [float(v) for v in scored[0][2]],
                            "core_radius_mm": float(chosen.get("core_radius_mm", 0.0)),
                        }
                    else:
                        note = {
                            "method": "LARGEST_INTERIOR_CORE_NO_TWO_NEIGHBOURS",
                            "candidate_components": len(comps),
                            "core_radius_mm": float(chosen.get("core_radius_mm", 0.0)),
                        }
                selected[label] = (cc, int(chosen["id"]), int(chosen["size"]), local_sl)
                selected_centroid[label] = chosen["centroid_mm"]
                selection_notes[label] = note

        def _sequence_for_label(label):
            label = int(label)
            if 1 <= label <= 16:
                return list(range(1, 17))
            if 17 <= label <= 32:
                return list(range(17, 33))
            if 33 <= label <= 42:
                return list(range(33, 43))
            if 43 <= label <= 52:
                return list(range(43, 53))
            return []

        def _midpoint_window_seed(label, fallback_seed):
            """Carve a local identity core around the expected neighbour midpoint.

            This is used only when both *immediate learned neighbours* are present.
            It can split a single connected Universal label that accidentally spans
            two teeth: the marker begins near the expected centre of this identity,
            then the path reconciler recovers the complete crown/root territory.
            """
            seq = _sequence_for_label(label)
            if not seq or int(label) not in seq:
                return fallback_seed, None
            pos = seq.index(int(label))
            prev_label = seq[pos - 1] if pos > 0 else None
            next_label = seq[pos + 1] if pos + 1 < len(seq) else None
            if prev_label not in selected_centroid or next_label not in selected_centroid:
                return fallback_seed, None
            prev_c = np.asarray(selected_centroid[prev_label], dtype=np.float64)
            next_c = np.asarray(selected_centroid[next_label], dtype=np.float64)
            expected = 0.5 * (prev_c + next_c)
            neighbour_span = float(np.linalg.norm(next_c - prev_c))
            radius_mm = max(2.2, min(4.2, 0.30 * neighbour_span))
            center_idx = expected / spacing
            radius_vox = np.asarray([
                max(1, int(math.ceil(radius_mm / max(float(spacing[i]), 1.0e-6))))
                for i in range(3)
            ], dtype=np.int64)
            lo = np.maximum(0, np.floor(center_idx).astype(np.int64) - radius_vox)
            hi = np.minimum(np.asarray(raw.shape, dtype=np.int64), np.ceil(center_idx).astype(np.int64) + radius_vox + 1)
            sl = tuple(slice(int(lo[i]), int(hi[i])) for i in range(3))
            block = (raw[sl] == int(label))
            if int(block.sum()) < 16:
                return fallback_seed, None
            zz, yy, xx = np.indices(block.shape, dtype=np.float64)
            zz = (zz + float(lo[0])) * float(spacing[0]) - float(expected[0])
            yy = (yy + float(lo[1])) * float(spacing[1]) - float(expected[1])
            xx = (xx + float(lo[2])) * float(spacing[2]) - float(expected[2])
            sphere = (zz * zz + yy * yy + xx * xx) <= float(radius_mm * radius_mm)
            local = block & sphere
            if int(local.sum()) < 16:
                return fallback_seed, None
            structure = ndimage.generate_binary_structure(3, 2)
            cc_local, count = ndimage.label(local, structure=structure)
            if int(count) <= 0:
                return fallback_seed, None
            sizes = np.bincount(cc_local.ravel())
            candidates = []
            for comp_id in range(1, int(count) + 1):
                if int(sizes[comp_id]) < 12:
                    continue
                coords = np.argwhere(cc_local == comp_id)
                centroid = (coords + lo[None, :]).mean(axis=0) * spacing
                distance = float(np.linalg.norm(centroid - expected))
                candidates.append((distance, -int(sizes[comp_id]), int(comp_id)))
            if not candidates:
                return fallback_seed, None
            candidates.sort()
            chosen_id = candidates[0][2]
            chosen = (cc_local == int(chosen_id))
            # Remove the outermost partial-volume shell when possible. This makes
            # the seed analogous to the canal centre path rather than its noisy wall.
            inside = ndimage.distance_transform_edt(chosen, sampling=tuple(float(v) for v in spacing))
            inner = chosen & (inside >= 0.35)
            if int(inner.sum()) >= 12:
                chosen = inner
            out = np.zeros_like(fallback_seed, dtype=bool)
            out[sl] = chosen
            return out, {
                "method": "IMMEDIATE_NEIGHBOUR_MIDPOINT_CORE",
                "radius_mm": float(radius_mm),
                "neighbour_span_mm": float(neighbour_span),
                "seed_voxels": int(chosen.sum()),
            }

        markers = np.zeros(raw.shape, dtype=np.int16)
        seed_counts = {}
        for label, (cc, comp_id, _size, local_sl) in selected.items():
            seed_local = (cc == int(comp_id))
            if not seed_local.any():
                continue
            # DSG 9.2.12: the eroded anatomical core is a marker, never output.
            # 9.2.15 stores it directly in one shared marker volume instead of
            # retaining one full-size boolean seed array per tooth.
            marker_view = markers[local_sl]
            marker_view[seed_local] = int(label)
            seed_counts[int(label)] = int(seed_local.sum())
        if not seed_counts:
            return {"arch": arch_name, "checked": False, "corrected": False, "reason": "no robust seeds"}

        # Ignore disconnected verifier islands that contain no Universal tooth
        # identity. This is the dental equivalent of not drawing a synthetic long
        # nerve segment through unsupported anatomy.
        cc_candidate, _ = ndimage.label(candidate, structure=ndimage.generate_binary_structure(3, 2))
        ids_with_seed = np.unique(cc_candidate[markers > 0])
        ids_with_seed = ids_with_seed[ids_with_seed > 0]
        valid_candidate = np.isin(cc_candidate, ids_with_seed)
        valid_candidate |= (markers > 0)

        distance = ndimage.distance_transform_edt(valid_candidate, sampling=tuple(float(v) for v in spacing))
        elevation = -np.asarray(distance, dtype=np.float32)
        del distance
        segmented = watershed(
            elevation,
            markers=markers,
            mask=valid_candidate,
            connectivity=ndimage.generate_binary_structure(3, 2),
            watershed_line=False,
        )
        del elevation
        # One bbox pass for all watershed basins. Previous code rescanned the full
        # arch with argwhere once per tooth inside the competition guard.
        segmented_boxes = ndimage.find_objects(segmented, max_label=55)

        # Transaction buffer: one int16 label volume instead of 20-32 full-size
        # boolean final masks. This is the other major 9.2.15 memory reduction.
        reconciled = np.zeros(raw.shape, dtype=raw.dtype)
        labels_to_replace = []
        tooth_details = []
        corrected_voxels = 0
        review_labels = []
        structure26 = ndimage.generate_binary_structure(3, 2)

        def _seed_connected_raw(label, seed):
            """Non-destructive fallback for one UniversalLab identity.

            The eroded interior is a *marker*, never a final tooth. If a proposed
            competitive territory is implausible, preserve the original learned
            anatomy connected to that marker and only trim voxels clearly owned by
            another dental core. This prevents the historical regression where a
            rejected path was materialised as the tiny eroded seed.
            """
            raw_label = (raw == int(label))
            if not raw_label.any():
                return np.asarray(seed, dtype=bool).copy(), {
                    "mode": "SEED_ONLY_NO_RAW", "raw_fraction": 0.0,
                }
            cc_raw, count_raw = ndimage.label(raw_label, structure=structure26)
            seed_ids = np.unique(cc_raw[np.asarray(seed, dtype=bool)])
            seed_ids = seed_ids[seed_ids > 0]
            if seed_ids.size:
                connected = np.isin(cc_raw, seed_ids)
            elif int(count_raw) > 0:
                sizes = np.bincount(cc_raw.ravel())
                largest_id = int(np.argmax(sizes[1:]) + 1)
                connected = (cc_raw == largest_id)
            else:
                connected = raw_label.copy()
            # Use a more permissive ownership tolerance for the rescue path. The
            # purpose here is to remove obvious neighbour capture without shaving
            # the physiological tooth envelope.
            guarded, guard_note = _competitive_seed_guard(
                int(label), seed, connected, markers, tolerance_mm=0.85
            )
            guarded |= np.asarray(seed, dtype=bool)
            raw_count_local = int(raw_label.sum())
            guarded_count = int(guarded.sum())
            # Never collapse a clinical tooth to a tiny marker. In an ambiguous
            # case, preserve the seed-connected learned component and mark REVIEW.
            min_preserved = max(int(np.asarray(seed, dtype=bool).sum()),
                                int(math.floor(0.45 * max(raw_count_local, 1))))
            if guarded_count < min_preserved:
                guarded = connected | np.asarray(seed, dtype=bool)
                mode = "RAW_CONNECTED_RESCUE_REVIEW"
            else:
                mode = "RAW_CONNECTED_COMPETITIVE_RESCUE"
            return guarded, {
                "mode": mode,
                "raw_fraction": float(int(guarded.sum()) / max(raw_count_local, 1)),
                "competition": guard_note,
            }

        for label in sorted(seed_counts):
            seed = np.asarray(markers == int(label), dtype=bool)
            territory = (segmented == int(label))
            seed_count = int(seed_counts.get(int(label), int(seed.sum())))
            territory_bbox = segmented_boxes[label - 1] if label - 1 < len(segmented_boxes) else None
            territory, competition = _competitive_seed_guard(
                int(label), seed, territory, markers, tolerance_mm=0.30, bbox=territory_bbox
            )
            terr_count = int(territory.sum())
            raw_label = (raw == int(label))
            raw_count = int(raw_voxels_by_label.get(label, int(raw_label.sum())))
            growth_ratio = float(terr_count / max(seed_count, 1))
            volume_ratio_to_raw = float(terr_count / max(raw_count, 1))
            raw_intersection = int(np.count_nonzero(territory & raw_label))
            raw_recall = float(raw_intersection / max(raw_count, 1))
            metrics = _corridor_metrics(seed, territory)

            # 9.2.12 volume-preserving rule: deep cores are watershed markers, not
            # anatomical output. A legitimate crown/root can be far more than 10x
            # the eroded core, so growth_ratio is diagnostic only. Compare the
            # reconstructed territory with the original learned tooth instead.
            catastrophic_volume = (
                terr_count < seed_count
                or (raw_count >= 24 and volume_ratio_to_raw < 0.35)
                or (raw_count >= 24 and volume_ratio_to_raw > 2.40)
            )
            if not catastrophic_volume:
                final = territory
                status = "PATH_RECONSTRUCTED_COMPETITIVE_VOLUME_PRESERVED"
                fallback_note = None
                # Corridor metrics are QA flags only. They must not shrink a tooth
                # back to its marker.
                if metrics.get("usable") and not (
                    metrics.get("lateral_ok", False)
                    and metrics.get("shift_ok", False)
                    and float(metrics.get("axial_extra_mm", 0.0)) <= 18.0
                ):
                    status = "REVIEW_PATH_GEOMETRY_QA"
                    review_labels.append(int(label))
            else:
                final, fallback_note = _seed_connected_raw(int(label), seed)
                status = "REVIEW_RAW_ANATOMY_RESCUE"
                review_labels.append(int(label))

            # Last invariant: a present learned tooth may be flagged, but it may
            # not disappear or be materialised as a tiny eroded marker.
            if raw_count >= 24 and int(final.sum()) < max(seed_count, int(0.35 * raw_count)):
                rescue, rescue_note = _seed_connected_raw(int(label), seed)
                if int(rescue.sum()) > int(final.sum()):
                    final = rescue
                    fallback_note = rescue_note
                    status = "REVIEW_MIN_VOLUME_RESCUE"
                    if int(label) not in review_labels:
                        review_labels.append(int(label))

            final = np.asarray(final, dtype=bool)
            # Final territories should be mutually exclusive. If an ambiguous
            # rescue overlaps a territory already written, preserve the original
            # UniversalLab owner at that overlap instead of making result depend
            # on loop order.
            overlap = final & (reconciled != 0) & (reconciled != int(label))
            if bool(overlap.any()):
                final[overlap] = (raw[overlap] == int(label))
            corrected_voxels += int(np.count_nonzero(final & (raw != int(label))))
            reconciled[final] = int(label)
            labels_to_replace.append(int(label))
            final_voxels = int(final.sum())
            detail = {
                "label": int(label),
                "fdi": int(universal_to_fdi(label, source="CBCT")),
                "status": status,
                "raw_voxels": raw_count,
                "seed_voxels": seed_count,
                "territory_voxels": terr_count,
                "final_voxels": int(final_voxels),
                "growth_ratio": growth_ratio,
                "volume_ratio_to_raw": volume_ratio_to_raw,
                "raw_recall": raw_recall,
                "seed_selection": selection_notes.get(label, {}),
                "competition_guard": competition,
                "fallback": fallback_note,
            }
            detail.update(metrics)
            tooth_details.append(detail)

        # Non-destructive transactional write. Replace only identities for which a
        # final mask exists. If a future seed-selection change fails for one label,
        # that original UniversalLab tooth remains visible instead of being erased.
        labels_to_replace = sorted(set(int(v) for v in labels_to_replace))
        if labels_to_replace:
            replace_mask = np.isin(raw, np.asarray(labels_to_replace, dtype=raw.dtype))
            raw[replace_mask] = 0
            write_mask = reconciled != 0
            raw[write_mask] = reconciled[write_mask]

        return {
            "arch": arch_name,
            "checked": True,
            "corrected": bool(corrected_voxels or any(str(d["status"]).startswith("PATH_RECONSTRUCTED") for d in tooth_details)),
            "seed_count": int(len(seed_counts)),
            "candidate_voxels": int(valid_candidate.sum()),
            "support_voxels": int(support.sum()),
            "corrected_added_voxels": int(corrected_voxels),
            "review_labels": sorted(set(review_labels)),
            "review_fdi": [int(universal_to_fdi(v, source="CBCT")) for v in sorted(set(review_labels))],
            "teeth": tooth_details,
            "policy": "UNIVERSAL_INTERIOR_CORE + DENTALSEGMENTATOR_SUPPORT + COMPETITIVE_3D_PATH",
        }

    upper = _process_arch("MAXILLA", upper_support_mask, upper_support_origin)
    lower = _process_arch("MANDIBLE", lower_support_mask, lower_support_origin)
    corrected = bool(upper.get("corrected") or lower.get("corrected"))
    return {
        "checked": bool(upper.get("checked") or lower.get("checked")),
        "corrected": corrected,
        "upper": upper,
        "lower": lower,
        "policy": "FOLLOW_INTERIOR_TOOTH_CORE + COMPETITIVE_BOUNDARIES",
    }
