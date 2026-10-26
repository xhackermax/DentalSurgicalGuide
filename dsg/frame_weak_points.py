"""Weak points of the guide frame, found from the frame alone (pure numpy).

The IOS is deliberately not used here.  A frame is weakest where it is far
from the sleeve that loads it, and where it either turns sharply (corners) or
runs straight for a long way (long unsupported spans).  A reinforcement that
leaves the frame at such a point and reaches the sleeve closes the largest
triangle with the frame, which is what stiffens the structure most.

Only after these points are chosen are the reinforcements routed over the
IOS surface (geodesics), elsewhere.
"""
from __future__ import annotations

import numpy as np

TURN_WINDOW_MM = 3.0          # arc length on each side used to measure turning
CORNER_MIN_DEG = 30.0         # turning above this is a corner
STRAIGHT_MAX_DEG = 10.0       # turning below this is a straight run
STRAIGHT_MIN_MM = 10.0        # shortest straight run that counts
SLEEVE_EXCLUSION_MM = 5.0     # beyond the sleeve outer radius
SUPPORT_EXCLUSION_MM = 4.0    # supports are clamped on the teeth, not weak
MIN_SPACING_MM = 10.0


def _arc_lengths(points, closed):
    seg = np.linalg.norm(np.diff(points, axis=0), axis=1)
    s = np.concatenate(([0.0], np.cumsum(seg)))
    total = float(s[-1] + (np.linalg.norm(points[0] - points[-1]) if closed else 0.0))
    return s, total


def _point_at(points, s, closed, total, target):
    """Point at arc length ``target`` (wrapping when closed, clamped otherwise)."""
    if closed:
        target = target % total
        pts = np.vstack((points, points[:1]))
        ss = np.concatenate((s, [total]))
    else:
        target = min(max(target, 0.0), float(s[-1]))
        pts, ss = points, s
    k = int(np.searchsorted(ss, target, side='right') - 1)
    k = min(max(k, 0), len(pts) - 2)
    span = ss[k + 1] - ss[k]
    t = 0.0 if span <= 1e-12 else (target - ss[k]) / span
    return pts[k] + (pts[k + 1] - pts[k]) * t


def turning_angles(points, closed=True, window_mm=TURN_WINDOW_MM):
    """Turning angle (degrees) at every vertex, measured over +-window_mm of arc."""
    points = np.asarray(points, float)
    s, total = _arc_lengths(points, closed)
    out = np.zeros(len(points))
    for i, p in enumerate(points):
        if not closed and (s[i] < window_mm or s[i] > s[-1] - window_mm):
            continue
        a = _point_at(points, s, closed, total, s[i] - window_mm)
        b = _point_at(points, s, closed, total, s[i] + window_mm)
        u, v = p - a, b - p
        nu, nv = np.linalg.norm(u), np.linalg.norm(v)
        if nu < 1e-9 or nv < 1e-9:
            continue
        out[i] = float(np.degrees(np.arccos(np.clip(np.dot(u, v) / (nu * nv), -1.0, 1.0))))
    return out


def _arc_distance(s, total, closed, i, j):
    d = abs(s[i] - s[j])
    return min(d, total - d) if closed else d


def candidates(points, closed=True):
    """Corner and straight-run candidates: list of (index, kind, strength 0-1)."""
    points = np.asarray(points, float)
    n = len(points)
    if n < 4:
        return []
    s, total = _arc_lengths(points, closed)
    angle = turning_angles(points, closed)
    out = []
    # Corners: local maxima of the turning angle.
    for i in range(n):
        if angle[i] < CORNER_MIN_DEG:
            continue
        near = [j for j in range(n) if _arc_distance(s, total, closed, i, j) <= TURN_WINDOW_MM * 1.5]
        if angle[i] >= max(angle[j] for j in near) - 1e-9:
            out.append((i, 'CORNER', min(1.0, angle[i] / 90.0)))
    # Long straight runs: their midpoint is the most unsupported spot.
    straight = angle <= STRAIGHT_MAX_DEG
    if straight.all():
        runs = [list(range(n))]
    else:
        runs, current = [], []
        start = int(np.argmin(straight)) if closed else 0  # begin at a bend so runs do not split
        order = [(start + k) % n for k in range(n)] if closed else list(range(n))
        for i in order:
            if straight[i]:
                current.append(i)
            elif current:
                runs.append(current)
                current = []
        if current:
            runs.append(current)
    for run in runs:
        length = sum(np.linalg.norm(points[run[k + 1]] - points[run[k]]) for k in range(len(run) - 1))
        if length < STRAIGHT_MIN_MM:
            continue
        half, walked, mid = length / 2.0, 0.0, run[0]
        for k in range(len(run) - 1):
            walked += float(np.linalg.norm(points[run[k + 1]] - points[run[k]]))
            if walked >= half:
                mid = run[k + 1]
                break
        out.append((mid, 'STRAIGHT', min(1.0, length / 30.0)))
    return out


