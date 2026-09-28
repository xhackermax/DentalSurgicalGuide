"""Shared dental surface geometry for DSG automatic alignment and IOS matching.

The module deliberately keeps treatment decisions out of geometry.  It only
extracts the surfaces that an intraoral scanner can actually observe from a
segmented CBCT tooth: occlusal / incisal crown patches and reproducible crown
landmarks.  The same reference definition is then reused by alignment and by
GeoMatch selection, preventing both modules from inventing different meanings
for "crown surface".

Design goals
------------
* orientation independent: no assumption that Blender Z is occlusal;
* jaw aware: the common occlusal axis is inferred from the dental arch and
  face-normal evidence, with a conservative LPS fallback only if geometry is
  genuinely ambiguous;
* root safe: patches are restricted by both coronal position and surface normal;
* deterministic: no random sampling, so repeated runs are reproducible;
* KISS at the UI level: all of this remains internal to DSG.
"""

from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
from mathutils.bvhtree import BVHTree


_EPS = 1.0e-12


def valid_mesh(obj) -> bool:
    return bool(
        obj is not None
        and getattr(obj, "type", "") == "MESH"
        and getattr(obj, "data", None) is not None
        and len(obj.data.vertices) >= 3
        and len(obj.data.polygons) >= 1
    )


def fdi_arch(fdi: int) -> str:
    try:
        quadrant = int(fdi) // 10
    except Exception:
        return ""
    if quadrant in (1, 2, 5, 6):
        return "MAXILLA"
    if quadrant in (3, 4, 7, 8):
        return "MANDIBLE"
    return ""


def fdi_position(fdi: int) -> int:
    try:
        return int(fdi) % 10
    except Exception:
        return 0


def tooth_class(fdi: int) -> str:
    position = fdi_position(fdi)
    if position in (1, 2):
        return "INCISOR"
    if position == 3:
        return "CANINE"
    if 4 <= position <= 8:
        return "POSTERIOR"
    return "UNKNOWN"


def _world_vertex_arrays(obj):
    mesh = obj.data
    n = len(mesh.vertices)
    coordinates = np.empty(n * 3, dtype=np.float64)
    normals = np.empty(n * 3, dtype=np.float64)
    mesh.vertices.foreach_get("co", coordinates)
    mesh.vertices.foreach_get("normal", normals)
    local_points = coordinates.reshape((-1, 3))
    local_normals = normals.reshape((-1, 3))
    mw = np.asarray(obj.matrix_world, dtype=np.float64)
    world_points = local_points @ mw[:3, :3].T + mw[:3, 3]
    try:
        normal_matrix = np.linalg.inv(mw[:3, :3]).T
    except np.linalg.LinAlgError:
        normal_matrix = mw[:3, :3]
    world_normals = local_normals @ normal_matrix.T
    lengths = np.linalg.norm(world_normals, axis=1, keepdims=True)
    world_normals = world_normals / np.maximum(lengths, _EPS)
    return world_points, world_normals


def _world_face_arrays(obj):
    mesh = obj.data
    n = len(mesh.polygons)
    centers = np.empty(n * 3, dtype=np.float64)
    normals = np.empty(n * 3, dtype=np.float64)
    mesh.polygons.foreach_get("center", centers)
    mesh.polygons.foreach_get("normal", normals)
    local_centers = centers.reshape((-1, 3))
    local_normals = normals.reshape((-1, 3))
    mw = np.asarray(obj.matrix_world, dtype=np.float64)
    world_centers = local_centers @ mw[:3, :3].T + mw[:3, 3]
    try:
        normal_matrix = np.linalg.inv(mw[:3, :3]).T
    except np.linalg.LinAlgError:
        normal_matrix = mw[:3, :3]
    world_normals = local_normals @ normal_matrix.T
    lengths = np.linalg.norm(world_normals, axis=1, keepdims=True)
    world_normals = world_normals / np.maximum(lengths, _EPS)
    areas = np.empty(n, dtype=np.float64)
    try:
        mesh.polygons.foreach_get("area", areas)
    except Exception:
        areas = np.asarray([float(poly.area) for poly in mesh.polygons], dtype=np.float64)
    return world_centers, world_normals, np.maximum(areas, _EPS)


