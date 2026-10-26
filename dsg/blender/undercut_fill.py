"""Volumetric undercut fill along the insertion axis (DSG 9.23).

The view-parallel blockout moves IOS vertices up the insertion axis until they
touch the surface that hides them.  That only fills undercuts where a vertex
happens to be, stretches the faces between moved and unmoved vertices
("curtains", spikes) and the stretched faces can stay hidden under the bulge
(residual retention).

Dental CAD blocks out undercuts as a *volume*: everything that cannot be seen
from the insertion direction is filled, with vertical walls at the height of
contour.  Here this is done per column of a grid perpendicular to the axis:
a ray scans the column from above; each gap between the underside of a bulge
(ray leaves the solid) and the surface below it (ray enters again) is an
undercut.  The gap is filled up to ``relief`` below the underside (the
retention the clinician chose; with ~0 retention the fill merges into the
bulge).  Each fill layer becomes a closed slab mesh (top, bottom and vertical
walls on the grid), which is united with the closed model by MANIFOLD.

DSG 9.23.7 (survey-line model, as dental CAD / surveyors do it):
* every column of the arch footprint is scanned, not only the columns next
  to a displaced vertex, so the whole shadow of each height of contour is
  filled (no strips along the gingival margin, no missed undercuts);
* the fill always merges into the bulge; the clinician's retention is the
  *horizontal* depth the guide may enter under the height of contour (what an
  undercut gauge measures), obtained by eroding the fill from its open side.
  The old vertical relief left a thin flap of guide under the whole bulge;
* the stair-stepped outline of the walls is smoothed in the plane, so the
  walls stay vertical (parallel to the insertion axis) but follow the survey
  line smoothly; roofs and floors take the lowest neighbouring height so no
  fin sticks out of the bulge, needles are joined or dropped.

Orientation: the stored blockout axis points away from the guide (towards
the base of the model); the guide arrives from -axis.  A gap is the space
between a tooth surface facing +axis (beyond the height of contour) and the
surface above it that faces the guide.
"""
import math
import time

import bpy
import numpy as np
from mathutils import Vector

FILL_NAME = 'DSG_BlockoutFill'
CELL_MM = 0.10            # grid spacing perpendicular to the axis
MAX_CELLS = 1_500_000     # the cell grows when the arch would exceed this
SINK_MM = 0.15            # slab bottom sinks into the surface below the gap
MERGE_MM = 0.15           # slab top enters the bulge when retention is ~0
MERGE_RELIEF_MM = 0.03    # below this retention the fill merges into the bulge
MIN_GAP_MM = 0.02
MAX_HITS = 32
MAX_LAYERS = 3
CANDIDATE_DILATION = 3    # cells around the arch footprint that are scanned
FILL_VERSION = 5
REFINE_ITERATIONS = 8     # bisection steps locating the survey line (0.1 mm / 2^8)
MAX_DRAFT_OFFSET_MM = 2.0
MIN_COMPONENT_CELLS = 6   # isolated needles smaller than this are dropped
WALL_SMOOTH_ITERATIONS = 0   # 9.23.8: the outline follows the survey line instead


def retention_steps(relief_mm, cell_mm):
    relief = max(0.0, float(relief_mm))
    if relief < MERGE_RELIEF_MM:
        return 0
    return max(1, int(round(relief / float(cell_mm))))


def _basis(axis):
    axis = Vector(axis).normalized()
    helper = Vector((1.0, 0.0, 0.0)) if abs(axis.x) < 0.9 else Vector((0.0, 1.0, 0.0))
    e1 = axis.cross(helper).normalized()
    e2 = axis.cross(e1).normalized()          # e1 x e2 == axis
    return axis, e1, e2


def _dilate(mask, steps):
    out = mask.copy()
    for _ in range(int(steps)):
        grown = out.copy()
        grown[1:, :] |= out[:-1, :]
        grown[:-1, :] |= out[1:, :]
        grown[:, 1:] |= out[:, :-1]
        grown[:, :-1] |= out[:, 1:]
        out = grown
    return out


