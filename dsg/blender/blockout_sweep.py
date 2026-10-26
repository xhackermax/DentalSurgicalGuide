"""Blockout by extrusion along the view (DSG 9.24).

Same idea as Open Dental CAD (patmo141/odc_public, blockout_undercuts.py):
the surfaces the clinician cannot see from the insertion direction are
extruded along that direction and united with the model.  The side walls of
the extrusion stand exactly on the line of maximum crown perimeter (the
silhouette of the mesh seen from the view), so the blockout follows the real
contour of every tooth: no grid, no smoothing.

Differences with ODC, kept small:
* each vertex is extruded only up to the surface that hides it (the ray
  already cast by the blockout, ``DSG_hit_distance``) plus a small merge, not
  a fixed 10 mm, so nothing comes out of the other side of the model;
* retention: faces closer than ``relief`` (measured in the plane, like an
  undercut gauge) to the line of maximum perimeter are not extruded, so the
  wall stands ``relief`` inside that line;
* draft angle: the top of the extrusion opens outward by height·tan(draft);
* union with MANIFOLD (keeps every IOS detail); voxel remesh only as a
  fallback.

Orientation: ``axis`` points away from the guide (towards the base); the
guide arrives from -axis.
"""
import math

import numpy as np

MERGE_MM = 0.15          # the top enters the hiding surface
FLOOR_MM = 0.05          # the bottom sinks into the tooth (no coplanar faces)
MISSING_TOP_MM = 0.05    # vertex of an extruded face that is not hidden itself
AUDIT_WIDTH_MM = 0.12     # narrowest pocket that counts as a lock (≈ fit spacer)
SEAL_MM = 0.0            # no outward seal: it left overhanging ledges (new undercuts)
MIN_SURVEY_CHAIN_MM = 1.0


