"""Closing lid that follows the IOS footprint, with a rounded edge.

The previous closure joined the basal rim to its convex hull, so a U-shaped
arch got a flat plate spanning from one side of the U to the other.  Here
the lid keeps the outline of the scan itself: the rim is extended as a wall
whose plan outline is progressively smoothed (Taubin, no shrinkage), the
wall bends inward through a quarter circle (a bevel-like rounded edge) and
the last ring is closed by a planar lid with exactly that U outline.

Everything is planned in NumPy first and validated (simple outlines, same
winding, complete triangulation); geometry is only created when the plan is
valid, so the caller can keep its previous closure as a fallback.
"""
import numpy as np

FILLET_MM = 1.5
WALL_RINGS = 6
FILLET_RINGS = 6
OUTLINE_SMOOTHING_MM = 1.0
MAX_SMOOTHING_FACTOR = 4.0


def arc_gaussian(points, sigma):
    """Gaussian low-pass of a closed 2-D polyline over its arc length.

    Uniform resampling + periodic FFT convolution, evaluated back at every
    original vertex, so the vertex count (the 1:1 ring correspondence) is
    preserved.  Shrinkage is ~sigma^2 * curvature / 2: negligible for a
    1 mm sigma on a dental arch.
    """
    p = np.asarray(points, dtype=float)
    lengths = np.linalg.norm(np.roll(p, -1, axis=0) - p, axis=1)
    if float(lengths.sum()) <= 1e-12 or sigma <= 0.0:
        return p.copy()
    return _smooth_field(p, lengths, sigma)