def scan_columns(tree, axis, candidate_points, relief_mm, cell_mm=CELL_MM,
                 max_gap_mm=25.0, extent_points=None, candidate_hits=None, draft_deg=0.0,
                 extra_erosion=0):
    """Return the fill layers as grids: list of (mask, top, bottom), plus grid info."""
    axis, e1, e2 = _basis(axis)
    a = np.array(axis, dtype=np.float64)
    b1 = np.array(e1, dtype=np.float64)
    b2 = np.array(e2, dtype=np.float64)
    pts = np.asarray(candidate_points, dtype=np.float64).reshape(-1, 3)
    ext = pts if extent_points is None else np.asarray(extent_points, dtype=np.float64).reshape(-1, 3)
    if not len(ext):
        return [], None
    cand = pts
    pts = ext          # 9.23.7: scan the whole footprint of the arch
    h_all = ext @ a
    top_h = float(h_all.max()) + 1.0
    span = float(h_all.max() - h_all.min()) + 2.0
    u = pts @ b1
    v = pts @ b2
    pad = (CANDIDATE_DILATION + 2) * cell_mm
    u0, v0 = float(u.min()) - pad, float(v.min()) - pad
    cell = float(cell_mm)
    nu = int(math.ceil((float(u.max()) + pad - u0) / cell)) + 1
    nv = int(math.ceil((float(v.max()) + pad - v0) / cell)) + 1
    while nu * nv > MAX_CELLS:
        cell *= 1.25
        nu = int(math.ceil((float(u.max()) + pad - u0) / cell)) + 1
        nv = int(math.ceil((float(v.max()) + pad - v0) / cell)) + 1
    seed = np.zeros((nu, nv), dtype=bool)
    iu = np.clip(((u - u0) / cell).astype(np.int64), 0, nu - 1)
    iv = np.clip(((v - v0) / cell).astype(np.int64), 0, nv - 1)
    seed[iu, iv] = True
    scan = _dilate(seed, CANDIDATE_DILATION)

    layers = [(np.zeros((nu, nv), dtype=bool), np.zeros((nu, nv)), np.zeros((nu, nv)))
              for _ in range(MAX_LAYERS)]
    undersides = [np.zeros((nu, nv)) for _ in range(MAX_LAYERS)]
    surfaces = [np.zeros((nu, nv)) for _ in range(MAX_LAYERS)]
    # Height the guide reaches in each column coming from -axis (the axis
    # points away from the guide, towards the base): the lowest surface that
    # faces the guide.  Empty columns are open all the way.
    reach = np.full((nu, nv), np.inf)
    down = -axis
    relief = max(0.0, float(relief_mm))
    rays = 0
    for i, j in zip(*np.nonzero(scan)):
        cu = u0 + (i + 0.5) * cell
        cv = v0 + (j + 0.5) * cell
        origin = e1 * cu + e2 * cv + axis * top_h
        remaining = span + 2.0
        hits = []
        while len(hits) < MAX_HITS and remaining > 0.0:
            location, normal, _index, distance = tree.ray_cast(origin, down, remaining)
            rays += 1
            if location is None:
                break
            hits.append((float(location.dot(axis)), 1 if normal.dot(axis) > 0.0 else -1))
            step = float(distance) + 1.0e-4
            origin = location + down * 1.0e-4
            remaining -= step
        if hits:
            reach[i, j] = hits[-1][0] if hits[-1][1] < 0 else -np.inf
        layer = 0
        k = 0
        while k < len(hits) - 1:
            if layer >= MAX_LAYERS:
                break
            z_u, s_u = hits[k]
            if s_u >= 0:
                k += 1
                continue
            # Next surface facing up below this underside.  IOS meshes have
            # small self-intersections, so the hit parity is not trusted:
            # extra undersides in between are part of the same shadow.
            n = k + 1
            while n < len(hits) and hits[n][1] <= 0:
                n += 1
            if n >= len(hits):
                break
            z_e = hits[n][0]
            gap = z_u - z_e
            k_next = n
            if gap < MIN_GAP_MM or gap > max_gap_mm:
                k = k_next
                continue
            above = hits[k - 1][0] if k > 0 else None
            below = hits[n + 1][0] if n + 1 < len(hits) else None
            k = k_next
            bottom = z_e - (min(SINK_MM, 0.45 * (z_e - below)) if below is not None else SINK_MM)
            # The fill always merges into the bulge; retention is horizontal.
            top = z_u + (min(MERGE_MM, 0.45 * (above - z_u)) if above is not None else 0.0)
            mask, tops, bottoms = layers[layer]
            mask[i, j] = True
            tops[i, j] = top
            bottoms[i, j] = bottom
            undersides[layer][i, j] = z_u
            surfaces[layer][i, j] = z_e
            layer += 1
    # Undercuts found by the per-vertex rays but narrower than a cell (the
    # column through the cell centre misses them) are filled in their cell:
    # every detected undercut is covered.
    if candidate_hits is not None and len(cand):
        hits_c = np.asarray(candidate_hits, dtype=np.float64).reshape(-1)
        ok = (hits_c > MIN_GAP_MM) & (hits_c <= max_gap_mm)
        ci = np.floor((cand[ok] @ b1 - u0) / cell).astype(np.int64)
        cj = np.floor((cand[ok] @ b2 - v0) / cell).astype(np.int64)
        hz = cand[ok] @ a
        tz = hz + hits_c[ok]
        inside = (ci >= 0) & (ci < nu) & (cj >= 0) & (cj < nv)
        mask0, tops0, bottoms0 = layers[0]
        occupied = np.zeros((nu, nv), dtype=bool)
        for mask, _t, _b in layers:
            occupied |= mask
        for i, j, z_e, z_u in zip(ci[inside], cj[inside], hz[inside], tz[inside]):
            if occupied[i, j] and not mask0[i, j]:
                continue
            if mask0[i, j]:
                tops0[i, j] = max(tops0[i, j], z_u + MERGE_MM)
                bottoms0[i, j] = min(bottoms0[i, j], z_e - SINK_MM)
                undersides[0][i, j] = max(undersides[0][i, j], z_u)
                surfaces[0][i, j] = min(surfaces[0][i, j], z_e)
                continue
            mask0[i, j] = True
            tops0[i, j] = z_u + MERGE_MM
            bottoms0[i, j] = z_e - SINK_MM
            undersides[0][i, j] = z_u
            surfaces[0][i, j] = z_e
            occupied[i, j] = True
    band = np.zeros((nu, nv), dtype=bool)
    for number, (mask, tops, bottoms) in enumerate(layers):
        if mask.any():
            band |= clean_mask(mask, tops, bottoms, undersides[number], surfaces[number])
    # The whole shadow (before the retention is opened) is kept to trace the
    # line of maximum crown perimeter all around, also where the retention
    # leaves no fill.
    shadow = [(mask.copy(), surfaces[number].copy(), undersides[number].copy())
              for number, (mask, _t, _b) in enumerate(layers) if mask.any()]
    steps = retention_steps(relief, cell) + int(extra_erosion)
    for number, (mask, _tops, _bottoms) in enumerate(layers):
        if mask.any() and steps:
            band |= erode_open_side(mask, undersides[number], surfaces[number], reach, steps)
    grid = {'u0': u0, 'v0': v0, 'cell': cell, 'nu': nu, 'nv': nv,
            'axis': axis, 'e1': e1, 'e2': e2, 'rays': rays,
            'scanned': int(scan.sum()), 'band': band, 'steps': steps,
            'tree': tree, 'top_h': top_h, 'span': span, 'reach': reach,
            'relief': relief, 'draft_deg': max(0.0, float(draft_deg)),
            'max_gap': float(max_gap_mm), 'shadow': shadow}
    return [layer for layer in layers if layer[0].any()], grid


def _column_gaps(tree, axis, e1, e2, u, v, top_h, span, max_gap):
    """Gaps (surface z_e, hiding surface z_u, next surface below) of one column."""
    origin = e1 * u + e2 * v + axis * top_h
    down = -axis
    remaining = span + 2.0
    hits = []
    while len(hits) < MAX_HITS and remaining > 0.0:
        location, normal, _index, distance = tree.ray_cast(origin, down, remaining)
        if location is None:
            break
        hits.append((float(location.dot(axis)), 1 if normal.dot(axis) > 0.0 else -1))
        origin = location + down * 1.0e-4
        remaining -= float(distance) + 1.0e-4
    gaps = []
    k = 0
    while k < len(hits) - 1:
        z_u, s_u = hits[k]
        if s_u >= 0:
            k += 1
            continue
        n = k + 1
        while n < len(hits) and hits[n][1] <= 0:
            n += 1
        if n >= len(hits):
            break
        z_e = hits[n][0]
        if MIN_GAP_MM <= z_u - z_e <= max_gap:
            below = hits[n + 1][0] if n + 1 < len(hits) else None
            gaps.append((z_e, z_u, below))
        k = n
    return gaps


