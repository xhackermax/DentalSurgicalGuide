"""Deterministic, multi-station section profiling of an actual Boolean mesh.

Pure NumPy and the existing hole-aware Boolean section kernel. All probes
must be physically INSIDE the retained mesh; surface points or unmerged
geodesic previews do not qualify. No clinical or structural pass/fail claim.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from .frame_boolean_section_core import (
    InvalidBooleanSection,
    measure_boolean_section,
    compare_section_to_nominal_circle,
)


@dataclass(frozen=True)
class BooleanPathStation:
    index: int
    arclength_mm: float
    point_mm: tuple[float, float, float]
    tangent: tuple[float, float, float]
    area_mm2: float
    principal_inertia_min_mm4: float
    principal_inertia_max_mm4: float
    boundary_count: int
    hole_count: int
    component_count: int
    nominal_area_ratio: float | None
    nominal_weak_inertia_ratio: float | None


@dataclass(frozen=True)
class BooleanPathProfile:
    stations: tuple[BooleanPathStation, ...]
    arclength_mm: float
    area_min_mm2: float
    area_median_mm2: float
    weak_inertia_min_mm4: float
    weak_inertia_median_mm4: float
    worst_station_index_by_area: int
    worst_station_index_by_inertia: int
    probe_count: int
    complete: bool = True
    mechanical_fem_validated: bool = False
    retention_validated: bool = False


def _validate_centerline(centerline):
    p = np.asarray(centerline, dtype=np.float64)
    if p.ndim != 2 or p.shape[1] != 3 or len(p) < 2 or not np.isfinite(p).all():
        raise ValueError("BOOLEAN_PATH_REQUIRES_FINITE_POLYLINE")
    segments = np.linalg.norm(np.diff(p, axis=0), axis=1)
    if np.any(segments <= 1e-7):
        raise ValueError("BOOLEAN_PATH_DUPLICATE_POINTS")
    total = float(segments.sum())
    return p, np.concatenate(([0.0], np.cumsum(segments))), total


def _at_distance(path, cumulative, distance):
    i = int(np.searchsorted(cumulative, distance, side="right") - 1)
    i = max(0, min(i, len(path) - 2))
    length = float(cumulative[i + 1] - cumulative[i])
    factor = max(0., min(1., (distance - float(cumulative[i])) / length))
    return (1.0 - factor) * path[i] + factor * path[i + 1]


def profile_boolean_path(
    vertices_mm, triangles, interior_centerline_mm,
    *, nominal_radii_mm=None,
    sample_count: int = 11,
    end_margin_fraction: float = 0.08,
    slice_tolerance_mm: float = 1e-5,
    max_turn_degrees: float = 110.0,
) -> BooleanPathProfile:
    """Profile a retained-material centerline against a Boolean-cut mesh.

    The caller provides an *interior* tracing path: the original surface
    geodesic generally lies on the Boolean boundary, so it is NOT sufficient.
    Bends exceeding max_turn_degrees are rejected because the normal section
    interpretation becomes unreliable there.
    """
    p, s, total = _validate_centerline(interior_centerline_mm)
    if not isinstance(sample_count, int) or isinstance(sample_count, bool) or not 2 <= sample_count <= 32:
        raise ValueError("BOOLEAN_PATH_SAMPLE_COUNT_OUT_OF_RANGE")
    margin = float(end_margin_fraction)
    if not math.isfinite(margin) or not 0.0 < margin < 0.45:
        raise ValueError("BOOLEAN_PATH_INVALID_END_MARGIN")
    if not math.isfinite(max_turn_degrees) or not 0 < max_turn_degrees <= 180:
        raise ValueError("BOOLEAN_PATH_INVALID_MAX_TURN")
    directions = np.diff(p, axis=0) / np.diff(s)[:, None]
    cos_limit = math.cos(math.radians(float(max_turn_degrees)))
    turns = np.einsum("ij,ij->i", directions[:-1], directions[1:])
    if np.any(turns < cos_limit):
        raise InvalidBooleanSection("BOOLEAN_PATH_SHARP_BEND: sections undefined near kink")
    radii = None
    if nominal_radii_mm is not None:
        radii = np.asarray(nominal_radii_mm, dtype=float)
        if (radii.shape != (len(p),) or not np.isfinite(radii).all()
                or np.any(radii <= 0)):
            raise ValueError("BOOLEAN_PATH_INVALID_REFERENCE_RADII")
    spans = np.linspace(margin * total, (1 - margin) * total, sample_count)
    out = []
    delta = min(total * 1e-3, float(np.min(np.diff(s))) * 0.20)
    for index, arclength in enumerate(spans):
        point = _at_distance(p, s, float(arclength))
        before = _at_distance(p, s, max(0., float(arclength) - delta))
        after = _at_distance(p, s, min(total, float(arclength) + delta))
        tangent = after - before
        length = float(np.linalg.norm(tangent))
        if length <= 1e-10:
            raise InvalidBooleanSection("BOOLEAN_PATH_TANGENT_DEGENERATE")
        tangent /= length
        try:
            section = measure_boolean_section(
                vertices_mm, triangles, point, tangent,
                probe_point_mm=point, tolerance_mm=slice_tolerance_mm
            )
        except InvalidBooleanSection as exc:
            raise InvalidBooleanSection(
                f"BOOLEAN_PATH_SECTION_{index}_FAILED_AT_{arclength:.3f}MM: {exc}"
            ) from exc
        area_ratio = inertia_ratio = None
        if radii is not None:
            radius = float(np.interp(arclength, s, radii))
            comparison = compare_section_to_nominal_circle(section, nominal_radius_mm=radius)
            area_ratio = comparison.measured_area_ratio
            inertia_ratio = comparison.measured_weak_axis_bending_ratio
        out.append(BooleanPathStation(
            index=index,
            arclength_mm=float(arclength),
            point_mm=tuple(float(v) for v in point),
            tangent=tuple(float(v) for v in tangent),
            area_mm2=section.area_mm2,
            principal_inertia_min_mm4=section.principal_inertia_min_mm4,
            principal_inertia_max_mm4=section.principal_inertia_max_mm4,
            boundary_count=section.boundary_count,
            hole_count=section.hole_count,
            component_count=section.global_component_count,
            nominal_area_ratio=area_ratio,
            nominal_weak_inertia_ratio=inertia_ratio,
        ))
    a = np.asarray([x.area_mm2 for x in out])
    inertia = np.asarray([x.principal_inertia_min_mm4 for x in out])
    return BooleanPathProfile(
        stations=tuple(out), arclength_mm=total,
        area_min_mm2=float(np.min(a)),
        area_median_mm2=float(np.median(a)),
        weak_inertia_min_mm4=float(np.min(inertia)),
        weak_inertia_median_mm4=float(np.median(inertia)),
        worst_station_index_by_area=int(np.argmin(a)),
        worst_station_index_by_inertia=int(np.argmin(inertia)),
        probe_count=len(out),
    )