def _face_adjacency(mesh):
    adjacency = [set() for _ in mesh.polygons]
    edge_faces = defaultdict(list)
    for polygon in mesh.polygons:
        verts = tuple(int(v) for v in polygon.vertices)
        for i, first in enumerate(verts):
            second = verts[(i + 1) % len(verts)]
            key = (first, second) if first < second else (second, first)
            edge_faces[key].append(int(polygon.index))
    for linked in edge_faces.values():
        if len(linked) < 2:
            continue
        for index in linked:
            adjacency[index].update(other for other in linked if other != index)
    return adjacency


def _connected_components(nodes, adjacency):
    pending = set(int(i) for i in nodes)
    result = []
    while pending:
        seed = pending.pop()
        component = {seed}
        stack = [seed]
        while stack:
            current = stack.pop()
            for neighbour in adjacency[current]:
                if neighbour in pending:
                    pending.remove(neighbour)
                    component.add(neighbour)
                    stack.append(neighbour)
        result.append(component)
    return result


def _normalise(vector):
    vector = np.asarray(vector, dtype=np.float64)
    length = float(np.linalg.norm(vector))
    if length <= _EPS:
        return None
    return vector / length


def _tooth_centroid(obj):
    points, _normals = _world_vertex_arrays(obj)
    return points.mean(axis=0) if len(points) else None


def _single_tooth_axis(obj):
    """Estimate an unsigned root-crown axis from one segmented tooth.

    The longest PCA axis is normally root-to-crown for a complete segmented
    tooth.  Sign is resolved separately from crown-end surface evidence.
    """
    points, _ = _world_vertex_arrays(obj)
    if len(points) < 6:
        return None
    centre = points.mean(axis=0)
    centred = points - centre
    covariance = centred.T @ centred / max(len(points) - 1, 1)
    values, vectors = np.linalg.eigh(covariance)
    axis = vectors[:, int(np.argmax(values))]
    return _normalise(axis)