CURTAIN_THICKNESS_MM = 0.35   # inward depth of the survey-line wall (covers the grid steps)
CURTAIN_SAMPLE_MM = 0.15      # spacing of the wall stations along the survey line
CURTAIN_MIN_CHAIN_MM = 1.0    # shorter silhouette pieces are scan noise
CURTAIN_NAME = 'DSG_BlockoutFill_Curtain'


def survey_line_from_mesh(world, triangles, tri_normals, tree, axis):
    """Line of maximum crown perimeter on the mesh, from the clinician's view.

    Each triangle is classified with a ray towards the viewer (the guide
    arrives from -axis): *visible* when it faces the viewer and the ray is
    free.  The survey line is made of the mesh edges between a visible
    triangle and a triangle turned away from the viewer – the silhouette of
    the crown, where its perimeter is maximum.  Returns chains of vertex
    indices (lists), shortest noise removed."""
    a = np.array(axis, dtype=np.float64)
    tris = np.asarray(triangles, dtype=np.int64)
    centers = world[tris].mean(axis=1)
    facing = tri_normals @ (-a)
    visible = facing > 1.0e-4
    down = Vector(-a)
    for t in np.flatnonzero(visible).tolist():
        origin = Vector(centers[t]) + down * 0.01
        location, _normal, _index, _distance = tree.ray_cast(origin, down, 60.0)
        if location is not None:
            visible[t] = False                       # hidden by another part
    away = facing <= 1.0e-4
    edges = np.vstack([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    owner = np.concatenate([np.arange(len(tris))] * 3)
    keys = np.sort(edges, axis=1)
    order = np.lexsort((keys[:, 1], keys[:, 0]))
    keys, owner = keys[order], owner[order]
    same = np.all(keys[1:] == keys[:-1], axis=1)
    first = np.flatnonzero(same)
    t1, t2 = owner[first], owner[first + 1]
    survey = (visible[t1] & away[t2]) | (visible[t2] & away[t1])
    pairs = keys[first[survey]]
    # chains
    neighbours = {}
    for p, q in pairs.tolist():
        neighbours.setdefault(p, []).append(q)
        neighbours.setdefault(q, []).append(p)
    seen_edges = set()
    chains = []
    starts = [v for v, n in neighbours.items() if len(n) != 2] + list(neighbours)
    for start in starts:
        for nxt in list(neighbours[start]):
            key = (min(start, nxt), max(start, nxt))
            if key in seen_edges:
                continue
            chain = [start]
            prev, cur = start, nxt
            seen_edges.add(key)
            while True:
                chain.append(cur)
                options = [n for n in neighbours[cur] if n != prev
                           and (min(cur, n), max(cur, n)) not in seen_edges]
                if len(neighbours[cur]) != 2 or not options:
                    break
                prev, cur = cur, options[0]
                seen_edges.add((min(prev, cur), max(prev, cur)))
            chains.append(chain)
    result = []
    for chain in chains:
        pts = world[chain]
        length = float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum())
        if length >= CURTAIN_MIN_CHAIN_MM:
            result.append(chain)
    return result


def _resample(chain, world, step):
    """Keep chain vertices at least ``step`` apart (mesh points, no smoothing)."""
    kept = [chain[0]]
    for index in chain[1:]:
        if np.linalg.norm(world[index] - world[kept[-1]]) >= step:
            kept.append(index)
    if kept[-1] != chain[-1]:
        kept.append(chain[-1])
    return kept


def build_survey_curtain(world, triangles, tri_normals, vertex_normals, tree, axis,
                         relief_mm, draft_deg, max_gap_mm=25.0):
    """Walls standing on the survey line of the mesh (vertices, faces, line).

    For every station of the survey line the wall rises parallel to the
    axis (opening by tan(draft) towards the gingiva) from the line, placed
    ``relief`` inside it, up to the surface that hides the undercut.  Each
    wall is a closed band ``CURTAIN_THICKNESS_MM`` deep towards the tooth, so
    the grid fill behind it never shows.  Stations without a hiding surface
    above (nothing to block) split the band."""
    a = np.array(axis, dtype=np.float64)
    av = Vector(a)
    relief = max(0.0, float(relief_mm))
    tan_draft = math.tan(math.radians(min(15.0, max(0.0, float(draft_deg)))))
    chains = survey_line_from_mesh(world, triangles, tri_normals, tree, a)
    vertices = []
    faces = []
    line_points = []
    line_edges = []
    for chain in chains:
        closed = len(chain) > 3 and chain[0] == chain[-1]
        stations = _resample(chain[:-1] if closed else chain, world, CURTAIN_SAMPLE_MM)
        run = []

        def flush(run, closed_run):
            if len(run) < 2:
                return
            base = len(vertices)
            for ring in run:
                vertices.extend(ring)
            count = len(run)
            last = count if closed_run else count - 1
            for k in range(last):
                i0 = base + 4 * k
                i1 = base + 4 * ((k + 1) % count)
                ob0, ot0, it0, ib0 = i0, i0 + 1, i0 + 2, i0 + 3
                ob1, ot1, it1, ib1 = i1, i1 + 1, i1 + 2, i1 + 3
                faces.append((ob0, ob1, ot1, ot0))      # outer wall (the visible one)
                faces.append((ot0, ot1, it1, it0))      # roof (inside the gingiva)
                faces.append((it0, it1, ib1, ib0))      # inner face (inside the fill)
                faces.append((ib0, ib1, ob1, ob0))      # floor (on the survey line)
            if not closed_run:
                s, e = base, base + 4 * (count - 1)
                faces.append((s + 3, s + 2, s + 1, s))
                faces.append((e, e + 1, e + 2, e + 3))

        for index in stations:
            s = world[index]
            n = vertex_normals[index] - (vertex_normals[index] @ a) * a
            length = float(np.linalg.norm(n))
            if length < 1.0e-6:
                flush(run, False)
                run = []
                continue
            n /= length                                  # outward, in the plane
            start = Vector(s + n * 0.03 + a * 0.01)
            location, normal, _index, distance = tree.ray_cast(start, av, max_gap_mm)
            if location is None or normal.dot(av) >= 0.0:
                flush(run, False)
                run = []
                continue
            z_s = float(s @ a)
            top = float(np.array(location) @ a) + MERGE_MM
            plane = s - z_s * a
            lean = min(MAX_DRAFT_OFFSET_MM, max(0.0, top - z_s) * tan_draft)
            outer_bottom = plane - n * relief + a * z_s
            outer_top = plane + n * (lean - relief) + a * top
            inner_top = plane - n * (relief + CURTAIN_THICKNESS_MM) + a * top
            inner_bottom = plane - n * (relief + CURTAIN_THICKNESS_MM) + a * (z_s - 0.1)
            run.append([tuple(outer_bottom), tuple(outer_top), tuple(inner_top), tuple(inner_bottom)])
            line_points.append(tuple(s))
            if len(run) > 1:
                line_edges.append((len(line_points) - 2, len(line_points) - 1))
        flush(run, closed and len(run) == len(stations))
    return vertices, faces, (line_points, line_edges)


def trace_survey_line(grid):
    """Line of maximum crown perimeter, traced with rays parallel to the view.

    For every edge between a hidden column (shadow of a crown) and an open
    column on the guide side, rays across the edge are bisected until the
    last hidden one: the point where it grazes the tooth is on the height of
    contour.  Points sharing a grid corner are linked into the line.
    Returns (points, edges)."""
    tree = grid.get('tree')
    if tree is None:
        return [], []
    cell = float(grid['cell'])
    reach = grid['reach']
    axis, e1, e2 = grid['axis'], grid['e1'], grid['e2']
    top_h, span, max_gap = grid['top_h'], grid['span'], grid['max_gap']
    points = []
    corners = {}
    for mask, surface, underside in grid.get('shadow', []):
        nu, nv = mask.shape
        for i, j in zip(*np.nonzero(mask)):
            for (di, dj), corner_a, corner_b in (((0, -1), (i, j), (i + 1, j)),
                                                 ((1, 0), (i + 1, j), (i + 1, j + 1)),
                                                 ((0, 1), (i, j + 1), (i + 1, j + 1)),
                                                 ((-1, 0), (i, j), (i, j + 1))):
                ni, nj = i + di, j + dj
                if 0 <= ni < nu and 0 <= nj < nv:
                    if mask[ni, nj] or not (reach[ni, nj] > surface[i, j] + 1.0e-3):
                        continue
                cu = grid['u0'] + (i + 0.5) * cell
                cv = grid['v0'] + (j + 0.5) * cell
                z_lo = float(surface[i, j]) - 0.3
                z_hi = float(underside[i, j]) + 0.3

                def probe(s):
                    return _gap_near(_column_gaps(tree, axis, e1, e2, cu + di * s, cv + dj * s,
                                                  top_h, span, max_gap), z_lo, z_hi)

                if probe(0.0) is None:
                    continue
                lo, hi = 0.0, cell
                if probe(hi) is not None:
                    continue
                for _ in range(REFINE_ITERATIONS):
                    mid = 0.5 * (lo + hi)
                    if probe(mid) is None:
                        hi = mid
                    else:
                        lo = mid
                hidden = probe(lo)
                su, sv = cu + di * lo, cv + dj * lo
                points.append(tuple(e1 * su + e2 * sv + axis * hidden[0]))
                index = len(points) - 1
                corners.setdefault(corner_a, []).append(index)
                corners.setdefault(corner_b, []).append(index)
    edges = []
    for members in corners.values():
        if len(members) == 2:
            edges.append((members[0], members[1]))
        elif len(members) > 2:
            for a, b in zip(members, members[1:]):
                edges.append((a, b))
    return points, edges


def _gap_near(gaps, z_lo, z_hi):
    for z_e, z_u, below in gaps:
        if z_u >= z_lo and z_e <= z_hi:
            return z_e, z_u, below
    return None


def refine_outline(grid, mask, tops, bottoms, ci, cj, corner_top, corner_bot, walls):
    """Trace the line of maximum crown perimeter and stand the walls on it.

    Step 1 – survey line.  Rays parallel to the clinician's view (the
    insertion axis) are cast across every outline edge of the fill that faces
    the guide side, between the centre of the filled column (hidden by the
    crown) and its open neighbour.  Bisection finds where the rays stop being
    hidden: that is the crown's height of contour, the line of maximum
    perimeter seen from the view.  Its 3D point is where the last hidden ray
    grazes the tooth.

    Step 2 – walls.  Each outline corner is moved (dual contouring, a 2x2
    least-squares fit of its two edges) so the wall stands ``relief`` inside
    that line, parallel to the axis; with a draft angle the wall opens
    towards the gingiva by (height above the line) · tan(draft).  Floor and
    roof are read on the mesh at the wall position.

    Returns per-corner (u_top, v_top, u_bot, v_bot, top, bottom) and the
    survey line as (points, edges).
    """
    tree = grid.get('tree')
    cell = float(grid['cell'])
    u = grid['u0'] + ci * cell
    v = grid['v0'] + cj * cell
    out = [u.astype(np.float64), v.astype(np.float64), u.astype(np.float64), v.astype(np.float64),
           corner_top[ci, cj].astype(np.float64), corner_bot[ci, cj].astype(np.float64)]
    survey_points = []
    survey_edges = []
    if tree is None or not walls:
        return out, (survey_points, survey_edges)
    nu, nv = mask.shape
    reach = grid['reach']
    axis = grid['axis']
    e1 = grid['e1']
    e2 = grid['e2']
    top_h = grid['top_h']
    span = grid['span']
    max_gap = grid['max_gap']
    relief = float(grid.get('relief', 0.0))
    tan_draft = math.tan(math.radians(min(15.0, float(grid.get('draft_deg', 0.0)))))
    if grid.get('curtain'):
        tan_draft = 0.0     # the survey-line wall carries the draft; the grid stays behind it
    n_corner = len(ci)
    per_corner = [[] for _ in range(n_corner)]      # (normal(2), shift, z_s, survey index)

    def gaps_at(pu, pv):
        return _column_gaps(tree, axis, e1, e2, pu, pv, top_h, span, max_gap)

    for p, q, (i, j), (ni, nj) in walls:
        if 0 <= ni < nu and 0 <= nj < nv:
            if mask[ni, nj] or not (reach[ni, nj] > bottoms[i, j] + 1.0e-3):
                continue                      # crown side: not a guide-facing wall
        direction = np.array([ni - i, nj - j], dtype=np.float64)
        cu = grid['u0'] + (i + 0.5) * cell
        cv = grid['v0'] + (j + 0.5) * cell
        z_lo = float(bottoms[i, j]) - 0.3
        z_hi = float(tops[i, j]) + 0.3

        def probe(s):
            return _gap_near(gaps_at(cu + direction[0] * s, cv + direction[1] * s), z_lo, z_hi)

        if probe(0.0) is None:
            continue
        lo, hi = 0.0, 0.5 * cell + relief + 2.5 * cell
        if probe(hi) is not None:
            continue
        for _ in range(REFINE_ITERATIONS):
            mid = 0.5 * (lo + hi)
            if probe(mid) is None:
                hi = mid
            else:
                lo = mid
        hidden = probe(lo)
        z_s = hidden[0]
        su = cu + direction[0] * lo
        sv = cv + direction[1] * lo
        survey_points.append(tuple(e1 * su + e2 * sv + axis * z_s))
        index = len(survey_points) - 1
        shift = max(0.05 * cell, min(0.95 * cell, lo - relief)) - 0.5 * cell
        per_corner[p].append((direction, shift, z_s, index))
        per_corner[q].append((direction, shift, z_s, index))

    for k in range(n_corner):
        entries = per_corner[k]
        if not entries:
            continue
        normals = np.array([e[0] for e in entries])
        shifts = np.array([e[1] for e in entries])
        delta, *_ = np.linalg.lstsq(normals, shifts, rcond=None)
        length = float(np.linalg.norm(delta))
        if length > 0.6 * cell:
            delta *= 0.6 * cell / length
        outward = normals.sum(axis=0)
        norm = float(np.linalg.norm(outward))
        outward = outward / norm if norm > 1.0e-9 else normals[0]
        z_s = float(np.mean([e[2] for e in entries]))
        if len(entries) >= 2:
            survey_edges.append((entries[0][3], entries[1][3]))
        bu = u[k] + delta[0]
        bv = v[k] + delta[1]
        i, j = int(ci[k]), int(cj[k])
        z_lo = float(corner_bot[i, j]) - 0.3
        z_hi = float(corner_top[i, j]) + 0.3
        at_wall = _gap_near(gaps_at(bu, bv), z_lo, z_hi)
        if at_wall is not None:
            z_e, _z_u, below = at_wall
            sink = min(SINK_MM, 0.45 * (z_e - below)) if below is not None else SINK_MM
            bottom = z_e - sink
            z_floor = z_e
        else:
            bottom = min(z_s, float(corner_bot[i, j]))
            z_floor = z_s
        top = float(corner_top[i, j])
        tu, tv = bu, bv
        for _ in range(2 if tan_draft > 0.0 else 1):   # roof height and lean depend on each other
            lean = min(MAX_DRAFT_OFFSET_MM, max(0.0, top - z_s) * tan_draft)
            tu = bu + outward[0] * lean
            tv = bv + outward[1] * lean
            start = e1 * tu + e2 * tv + axis * (max(z_s, z_floor) + 0.02)
            location, normal, _index, _distance = tree.ray_cast(start, axis, max_gap)
            if location is not None and normal.dot(axis) < 0.0:
                top = float(location.dot(axis)) + MERGE_MM
        out[0][k], out[1][k] = tu, tv
        out[2][k], out[3][k] = bu, bv
        out[4][k] = max(top, bottom + MIN_GAP_MM)
        out[5][k] = bottom
    return out, (survey_points, survey_edges)

def _components(mask):
    """Connected components (4-neighbourhood) as lists of cells."""
    seen = np.zeros_like(mask)
    nu, nv = mask.shape
    out = []
    for i0, j0 in zip(*np.nonzero(mask)):
        if seen[i0, j0]:
            continue
        stack = [(i0, j0)]
        seen[i0, j0] = True
        cells = []
        while stack:
            i, j = stack.pop()
            cells.append((i, j))
            for ni, nj in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                if 0 <= ni < nu and 0 <= nj < nv and mask[ni, nj] and not seen[ni, nj]:
                    seen[ni, nj] = True
                    stack.append((ni, nj))
        out.append(cells)
    return out


def clean_mask(mask, tops, bottoms, underside, surface):
    """Join needles into continuous walls and drop isolated micro-pockets.

    A one-cell closing bridges single-cell gaps between fill columns (the new
    cells take the most conservative neighbour heights), then components
    smaller than ``MIN_COMPONENT_CELLS`` (< 0.06 mm² at 0.1 mm) are removed:
    they would print as needles and are below any clinical retention.  The
    dropped cells are returned (treated as accepted micro-undercut)."""
    closed = _dilate(mask, 1)
    closed = ~_dilate(~closed, 1)
    new = closed & ~mask
    if new.any():
        nu, nv = mask.shape
        for i, j in zip(*np.nonzero(new)):
            near = [(ni, nj) for ni, nj in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1),
                                            (i + 1, j + 1), (i - 1, j - 1), (i + 1, j - 1), (i - 1, j + 1))
                    if 0 <= ni < nu and 0 <= nj < nv and mask[ni, nj]]
            if not near:
                continue
            tops[i, j] = max(tops[p] for p in near)
            bottoms[i, j] = min(bottoms[p] for p in near)
            underside[i, j] = max(underside[p] for p in near)
            surface[i, j] = min(surface[p] for p in near)
            mask[i, j] = True
    dropped = np.zeros_like(mask)
    # Opening: strips one or two cells wide (≤ 0.2 mm: scan micro-folds of
    # the mucosa) would print as thin plates hanging from the gingiva; the
    # resin cannot enter such a slit through the fit spacer anyway.
    opened = _dilate(~_dilate(~mask, 1), 1) & mask
    thin = mask & ~opened
    if thin.any():
        mask[thin] = False
        dropped |= thin
    for cells in _components(mask):
        if len(cells) < MIN_COMPONENT_CELLS:
            for p in cells:
                mask[p] = False
                dropped[p] = True
    return dropped