def signed_area(points):
    x, y = points[:, 0], points[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def inward_normals(points, counter_clockwise, sigma=0.0):
    """Unit inward normals, averaged over ``sigma`` of arc length.

    Averaging over about the fillet radius fans the normals out smoothly at
    tight turns (distal ends of the arch), so the inset ring of the rounded
    edge does not fold into a swallowtail.
    """
    tangent = np.roll(points, -1, axis=0) - np.roll(points, 1, axis=0)
    normal = np.column_stack([-tangent[:, 1], tangent[:, 0]])
    normal /= np.maximum(np.linalg.norm(normal, axis=1), 1e-12)[:, None]
    if not counter_clockwise:
        normal = -normal
    if sigma > 0.0:
        lengths = np.linalg.norm(np.roll(points, -1, axis=0) - points, axis=1)
        normal = _smooth_field(normal, lengths, sigma)
    return normal / np.maximum(np.linalg.norm(normal, axis=1), 1e-12)[:, None]


def _smooth_field(values, lengths, sigma):
    stations = np.concatenate([[0.0], np.cumsum(lengths)])
    total = float(stations[-1])
    closed = np.vstack([values, values[:1]])
    count = int(min(1 << 16, max(256, np.ceil(total / max(sigma / 8.0, 1e-9)))))
    grid = np.linspace(0.0, total, count, endpoint=False)
    samples = np.column_stack([np.interp(grid, stations, closed[:, k]) for k in range(values.shape[1])])
    frequency = np.fft.rfftfreq(count, d=total / count)
    response = np.exp(-2.0 * (np.pi * frequency * float(sigma)) ** 2)
    smooth = np.fft.irfft(np.fft.rfft(samples, axis=0) * response[:, None], n=count, axis=0)
    wrapped = np.vstack([smooth, smooth[:1]])
    grid_closed = np.concatenate([grid, [total]])
    return np.column_stack([np.interp(stations[:-1], grid_closed, wrapped[:, k])
                            for k in range(values.shape[1])])


def _orient(p, q, r):
    return (q[..., 0] - p[..., 0]) * (r[..., 1] - p[..., 1]) - (q[..., 1] - p[..., 1]) * (r[..., 0] - p[..., 0])


def is_simple(points, chunk=256):
    """True when no two non-adjacent edges of the closed polygon cross."""
    a = np.asarray(points, dtype=float)
    b = np.roll(a, -1, axis=0)
    count = len(a)
    if count < 3:
        return False
    low = np.minimum(a, b)
    high = np.maximum(a, b)
    columns = np.arange(count)[None, :]
    for start in range(0, count, chunk):
        rows = np.arange(start, min(count, start + chunk))
        overlap = np.all((low[rows][:, None, :] <= high[None, :, :])
                         & (low[None, :, :] <= high[rows][:, None, :]), axis=2)
        gap = np.abs(rows[:, None] - columns)
        overlap &= (gap > 1) & (gap < count - 1)
        i, j = np.nonzero(overlap)
        if not len(i):
            continue
        i = rows[i]
        o1 = _orient(a[i], b[i], a[j])
        o2 = _orient(a[i], b[i], b[j])
        o3 = _orient(a[j], b[j], a[i])
        o4 = _orient(a[j], b[j], b[i])
        if np.any((o1 * o2 < 0.0) & (o3 * o4 < 0.0)):
            return False
    return True


def plan(collar, direction, axis_u, axis_v, base_plane, fillet, smoothing_length):
    """Ring positions from the collar to the lid outline, or (None, reason).

    ``collar`` is the (n, 3) duplicated rim; ``direction`` points from the
    teeth towards the base.  Returns ``(rings, info)`` where ``rings`` is a
    list of (n, 3) arrays; the last one is the planar lid outline.
    """
    collar = np.asarray(collar, dtype=float)
    direction = np.asarray(direction, dtype=float)
    axis_u = np.asarray(axis_u, dtype=float)
    axis_v = np.asarray(axis_v, dtype=float)
    uv = np.column_stack([collar @ axis_u, collar @ axis_v])
    height = collar @ direction
    area = signed_area(uv)
    if abs(area) < 1e-9:
        return None, 'degenerate_outline'
    ccw = area > 0.0
    sigma = float(smoothing_length)
    outline = arc_gaussian(uv, sigma)
    # Noisy scan rims can zigzag: widen the low-pass until the outline is a
    # simple polygon (bounded so the outline never departs from the arch).
    while not is_simple(outline) and sigma < MAX_SMOOTHING_FACTOR * float(smoothing_length):
        sigma *= 1.5
        outline = arc_gaussian(uv, sigma)
    if signed_area(outline) * area <= 0.0 or not is_simple(outline):
        return None, 'outline_not_simple'
    fillet = float(fillet)
    knee = float(base_plane) - fillet
    if float(height.max()) > knee + 1e-9:
        return None, 'base_plane_too_close'
    normals = inward_normals(outline, ccw, sigma=fillet)
    plan_rings = []
    for k in range(1, WALL_RINGS + 1):
        s = k / WALL_RINGS
        # The plan leaves the scanner zigzag fast (70 % smooth at a third of
        # the height) so the wall does not inherit it as vertical striations.
        plan_ease = 1.0 - (1.0 - s) ** 3
        height_ease = s * s * (3.0 - 2.0 * s)
        plan_rings.append((uv + (outline - uv) * plan_ease, height + (knee - height) * height_ease))
    for k in range(1, FILLET_RINGS + 1):
        theta = 0.5 * np.pi * k / FILLET_RINGS
        ring_uv = outline + normals * (fillet * (1.0 - np.cos(theta)))
        plan_rings.append((ring_uv, np.full(len(uv), knee + fillet * np.sin(theta))))
    lid = plan_rings[-1][0]
    if signed_area(lid) * area <= 0.0 or not is_simple(lid):
        return None, 'lid_not_simple'
    rings = [ring_uv[:, :1] * axis_u + ring_uv[:, 1:] * axis_v + ring_h[:, None] * direction
             for ring_uv, ring_h in plan_rings]
    width = float(np.linalg.norm(outline - uv, axis=1).max())
    return rings, {'outline_max_shift': width, 'smoothing_sigma': sigma, 'lid_area': abs(signed_area(lid)),
                   'outline_area': abs(area), 'rings': len(rings)}


def build(bm, loop_verts, collar_positions, direction, axis_u, axis_v, base_plane,
          fillet, smoothing_length):
    """Create collar, wall, rounded edge and U lid in ``bm``; None if not valid.

    Nothing is added to ``bm`` unless the full plan, including the lid
    triangulation, has been validated.
    """
    from mathutils import Vector
    from mathutils.geometry import tessellate_polygon
    vec = lambda v: np.array(tuple(v), dtype=float)
    collar = np.array([tuple(p) for p in collar_positions], dtype=float)
    rings, info = plan(collar, vec(direction), vec(axis_u), vec(axis_v), base_plane,
                       fillet, smoothing_length)
    if rings is None:
        return None, {'u_lid_rejected': info}
    lid = [Vector(tuple(p)) for p in rings[-1]]
    triangles = tessellate_polygon([lid])
    count = len(lid)
    if len(triangles) != count - 2 or any(len(set(t)) != 3 for t in triangles):
        return None, {'u_lid_rejected': f'triangulation {len(triangles)}/{count - 2}'}
    previous = list(loop_verts)
    side_faces = 0
    for positions in [collar] + rings:
        ring = [bm.verts.new(tuple(p)) for p in positions]
        for index in range(count):
            nxt = (index + 1) % count
            face = bm.faces.new((previous[index], previous[nxt], ring[nxt], ring[index]))
            face.smooth = True
            side_faces += 1
        previous = ring
    for a, b, c in triangles:
        bm.faces.new((previous[a], previous[b], previous[c]))
    bm.verts.index_update()
    info.update({'u_lid': True, 'fillet': float(fillet), 'lid_triangles': len(triangles)})
    return (previous, side_faces, len(triangles)), info
