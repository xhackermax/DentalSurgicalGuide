"""Centripetal Catmull-Rom represented exactly by cubic Bezier handles."""
import numpy as np


def handles(points, scales=None):
    p = np.asarray(points, dtype=float)
    previous = np.roll(p, 1, axis=0)
    following = np.roll(p, -1, axis=0)
    before = np.sqrt(np.maximum(np.linalg.norm(p - previous, axis=1), 1e-10))
    after = np.sqrt(np.maximum(np.linalg.norm(following - p, axis=1), 1e-10))
    tangent = ((p - previous) / before[:, None]
               - (following - previous) / (before + after)[:, None]
               + (following - p) / after[:, None])
    if scales is not None:
        tangent *= np.asarray(scales)[:, None]
    return p - tangent * before[:, None] / 3, p + tangent * after[:, None] / 3


def evaluate(a, right, left, b, count=17):
    t = np.linspace(0, 1, count)[:, None]
    return ((1-t)**3 * a + 3*(1-t)**2*t*right
            + 3*(1-t)*t*t*left + t**3*b)


def route_distance(samples, reference):
    a, b = reference[:-1], reference[1:]
    delta = b-a
    length2 = np.maximum(np.sum(delta*delta, axis=1), 1e-20)
    diff = samples[:, None, :] - a[None, :, :]
    t = np.clip(np.sum(diff*delta[None, :, :], axis=2) / length2, 0, 1)
    nearest = a[None, :, :] + t[:, :, None]*delta[None, :, :]
    return np.sqrt(np.min(np.sum((samples[:, None, :] - nearest)**2, axis=2), axis=1))