def erode_open_side(mask, underside, surface, reach, steps):
    """Remove ``steps`` cells of fill from the side the guide comes from.

    The guide arrives from -axis.  A fill cell (gap between the tooth surface
    beyond the height of contour, ``surface``, and the surface that hides it,
    ``underside``) is reachable when the guide already stands higher than the
    gap floor in a neighbouring column: there it can slide horizontally under
    the height of contour.  Columns through the crown are never open, so no
    closed void is created.  Returns the removed cells (the retention band);
    ``mask`` is modified in place.
    """
    nu, nv = mask.shape
    level = np.where(mask, -np.inf, reach)          # guide height per column
    removed = np.zeros_like(mask)
    for _ in range(int(steps)):
        open_side = np.zeros_like(mask)
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            neighbour = np.full((nu, nv), -np.inf)
            src_i = slice(max(0, di), nu + min(0, di))
            dst_i = slice(max(0, -di), nu + min(0, -di))
            src_j = slice(max(0, dj), nv + min(0, dj))
            dst_j = slice(max(0, -dj), nv + min(0, -dj))
            neighbour[dst_i, dst_j] = level[src_i, src_j]
            open_side |= neighbour > surface + 1.0e-3
        take = mask & open_side
        if not take.any():
            break
        mask[take] = False
        removed |= take
        level[take] = underside[take]
    return removed


