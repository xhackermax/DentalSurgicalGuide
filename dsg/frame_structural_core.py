"""Pure-Python structural heuristics for DSG GenerativeFrame.

This module intentionally contains no bpy/mathutils imports so its numerical
logic can be unit-tested outside Blender.  It is NOT a finite-element solver.
It provides dimensionless geometric proxies that rank long/slender/remote
frame spans and defines the directed support→sleeve topology invariants used
by the Blender adapter.
"""
from __future__ import annotations

from math import sqrt
from typing import Iterable, Sequence

SCHEMA = "dsg.frame_structural_analysis.v1"
CONTRACT_VERSION = 1


def _p3(p: Sequence[float]) -> tuple[float, float, float]:
    if len(p) != 3:
        raise ValueError("3D point required")
    return float(p[0]), float(p[1]), float(p[2])


def distance(a: Sequence[float], b: Sequence[float]) -> float:
    ax, ay, az = _p3(a); bx, by, bz = _p3(b)
    return sqrt((ax-bx)**2 + (ay-by)**2 + (az-bz)**2)


def polyline_length(points: Iterable[Sequence[float]]) -> float:
    pts = [_p3(p) for p in points]
    return sum(distance(a, b) for a, b in zip(pts, pts[1:]))


def point_at_fraction(points: Iterable[Sequence[float]], fraction: float) -> tuple[float, float, float]:
    pts = [_p3(p) for p in points]
    if not pts:
        raise ValueError("polyline is empty")
    if len(pts) == 1:
        return pts[0]
    fraction = max(0.0, min(1.0, float(fraction)))
    total = polyline_length(pts)
    if total <= 1e-12:
        return pts[0]
    target = total * fraction
    acc = 0.0
    for a, b in zip(pts, pts[1:]):
        seg = distance(a, b)
        if acc + seg >= target and seg > 1e-12:
            t = (target - acc) / seg
            return tuple(a[i] + (b[i]-a[i]) * t for i in range(3))
        acc += seg
    return pts[-1]


def structural_need_proxy(span_mm: float, frame_diameter_mm: float,
                          sleeve_distance_mm: float, local_thickness_mm: float | None = None) -> dict:
    """Return an uncalibrated geometric ranking proxy, never a pass/fail rule.

    The output is deliberately dimensionless.  It makes long spans, large
    distances from the nearest sleeve/load node and locally thin material rank
    higher.  It does not claim to predict stress or displacement.
    """
    span = max(0.0, float(span_mm))
    diameter = max(1e-6, float(frame_diameter_mm))
    sleeve_distance = max(0.0, float(sleeve_distance_mm))
    thickness = None if local_thickness_mm is None else max(1e-6, float(local_thickness_mm))

    span_ratio = span / diameter
    sleeve_ratio = sleeve_distance / diameter
    thickness_ratio = 1.0 if thickness is None else diameter / thickness
    # Monotone, simple, explainable; not a clinical or engineering threshold.
    score = span_ratio * (1.0 + 0.50 * sleeve_ratio) * max(1.0, thickness_ratio)
    return {
        "span_ratio": span_ratio,
        "sleeve_distance_ratio": sleeve_ratio,
        "thickness_ratio": thickness_ratio,
        "geometric_need_proxy": score,
        "interpretation": "RELATIVE_RANKING_ONLY_NOT_FEA",
    }


def normalize_scores(items: list[dict], key: str = "geometric_need_proxy") -> list[dict]:
    values = [max(0.0, float(item.get(key, 0.0))) for item in items]
    hi = max(values, default=0.0)
    out = []
    for item, value in zip(items, values):
        row = dict(item)
        row["relative_need_0_1"] = 0.0 if hi <= 1e-12 else value / hi
        out.append(row)
    return out


def single_sleeve_primary_topology(support_ids: Sequence[str] = ("P1", "P2", "P3", "P4"),
                                   sleeve_id: str = "S1") -> dict:
    """Canonical topology invariant requested by the DSG architect.

    There are no P1→P3 or P2→P4 direct diagonals.  The apparent diagonals are
    pairs of independent directed branches terminating on the sleeve structural
    envelope: P1→S←P3 and P2→S←P4.
    """
    if tuple(support_ids) != ("P1", "P2", "P3", "P4"):
        raise ValueError("support_ids must be exactly P1,P2,P3,P4")
    branches = [
        {"from": "P1", "to": sleeve_id, "direction": "SUPPORT_TO_SLEEVE"},
        {"from": "P3", "to": sleeve_id, "direction": "SUPPORT_TO_SLEEVE"},
        {"from": "P2", "to": sleeve_id, "direction": "SUPPORT_TO_SLEEVE"},
        {"from": "P4", "to": sleeve_id, "direction": "SUPPORT_TO_SLEEVE"},
    ]
    return {
        "sleeve_id": sleeve_id,
        "branches": branches,
        "route_groups": [["P1", sleeve_id, "P3"], ["P2", sleeve_id, "P4"]],
        "forbidden_direct_diagonals": [["P1", "P3"], ["P2", "P4"]],
        "invariants": [
            "BRANCH_DIRECTION_SUPPORT_TO_SLEEVE",
            "TERMINATE_ON_SLEEVE_STRUCTURAL_ENVELOPE",
            "NEVER_INTERSECT_SLEEVE_LUMEN",
        ],
    }


def validate_thresholds(metrics: dict, thresholds: dict | None) -> dict:
    """Apply only explicit user/MCP thresholds; never invent engineering limits."""
    thresholds = dict(thresholds or {})
    checks = []
    mapping = {
        "max_span_mm": ("max_unsupported_span_mm", lambda v, t: v <= t),
        "max_relative_need": ("max_relative_need_0_1", lambda v, t: v <= t),
        "min_local_thickness_mm": ("min_local_thickness_mm", lambda v, t: v >= t),
    }
    passed = True
    for threshold_key, (metric_key, predicate) in mapping.items():
        if threshold_key not in thresholds:
            continue
        value = metrics.get(metric_key)
        if value is None:
            ok = False
        else:
            ok = bool(predicate(float(value), float(thresholds[threshold_key])))
        checks.append({"threshold": threshold_key, "metric": metric_key,
                       "value": value, "limit": thresholds[threshold_key], "passed": ok})
        passed = passed and ok
    return {"checks": checks, "passed": passed if checks else None,
            "thresholds_were_explicit": bool(checks)}