def adaptive_controls(points, anchors=(), spacing=1.0, tolerance=.15, max_length_ratio=1.05):
    raw = np.asarray(points, dtype=float)
    if len(raw) < 4 or not np.isfinite(raw).all():
        raise ValueError('El frame necesita al menos cuatro puntos finitos.')
    keep = np.r_[True, np.linalg.norm(np.diff(raw, axis=0), axis=1) > 1e-7]
    raw = raw[keep]
    if np.linalg.norm(raw[-1]-raw[0]) < 1e-7:
        raw = raw[:-1]
    if len(raw) < 4:
        raise ValueError('El recorrido contiene demasiados puntos coincidentes.')
    chosen = {0}
    distance = 0.
    for i in range(1, len(raw)):
        distance += np.linalg.norm(raw[i]-raw[i-1])
        if distance >= spacing:
            chosen.add(i)
            distance = 0.
    # Surface-resolved user anchors are mandatory, including the cyclic seam.
    for anchor in anchors:
        i = int(np.argmin(np.linalg.norm(raw-np.asarray(anchor), axis=1)))
        if np.linalg.norm(raw[i]-anchor) > 1e-4:
            raise ValueError('Un punto marcado se ha perdido del recorrido geodésico.')
        chosen.add(i)
    if len(chosen) < 4:
        chosen.update(np.linspace(0, len(raw)-1, 4).astype(int))
    scales = np.ones(len(raw))
    for iteration in range(32):
        indices = sorted(chosen)
        controls = raw[indices]
        left, right = handles(controls, scales[indices])
        failed = []
        max_error, length = 0., 0.
        for j, begin in enumerate(indices):
            end = indices[(j+1) % len(indices)]
            route_ids = list(range(begin, end+1)) if end > begin else list(range(begin, len(raw)))+list(range(end+1))
            ref = raw[route_ids]
            route_length = np.linalg.norm(np.diff(ref, axis=0), axis=1).sum()
            samples = evaluate(controls[j], right[j], left[(j+1) % len(indices)], controls[(j+1) % len(indices)],
                               max(17, int(route_length/.10)+1))
            error = float(route_distance(samples, ref).max())
            span_length = float(np.linalg.norm(np.diff(samples, axis=0), axis=1).sum())
            max_error = max(max_error, error)
            length += span_length
            if error > tolerance or span_length > route_length*max_length_ratio + 1e-6:
                failed.append((begin, end, route_ids))
        if not failed:
            return controls, left, right, {'max_route_deviation_mm': max_error, 'curve_length_mm': length,
                                           'adaptive_iterations': iteration, 'control_count': len(indices)}
        for begin, end, ids in failed:
            if len(ids) > 2:
                chosen.add(ids[len(ids)//2])
            else:
                scales[begin] *= .5
                scales[end] *= .5
    raise ValueError('No se pudo suavizar el frame dentro del corredor geodésico.')


def circular_gaussian(values, sigma_samples):
    """Low-pass filter on a closed loop (wraps around the seam)."""
    if sigma_samples < 0.5:
        return values.copy()
    half = int(min(len(values) // 2 - 1, max(1, round(3.0 * sigma_samples))))
    offsets = np.arange(-half, half + 1)
    kernel = np.exp(-0.5 * (offsets / sigma_samples) ** 2)
    kernel /= kernel.sum()
    out = np.zeros_like(values, dtype=float)
    for weight, offset in zip(kernel, offsets):
        out += weight * np.roll(values, -offset, axis=0)
    return out


def least_bending_in_tube(route, curve, limit, iterations=2500):
    """Smoothest closed curve within ``limit`` mm of ``route``.

    Projected descent on the bending energy (squared second differences).
    Clipping a smoothed curve against the limit used to leave small corners
    where it touched it; this keeps the same corridor without corners.
    """
    curve = np.array(curve, dtype=float)
    for _ in range(iterations):
        second = np.roll(curve, -1, axis=0) - 2.0 * curve + np.roll(curve, 1, axis=0)
        fourth = np.roll(second, -1, axis=0) - 2.0 * second + np.roll(second, 1, axis=0)
        curve = curve - fourth / 20.0
        delta = curve - route
        length = np.linalg.norm(delta, axis=1)
        curve = route + delta * np.minimum(1.0, limit / np.maximum(length, 1e-12))[:, None]
    return curve


def _resample_closed(points, step):
    p = np.asarray([tuple(point) for point in points], dtype=float)
    closed = np.vstack([p, p[:1]])
    lengths = np.linalg.norm(np.diff(closed, axis=0), axis=1)
    total = float(lengths.sum())
    count = max(16, int(round(total / step)))
    stations = np.concatenate([[0.0], np.cumsum(lengths)])
    targets = np.linspace(0.0, total, count, endpoint=False)
    return np.column_stack([np.interp(targets, stations, closed[:, k]) for k in range(3)]), total / count


def smooth_route(points, axis, radius):
    """Smooth, even centreline from the dense geodesic route.

    The shortest surface path climbs over every cusp and dips into every
    embrasure; swept with a thick radius that looked like a stack of rolls.
    Height along the insertion axis is smoothed strongly, the in-plane course
    gently, and every point stays within 45 % of the radius of the solved
    route so the tube keeps resting on the model (the final Boolean trims any
    overlap with anatomy, as before).
    """
    route, step = _resample_closed(points, 0.4)
    direction = np.asarray(tuple(axis), dtype=float)
    norm = float(np.linalg.norm(direction))
    direction = direction / norm if norm > 1e-9 else np.array([0.0, 0.0, 1.0])
    height = route @ direction
    planar = route - np.outer(height, direction)
    r = float(radius)
    height = circular_gaussian(height, max(3.0, r * 1.6) / step)
    planar = circular_gaussian(planar, max(1.2, r * 0.6) / step)
    smooth = planar + np.outer(height, direction)
    limit = max(0.2, r * 0.45)
    for _ in range(3):
        delta = smooth - route
        length = np.linalg.norm(delta, axis=1)
        scale = np.minimum(1.0, limit / np.maximum(length, 1e-12))
        smooth = route + delta * scale[:, None]
        smooth = circular_gaussian(smooth, 0.8 / step)
    smooth = least_bending_in_tube(route, smooth, limit)
    return smooth, float(np.linalg.norm(smooth - route, axis=1).max())
