"""Analytical local contact/section model for GenerativeFrame 3.0.

Pure geometry: a circular beam overlaps a *locally planar* passive surface.
The retained region is the part of the circle on the outward-normal side.
This is NOT a Boolean-solid simulator, undercut/retention test or validated
medical-device/mechanical model. Clinical dimensions are caller-supplied.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


class NoFeasibleContact(ValueError):
    """No depth satisfies the supplied contact and remaining-section limits."""


@dataclass(frozen=True)
class ContactPolicy:
    min_contact_width_mm: float
    min_retained_area_ratio: float
    min_bending_inertia_ratio: float
    min_penetration_mm: float
    max_penetration_mm: float


@dataclass(frozen=True)
class ContactSection:
    radius_mm: float
    penetration_mm: float
    center_offset_mm: float
    contact_width_mm: float
    retained_area_mm2: float
    removed_area_mm2: float
    centroid_from_center_mm: float
    inertia_about_surface_tangent_mm4: float
    inertia_about_surface_lateral_mm4: float
    retained_area_ratio: float
    min_retained_bending_inertia_ratio: float


@dataclass(frozen=True)
class ContactRouteEstimate:
    centerline_mm: np.ndarray
    surface_line_mm: np.ndarray
    sections: tuple[ContactSection, ...]
    estimated_contact_area_mm2: float
    estimated_retained_volume_mm3: float
    nominal_volume_mm3: float
    min_retained_area_ratio: float
    min_bending_inertia_ratio: float


def _finite_positive(value, label):
    v = float(value)
    if not math.isfinite(v) or v <= 0:
        raise ValueError(f"{label} must be finite and positive")
    return v


def _valid_policy(radius_mm, policy: ContactPolicy):
    r = _finite_positive(radius_mm, "radius_mm")
    values = (
        policy.min_contact_width_mm,
        policy.min_retained_area_ratio,
        policy.min_bending_inertia_ratio,
        policy.min_penetration_mm,
        policy.max_penetration_mm,
    )
    if not all(math.isfinite(float(x)) for x in values):
        raise ValueError("contact policy requires finite values")
    if not 0 <= policy.min_contact_width_mm <= 2 * r:
        raise NoFeasibleContact("CONTACT_WIDTH_UNATTAINABLE: width exceeds beam diameter")
    if not 0 <= policy.min_retained_area_ratio <= 1:
        raise ValueError("min_retained_area_ratio outside [0,1]")
    if not 0 <= policy.min_bending_inertia_ratio <= 1:
        raise ValueError("min_bending_inertia_ratio outside [0,1]")
    if (policy.min_penetration_mm < 0 or
            policy.max_penetration_mm < policy.min_penetration_mm):
        raise ValueError("invalid penetration range")
    # Until a full Boolean / contact FEM exists, the circular centre must
    # not lie inside the anatomy. This keeps at least half of nominal area.
    if policy.min_penetration_mm > r:
        raise NoFeasibleContact("CONTACT_CENTER_EMBEDDED: local planar model unsupported")
    return r


def circular_section_after_planar_cut(radius_mm: float, penetration_mm: float) -> ContactSection:
    """Closed-form cross-section for 0 <= penetration <= radius.

    Plane: y=-offset measured from circle centre; retained material y>=-offset.
    Central second moments are computed for the truncated region. Polar second
    moment is NOT an exact Saint-Venant torsion constant for a noncircle.
    """
    r = _finite_positive(radius_mm, "radius_mm")
    p = float(penetration_mm)
    if not math.isfinite(p) or p < 0 or p > r:
        raise ValueError("penetration must be finite and in [0,radius]")
    full_area = math.pi * r * r
    full_inertia = math.pi * r**4 / 4.0
    if p == 0:
        return ContactSection(r, p, r, 0.0, full_area, 0.0, 0.0,
                              full_inertia, full_inertia, 1.0, 1.0)
    center_offset = r - p
    a = -center_offset
    h = math.sqrt(max(0.0, r * r - a * a))
    theta = math.acos(a / r)
    area = r * r * theta - a * h
    first_moment = 2.0 / 3.0 * h**3
    second_normal = r**4 * theta / 4.0 + a * h * (r * r - 2 * a * a) / 4.0
    second_lateral = r**4 * theta / 4.0 - a * h * (5 * r * r - 2 * a * a) / 12.0
    centroid = first_moment / area
    inertia_tangent = max(0.0, second_normal - first_moment**2 / area)
    inertia_lateral = max(0.0, second_lateral)
    ratio = min(inertia_tangent, inertia_lateral) / full_inertia
    return ContactSection(
        radius_mm=r,
        penetration_mm=p,
        center_offset_mm=center_offset,
        contact_width_mm=2.0 * h,
        retained_area_mm2=area,
        removed_area_mm2=max(0.0, full_area - area),
        centroid_from_center_mm=centroid,
        inertia_about_surface_tangent_mm4=inertia_tangent,
        inertia_about_surface_lateral_mm4=inertia_lateral,
        retained_area_ratio=min(1.0, area / full_area),
        min_retained_bending_inertia_ratio=min(1.0, ratio),
    )


def select_contact_section(radius_mm: float, policy: ContactPolicy) -> ContactSection:
    """Choose shallowest depth meeting *explicit*, caller-supplied geometry limits.

    The minimum overlap needed for an interface chord w is
    p = r - sqrt(r**2 - (w/2)**2). More penetration decreases surviving area
    and weakest-axis bending inertia for the supported p<=r model.
    """
    r = _valid_policy(radius_mm, policy)
    half_width = policy.min_contact_width_mm / 2.0
    depth_for_width = r - math.sqrt(max(0.0, r * r - half_width * half_width))
    depth = max(float(policy.min_penetration_mm), depth_for_width)
    upper = min(float(policy.max_penetration_mm), r)
    tol = max(1e-9, r * 1e-9)
    if depth > upper + tol:
        raise NoFeasibleContact("CONTACT_DEPTH_LIMIT: required contact exceeds allowed penetration")
    section = circular_section_after_planar_cut(r, min(depth, upper))
    if section.retained_area_ratio + 1e-9 < policy.min_retained_area_ratio:
        raise NoFeasibleContact("CONTACT_SECTION_TOO_SMALL: retained area requirement fails")
    if section.min_retained_bending_inertia_ratio + 1e-9 < policy.min_bending_inertia_ratio:
        raise NoFeasibleContact("CONTACT_INERTIA_TOO_SMALL: weakest-axis bending requirement fails")
    if section.contact_width_mm + tol < policy.min_contact_width_mm:
        raise NoFeasibleContact("CONTACT_WIDTH_UNATTAINABLE: contact chord too short")
    return section


def estimate_contact_route(surface_points_mm, surface_normals, radii_mm,
                           policy: ContactPolicy) -> ContactRouteEstimate:
    """Return estimated shifted centreline and section/contact integrals.

    A single common policy is used for every sample; no nonplanar Boolean
    results or material strengths are inferred. Local unit normals must be
    consistently oriented. This result must never be marked 'clinically safe'.
    """
    points = np.asarray(surface_points_mm, dtype=np.float64)
    normals = np.asarray(surface_normals, dtype=np.float64)
    radii = np.asarray(radii_mm, dtype=np.float64)
    if (points.ndim != 2 or points.shape[1] != 3 or len(points) < 2
            or normals.shape != points.shape or radii.shape != (len(points),)
            or not np.isfinite(points).all() or not np.isfinite(normals).all()
            or not np.isfinite(radii).all()):
        raise ValueError("contact route needs aligned finite Nx3 points and normals, N radii")
    norm = np.linalg.norm(normals, axis=1)
    if (norm <= 1e-9).any():
        raise ValueError("contact normals cannot be zero")
    n = normals / norm[:, None]
    if np.any(np.einsum("ij,ij->i", n[:-1], n[1:]) < 0):
        raise NoFeasibleContact("CONTACT_NORMAL_FLIP: adjacent surface normals disagree")
    seg_lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
    if (seg_lengths <= 1e-8).any():
        raise ValueError("contact route contains duplicated points")
    sections = tuple(select_contact_section(float(r), policy) for r in radii)
    centres = points + np.asarray([sec.center_offset_mm for sec in sections])[:, None] * n
    nominal = np.asarray([math.pi * sec.radius_mm**2 for sec in sections])
    retained = np.asarray([sec.retained_area_mm2 for sec in sections])
    widths = np.asarray([sec.contact_width_mm for sec in sections])
    # Trapezoidal integration along the *surface* polyline is a local estimate.
    def integrate(values):
        return float(np.sum(seg_lengths * (values[:-1] + values[1:]) * 0.5))
    return ContactRouteEstimate(
        centerline_mm=centres,
        surface_line_mm=points.copy(),
        sections=sections,
        estimated_contact_area_mm2=integrate(widths),
        estimated_retained_volume_mm3=integrate(retained),
        nominal_volume_mm3=integrate(nominal),
        min_retained_area_ratio=min(x.retained_area_ratio for x in sections),
        min_bending_inertia_ratio=min(x.min_retained_bending_inertia_ratio for x in sections),
    )
