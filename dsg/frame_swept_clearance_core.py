"""Conservative swept-capsule clearance against explicit protected solids.

A polyline with variable radii represents a swept tube. The test uses exact
signed-distance functions for spheres and finite cylinders plus a Lipschitz
bound between samples. It is fail-closed: uncertainty near a zone is *not*
reported as clearance. Blender/clinical anatomy still needs full mesh BVH.

Coordinates/radii in mm. No clinical approval or automatic Boolean.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np


class InvalidClearanceGeometry(ValueError):
    pass


@dataclass(frozen=True)
class SphereKeepOut:
    label: str
    center_mm: tuple[float, float, float]
    radius_mm: float


@dataclass(frozen=True)
class CylinderKeepOut:
    label: str
    center_mm: tuple[float, float, float]
    axis: tuple[float, float, float]
    radius_mm: float
    half_height_mm: float


@dataclass(frozen=True)
class SweptClearanceReport:
    clear: bool
    status: str
    conservative_min_clearance_mm: float
    minimum_sampled_clearance_mm: float
    nearest_zone: str | None
    samples: int
    declared_zone_count: int
    whole_anatomy_validated: bool = False


def _validated_zone(zone):
    if not isinstance(zone, (SphereKeepOut, CylinderKeepOut)):
        raise InvalidClearanceGeometry("SWEEP_UNSUPPORTED_KEEP_OUT")
    if not isinstance(zone.label, str) or not zone.label.strip():
        raise InvalidClearanceGeometry("SWEEP_ZONE_LABEL_MISSING")
    center=np.asarray(zone.center_mm,dtype=np.float64)
    radius=float(zone.radius_mm)
    if center.shape!=(3,) or not np.isfinite(center).all() or not math.isfinite(radius) or radius<=0:
        raise InvalidClearanceGeometry("SWEEP_INVALID_ZONE")
    if isinstance(zone, SphereKeepOut):
        return (zone.label,"SPHERE",center,radius,None,None)
    axis=np.asarray(zone.axis,dtype=np.float64)
    height=float(zone.half_height_mm)
    if (axis.shape!=(3,) or not np.isfinite(axis).all()
            or not math.isfinite(height) or height<=0):
        raise InvalidClearanceGeometry("SWEEP_INVALID_CYLINDER")
    length=float(np.linalg.norm(axis))
    if length<=1e-12:
        raise InvalidClearanceGeometry("SWEEP_ZERO_AXIS")
    return (zone.label,"CYLINDER",center,radius,axis/length,height)


def _signed_distance(p, zone):
    name,kind,center,radius,axis,half_height=zone
    v=p-center
    if kind=="SPHERE":
        return float(np.linalg.norm(v)-radius)
    z=float(v@axis)
    radial=float(np.linalg.norm(v-z*axis))
    dr=radial-radius
    dz=abs(z)-half_height
    return (math.hypot(max(dr,0.),max(dz,0.))
            + min(max(dr,dz),0.))


def check_swept_tube_clearance(
    centerline_mm, radii_mm, protected_zones,
    *, sample_spacing_mm=0.20, margin_mm=0.0, max_samples=20000,
) -> SweptClearanceReport:
    """Certify clearance ONLY for the supplied explicit zones.

    A segment between successive samples has a conservative lower bound:
    min(endpoint signed distances) - spacing/2 - max(tube endpoint radii).
    Because signed distance is 1-Lipschitz, a positive bound proves the
    swept tube cannot enter that zone between samples. A nonpositive bound
    is UNSURE, never accepted as safe. Actual sampled overlap is INTERSECTION.
    """
    path=np.asarray(centerline_mm,dtype=np.float64)
    radii=np.asarray(radii_mm,dtype=np.float64)
    if (path.ndim!=2 or path.shape[1]!=3 or len(path)<2
            or not np.isfinite(path).all() or radii.shape!=(len(path),)
            or not np.isfinite(radii).all() or np.any(radii<=0)):
        raise InvalidClearanceGeometry("SWEEP_INVALID_PATH_OR_RADII")
    lengths=np.linalg.norm(np.diff(path,axis=0),axis=1)
    if np.any(lengths<=1e-8):
        raise InvalidClearanceGeometry("SWEEP_DUPLICATED_POINTS")
    spacing=float(sample_spacing_mm)
    margin=float(margin_mm)
    if not math.isfinite(spacing) or spacing<=0 or spacing>10 or not math.isfinite(margin) or margin<0:
        raise ValueError("SWEEP_INVALID_SPACING_OR_MARGIN")
    zones=tuple(_validated_zone(z) for z in protected_zones)
    labels=[z[0] for z in zones]
    if len(labels)!=len(set(labels)):
        raise InvalidClearanceGeometry("SWEEP_DUPLICATE_ZONE_NAMES")
    counts=np.maximum(1,np.ceil(lengths/spacing).astype(np.int64))
    n_samples=int(1+counts.sum())
    if not isinstance(max_samples,int) or n_samples>max_samples:
        raise InvalidClearanceGeometry("SWEEP_TOO_MANY_SAMPLES")
    if not zones:
        return SweptClearanceReport(
            clear=True,status="CLEAR_FOR_DECLARED_ZONES_ONLY",
            conservative_min_clearance_mm=math.inf,
            minimum_sampled_clearance_mm=math.inf,
            nearest_zone=None,samples=n_samples,declared_zone_count=0)
    positions=[path[0]]
    rad=[float(radii[0])]
    for a,b,r0,r1,count in zip(path[:-1],path[1:],radii[:-1],radii[1:],counts):
        for k in range(1,int(count)+1):
            t=k/int(count)
            positions.append((1-t)*a+t*b)
            rad.append(float((1-t)*r0+t*r1))
    pts=np.asarray(positions,dtype=np.float64)
    rr=np.asarray(rad,dtype=np.float64)
    min_bound=math.inf
    min_sample=math.inf
    nearest=None
    found_overlap=False
    for z in zones:
        distances=np.asarray([_signed_distance(p,z) for p in pts],dtype=np.float64)
        sampled=float(np.min(distances-rr-margin))
        ds=np.linalg.norm(np.diff(pts,axis=0),axis=1)
        bound=float(np.min(
            np.minimum(distances[:-1],distances[1:])
            -0.5*ds-np.maximum(rr[:-1],rr[1:])-margin))
        if bound<min_bound:
            min_bound=bound
            nearest=z[0]
        min_sample=min(min_sample,sampled)
        if sampled<0:
            found_overlap=True
    if found_overlap:
        status="INTERSECTION"
    elif min_bound<=0:
        status="UNVERIFIED_NEAR_BOUNDARY"
    else:
        status="CLEAR_FOR_DECLARED_ZONES_ONLY"
    return SweptClearanceReport(
        clear=status=="CLEAR_FOR_DECLARED_ZONES_ONLY",
        status=status,
        conservative_min_clearance_mm=min_bound,
        minimum_sampled_clearance_mm=min_sample,
        nearest_zone=nearest,
        samples=n_samples,declared_zone_count=len(zones),
    )
