"""Explicit pre-Boolean sleeve junction contract, conservatively deferred.

A strut may merge at the *outer wall* of its TARGET sleeve. Before the final
drilling Boolean its envelope can intersect the ideal lumen; that is not
equivalent to final lumen blockage. Only a short, externally attached tip can
be provisionally deferred. All other sleeve lumens and upstream target-lumen
clearance must pass the existing conservative swept-tube engine.

This is a research design candidate, NEVER clearance of the final printed
lumen: post-Boolean solid inspection is a separate mandatory acceptance gate.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np

from . import frame_swept_clearance_core as swept


class InvalidSleeveJunction(ValueError):
    pass


@dataclass(frozen=True)
class SleeveJunctionPreflight:
    candidate_admissible: bool
    status: str
    target_sleeve: str
    deferred_tip_mm: float
    upstream_checked_length_mm: float
    declared_lumens: int
    non_target_lumens_checked: int
    post_boolean_lumen_validation_required: bool = True
    final_lumen_clear: bool = False
    whole_anatomy_validated: bool = False


def _finite_vector(raw, name):
    value = np.asarray(raw, dtype=float)
    if value.shape != (3,) or not np.isfinite(value).all():
        raise InvalidSleeveJunction(f"JUNCTION_INVALID_{name}")
    return value


def _line_prefix(points, radii, remaining_mm):
    """Return exact arclength-truncated prefix, interpolating the tube radius."""
    segments=np.linalg.norm(np.diff(points,axis=0),axis=1)
    total=float(segments.sum())
    target=total-float(remaining_mm)
    if target<=0:
        raise InvalidSleeveJunction("JUNCTION_WELD_EXEMPTION_CONSUMES_ROUTE")
    output=[points[0].copy()]
    sizes=[float(radii[0])]
    covered=0.0
    for i, length in enumerate(segments):
        if covered+length >= target:
            fraction=max(0.,min(1.,(target-covered)/float(length)))
            pos=(1-fraction)*points[i]+fraction*points[i+1]
            radius=(1-fraction)*radii[i]+fraction*radii[i+1]
            if np.linalg.norm(pos-output[-1])>1e-8:
                output.append(pos)
                sizes.append(float(radius))
            break
        output.append(points[i+1].copy())
        sizes.append(float(radii[i+1]))
        covered+=float(length)
    return np.asarray(output), np.asarray(sizes), target


def preflight_sleeve_junction(
    path_points_mm, tube_radii_mm, sleeves, *,
    target_sleeve_id: str, maximum_deferred_tip_mm: float = 2.5,
    attachment_tolerance_mm: float = 0.25,
    clearance_margin_mm: float = 0.0,
) -> SleeveJunctionPreflight:
    """Allow only the target sleeve's *outer wall junction* as provisional.

    A short terminal interval at the actual outer-wall attachment is excluded
    from TARGET-lumen preBoolean clearance. Non-target sleeve lumens are
    verified along the ENTIRE swept tube. The excluded target tip still needs
    final drilling Boolean + residual wall checks before any clinical apply.
    """
    pts=np.asarray(path_points_mm,dtype=float)
    rad=np.asarray(tube_radii_mm,dtype=float)
    if (pts.ndim!=2 or pts.shape[1]!=3 or len(pts)<2 or
            not np.isfinite(pts).all() or rad.shape!=(len(pts),)
            or not np.isfinite(rad).all() or np.any(rad<=0)):
        raise InvalidSleeveJunction("JUNCTION_INVALID_PATH")
    segs=np.linalg.norm(np.diff(pts,axis=0),axis=1)
    if np.any(segs<=1e-8):
        raise InvalidSleeveJunction("JUNCTION_DUPLICATE_POINTS")
    route_length=float(segs.sum())
    limit=float(maximum_deferred_tip_mm)
    tol=float(attachment_tolerance_mm)
    if not math.isfinite(limit) or limit<=0 or not math.isfinite(tol) or tol<=0:
        raise InvalidSleeveJunction("JUNCTION_INVALID_PARAMETERS")
    if not target_sleeve_id or not isinstance(target_sleeve_id,str):
        raise InvalidSleeveJunction("JUNCTION_TARGET_ID_MISSING")
    if not sleeves:
        raise InvalidSleeveJunction("JUNCTION_NO_DECLARED_SLEEVES")
    records=[]
    for record in sleeves:
        sid=str(record.get("id","")).strip()
        if not sid or any(sid==s["id"] for s in records):
            raise InvalidSleeveJunction("JUNCTION_DUPLICATE_OR_MISSING_SLEEVE_ID")
        center=_finite_vector(record.get("center"),"CENTER")
        axis=_finite_vector(record.get("axis"),"AXIS")
        axis_length=float(np.linalg.norm(axis))
        if axis_length<=1e-9:
            raise InvalidSleeveJunction("JUNCTION_ZERO_AXIS")
        axis=axis/axis_length
        outer=float(record.get("outer_radius_mm",float("nan")))
        inner=float(record.get("inner_radius_mm",float("nan")))
        height=float(record.get("height_mm",float("nan")))
        if not all(math.isfinite(z) for z in (inner,outer,height)) or not (0<inner<outer and height>0):
            raise InvalidSleeveJunction("JUNCTION_INVALID_SLEEVE_DIMENSIONS")
        if record.get("lumen_keep_out") is not True:
            raise InvalidSleeveJunction("JUNCTION_MISSING_LUMEN_POLICY")
        records.append(dict(id=sid,center=center,axis=axis,
                            outer=outer,inner=inner,height=height,
                            zone=swept.CylinderKeepOut(
                                f"{sid}:LUMEN",tuple(center),tuple(axis),inner,height*0.5)))
    target=next((s for s in records if s["id"]==target_sleeve_id),None)
    if target is None:
        raise InvalidSleeveJunction("JUNCTION_UNMAPPED_TARGET_SLEEVE")
    terminal=pts[-1]-target["center"]
    axial=float(np.dot(terminal,target["axis"]))
    radial=float(np.linalg.norm(terminal-axial*target["axis"]))
    if abs(radial-target["outer"])>tol or abs(axial)>target["height"]*0.5-tol:
        raise InvalidSleeveJunction("JUNCTION_ATTACHMENT_NOT_ON_OUTER_WALL")
    # Explicit deferral cannot exceed 2.5 mm. It covers only a short external
    # weld and cannot be used to authorize a free-space tunnel to the lumen.
    if limit>2.5 or route_length<=limit+0.1:
        raise InvalidSleeveJunction("JUNCTION_UNBOUNDED_EXEMPTION")
    others=[s["zone"] for s in records if s["id"]!=target_sleeve_id]
    if others:
        all_other=swept.check_swept_tube_clearance(
            pts,rad,others,sample_spacing_mm=0.1,margin_mm=clearance_margin_mm)
        if not all_other.clear:
            return SleeveJunctionPreflight(False,
                f"NON_TARGET_LUMEN_{all_other.status}",
                target_sleeve_id,0.,route_length,len(records),len(others))
    upstream,upstream_r,checked=_line_prefix(pts,rad,limit)
    check=swept.check_swept_tube_clearance(
        upstream,upstream_r,[target["zone"]],
        sample_spacing_mm=0.1,margin_mm=clearance_margin_mm)
    if not check.clear:
        return SleeveJunctionPreflight(False,
            f"UPSTREAM_TARGET_LUMEN_{check.status}",
            target_sleeve_id,limit,checked,len(records),len(others))
    return SleeveJunctionPreflight(
        True,"OUTER_WALL_WELD_DEFERRED_TO_POST_BOOLEAN",
        target_sleeve_id,limit,checked,len(records),len(others))