def _repair_mask(mask, tops, bottoms):
    """Make the cell set build a manifold slab: no diagonal-only contacts
    and no single-cell holes."""
    for _ in range(40):
        changed = False
        a = mask[:-1, :-1]
        b = mask[1:, :-1]
        c = mask[:-1, 1:]
        d = mask[1:, 1:]
        diag1 = a & d & ~b & ~c          # (i,j) and (i+1,j+1)
        diag2 = b & c & ~a & ~d          # (i+1,j) and (i,j+1)
        for (ii, jj) in zip(*np.nonzero(diag1)):
            mask[ii + 1, jj] = True
            tops[ii + 1, jj] = 0.5 * (tops[ii, jj] + tops[ii + 1, jj + 1])
            bottoms[ii + 1, jj] = 0.5 * (bottoms[ii, jj] + bottoms[ii + 1, jj + 1])
            changed = True
        for (ii, jj) in zip(*np.nonzero(diag2)):
            if mask[ii, jj] or mask[ii + 1, jj + 1]:
                continue
            mask[ii, jj] = True
            tops[ii, jj] = 0.5 * (tops[ii + 1, jj] + tops[ii, jj + 1])
            bottoms[ii, jj] = 0.5 * (bottoms[ii + 1, jj] + bottoms[ii, jj + 1])
            changed = True
        # single-cell holes surrounded on four sides
        inner = np.zeros_like(mask)
        inner[1:-1, 1:-1] = (~mask[1:-1, 1:-1] & mask[:-2, 1:-1] & mask[2:, 1:-1]
                             & mask[1:-1, :-2] & mask[1:-1, 2:])
        if inner.any():
            for (ii, jj) in zip(*np.nonzero(inner)):
                near = [(ii - 1, jj), (ii + 1, jj), (ii, jj - 1), (ii, jj + 1)]
                mask[ii, jj] = True
                tops[ii, jj] = float(np.mean([tops[p] for p in near]))
                bottoms[ii, jj] = float(np.mean([bottoms[p] for p in near]))
            changed = True
        if not changed:
            break
    return mask, tops, bottoms


