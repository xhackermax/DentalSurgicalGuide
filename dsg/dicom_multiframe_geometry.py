"""Fail-closed physical geometry for DICOM multi-frame CBCT stacks.

All positions are **DICOM LPS**. This independent pure module keeps the scalar
frames and their *per-frame* slope/intercept paired during sorting and records
the new physical origin. It never performs a one-axis mirror to "fix" laterality.

The Blender DICOM reader collects enhanced functional-group metadata before
calling this module, off the UI thread. Source data remains untouched.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np


class MultiframeGeometryError(ValueError):
    """Unsafe/ambiguous DICOM stack; do not silently generate clinical STL."""


@dataclass(frozen=True)
class PhysicalMultiframeGeometry:
    volume: np.ndarray
    slopes: np.ndarray
    intercepts: np.ndarray
    origin_lps: tuple[float, float, float]
    spacing_z_mm: float
    source_frame_indices: tuple[int, ...]
    reordered: bool


def normalize_multiframe_geometry(
    volume, slopes, intercepts, orientation_xyz, positions_lps, *,
    max_spacing_fraction: float = 0.05,
    max_inplane_drift_mm: float = 0.25,
) -> PhysicalMultiframeGeometry:
    """Return physically ascending voxel Z, or reject an ambiguous acquisition.

    positions_lps must contain one explicitly established physical position
    PER decoded frame (from enhanced functional groups, or a separately
    validated source geometry). A single top-level ImagePositionPatient is
    NOT enough to establish frame order.

    Irregular/splayed/duplicate planes cannot be represented by DSG's current
    single uniform-spacing 3-D volume contract and must fail closed.
    """
    vox = np.asarray(volume)
    slopes = np.asarray(slopes)
    intercepts = np.asarray(intercepts)
    if vox.ndim != 3 or vox.shape[0] < 2 or not all(
        np.issubdtype(np.asarray(a).dtype, np.number)
        for a in (vox, slopes, intercepts)
    ):
        raise MultiframeGeometryError("DICOM_GEOMETRY_INVALID_VOLUME")
    count = int(vox.shape[0])
    if slopes.shape != (count,) or intercepts.shape != (count,):
        raise MultiframeGeometryError("DICOM_GEOMETRY_FRAME_CALIBRATION_MISMATCH")
    if not np.all(np.isfinite(slopes)) or not np.all(np.isfinite(intercepts)):
        raise MultiframeGeometryError("DICOM_GEOMETRY_NONFINITE_CALIBRATION")

    matrix = np.asarray(orientation_xyz, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
        raise MultiframeGeometryError("DICOM_GEOMETRY_ORIENTATION_MISSING")
    if not np.allclose(matrix.T @ matrix, np.eye(3), atol=1e-3) or np.linalg.det(matrix) < 0.999:
        raise MultiframeGeometryError("DICOM_GEOMETRY_INVALID_ORIENTATION")

    try:
        positions = np.asarray(positions_lps, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise MultiframeGeometryError("DICOM_GEOMETRY_FRAME_POSITIONS_MISSING") from exc
    if positions.shape != (count, 3) or not np.all(np.isfinite(positions)):
        raise MultiframeGeometryError("DICOM_GEOMETRY_FRAME_POSITIONS_MISSING")

    normal = matrix[:, 2]
    delta = positions - positions[0]
    projection = delta @ normal
    lateral = delta - projection[:, None] * normal[None, :]
    if float(np.linalg.norm(lateral, axis=1).max()) > float(max_inplane_drift_mm):
        raise MultiframeGeometryError("DICOM_GEOMETRY_INPLANE_DRIFT")

    permutation = np.argsort(projection, kind="stable")
    positive_steps = np.diff(projection[permutation])
    if not np.all(np.isfinite(positive_steps)) or np.any(positive_steps <= 1e-5):
        raise MultiframeGeometryError("DICOM_GEOMETRY_DUPLICATE_OR_INVALID_FRAME_POSITION")
    spacing = float(np.median(positive_steps))
    if spacing <= 1e-6 or np.max(abs(positive_steps - spacing)) > max(0.05, float(max_spacing_fraction) * spacing):
        raise MultiframeGeometryError("DICOM_GEOMETRY_NONUNIFORM_SLICE_SPACING")
    ordered = tuple(int(i) for i in permutation)
    changed = ordered != tuple(range(count))
    return PhysicalMultiframeGeometry(
        volume=np.ascontiguousarray(vox[permutation]) if changed else vox,
        slopes=np.ascontiguousarray(slopes[permutation]) if changed else slopes,
        intercepts=np.ascontiguousarray(intercepts[permutation]) if changed else intercepts,
        origin_lps=tuple(float(x) for x in positions[permutation[0]]),
        spacing_z_mm=spacing,
        source_frame_indices=ordered,
        reordered=changed,
    )