def _edge_pairs(triangles):
    """Pairs of triangles sharing an edge: (edge vertices, tri a, tri b)."""
    tris = np.asarray(triangles, dtype=np.int64)
    edges = np.vstack([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    owner = np.tile(np.arange(len(tris)), 3)
    keys = np.sort(edges, axis=1)
    order = np.lexsort((keys[:, 1], keys[:, 0]))
    keys, owner = keys[order], owner[order]
    same = np.all(keys[1:] == keys[:-1], axis=1)
    first = np.flatnonzero(same)
    return keys[first], owner[first], owner[first + 1]


def survey_line(world, triangles, tri_normals, axis, tree=None):
    """Line of maximum crown perimeter seen from the view.

    Mesh edges between a triangle facing the viewer and one turned away,
    where the facing one is nearer the viewer (a convex silhouette, not the
    crease at the gingival margin) and, when ``tree`` is given, visible
    (its ray towards the viewer is free).  Chains shorter than 1 mm are scan
    noise.  Returns (points (n,3), edges (m,2)) of the line."""
    a = np.asarray(axis, dtype=np.float64)
    tris = np.asarray(triangles, dtype=np.int64)
    facing = tri_normals @ (-a) > 1.0e-4
    centers = world[tris].mean(axis=1)
    keys, t1, t2 = _edge_pairs(tris)
    diff = facing[t1] != facing[t2]
    keys, t1, t2 = keys[diff], t1[diff], t2[diff]
    front = np.where(facing[t1], t1, t2)
    back = np.where(facing[t1], t2, t1)
    convex = (centers[front] @ a) < (centers[back] @ a)
    keys, front = keys[convex], front[convex]
    if tree is not None and len(front):
        from mathutils import Vector
        down = Vector(-a)
        visible = np.ones(len(front), dtype=bool)
        for n, t in enumerate(front.tolist()):
            location, _normal, _index, _distance = tree.ray_cast(Vector(centers[t]) + down * 0.01, down, 60.0)
            visible[n] = location is None
        keys = keys[visible]
    if not len(keys):
        return np.zeros((0, 3)), np.zeros((0, 2), dtype=np.int64)
    # keep connected pieces at least MIN_SURVEY_CHAIN_MM long
    vertices = np.unique(keys)
    index = {v: i for i, v in enumerate(vertices.tolist())}
    parent = list(range(len(vertices)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    local = np.array([[index[p], index[q]] for p, q in keys.tolist()], dtype=np.int64)
    for p, q in local.tolist():
        rp, rq = find(p), find(q)
        if rp != rq:
            parent[rp] = rq
    roots = np.array([find(i) for i in range(len(vertices))])
    lengths = np.linalg.norm(world[vertices[local[:, 0]]] - world[vertices[local[:, 1]]], axis=1)
    total = {}
    for edge, length in zip(local.tolist(), lengths.tolist()):
        r = roots[edge[0]]
        total[r] = total.get(r, 0.0) + length
    keep_edge = np.array([total[roots[p]] >= MIN_SURVEY_CHAIN_MM for p, _q in local.tolist()], dtype=bool)
    local = local[keep_edge]
    used = np.unique(local)
    remap = -np.ones(len(vertices), dtype=np.int64)
    remap[used] = np.arange(len(used))
    return world[vertices[used]], remap[local]


def audit_union(context, source_obj, fills, axis, relief_mm=0.0, survey_points=None,
                min_hit=0.01, reach=25.0, sample_limit=60000, ignore_tree=None):
    """Seating audit on the real result (model ∪ extrusion).

    Every vertex of the united model that is turned away from the viewer
    casts a ray away from the viewer; hitting a surface that faces the viewer
    means the guide would lock there.  Points within the retention of the
    survey line are the undercut the clinician allowed.  Returns
    (residual distances, sampled vertices)."""
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    a = np.asarray(axis, dtype=np.float64)
    a = a / np.linalg.norm(a)
    temp = bpy.data.objects.new('_DSG_SeatingAuditUnion', source_obj.data)
    temp.matrix_world = source_obj.matrix_world.copy()
    context.scene.collection.objects.link(temp)
    mesh = None
    try:
        for fill in fills:
            modifier = temp.modifiers.new('DSG_audit_union', 'BOOLEAN')
            modifier.operation = 'UNION'
            modifier.object = fill
            try:
                modifier.solver = 'MANIFOLD'
            except Exception:
                modifier.solver = 'EXACT'
        depsgraph = context.evaluated_depsgraph_get()
        mesh = bpy.data.meshes.new_from_object(temp.evaluated_get(depsgraph), depsgraph=depsgraph)
        matrix = temp.matrix_world.copy()
    finally:
        bpy.data.objects.remove(temp, do_unlink=True)
    try:
        n = len(mesh.vertices)
        co = np.empty(n * 3)
        mesh.vertices.foreach_get('co', co)
        transform = np.array(matrix, dtype=np.float64)
        world = co.reshape(-1, 3) @ transform[:3, :3].T + transform[:3, 3]
        normals = np.empty(n * 3)
        mesh.vertex_normals.foreach_get('vector', normals)
        normals = normals.reshape(-1, 3) @ np.array(matrix.to_3x3().inverted_safe().transposed()).T
        mesh.calc_loop_triangles()
        tris = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int64)
        mesh.loop_triangles.foreach_get('vertices', tris)
        tree = BVHTree.FromPolygons(world.tolist(), tris.reshape(-1, 3).tolist(), all_triangles=True)
    finally:
        bpy.data.meshes.remove(mesh)
    candidates = np.flatnonzero(normals @ a > 1.0e-3)
    step = max(1, int(math.ceil(len(candidates) / float(sample_limit))))
    candidates = candidates[::step]
    allowed = np.zeros(len(world), dtype=bool)
    relief = max(0.0, float(relief_mm))
    if relief > 0.0 and survey_points is not None and len(survey_points):
        from mathutils.kdtree import KDTree
        helper = np.array([1.0, 0.0, 0.0]) if abs(a[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        e1 = np.cross(a, helper)
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(a, e1)
        kd = KDTree(len(survey_points))
        for k, p in enumerate(np.asarray(survey_points, dtype=np.float64)):
            kd.insert((float(p @ e1), float(p @ e2), 0.0), k)
        kd.balance()
        for v in candidates.tolist():
            p = world[v]
            _c, _i, distance = kd.find((float(p @ e1), float(p @ e2), 0.0))
            allowed[v] = distance is not None and distance <= relief + AUDIT_WIDTH_MM
    av = Vector(a)
    residuals = []
    for v in candidates.tolist():
        if allowed[v]:
            continue
        location, normal, _index, distance = tree.ray_cast(Vector(world[v]) + av * 0.002, av, float(reach))
        if location is None or normal.dot(av) >= 0.0:
            continue
        if distance <= float(min_hit):
            continue
        if ignore_tree is not None:
            near = ignore_tree.find_nearest(location, 0.02)
            if near[0] is not None:
                continue              # artificial base of the closed model: not anatomy
        # A lock needs room for resin: a pocket narrower than the fit spacer
        # (IOS micro-folds, hairlines along a wall) cannot hold the guide.
        # The same ray moved AUDIT_WIDTH_MM outward must still be blocked.
        n = normals[v] - (normals[v] @ a) * a
        length = float(np.linalg.norm(n))
        if length > 1.0e-6:
            side = Vector(world[v] + n / length * AUDIT_WIDTH_MM) + av * 0.002
            location2, normal2, _i2, distance2 = tree.ray_cast(side, av, float(reach))
            if location2 is None or normal2.dot(av) >= 0.0 or distance2 <= float(min_hit):
                continue
        residuals.append(float(distance))
    return residuals, int(len(candidates))


def build_sweep(world, triangles, vertex_normals, hits, axis, relief_mm=0.0, draft_deg=0.0,
                min_hit=0.01, max_hit=25.0, survey_points=None, tree=None):
    """Closed extrusion of the hidden surface: (vertices (n,3), faces list).

    ``hits[v]`` is the distance along ``axis`` from vertex v to the surface
    that hides it (<= ``min_hit`` when it is not hidden)."""
    a = np.asarray(axis, dtype=np.float64)
    a = a / np.linalg.norm(a)
    tris = np.asarray(triangles, dtype=np.int64)
    hits = np.asarray(hits, dtype=np.float64)
    hidden = (hits > float(min_hit)) & (hits <= float(max_hit))
    selected = hidden[tris].any(axis=1)
    relief = max(0.0, float(relief_mm))
    if relief > 0.0 and survey_points is not None and len(survey_points):
        from mathutils.kdtree import KDTree
        helper = np.array([1.0, 0.0, 0.0]) if abs(a[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        e1 = np.cross(a, helper)
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(a, e1)
        kd = KDTree(len(survey_points))
        for n, p in enumerate(np.asarray(survey_points, dtype=np.float64)):
            kd.insert((float(p @ e1), float(p @ e2), 0.0), n)
        kd.balance()
        candidates = np.unique(tris[selected])
        inset = np.full(len(world), np.inf)
        for v in candidates.tolist():
            p = world[v]
            _co, _index, distance = kd.find((float(p @ e1), float(p @ e2), 0.0))
            inset[v] = distance
        # a face stays extruded when its centre is beyond the retention
        # band; requiring all three corners widened the band by a triangle
        finite = np.where(np.isfinite(inset), inset, 1.0e6)
        selected &= finite[tris].mean(axis=1) >= relief
    faces_sel = tris[selected]
    if not len(faces_sel):
        return np.zeros((0, 3)), []
    used = np.unique(faces_sel)
    remap = -np.ones(len(world), dtype=np.int64)
    remap[used] = np.arange(len(used))
    points = world[used]
    # A vertex of an extruded face that is not hidden itself (just below the
    # survey line, or at the gingival crease) rises as high as the hidden
    # vertices of its faces: the roof stays flat over the edge of the hidden
    # zone instead of sloping down and leaving a wedge open under the gum.
    # Its column runs through the crown, so the extra height is harmless.
    vertex_lift = np.where(hidden, hits + MERGE_MM, 0.0)
    face_lift = vertex_lift[faces_sel].max(axis=1)
    spread = np.zeros(len(world))
    np.maximum.at(spread, faces_sel.ravel(), np.repeat(face_lift, 3))
    # Hidden vertices also take the highest roof of their faces: between two
    # vertices the surface that hides them is curved or ragged (vestibular
    # fold), and a roof drawn straight between their own heights would dip
    # out of it and leave pockets under the gum.
    lift = np.maximum(np.maximum(spread[used], vertex_lift[used]), MISSING_TOP_MM)
    normals = np.asarray(vertex_normals, dtype=np.float64)[used]
    outward = normals - np.outer(normals @ a, a)
    length = np.linalg.norm(outward, axis=1)
    length[length < 1.0e-9] = 1.0
    outward /= length[:, None]
    tan_draft = math.tan(math.radians(min(15.0, max(0.0, float(draft_deg)))))
    bottom = points - a * FLOOR_MM + outward * SEAL_MM
    top = points + np.outer(lift, a) + outward * SEAL_MM
    count = len(used)
    f = remap[faces_sel]
    faces = [tuple(x) for x in f[:, ::-1].tolist()] + [tuple(x) for x in (f + count).tolist()]
    edges = np.vstack([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    keys = np.sort(edges, axis=1)
    _unique, inverse, counts = np.unique(keys, axis=0, return_inverse=True, return_counts=True)
    boundary = edges[counts[inverse.ravel()] == 1]
    faces += [(int(p), int(q), int(q) + count, int(p) + count) for p, q in boundary.tolist()]
    if tan_draft > 0.0 and len(boundary):
        top = _apply_draft(top, points, lift, f, boundary, a, tan_draft, tree)
    # The wall footprint follows triangle edges and zigzags ±half a triangle;
    # fair it in the plane (Taubin λ|μ, no shrinkage) so the walls are smooth
    # vertical surfaces without steps.  Only wall vertices move, never along
    # the axis, at most WALL_FAIR_MAX_MM.
    bottom, top = _fair_wall(bottom, top, boundary, a, outward)
    return np.vstack([bottom, top]), faces


DRAFT_HEIGHT_MM = 3.0     # the draft acts over the first millimetres above the survey line
MAX_LEAN_MM = 0.35        # never lean a wall more than this (no curtains)


def _apply_draft(top, points, lift, faces, boundary, axis, tan_draft, tree=None):
    """Open only the WALLS outward (9.24.2).

    Leaning every vertex of the extrusion sheared the whole volume: with
    6° and tall extrusions (vestibular fold, up to 25 mm) the tops moved
    1–2.6 mm sideways and left slanted "curtains" in the air and folded
    faces that break the final Boolean.  Now only the wall vertices lean,
    in the true outward direction of the wall (perpendicular to its edge,
    away from the extruded zone), by min(height, DRAFT_HEIGHT_MM)·tan(draft)
    capped at MAX_LEAN_MM; the top is lifted by the same amount so it stays
    buried in the surface that hides it."""
    a = np.asarray(axis, dtype=np.float64)
    count = len(points)
    # third vertex of the face owning each boundary edge
    owner = {}
    for tri in np.asarray(faces, dtype=np.int64).tolist():
        for k in range(3):
            p, q, r = tri[k], tri[(k + 1) % 3], tri[(k + 2) % 3]
            owner[(p, q)] = r
    direction = np.zeros((count, 3))
    for p, q in np.asarray(boundary, dtype=np.int64).tolist():
        r = owner.get((p, q), owner.get((q, p)))
        if r is None:
            continue
        edge = points[q] - points[p]
        edge -= (edge @ a) * a
        normal = np.cross(a, edge)
        length = float(np.linalg.norm(normal))
        if length < 1.0e-12:
            continue
        normal /= length
        inside = points[r] - points[p]
        if normal @ inside > 0.0:
            normal = -normal
        direction[p] += normal
        direction[q] += normal
    norm = np.linalg.norm(direction, axis=1)
    wall = norm > 1.0e-9
    direction[wall] /= norm[wall][:, None]
    lean = np.minimum(np.minimum(lift, DRAFT_HEIGHT_MM) * tan_draft, MAX_LEAN_MM)
    lean[~wall] = 0.0
    out = top.copy()
    if tree is None:
        moved = lean > 0.0
        out[moved] += direction[moved] * lean[moved][:, None] + np.outer(lean[moved], a)
        return out
    # The leaned top is put back on the surface that hides it, read at its
    # new position; where that surface is not found close above (the wall
    # would leave the hidden zone: vestibular fold, open side) the wall stays
    # vertical.  No top can stick out of the tissue: no curtains.
    from mathutils import Vector
    av = Vector(a)
    for v in np.flatnonzero(lean > 0.0).tolist():
        base = points[v] + direction[v] * lean[v]
        start = Vector(base + a * 0.02)
        location, normal, _index, distance = tree.ray_cast(start, av, float(lift[v]) + 1.0)
        if location is None or normal.dot(av) >= 0.0:
            continue
        height = float(distance) + 0.02 + MERGE_MM
        if height > float(lift[v]) + 1.0:
            continue
        out[v] = base + a * height
    return out


WALL_FAIR_ITERATIONS = 6
WALL_FAIR_MAX_MM = 0.12


def _fair_wall(bottom, top, boundary, axis, outward=None):
    if not len(boundary):
        return bottom, top
    edges = np.asarray(boundary, dtype=np.int64)
    ring = np.unique(edges)
    degree = np.bincount(edges.ravel(), minlength=len(bottom)).astype(np.float64)
    simple = ring[degree[ring] == 2]           # skip junctions of several walls
    if not len(simple):
        return bottom, top
    a = np.asarray(axis, dtype=np.float64)
    out = []
    for layer in (bottom, top):
        start = layer.copy()
        work = layer.copy()
        for k in range(WALL_FAIR_ITERATIONS):
            factor = 0.5 if k % 2 == 0 else -0.53
            total = np.zeros_like(work)
            np.add.at(total, edges[:, 0], work[edges[:, 1]])
            np.add.at(total, edges[:, 1], work[edges[:, 0]])
            mean = total[simple] / degree[simple][:, None]
            delta = mean - work[simple]
            delta -= np.outer(delta @ a, a)          # stay in the plane
            work[simple] += factor * delta
        move = work - start
        if outward is not None:
            # never pull a wall inward: that would reopen part of the undercut
            inward = np.einsum('ij,ij->i', move, outward)
            pull = inward < 0.0
            move[pull] -= outward[pull] * inward[pull][:, None]
        length = np.linalg.norm(move, axis=1)
        too_far = length > WALL_FAIR_MAX_MM
        move[too_far] *= (WALL_FAIR_MAX_MM / length[too_far])[:, None]
        out.append(start + move)
    return out[0], out[1]
