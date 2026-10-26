"""Neighbour-root limits for the implant proposal when the teeth are not segmented.

In the simple route the CBCT arch holds bone and teeth together, so the search
cannot see the neighbouring roots.  The crown the clinician removed from the
IOS (guided tooth removal) still tells where the gap is: its mesial and distal
faces touch the neighbouring crowns.  The neighbouring roots are taken to lie
beyond those contact planes, a little wider than the crown contour
(ROOT_OUTSET_MM), and are given to the search as two slabs that run apically
along the planned axis.  The usual tooth clearance applies to them.

This is an estimate: tilted or convergent roots must still be checked in MPR.
"""
import numpy as np

ROOT_OUTSET_MM = 0.75    # crown contour bulge over the root surface, per side
SLAB_THICKNESS_MM = 3.0
APICAL_EXTENT_MM = 24.0  # beyond any implant length in the catalogues
BUCCOLINGUAL_PAD_MM = 2.0
REMOVED_DISTANCE_MM = 0.4
NEIGHBOUR_RADIUS_MM = 12.0
EDGE_PERCENTILE = 2.0
KIND = 'Raíz vecina (estimada)'


def gap_frame(crown, ios, axis):
    """Frame of the removed crown's gap (pure numpy, world mm).

    ``crown``: points of the removed crown; ``ios``: points of the remaining IOS;
    ``axis``: planned implant axis (either sense).  Returns None if the gap
    cannot be measured.
    """
    crown = np.asarray(crown, float)
    ios = np.asarray(ios, float)
    a = np.asarray(axis, float)
    if len(crown) < 20 or len(ios) < 20 or np.linalg.norm(a) < 1e-9:
        return None
    a = a / np.linalg.norm(a)
    center = crown.mean(axis=0)
    d = ios - center
    t = d @ a
    q = d - np.outer(t, a)
    # Orient the axis occlusally: what remains of the IOS inside the crown's
    # footprint is the ridge / closed socket, on the apical side.
    under = np.linalg.norm(q, axis=1) < 2.5
    if under.sum() and np.mean(t[under]) > 0:
        a, t = -a, -t
    t_crown = (crown - center) @ a
    t_occ, t_cer = float(t_crown.max()), float(t_crown.min())
    band = (t > t_cer + 1.5) & (t <= t_occ + 0.5) & (np.linalg.norm(q, axis=1) < NEIGHBOUR_RADIUS_MM)
    if band.sum() < 20:
        return None
    # The neighbouring crowns spread along the arch: their main direction is
    # mesio-distal, whatever the shape of the removed crown.
    neighbours = q[band]
    _values, vectors = np.linalg.eigh(np.cov(neighbours.T))
    e1 = vectors[:, -1]
    e1 = e1 - (e1 @ a) * a
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(a, e1)
    qc = (crown - center) - np.outer(t_crown, a)
    s1, s2 = qc @ e1, qc @ e2
    lo, hi = np.percentile(s1, [EDGE_PERCENTILE, 100 - EDGE_PERCENTILE])
    bl_lo, bl_hi = np.percentile(s2, [EDGE_PERCENTILE, 100 - EDGE_PERCENTILE])
    if hi - lo < 3.0:
        return None
    return {'center': center, 'axis': a, 'e1': e1, 'e2': e2,
            'lo': float(lo), 'hi': float(hi), 'bl_lo': float(bl_lo), 'bl_hi': float(bl_hi),
            't_occ': t_occ, 't_cer': t_cer}


_BOX_FACES = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
                       [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]], int)


def _box(origin, u, v, w, su, sv, sw):
    corners = []
    for z in (sw[0], sw[1]):
        for x, y in ((su[0], sv[0]), (su[1], sv[0]), (su[1], sv[1]), (su[0], sv[1])):
            corners.append(origin + x * u + y * v + z * w)
    vertices = np.array(corners, float)
    faces = _BOX_FACES.copy()
    # Outward winding whatever the handedness of (u, v, w).
    if np.dot(np.cross(u, v), w) < 0:
        faces = faces[:, ::-1]
    return vertices, faces


def slabs(frame):
    """Two closed boxes beyond the mesial and distal contacts, running apically."""
    c, a, e1, e2 = frame['center'], frame['axis'], frame['e1'], frame['e2']
    sv = (frame['bl_lo'] - BUCCOLINGUAL_PAD_MM, frame['bl_hi'] + BUCCOLINGUAL_PAD_MM)
    sw = (frame['t_cer'] - APICAL_EXTENT_MM, frame['t_occ'])
    near_hi = frame['hi'] + ROOT_OUTSET_MM
    near_lo = frame['lo'] - ROOT_OUTSET_MM
    # Each box with its inner plane: point on the face towards the gap and
    # the normal pointing into the gap.
    return [(*_box(c, e1, e2, a, (near_hi, near_hi + SLAB_THICKNESS_MM), sv, sw), c + near_hi * e1, -e1),
            (*_box(c, e1, e2, a, (near_lo - SLAB_THICKNESS_MM, near_lo), sv, sw), c + near_lo * e1, e1)]


# ── Blender side ─────────────────────────────────────────────────────

def _world(obj, coords):
    m = np.array(obj.matrix_world)
    return coords @ m[:3, :3].T + m[:3, 3]


def removed_crown(model):
    """World points of the crown removed from the IOS, or None."""
    from mathutils.bvhtree import BVHTree
    backup = model.get('DSG_ios_tooth_edit_backup') if model is not None else None
    if backup is None or not int(model.get('DSG_ios_socket_count', 0) or 0):
        return None
    mesh = model.data
    tree = BVHTree.FromPolygons([v.co for v in mesh.vertices], [p.vertices[:] for p in mesh.polygons])
    removed = []
    for vertex in backup.vertices:
        hit = tree.find_nearest(vertex.co)
        if hit[0] is None or hit[3] > REMOVED_DISTANCE_MM:
            removed.append(tuple(vertex.co))
    if len(removed) < 20:
        return None
    return _world(model, np.array(removed, float))


def frame_for(context, implant):
    from mathutils import Vector
    from .ios_tooth_edit import model as ios_model
    model = ios_model(context)
    crown = removed_crown(model)
    if crown is None:
        return None
    coords = np.empty(len(model.data.vertices) * 3)
    model.data.vertices.foreach_get('co', coords)
    ios = _world(model, coords.reshape(-1, 3))
    axis = np.array(implant.matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0)))
    return gap_frame(crown, ios, axis)


def obstacles(context, implant, folder, margin_mm):
    """Obstacle rows for the search request (identity matrix, world vertices)."""
    frame = frame_for(context, implant)
    if frame is None:
        return []
    rows = []
    for index, (vertices, faces, point, normal) in enumerate(slabs(frame)):
        name = f'DSG_SimpleNeighbourRoot_{index + 1}'
        vp = folder / (name + '_v.npy')
        fp = folder / (name + '_f.npy')
        np.save(vp, vertices, allow_pickle=False)
        np.save(fp, faces, allow_pickle=False)
        rows.append({'name': name, 'vertices_path': str(vp), 'faces_path': str(fp),
                     'matrix': [list(r) for r in np.eye(4)], 'kind': KIND, 'fdi': 0,
                     'margin_mm': float(margin_mm), 'allow_hull': False,
                     'plane': {'point': [float(x) for x in point], 'normal': [float(x) for x in normal]}})
    return rows