def _arch_plane_axis(objects):
    centroids = [c for c in (_tooth_centroid(obj) for obj in objects) if c is not None]
    if len(centroids) >= 3:
        points = np.asarray(centroids, dtype=np.float64)
        centred = points - points.mean(axis=0)
        covariance = centred.T @ centred / max(len(points) - 1, 1)
        values, vectors = np.linalg.eigh(covariance)
        return _normalise(vectors[:, int(np.argmin(values))])
    if len(objects) == 1:
        return _single_tooth_axis(objects[0])
    blocks = []
    for obj in objects:
        points, _ = _world_vertex_arrays(obj)
        if len(points):
            step = max(1, len(points) // 2500)
            blocks.append(points[::step])
    if not blocks:
        return None
    points = np.concatenate(blocks, axis=0)
    centred = points - points.mean(axis=0)
    covariance = centred.T @ centred / max(len(points) - 1, 1)
    values, vectors = np.linalg.eigh(covariance)
    # For a collection of teeth the smallest variance is normally occlusal.
    return _normalise(vectors[:, int(np.argmin(values))])


def _end_score(obj, axis):
    """How likely is the +axis extreme to be the IOS-visible crown end?"""
    centers, normals, areas = _world_face_arrays(obj)
    if len(centers) < 6:
        return 0.0
    projection = centers @ axis
    threshold = float(np.percentile(projection, 72.0))
    band = projection >= threshold
    if int(np.count_nonzero(band)) < 2:
        return 0.0
    dots = np.clip(normals @ axis, -1.0, 1.0)
    # Occlusal/incisal surfaces should include a useful amount of outward
    # normal pointing in the crown direction.  Negative-facing walls do not
    # help choose the sign.
    positive = np.clip(dots[band], 0.0, 1.0)
    weights = areas[band]
    normal_score = float(np.sum(positive * weights) / max(np.sum(weights), _EPS))

    # Crown ends are generally broader than an apical tip.  This term is weak
    # on purpose because multi-rooted molars can have a wide root end.
    chosen = centers[band]
    axial = np.outer(chosen @ axis, axis)
    radial = chosen - axial
    radial_centre = radial.mean(axis=0)
    spread = float(np.sqrt(np.mean(np.sum((radial - radial_centre) ** 2, axis=1))))
    all_axial = np.outer(centers @ axis, axis)
    all_radial = centers - all_axial
    all_centre = all_radial.mean(axis=0)
    all_spread = float(np.sqrt(np.mean(np.sum((all_radial - all_centre) ** 2, axis=1))))
    breadth_score = float(np.clip(spread / max(all_spread, _EPS), 0.0, 1.35) / 1.35)

    # A crown cap tends to be one coherent surface whereas the root end can be
    # split across multiple tips.  Reward connectivity without requiring it.
    adjacency = _face_adjacency(obj.data)
    components = _connected_components(np.flatnonzero(band).tolist(), adjacency)
    connectivity = 1.0 / max(len(components), 1)
    return float(0.66 * normal_score + 0.20 * breadth_score + 0.14 * connectivity)


def estimate_occlusal_axis(objects):
    """Return a root->crown unit axis plus diagnostics for one dental arch."""
    objects = [obj for obj in objects if valid_mesh(obj)]
    if not objects:
        return None, {"method": "NONE", "confidence": 0.0}
    axis = _arch_plane_axis(objects)
    if axis is None:
        return None, {"method": "NONE", "confidence": 0.0}

    plus_scores = []
    minus_scores = []
    for obj in objects:
        try:
            plus_scores.append(_end_score(obj, axis))
            minus_scores.append(_end_score(obj, -axis))
        except Exception:
            continue
    plus = float(np.median(plus_scores)) if plus_scores else 0.0
    minus = float(np.median(minus_scores)) if minus_scores else 0.0
    chosen = axis if plus >= minus else -axis
    gap = abs(plus - minus)
    confidence = float(np.clip(gap / max(max(plus, minus), 0.10), 0.0, 1.0))
    method = "ARCH_PCA_NORMALS" if len(objects) >= 3 else "TOOTH_PCA_NORMALS"

    # Conservative final sign fallback for truly ambiguous cases.  DSG CBCT
    # data is stored in LPS orientation, but this is intentionally only a last
    # resort; normal/landmark geometry decides the sign whenever possible.
    if confidence < 0.08:
        arches = [fdi_arch(int(obj.get("DSG_fdi_number", 0) or 0)) for obj in objects]
        arch = next((value for value in arches if value), "")
        if arch in {"MAXILLA", "MANDIBLE"}:
            expected = np.asarray((0.0, 0.0, -1.0 if arch == "MAXILLA" else 1.0), dtype=np.float64)
            if float(np.dot(chosen, expected)) < 0.0:
                chosen = -chosen
            method = "ARCH_PCA_NORMALS_LPS_SIGN_FALLBACK"

    chosen = _normalise(chosen)
    return chosen, {
        "method": method,
        "confidence": float(confidence),
        "plus_score": float(plus),
        "minus_score": float(minus),
        "teeth": int(len(objects)),
    }


def occlusal_incisal_patch(obj, axis, *, relaxed=False):
    """Extract a connected IOS-visible occlusal/incisal face patch.

    The returned patch never intentionally reaches the root: a face must be in
    the crown-end projection band and either point broadly toward the occlusal
    direction or lie in the extreme crown cap.  Anterior teeth use a narrower
    positional band and a more permissive normal gate because an incisal edge
    is not a broad horizontal table.
    """
    if not valid_mesh(obj):
        return None
    axis = _normalise(axis)
    if axis is None:
        return None
    fdi = int(obj.get("DSG_fdi_number", 0) or 0)
    kind = tooth_class(fdi)
    centers, normals, areas = _world_face_arrays(obj)
    if len(centers) < 4:
        return None
    projection = centers @ axis
    low = float(np.min(projection))
    high = float(np.max(projection))
    span = max(high - low, _EPS)
    u = (projection - low) / span
    dots = np.clip(normals @ axis, -1.0, 1.0)

    if kind == "INCISOR":
        position_threshold = 0.70 if not relaxed else 0.62
        hard_cap = 0.90 if not relaxed else 0.84
        normal_angle = 82.0 if not relaxed else 86.0
    elif kind == "CANINE":
        position_threshold = 0.66 if not relaxed else 0.58
        hard_cap = 0.88 if not relaxed else 0.82
        normal_angle = 79.0 if not relaxed else 85.0
    else:
        position_threshold = 0.58 if not relaxed else 0.51
        hard_cap = 0.84 if not relaxed else 0.78
        normal_angle = 74.0 if not relaxed else 82.0

    minimum_dot = math.cos(math.radians(normal_angle))
    preliminary = set(np.flatnonzero(
        (u >= position_threshold)
        & ((dots >= minimum_dot) | (u >= hard_cap))
    ).tolist())
    if len(preliminary) < 3:
        preliminary = set(np.flatnonzero(u >= max(position_threshold, 0.78)).tolist())
    if len(preliminary) < 3:
        return None

    score = (
        0.62 * np.clip((u - position_threshold) / max(1.0 - position_threshold, _EPS), 0.0, 1.0)
        + 0.38 * np.clip((dots - minimum_dot) / max(1.0 - minimum_dot, _EPS), 0.0, 1.0)
    )
    adjacency = _face_adjacency(obj.data)
    components = _connected_components(preliminary, adjacency)
    if not components:
        return None
    components.sort(
        key=lambda comp: (
            sum(float(score[i]) * float(areas[i]) for i in comp),
            len(comp),
        ),
        reverse=True,
    )
    selected = set(components[0])

    # One restrained Select-More equivalent.  It fills cusp/incisal shoulders
    # but cannot walk apically into the root because the positional gate remains.
    grow_floor = max(0.42, position_threshold - (0.10 if relaxed else 0.07))
    grow_dot = math.cos(math.radians(88.0))
    for _ in range(2 if relaxed else 1):
        additions = set()
        for current in selected:
            for neighbour in adjacency[current]:
                if neighbour in selected:
                    continue
                if u[neighbour] < grow_floor:
                    continue
                if dots[neighbour] >= grow_dot or u[neighbour] >= hard_cap - 0.04:
                    additions.add(int(neighbour))
        if not additions:
            break
        selected.update(additions)

    if len(selected) < 3:
        return None
    selected_list = sorted(selected)
    weighted_score = np.asarray(
        [max(0.05, float(score[i])) * float(areas[i]) for i in selected_list],
        dtype=np.float64,
    )
    selected_centers = centers[selected_list]
    landmark = np.average(selected_centers, axis=0, weights=weighted_score)
    vertex_indices = set()
    for face_index in selected:
        vertex_indices.update(int(v) for v in obj.data.polygons[int(face_index)].vertices)
    return {
        "face_indices": set(int(i) for i in selected),
        "vertex_indices": set(vertex_indices),
        "landmark": np.asarray(landmark, dtype=np.float64),
        "kind": kind,
        "fdi": int(fdi),
        "position_threshold": float(position_threshold),
        "normal_angle_deg": float(normal_angle),
        "face_count": int(len(selected)),
        "vertex_count": int(len(vertex_indices)),
        "projection_span_mm": float(span),
    }



def registration_crown_patch(obj, axis, *, relaxed=False):
    """Return a root-safe coronal crown shell for automatic IOS registration.

    ``occlusal_incisal_patch`` is deliberately very selective and is excellent
    for crown landmarks, but using only cusp/incisal caps leaves a complete arch
    unnecessarily symmetric.  Plan A benefits from the buccal/lingual and
    proximal crown walls as well.  This helper therefore starts from the proven
    occlusal/incisal patch and grows *only coronally* through connected faces.

    The growth is positional rather than orientation-based so near-vertical
    axial crown walls are retained.  It never intentionally crosses the
    cervical/root half of the segmented tooth.  The original occlusal landmark
    is preserved for distributed anatomical validation.
    """
    if not valid_mesh(obj):
        return None
    axis = _normalise(axis)
    if axis is None:
        return None
    base = occlusal_incisal_patch(obj, axis, relaxed=relaxed)
    if base is None:
        return None

    fdi = int(obj.get("DSG_fdi_number", 0) or 0)
    kind = tooth_class(fdi)
    centers, _normals, areas = _world_face_arrays(obj)
    projection = centers @ axis
    low = float(np.min(projection))
    high = float(np.max(projection))
    span = max(high - low, _EPS)
    u = (projection - low) / span

    # Root->crown normalized projection.  The strict thresholds intentionally
    # leave a safety band above the estimated CEJ.  Relaxed mode is used only
    # when the strict shell is too sparse and still remains substantially more
    # coronal than the root half of the tooth.
    if kind == "INCISOR":
        crown_floor = 0.60 if not relaxed else 0.54
    elif kind == "CANINE":
        crown_floor = 0.57 if not relaxed else 0.51
    else:
        crown_floor = 0.54 if not relaxed else 0.48

    candidates = set(np.flatnonzero(u >= crown_floor).tolist())
    selected = set(int(i) for i in base["face_indices"])
    candidates.update(selected)
    adjacency = _face_adjacency(obj.data)

    # Keep exactly the coronal component connected to the known crown cap.
    # This handles segmentation islands without allowing a disconnected root
    # fragment to enter the automatic registration reference.
    frontier = list(selected)
    while frontier:
        current = frontier.pop()
        for neighbour in adjacency[current]:
            if neighbour in selected or neighbour not in candidates:
                continue
            selected.add(int(neighbour))
            frontier.append(int(neighbour))

    if len(selected) < 4:
        return None
    vertex_indices = set()
    shell_area = 0.0
    for face_index in selected:
        shell_area += float(areas[int(face_index)])
        vertex_indices.update(int(v) for v in obj.data.polygons[int(face_index)].vertices)
    if len(vertex_indices) < 4:
        return None

    return {
        "face_indices": set(int(i) for i in selected),
        "vertex_indices": set(vertex_indices),
        "landmark": np.asarray(base["landmark"], dtype=np.float64),
        "kind": kind,
        "fdi": int(fdi),
        "crown_floor": float(crown_floor),
        "face_count": int(len(selected)),
        "vertex_count": int(len(vertex_indices)),
        "surface_area": float(shell_area),
        "projection_span_mm": float(span),
        "occlusal_face_count": int(base.get("face_count", 0)),
    }


def build_registration_crown_graph_data(objects, *, relaxed=False):
    """Return the connected coronal crown shells used by Plan A alignment.

    This is intentionally richer than ``build_occlusal_graph_data`` while
    sharing the same orientation-independent occlusal axis and landmarks.
    Bone and roots never enter the graph.
    """
    objects = [obj for obj in objects if valid_mesh(obj)]
    axis, axis_diag = estimate_occlusal_axis(objects)
    if axis is None:
        return None
    point_blocks = []
    normal_blocks = []
    edge_blocks = []
    landmarks = {}
    patches = {}
    offset = 0
    for obj in objects:
        patch = registration_crown_patch(obj, axis, relaxed=relaxed)
        if patch is None:
            continue
        world_points, world_normals = _world_vertex_arrays(obj)
        selected_vertices = sorted(patch["vertex_indices"])
        if len(selected_vertices) < 3:
            continue
        local_to_compact = {local: i for i, local in enumerate(selected_vertices)}
        points = world_points[selected_vertices]
        normals = world_normals[selected_vertices]
        edges = set()
        for face_index in patch["face_indices"]:
            verts = [int(v) for v in obj.data.polygons[int(face_index)].vertices]
            for i, first in enumerate(verts):
                second = verts[(i + 1) % len(verts)]
                if first in local_to_compact and second in local_to_compact:
                    a = local_to_compact[first] + offset
                    b = local_to_compact[second] + offset
                    if a != b:
                        edges.add((a, b) if a < b else (b, a))
        point_blocks.append(points)
        normal_blocks.append(normals)
        if edges:
            edge_blocks.append(np.asarray(sorted(edges), dtype=np.int32))
        fdi = int(patch["fdi"])
        if fdi > 0:
            landmarks[fdi] = np.asarray(patch["landmark"], dtype=np.float64)
            patches[fdi] = {
                key: value for key, value in patch.items()
                if key not in {"face_indices", "vertex_indices", "landmark"}
            }
        offset += len(points)
    if not point_blocks:
        return None
    points = np.concatenate(point_blocks, axis=0)
    normals = np.concatenate(normal_blocks, axis=0)
    edges = np.concatenate(edge_blocks, axis=0) if edge_blocks else np.empty((0, 2), dtype=np.int32)
    return {
        "points": points,
        "normals": normals,
        "edges": edges,
        "occlusal_axis": np.asarray(axis, dtype=np.float64),
        "landmarks_by_fdi": landmarks,
        "patches_by_fdi": patches,
        "axis_diagnostics": axis_diag,
        "reference_surface": "CORONAL_CROWN_SHELL",
        "relaxed": bool(relaxed),
    }


def build_occlusal_graph_data(objects, *, relaxed=False):
    """Return points/normals/edges for occlusal+incisal CBCT patches only."""
    objects = [obj for obj in objects if valid_mesh(obj)]
    axis, axis_diag = estimate_occlusal_axis(objects)
    if axis is None:
        return None
    point_blocks = []
    normal_blocks = []
    edge_blocks = []
    landmarks = {}
    patches = {}
    offset = 0
    for obj in objects:
        patch = occlusal_incisal_patch(obj, axis, relaxed=relaxed)
        if patch is None:
            continue
        world_points, world_normals = _world_vertex_arrays(obj)
        selected_vertices = sorted(patch["vertex_indices"])
        if len(selected_vertices) < 3:
            continue
        local_to_compact = {local: i for i, local in enumerate(selected_vertices)}
        points = world_points[selected_vertices]
        normals = world_normals[selected_vertices]
        edges = set()
        for face_index in patch["face_indices"]:
            verts = [int(v) for v in obj.data.polygons[int(face_index)].vertices]
            for i, first in enumerate(verts):
                second = verts[(i + 1) % len(verts)]
                if first in local_to_compact and second in local_to_compact:
                    a = local_to_compact[first] + offset
                    b = local_to_compact[second] + offset
                    if a != b:
                        edges.add((a, b) if a < b else (b, a))
        point_blocks.append(points)
        normal_blocks.append(normals)
        if edges:
            edge_blocks.append(np.asarray(sorted(edges), dtype=np.int32))
        fdi = int(patch["fdi"])
        if fdi > 0:
            landmarks[fdi] = np.asarray(patch["landmark"], dtype=np.float64)
            patches[fdi] = {
                key: value for key, value in patch.items()
                if key not in {"face_indices", "vertex_indices", "landmark"}
            }
        offset += len(points)
    if not point_blocks:
        return None
    points = np.concatenate(point_blocks, axis=0)
    normals = np.concatenate(normal_blocks, axis=0)
    edges = np.concatenate(edge_blocks, axis=0) if edge_blocks else np.empty((0, 2), dtype=np.int32)
    return {
        "points": points,
        "normals": normals,
        "edges": edges,
        "occlusal_axis": np.asarray(axis, dtype=np.float64),
        "landmarks_by_fdi": landmarks,
        "patches_by_fdi": patches,
        "axis_diagnostics": axis_diag,
        "relaxed": bool(relaxed),
    }


def build_occlusal_reference_bvh(reference_objects, *, context_objects=None, relaxed=False):
    """BVH of only the occlusal/incisal surfaces of *reference_objects*.

    Axis estimation can use neighbour teeth through ``context_objects`` so a
    single target tooth still inherits the jaw's common occlusal direction.
    """
    reference_objects = [obj for obj in reference_objects if valid_mesh(obj)]
    context_objects = [obj for obj in (context_objects or reference_objects) if valid_mesh(obj)]
    axis, axis_diag = estimate_occlusal_axis(context_objects)
    if axis is None:
        return None
    vertices = []
    faces = []
    landmarks = {}
    kept_faces = 0
    for obj in reference_objects:
        patch = occlusal_incisal_patch(obj, axis, relaxed=relaxed)
        if patch is None:
            continue
        world_points, _world_normals = _world_vertex_arrays(obj)
        vertex_offset = len(vertices)
        vertices.extend(tuple(float(v) for v in point) for point in world_points)
        for face_index in sorted(patch["face_indices"]):
            polygon = obj.data.polygons[int(face_index)]
            faces.append(tuple(vertex_offset + int(v) for v in polygon.vertices))
        fdi = int(patch["fdi"])
        if fdi > 0:
            landmarks[fdi] = np.asarray(patch["landmark"], dtype=np.float64)
        kept_faces += len(patch["face_indices"])
    if not vertices or not faces:
        return None
    bvh = BVHTree.FromPolygons(vertices, faces, all_triangles=False)
    if bvh is None:
        return None
    return {
        "bvh": bvh,
        "occlusal_axis": np.asarray(axis, dtype=np.float64),
        "axis_diagnostics": axis_diag,
        "landmarks_by_fdi": landmarks,
        "face_count": int(kept_faces),
        "relaxed": bool(relaxed),
    }