def slab_geometry(mask, tops, bottoms, grid):
    """Closed quad mesh of one fill layer: vertices (world) and faces."""
    mask, tops, bottoms = _repair_mask(mask.copy(), tops.copy(), bottoms.copy())
    nu, nv = mask.shape
    cell = grid['cell']
    # Corner heights: the LOWEST top and the LOWEST bottom of the masked
    # cells sharing the corner.  An average lifts the roof of a low column
    # towards a tall neighbour and the roof then sticks out of the bulge as a
    # fin (12 % of the corners, up to 0.8 mm, on a real arch); the lowest
    # top keeps every roof inside the surface that hides the gap, and the
    # lowest bottom keeps every floor inside the tooth below it.
    count = np.zeros((nu + 1, nv + 1))
    corner_top = np.full((nu + 1, nv + 1), np.inf)
    corner_bot = np.full((nu + 1, nv + 1), np.inf)
    m = mask.astype(np.float64)
    big_top = np.where(mask, tops, np.inf)
    big_bot = np.where(mask, bottoms, np.inf)
    for di in (0, 1):
        for dj in (0, 1):
            count[di:di + nu, dj:dj + nv] += m
            corner_top[di:di + nu, dj:dj + nv] = np.minimum(corner_top[di:di + nu, dj:dj + nv], big_top)
            corner_bot[di:di + nu, dj:dj + nv] = np.minimum(corner_bot[di:di + nu, dj:dj + nv], big_bot)
    used = count > 0
    corner_top = np.where(used, corner_top, 0.0)
    corner_bot = np.where(used, corner_bot, 0.0)
    corner_top = np.maximum(corner_top, corner_bot + MIN_GAP_MM)

    ci, cj = np.nonzero(used)
    n_corner = len(ci)
    index = -np.ones((nu + 1, nv + 1), dtype=np.int64)
    index[ci, cj] = np.arange(n_corner)
    axis = np.array(grid['axis'], dtype=np.float64)
    e1 = np.array(grid['e1'], dtype=np.float64)
    e2 = np.array(grid['e2'], dtype=np.float64)
    uu = grid['u0'] + ci * cell
    vv = grid['v0'] + cj * cell
    T = lambda i, j: index[i, j]                         # noqa: E731
    B = lambda i, j: index[i, j] + n_corner              # noqa: E731

    faces = []
    wall_edges = []
    walls = []
    padded = np.zeros((nu + 2, nv + 2), dtype=bool)
    padded[1:-1, 1:-1] = mask
    for i, j in zip(*np.nonzero(mask)):
        c0, c1, c2, c3 = (i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)
        faces.append((T(*c0), T(*c1), T(*c2), T(*c3)))           # top, normal +axis
        faces.append((B(*c0), B(*c3), B(*c2), B(*c1)))           # bottom
        # walls on the edges whose neighbour is empty: (p, q, neighbour)
        for p, q, (ni, nj) in ((c0, c1, (i, j - 1)), (c1, c2, (i + 1, j)),
                               (c2, c3, (i, j + 1)), (c3, c0, (i - 1, j))):
            if not padded[ni + 1, nj + 1]:
                faces.append((T(*q), T(*p), B(*p), B(*q)))
                wall_edges.append((T(*p), T(*q)))
                walls.append((T(*p), T(*q), (i, j), (ni, nj)))
    survey = ([], [])
    if grid.get('tree') is not None and grid.get('refine', True):
        (ut, vt, ub, vb, tz, bz), survey = refine_outline(
            grid, mask, tops, bottoms, ci, cj, corner_top, corner_bot, walls)
    else:
        uu, vv = smooth_outline(uu, vv, wall_edges)
        ut, vt, ub, vb = uu, vv, uu, vv
        tz, bz = corner_top[ci, cj], corner_bot[ci, cj]
    verts_top = ut[:, None] * e1 + vt[:, None] * e2 + np.asarray(tz)[:, None] * axis
    verts_bot = ub[:, None] * e1 + vb[:, None] * e2 + np.asarray(bz)[:, None] * axis
    vertices = np.vstack([verts_top, verts_bot])
    grid.setdefault('survey', []).append(survey)
    return vertices, faces