def _local_maxima(values, s, total, closed, window_mm):
    n = len(values)
    out = []
    for i in range(n):
        if values[i] <= 0:
            continue
        near = [j for j in range(n) if _arc_distance(s, total, closed, i, j) <= window_mm]
        if values[i] >= max(values[j] for j in near) - 1e-12:
            out.append(i)
    return out


def select(points, sleeves, *, supports=(), closed=True, count=3, min_spacing_mm=MIN_SPACING_MM,
           displacement=None, bending=None):
    """Choose the weak points that reinforcements should start from.

    ``sleeves``: iterable of (center_xyz, outer_radius_mm).
    ``displacement`` / ``bending`` (optional, one value per point): the
    frame's own FEM response to the sleeve loads (deflection and bending
    utilization).  When given they rank the points (elastic curve and
    sigma = M*y/I: where the frame deflects and bends most is where it is
    weakest); corners and long straight runs add to the score.  Without them
    the distance to the sleeve stands in for the deflection.

    Returns a list of dicts {index, point, kind, strength, distance_mm, score},
    best first.
    """
    points = np.asarray(points, float)
    sleeves = [(np.asarray(c, float), float(r)) for c, r in sleeves]
    supports = [np.asarray(p, float) for p in supports]
    n = len(points)
    if not sleeves or n < 4:
        return []
    s, total = _arc_lengths(points, closed)
    geometric = {}
    for index, kind, strength in candidates(points, closed):
        if strength > geometric.get(index, (None, -1.0))[1]:
            geometric[index] = (kind, float(strength))
    mech = None
    if displacement is not None:
        d = np.asarray(displacement, float)
        b = np.zeros(n) if bending is None else np.asarray(bending, float)
        dn = d / d.max() if d.max() > 0 else d
        bn = b / b.max() if b.max() > 0 else b
        mech = 0.6 * dn + 0.4 * bn
        for i in _local_maxima(mech, s, total, closed, MIN_SPACING_MM * 0.5):
            geometric.setdefault(i, ('MECHANICAL', 0.0))
    distances = np.array([min(float(np.linalg.norm(p - c)) for c, _r in sleeves) for p in points])
    rows = []
    for index, (kind, strength) in geometric.items():
        p = points[index]
        if min(float(np.linalg.norm(p - c)) - r for c, r in sleeves) < SLEEVE_EXCLUSION_MM:
            continue
        if any(np.linalg.norm(p - q) < SUPPORT_EXCLUSION_MM for q in supports):
            continue
        rows.append({'index': int(index), 'point': p.copy(), 'kind': kind,
                     'strength': float(strength), 'distance_mm': float(distances[index])})
    if not rows:
        return []
    far = max(r['distance_mm'] for r in rows)
    for r in rows:
        weakness = float(mech[r['index']]) if mech is not None else r['distance_mm'] / far
        # Mechanics rank; a corner or a long straight run only adds a bonus.
        r['score'] = weakness * (1.0 + 0.25 * r['strength'])
    rows.sort(key=lambda r: -r['score'])
    chosen = []
    for r in rows:
        if all(np.linalg.norm(r['point'] - c['point']) >= min_spacing_mm for c in chosen):
            chosen.append(r)
        if len(chosen) >= count:
            break
    return chosen


def greedy_by_stiffening(points, candidate_indices, sleeve_displacement, *, count=3,
                         min_spacing_mm=MIN_SPACING_MM, bonus=None):
    """Pick the frame points whose link to the sleeve stiffens the guide most.

    ``sleeve_displacement(chosen_indices) -> float`` solves the structure with
    a link from the sleeve to every chosen point (K u = F) and returns the
    worst sleeve displacement.  Each round adds the point that lowers it most,
    given the links already chosen, so the second reinforcement is the one
    that best completes the triangle made by the first.  ``bonus`` (index ->
    0..1) gives corners / long straight runs a small edge on near-ties.
    Returns [(index, displacement_after, gain_ratio)], best first.
    """
    points = np.asarray(points, float)
    bonus = bonus or {}
    chosen, out = [], []
    current = float(sleeve_displacement([]))
    for _ in range(count):
        best = None
        for i in candidate_indices:
            if i in chosen or any(np.linalg.norm(points[i] - points[c]) < min_spacing_mm for c in chosen):
                continue
            d = float(sleeve_displacement(chosen + [i]))
            gain = (current - d) / current if current > 0 else 0.0
            key = gain * (1.0 + 0.1 * float(bonus.get(i, 0.0)))
            if best is None or key > best[0]:
                best = (key, i, d, gain)
        if best is None or best[3] <= 0.0:
            break
        chosen.append(best[1])
        out.append((best[1], best[2], best[3]))
        current = best[2]
    return out
