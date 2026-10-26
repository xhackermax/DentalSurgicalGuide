"""Smooth the line where the open IOS ends before the base is built.

Scanner borders are ragged: the last row of triangles zigzags in plan and
in height, and every wall ring built from it inherits the zigzag (the
vertical striations of the closed model).  Here the border loop is low-pass
filtered over its arc length (3-D Gaussian, sigma ~1 mm) and its displacement
is carried over to a ~2 mm band of the scan with a weight that fades to zero,
so the smoothed line blends into the untouched scan.

Only the border band moves (never the teeth): every displacement is capped,
faces are checked for flips (the move is scaled back, or cancelled), and the
original coordinates of the moved vertices are returned so the anatomy lock
can release exactly those vertices and nothing else.
"""
import numpy as np

SIGMA_MM = 1.0
MAX_SHIFT_MM = 0.6
BAND_WIDTH_SIGMA = 2.0  # band fades to zero 2 sigma (2 mm) from the border
NEIGHBOURS = 6
MIN_FACE_AREA_FRACTION = 1e-4  # of sigma^2 (1e-4 mm^2 for sigma 1 mm)


def coordinate_key(co):
    return (round(float(co[0]), 5), round(float(co[1]), 5), round(float(co[2]), 5))


def _face_normals(faces):
    return [face.normal.copy() for face in faces]


def _band_by_distance(loop_verts, limit, max_rings=60):
    """Vertices reachable from the border within ``limit`` (Euclidean)."""
    from mathutils.kdtree import KDTree
    tree = KDTree(len(loop_verts))
    for index, vert in enumerate(loop_verts):
        tree.insert(vert.co, index)
    tree.balance()
    seen = set(loop_verts)
    frontier = list(loop_verts)
    band = []
    for _ in range(int(max_rings)):
        nxt = []
        for vert in frontier:
            for edge in vert.link_edges:
                other = edge.other_vert(vert)
                if other in seen:
                    continue
                seen.add(other)
                if tree.find(other.co)[2] < limit:
                    nxt.append(other)
        if not nxt:
            break
        band.extend(nxt)
        frontier = nxt
    return band, tree


def smooth(bm, loop_verts, sigma, max_shift, band_width=None):
    """Smooth the border band in place; returns (released_keys, diagnostics)."""
    from mathutils import Vector
    from .arch_base import _smooth_field
    loop = list(loop_verts)
    if len(loop) < 8 or sigma <= 0.0:
        return set(), {'rim_smoothing': 'skipped'}
    width = float(band_width if band_width is not None else BAND_WIDTH_SIGMA * sigma)
    band, tree = _band_by_distance(loop, width)
    moving = loop + band
    original = {vert: vert.co.copy() for vert in moving}
    faces = list({face for vert in moving for face in vert.link_faces})
    for face in faces:
        face.normal_update()
    # Sliver faces (scanner debris at the border) have no meaningful normal.
    faces = [face for face in faces if face.calc_area() > MIN_FACE_AREA_FRACTION * sigma * sigma]
    normals_before = _face_normals(faces)

    points = np.array([tuple(vert.co) for vert in loop], dtype=float)
    lengths = np.linalg.norm(np.roll(points, -1, axis=0) - points, axis=1)
    delta = _smooth_field(points, lengths, float(sigma)) - points
    norm = np.linalg.norm(delta, axis=1)
    delta *= np.minimum(1.0, float(max_shift) / np.maximum(norm, 1e-12))[:, None]
    for vert, step in zip(loop, delta):
        vert.co = original[vert] + Vector(tuple(step))
    # The border displacement carries over to the band and fades to zero at
    # ``width``: inverse-distance blend of the nearest border moves, so the
    # band moves as a block with the border instead of folding against it.
    for vert in band:
        found = tree.find_n(original[vert], NEIGHBOURS)
        weights = np.array([1.0 / max(d, 1e-6) ** 2 for _co, _i, d in found])
        step = (weights[:, None] * delta[[i for _co, i, _d in found]]).sum(axis=0) / weights.sum()
        t = min(1.0, found[0][2] / width)
        fade = 1.0 - t * t * (3.0 - 2.0 * t)
        vert.co = original[vert] + Vector(tuple(step * fade))

    # Local safety: vertices of flipped faces are pulled back halfway, then
    # fully, until no face of the band is inverted (all-original is valid).
    backoffs = 0
    for attempt in range(len(moving)):
        flipped = []
        for face, before in zip(faces, normals_before):
            face.normal_update()
            if face.normal.dot(before) <= 0.0:
                flipped.append(face)
        if not flipped:
            break
        for vert in {vert for face in flipped for vert in face.verts if vert in original}:
            vert.co = original[vert].lerp(vert.co, 0.5) if attempt < 4 else original[vert].copy()
            backoffs += 1
    shifts = [float((vert.co - original[vert]).length) for vert in moving]
    if max(shifts, default=0.0) <= 0.0:
        return set(), {'rim_smoothing': 'no_change'}
    released = {coordinate_key(original[vert]) for vert in moving}
    return released, {
        'rim_smoothing': 'OK',
        'rim_vertices': len(loop),
        'band_vertices': len(band),
        'rim_sigma': float(sigma),
        'band_width': width,
        'rim_max_shift': max(shifts),
        'rim_vertex_backoffs': int(backoffs),
        'rim_unsmoothed_vertices': int(sum(1 for vert in loop if (vert.co - original[vert]).length == 0.0)),
    }