def smooth_outline(uu, vv, wall_edges, iterations=WALL_SMOOTH_ITERATIONS):
    """Smooth the stair-stepped outline in the plane (walls stay vertical).

    Only corners on the outline move, each towards the mean of its two
    outline neighbours, at most half a cell: the topology is unchanged."""
    if not wall_edges or iterations <= 0:
        return uu, vv
    edges = np.asarray(wall_edges, dtype=np.int64)
    uu = uu.astype(np.float64).copy()
    vv = vv.astype(np.float64).copy()
    on = np.unique(edges)
    degree = np.bincount(edges.ravel(), minlength=len(uu)).astype(np.float64)
    for _ in range(int(iterations)):
        su = np.zeros_like(uu)
        sv = np.zeros_like(vv)
        np.add.at(su, edges[:, 0], uu[edges[:, 1]])
        np.add.at(su, edges[:, 1], uu[edges[:, 0]])
        np.add.at(sv, edges[:, 0], vv[edges[:, 1]])
        np.add.at(sv, edges[:, 1], vv[edges[:, 0]])
        mean_u = su[on] / degree[on]
        mean_v = sv[on] / degree[on]
        uu[on] = 0.5 * uu[on] + 0.5 * mean_u
        vv[on] = 0.5 * vv[on] + 0.5 * mean_v
    return uu, vv


def build_fill_objects(context, tree, axis, candidate_points, relief_mm,
                       extent_points=None, name=FILL_NAME, candidate_hits=None,
                       draft_deg=0.0, surface=None, vertex_hits=None):
    """Create one hidden slab object per fill layer; returns (objects, stats)."""
    started = time.perf_counter()
    if surface is not None and vertex_hits is not None:
        try:
            swept = _build_sweep_object(context, tree, axis, relief_mm, draft_deg, surface,
                                        vertex_hits, name)
        except Exception:
            import logging
            logging.getLogger('dsg').warning('view extrusion blockout failed; grid fill used', exc_info=True)
            swept = None
        if swept is not None:
            stats = {'layers': 1, 'cells': 0, 'band_cells': 0, 'cell_mm': 0.0, 'rays': 0,
                     'scanned_columns': 0, 'method': 'VIEW_EXTRUSION',
                     'seconds': round(time.perf_counter() - started, 2)}
            return [swept], stats
    curtain = None
    if surface is not None:
        try:
            world_s, tris_s, tri_n_s, vert_n_s = surface
            curtain = build_survey_curtain(world_s, tris_s, tri_n_s, vert_n_s, tree, axis,
                                           relief_mm, draft_deg)
            if not curtain[1]:
                curtain = None
        except Exception:
            import logging
            logging.getLogger('dsg').warning('survey-line wall failed', exc_info=True)
            curtain = None
    # With the survey-line wall in front, the grid fill steps back one more
    # cell so its stepped outline always stays hidden behind the wall.
    layers, grid = scan_columns(tree, axis, candidate_points, relief_mm,
                                extent_points=extent_points, candidate_hits=candidate_hits,
                                draft_deg=draft_deg, extra_erosion=1 if curtain else 0)
    if grid is not None and curtain is not None:
        # Grid walls still follow the contour, one cell behind the wall that
        # stands on the survey line (never coplanar with it).
        grid['relief'] = float(grid['relief']) + float(grid['cell'])
        grid['curtain'] = True
    objects = []
    cells = 0
    for number, (mask, tops, bottoms) in enumerate(layers):
        vertices, faces = slab_geometry(mask, tops, bottoms, grid)
        if not faces:
            continue
        cells += int(mask.sum())
        mesh = bpy.data.meshes.new(f'{name}_{number}_Mesh')
        mesh.from_pydata(vertices.tolist(), [], faces)
        mesh.validate(clean_customdata=False)
        mesh.update(calc_edges=True)
        obj = bpy.data.objects.new(f'{name}_{number}', mesh)
        context.scene.collection.objects.link(obj)
        obj.hide_render = True
        obj.hide_set(True)
        obj['DSG_visual_only'] = False
        obj['DSG_exclude_from_export'] = True
        obj['DSG_undercut_fill'] = True
        obj['DSG_fill_layer'] = number
        obj['DSG_fill_relief_mm'] = float(relief_mm)
        obj['DSG_fill_draft_deg'] = float(draft_deg)
        objects.append(obj)
    if curtain is not None:
        import bmesh
        c_vertices, c_faces, _line = curtain
        mesh = bpy.data.meshes.new(CURTAIN_NAME + '_Mesh')
        mesh.from_pydata(c_vertices, [], c_faces)
        mesh.validate(clean_customdata=False)
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.to_mesh(mesh)
        bm.free()
        mesh.update(calc_edges=True)
        obj = bpy.data.objects.new(CURTAIN_NAME, mesh)
        context.scene.collection.objects.link(obj)
        obj.hide_render = True
        obj.hide_set(True)
        obj['DSG_visual_only'] = False
        obj['DSG_exclude_from_export'] = True
        obj['DSG_undercut_fill'] = True
        obj['DSG_fill_layer'] = -1
        obj['DSG_fill_relief_mm'] = float(relief_mm)
        obj['DSG_fill_draft_deg'] = float(draft_deg)
        obj['DSG_fill_version'] = FILL_VERSION
        objects.append(obj)
    if objects and grid is not None:
        band = grid.get('band')
        objects[0]['DSG_fill_version'] = FILL_VERSION
        objects[0]['DSG_fill_grid'] = [float(grid['u0']), float(grid['v0']), float(grid['cell']),
                                       float(grid['nu']), float(grid['nv'])]
        objects[0]['DSG_fill_axis'] = [float(c) for c in grid['axis']]
        objects[0]['DSG_retention_band_cells'] = (
            np.flatnonzero(band.ravel()).astype(np.int32).tolist() if band is not None else [])
        filled = np.zeros((int(grid['nu']), int(grid['nv'])), dtype=bool)
        for mask, _t, _b in layers:
            filled |= mask
        objects[0]['DSG_fill_cells'] = np.flatnonzero(filled.ravel()).astype(np.int32).tolist()
        for obj in objects:
            obj['DSG_fill_version'] = FILL_VERSION
        # Line of maximum crown perimeter traced by the rays (for the review).
        if curtain is not None:
            points, edges = curtain[2]
        else:
            try:
                points, edges = trace_survey_line(grid)
            except Exception:
                points, edges = [], []
        objects[0]['DSG_survey_points'] = [float(c) for point in points for c in point]
        objects[0]['DSG_survey_edges'] = [int(i) for edge in edges for i in edge]
    stats = {
        'layers': len(objects), 'cells': cells,
        'band_cells': int(grid['band'].sum()) if grid and grid.get('band') is not None else 0,
        'cell_mm': float(grid['cell']) if grid else 0.0,
        'rays': int(grid['rays']) if grid else 0,
        'scanned_columns': int(grid['scanned']) if grid else 0,
        'seconds': round(time.perf_counter() - started, 2),
    }
    return objects, stats


SWEEP_NAME = FILL_NAME + '_Sweep'
SWEEP_VOXEL_MM = 0.06


def _build_sweep_object(context, tree, axis, relief_mm, draft_deg, surface, vertex_hits, name):
    """9.24: blockout by extrusion along the view (Open Dental CAD method)."""
    import bmesh
    from . import blockout_sweep
    world_s, tris_s, tri_n_s, vert_n_s = surface
    a = np.array(axis, dtype=np.float64)
    points, edges = blockout_sweep.survey_line(world_s, tris_s, tri_n_s, a, tree)
    vertices, faces = blockout_sweep.build_sweep(
        world_s, tris_s, vert_n_s, vertex_hits, a, relief_mm=relief_mm, draft_deg=draft_deg,
        survey_points=points, tree=tree)
    if not faces:
        return None
    mesh = bpy.data.meshes.new(SWEEP_NAME + '_Mesh')
    mesh.from_pydata(vertices.tolist(), [], faces)
    mesh.validate(clean_customdata=False)
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(mesh)
    bm.free()
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(SWEEP_NAME, mesh)
    context.scene.collection.objects.link(obj)
    obj.hide_render = True
    obj.hide_set(True)
    obj['DSG_visual_only'] = False
    obj['DSG_exclude_from_export'] = True
    obj['DSG_undercut_fill'] = True
    obj['DSG_fill_layer'] = 0
    obj['DSG_fill_relief_mm'] = float(relief_mm)
    obj['DSG_fill_draft_deg'] = float(draft_deg)
    obj['DSG_fill_version'] = FILL_VERSION
    obj['DSG_fill_method'] = 'VIEW_EXTRUSION'
    obj['DSG_fill_axis'] = [float(c) for c in a]
    obj['DSG_survey_points'] = [float(c) for p in points for c in p]
    obj['DSG_survey_edges'] = [int(i) for e in edges for i in e]
    return obj


def remove_fill(name=FILL_NAME):
    for obj in list(bpy.data.objects):
        if obj.name.startswith(name + '_') and obj.get('DSG_undercut_fill'):
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh is not None and mesh.users == 0:
                bpy.data.meshes.remove(mesh)


def fill_objects(name=FILL_NAME):
    return sorted((o for o in bpy.data.objects
                   if o.type == 'MESH' and o.name.startswith(name + '_') and o.get('DSG_undercut_fill')),
                  key=lambda o: o.name)


def covered(points, axis, objects, probe_mm=0.02):
    """True per point when it lies inside one of the fill slabs."""
    from mathutils.bvhtree import BVHTree
    axis = Vector(axis).normalized()
    trees = []
    for obj in objects:
        mesh = obj.data
        world = [obj.matrix_world @ v.co for v in mesh.vertices]
        trees.append(BVHTree.FromPolygons(world, [tuple(p.vertices) for p in mesh.polygons]))
    result = np.zeros(len(points), dtype=bool)
    head = objects[0] if objects else None
    # View extrusion: points within the retention of the survey line are the
    # undercut the clinician allowed.
    if head is not None and head.get('DSG_fill_method') == 'VIEW_EXTRUSION':
        relief = float(head.get('DSG_fill_relief_mm', 0.0))
        survey = np.asarray(list(head.get('DSG_survey_points', [])), dtype=np.float64).reshape(-1, 3)
        if relief > 0.0 and len(survey):
            from mathutils.kdtree import KDTree
            _a, e1, e2 = _basis(head.get('DSG_fill_axis', axis))
            e1 = np.array(e1)
            e2 = np.array(e2)
            kd = KDTree(len(survey))
            for n, p in enumerate(survey):
                kd.insert((float(p @ e1), float(p @ e2), 0.0), n)
            kd.balance()
            for n, p in enumerate(np.asarray(points, dtype=np.float64).reshape(-1, 3)):
                _co, _i, distance = kd.find((float(p @ e1), float(p @ e2), 0.0))
                if distance is not None and distance <= relief + 0.05:
                    result[n] = True
    # Points in the retention band are the undercut the clinician allowed.
    band = list(head.get('DSG_retention_band_cells', [])) if head is not None else []
    band += list(head.get('DSG_fill_cells', [])) if head is not None else []
    if band and head.get('DSG_fill_grid') is not None:
        u0, v0, cell, nu, nv = (float(x) for x in head['DSG_fill_grid'])
        _a, e1, e2 = _basis(head.get('DSG_fill_axis', axis))
        band_mask = np.zeros(int(nu) * int(nv), dtype=bool)
        band_mask[np.asarray(band, dtype=np.int64)] = True
        band_mask = band_mask.reshape(int(nu), int(nv))
        grown = _dilate(band_mask, 1)
        pts = np.asarray(points, dtype=np.float64).reshape(-1, 3)
        iu = np.floor((pts @ np.array(e1) - u0) / cell).astype(np.int64)
        iv = np.floor((pts @ np.array(e2) - v0) / cell).astype(np.int64)
        inside_grid = (iu >= 0) & (iu < int(nu)) & (iv >= 0) & (iv < int(nv))
        result[inside_grid] = grown[iu[inside_grid], iv[inside_grid]]
    for n, point in enumerate(points):
        if result[n]:
            continue
        origin = Vector(point) + axis * probe_mm
        for tree in trees:
            location, normal, _index, _dist = tree.ray_cast(origin, axis, 60.0)
            if location is not None and normal.dot(axis) > 0.0:
                result[n] = True          # leaving the slab upwards → inside it
                break
    return result
