"""Native IOS–CBCT common-surface selection for DSG immediate cases.

This module is original DSG code.  It deliberately consumes already aligned
meshes and does not move, scale, retopologise or otherwise modify either input.
Its only result is a confidence-ranked face selection on a disposable IOS copy.
The clinician remains responsible for reviewing that selection before it is
used to define a virtual post-extraction socket.
"""

from __future__ import annotations

import logging as _dsg_logging
_DSG_LOG = _dsg_logging.getLogger(__name__)

import json
import math
import time
from collections import defaultdict
import heapq

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import dental_surface_geometry


SCORE_ATTRIBUTE = "DSG_common_surface_confidence"
METHOD_ID = "DSG_GEOMATCH_COMMON_SURFACE_V5_OCCLUSAL_ANCHOR"
LEGACY_METHOD_ID = "DSG_LEGACY_COMPATIBLE_COMMON_SURFACE_SEED_V2"
ANATOMY_LOCKED_METHOD_ID = "DSG_ANATOMY_LOCKED_COMMON_SURFACE_V7_OCCLUSAL_ANCHOR"

# Geometry-selection parameters, not clinical treatment parameters.  They
# tolerate the resolution gap between IOS and CBCT segmentation while retaining
# a stricter, reciprocal seed for the automatically selected area.
DEFAULT_DISTANCE_MM = 0.85
DEFAULT_NORMAL_ANGLE_DEG = 55.0
DEFAULT_SCORE_THRESHOLD = 0.62
DEFAULT_GROW_SCORE_THRESHOLD = 0.48
DEFAULT_GROW_ANGLE_DEG = 42.0
LEGACY_COMPATIBLE_DISTANCE_MM = 1.25
MIN_SELECTED_FACES = 12


def _valid_mesh(obj):
    return bool(obj is not None and obj.type == "MESH" and obj.data is not None
                and len(obj.data.vertices) and len(obj.data.polygons))


def _world_vertices(obj):
    return [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]


def _world_normal_matrix(obj):
    try:
        return obj.matrix_world.to_3x3().inverted().transposed()
    except Exception:
        return obj.matrix_world.to_3x3()


def _world_face_normal(obj, polygon, normal_matrix):
    normal = normal_matrix @ polygon.normal
    if normal.length <= 1.0e-10:
        return Vector((0.0, 0.0, 1.0))
    return normal.normalized()


def _build_face_adjacency(mesh):
    """Index-stable edge adjacency with a vectorized manifold fast path."""
    n_faces = len(mesh.polygons)
    n_loops = len(mesh.loops)
    n_edges = len(mesh.edges)
    adjacency = [set() for _ in range(n_faces)]
    if not n_faces or not n_loops or not n_edges:
        return adjacency
    try:
        loop_total = np.empty(n_faces, dtype=np.int64)
        mesh.polygons.foreach_get('loop_total', loop_total)
        if int(loop_total.sum()) != n_loops:
            raise ValueError('loop mismatch')
        edge_index = np.empty(n_loops, dtype=np.int64)
        mesh.loops.foreach_get('edge_index', edge_index)
        face_index = np.repeat(np.arange(n_faces, dtype=np.int64), loop_total)
        valid = (edge_index >= 0) & (edge_index < n_edges)
        edge_index = edge_index[valid]
        face_index = face_index[valid]
        counts = np.bincount(edge_index, minlength=n_edges)
        first = np.full(n_edges, n_faces, dtype=np.int64)
        last = np.full(n_edges, -1, dtype=np.int64)
        np.minimum.at(first, edge_index, face_index)
        np.maximum.at(last, edge_index, face_index)
        manifold = np.flatnonzero(counts == 2)
        for a, b in zip(first[manifold].tolist(), last[manifold].tolist()):
            if a != b:
                adjacency[a].add(b)
                adjacency[b].add(a)
        nonmanifold = np.flatnonzero(counts > 2)
        if nonmanifold.size:
            mask = np.isin(edge_index, nonmanifold)
            groups = defaultdict(set)
            for edge, face in zip(edge_index[mask].tolist(), face_index[mask].tolist()):
                groups[edge].add(face)
            for linked in groups.values():
                linked = list(linked)
                for i, a in enumerate(linked):
                    for b in linked[i + 1:]:
                        adjacency[a].add(b)
                        adjacency[b].add(a)
        return adjacency
    except Exception:
        edge_faces = {}
        for polygon in mesh.polygons:
            vertices = tuple(int(index) for index in polygon.vertices)
            for position, first in enumerate(vertices):
                second = vertices[(position + 1) % len(vertices)]
                key = (first, second) if first < second else (second, first)
                edge_faces.setdefault(key, []).append(int(polygon.index))
        for linked in edge_faces.values():
            if len(linked) < 2:
                continue
            for index in linked:
                adjacency[index].update(other for other in linked if other != index)
        return adjacency


def _connected_components(indices, adjacency):
    remaining = set(indices)
    components = []
    while remaining:
        start = remaining.pop()
        component = {start}
        frontier = [start]
        while frontier:
            current = frontier.pop()
            new = adjacency[current] & remaining
            if new:
                remaining.difference_update(new)
                component.update(new)
                frontier.extend(new)
        components.append(component)
    return components


def _expanded_bounds(objects, margin):
    points = []
    for obj in objects:
        points.extend(_world_vertices(obj))
    if not points:
        return None
    low = Vector((min(point.x for point in points), min(point.y for point in points), min(point.z for point in points)))
    high = Vector((max(point.x for point in points), max(point.y for point in points), max(point.z for point in points)))
    return low - Vector((margin, margin, margin)), high + Vector((margin, margin, margin))


def _inside_bounds(point, bounds):
    if bounds is None:
        return True
    low, high = bounds
    return low.x <= point.x <= high.x and low.y <= point.y <= high.y and low.z <= point.z <= high.z


def _reference_bvh(objects):
    vertices, faces = [], []
    for obj in objects:
        offset = len(vertices)
        world = _world_vertices(obj)
        vertices.extend(world)
        faces.extend(tuple(offset + int(index) for index in polygon.vertices)
                     for polygon in obj.data.polygons)
    if not vertices or not faces:
        return None
    return BVHTree.FromPolygons(vertices, faces, all_triangles=False)




def _reference_surface_data(objects, *, target_bvh=None, distance_mm=None, normal_angle_deg=72.0):
    """Combined reference surface, optionally restricted to the IOS-visible crown.

    A segmented CBCT tooth contains root surfaces that have no IOS counterpart.
    Matching against the whole tooth can therefore pull the IOS selection onto
    cervical gingiva or a nearby root surface.  When an aligned IOS BVH is
    supplied, each tooth is first reduced to the largest coherent face patch
    that is actually supported by the IOS.  This is a geometry-only crown mask;
    it does not require IOS tooth segmentation and it remains robust to open
    scans and different triangulations.
    """
    vertices, faces, normals, adjacency = [], [], [], []
    face_centers = []
    kept_reference_faces = 0
    total_reference_faces = 0
    # Shared root-safe fallback.  If IOS support is too sparse to recover the
    # complete visible crown, never fall back to the entire segmented tooth.
    # Use an occlusal/incisal patch instead.
    crown_axis, _crown_axis_diag = dental_surface_geometry.estimate_occlusal_axis(objects)

    for obj in objects:
        world = _world_vertices(obj)
        if not world:
            continue
        local_adj = _build_face_adjacency(obj.data)
        normal_matrix = _world_normal_matrix(obj)
        local_normals = [_world_face_normal(obj, polygon, normal_matrix)
                         for polygon in obj.data.polygons]
        local_centers = []
        for polygon in obj.data.polygons:
            points = [world[int(v)] for v in polygon.vertices]
            center = Vector((0.0, 0.0, 0.0))
            for point in points:
                center += point
            local_centers.append(center / max(len(points), 1))

        total_reference_faces += len(local_centers)
        keep_local = set(range(len(local_centers))) if target_bvh is None else set()
        support_scores = {}

        if target_bvh is not None and distance_mm is not None and len(local_centers) >= 8:
            limit = max(0.10, float(distance_mm))
            loose_limit = limit * 1.40
            strong_limit = limit * 0.98
            loose_dot = math.cos(math.radians(min(86.0, max(64.0, float(normal_angle_deg) + 10.0))))
            strong_dot = math.cos(math.radians(min(82.0, max(55.0, float(normal_angle_deg)))))
            candidates, strong = set(), set()

            for index, center in enumerate(local_centers):
                hit, hit_normal, _target_face, distance = target_bvh.find_nearest(center, loose_limit)
                if hit is None or distance is None:
                    continue
                normal_dot = 0.5
                if hit_normal is not None:
                    normal_dot = abs(float(local_normals[index].dot(hit_normal.normalized())))
                d = float(distance)
                if d <= loose_limit and normal_dot >= loose_dot:
                    candidates.add(index)
                    distance_score = math.exp(-((d / max(limit, 1.0e-9)) ** 2))
                    normal_score = max(0.0, min(1.0, (normal_dot - loose_dot) / max(1.0 - loose_dot, 1.0e-9)))
                    support_scores[index] = 0.72 * distance_score + 0.28 * normal_score
                    if d <= strong_limit and normal_dot >= strong_dot:
                        strong.add(index)

            # Grow only through IOS-supported CBCT faces.  This bridges small
            # segmentation/triangulation gaps while preventing the root from
            # becoming part of the reference merely because it is connected.
            supported = set(strong)
            frontier = list(strong)
            while frontier:
                current = frontier.pop()
                for neighbour in local_adj[current]:
                    if neighbour in supported or neighbour not in candidates:
                        continue
                    supported.add(neighbour)
                    frontier.append(neighbour)

            if len(supported) >= 8:
                components = _connected_components(supported, local_adj)
                ranked = []
                for component in components:
                    if not component:
                        continue
                    mean_score = sum(support_scores.get(i, 0.0) for i in component) / len(component)
                    ranked.append((mean_score, len(component), component))
                ranked.sort(key=lambda item: (item[0] * math.sqrt(max(item[1], 1)), item[1]), reverse=True)
                if ranked:
                    best = ranked[0][2]
                    # Keep one coherent patch per segmented tooth.  A second
                    # disconnected patch is more often root/gingiva ambiguity
                    # than useful crown evidence.
                    if len(best) >= 8:
                        keep_local = set(best)

        if not keep_local and crown_axis is not None:
            try:
                patch = dental_surface_geometry.occlusal_incisal_patch(
                    obj, crown_axis, relaxed=True)
                if patch is not None:
                    keep_local = set(int(i) for i in patch.get('face_indices', set()))
            except Exception:
                keep_local = set()
        if not keep_local:
            # Last safety fallback: a small coronal subset is preferable to
            # matching roots against gingiva.  Returning no data will make the
            # caller request review rather than silently use the full tooth.
            continue

        vertex_offset = len(vertices)
        vertices.extend(world)
        local_to_combined = {}
        for local_index in sorted(keep_local):
            polygon = obj.data.polygons[local_index]
            combined_index = len(faces)
            local_to_combined[local_index] = combined_index
            faces.append(tuple(vertex_offset + int(v) for v in polygon.vertices))
            normals.append(local_normals[local_index])
            face_centers.append(local_centers[local_index])
            adjacency.append(set())
        for local_index, combined_index in local_to_combined.items():
            adjacency[combined_index].update(
                local_to_combined[n] for n in local_adj[local_index]
                if n in local_to_combined
            )
        kept_reference_faces += len(keep_local)

    if not vertices or not faces:
        return None
    bvh = BVHTree.FromPolygons(vertices, faces, all_triangles=False)
    curvature = _curvature_signatures(normals, adjacency)
    return {
        'bvh': bvh, 'normals': normals, 'adjacency': adjacency,
        'curvature': curvature, 'centers': face_centers,
        'kept_reference_faces': int(kept_reference_faces),
        'total_reference_faces': int(total_reference_faces),
    }

def _curvature_signatures(normals, adjacency):
    signatures = []
    for index, normal in enumerate(normals):
        values = []
        for neighbour in adjacency[index]:
            if neighbour < 0 or neighbour >= len(normals):
                continue
            dot = abs(float(normal.dot(normals[neighbour])))
            dot = max(0.0, min(1.0, dot))
            values.append(math.acos(dot))
        if values:
            arr = np.asarray(values, dtype=np.float64)
            signatures.append((float(arr.mean()), float(arr.std())))
        else:
            signatures.append((0.0, 0.0))
    return signatures


def _curvature_similarity(first, second):
    if first is None or second is None:
        return 0.5
    dm = abs(float(first[0]) - float(second[0]))
    ds = abs(float(first[1]) - float(second[1]))
    return float(0.68 * math.exp(-dm / math.radians(18.0)) + 0.32 * math.exp(-ds / math.radians(15.0)))




def _orient_normals_locally(normals, adjacency, faces):
    """Return a locally coherent copy of the normal field on *faces*.

    Signed curvature only makes sense when neighbouring normals share a
    consistent orientation.  IOS meshes can be open or contain locally flipped
    triangles, so we propagate orientation over the contact corridor without
    touching the mesh itself.
    """
    face_set = {int(i) for i in faces if 0 <= int(i) < len(normals)}
    oriented = list(normals)
    visited = set()
    for seed in list(face_set):
        if seed in visited:
            continue
        visited.add(seed)
        stack = [seed]
        while stack:
            current = stack.pop()
            current_normal = oriented[current]
            for neighbour in adjacency[current]:
                neighbour = int(neighbour)
                if neighbour not in face_set or neighbour in visited:
                    continue
                candidate = oriented[neighbour]
                try:
                    if float(current_normal.dot(candidate)) < 0.0:
                        oriented[neighbour] = -candidate
                except Exception:
                    _DSG_LOG.debug("suppressed exception", exc_info=True)
                visited.add(neighbour)
                stack.append(neighbour)
    return oriented


def _dijkstra_face_path(adjacency, allowed, starts, goals, costs):
    """Shortest weighted face path inside *allowed* or [] when disconnected."""
    allowed = set(allowed)
    starts = [int(i) for i in starts if int(i) in allowed]
    goals = {int(i) for i in goals if int(i) in allowed}
    if not starts or not goals:
        return []
    heap = []
    best = {}
    parent = {}
    for start in starts:
        best[start] = 0.0
        heapq.heappush(heap, (0.0, start))
    found = None
    while heap:
        distance, current = heapq.heappop(heap)
        if distance != best.get(current):
            continue
        if current in goals:
            found = current
            break
        for neighbour in adjacency[current]:
            neighbour = int(neighbour)
            if neighbour not in allowed:
                continue
            step = float(costs.get(neighbour, 1.0))
            trial = distance + max(1.0e-6, step)
            if trial < best.get(neighbour, float('inf')):
                best[neighbour] = trial
                parent[neighbour] = current
                heapq.heappush(heap, (trial, neighbour))
    if found is None:
        return []
    path = [found]
    while path[-1] not in starts:
        previous = parent.get(path[-1])
        if previous is None:
            break
        path.append(previous)
    path.reverse()
    return path


def _connect_barrier_components(barrier, corridor, adjacency, curvature):
    """Connect fragmented valley seeds with low-cost paths inside contact corridor."""
    barrier = set(barrier)
    corridor = set(corridor)
    if len(barrier) < 2:
        return barrier, 0

    def components(nodes):
        pending = set(nodes)
        result = []
        while pending:
            seed = pending.pop()
            comp = {seed}
            stack = [seed]
            while stack:
                current = stack.pop()
                for neighbour in adjacency[current]:
                    neighbour = int(neighbour)
                    if neighbour in pending:
                        pending.remove(neighbour)
                        comp.add(neighbour)
                        stack.append(neighbour)
            result.append(comp)
        return result

    # Include one topological ring around the contested zone, but never the
    # whole crown. This lets the path bridge a 1-2 triangle sampling gap.
    allowed = set(corridor)
    for face in list(corridor):
        allowed.update(int(n) for n in adjacency[face])

    finite = [abs(float(curvature[i])) for i in allowed if 0 <= i < len(curvature) and math.isfinite(float(curvature[i]))]
    scale = float(np.percentile(np.asarray(finite, dtype=np.float64), 70.0)) if finite else 1.0
    scale = max(scale, 1.0e-8)
    costs = {}
    for face in allowed:
        value = float(curvature[face]) if 0 <= face < len(curvature) and math.isfinite(float(curvature[face])) else 0.0
        # Negative curvature is cheap, positive curvature expensive. Faces in
        # the original competition corridor are also cheaper than the 1-ring.
        valley = max(0.0, -value) / scale
        ridge = max(0.0, value) / scale
        cost = 1.0 + 1.4 * ridge - 0.55 * min(1.5, valley)
        if face not in corridor:
            cost += 0.65
        costs[face] = max(0.12, cost)

    added = 0
    while True:
        comps = components(barrier)
        if len(comps) <= 1:
            break
        base = max(comps, key=len)
        best_path = None
        best_cost = float('inf')
        for other in comps:
            if other is base:
                continue
            path = _dijkstra_face_path(adjacency, allowed, base, other, costs)
            if not path:
                continue
            cost = sum(costs.get(face, 1.0) for face in path)
            if cost < best_cost:
                best_cost = cost
                best_path = path
        if not best_path:
            break
        before = len(barrier)
        barrier.update(best_path)
        added += len(barrier) - before
    return barrier, added

def _signed_face_curvature(face_centers, normals, adjacency):
    """Estimate signed mean curvature from the normal field on face centres.

    With consistent outward IOS normals, convex crown regions are positive and
    interproximal concavities are negative.  Unlike the unsigned curvature
    signature used for CBCT correspondence, preserving the sign lets us retain
    the valley between two approximate tooth regions as a real stop line.
    """
    values = []
    for index, center in enumerate(face_centers):
        local = []
        normal = normals[index]
        for neighbour in adjacency[index]:
            if neighbour < 0 or neighbour >= len(face_centers):
                continue
            delta = face_centers[neighbour] - center
            length_sq = float(delta.length_squared)
            if length_sq <= 1.0e-14:
                continue
            # Discrete normal divergence.  For outward normals it is positive
            # on a crown bulge and negative in a contact/embrasure valley.
            local.append(float((normals[neighbour] - normal).dot(delta)) / length_sq)
        values.append(float(np.median(np.asarray(local, dtype=np.float64))) if local else 0.0)
    return values


def _negative_curvature_contact_barrier(mesh, world_vertices, normals, adjacency,
                                        contact_faces, selected):
    """Return a continuous, locally oriented interproximal stop barrier.

    The previous implementation removed only isolated negative-curvature faces.
    That could leave a 1-2 triangle doorway which later fill/grow operations
    crossed.  Here we orient normals locally, find robust negative-valley seeds,
    then connect fragmented seeds through the contested corridor by a weighted
    shortest path.
    """
    contact_faces = {int(index) for index in contact_faces if int(index) in selected}
    if len(contact_faces) < 3:
        return set(), {
            'negative_curvature_refinement': False,
            'negative_curvature_contact_faces': int(len(contact_faces)),
            'negative_curvature_barrier_faces': 0,
            'negative_curvature_connected_faces': 0,
        }
    centers = []
    for polygon in mesh.polygons:
        vertices = [world_vertices[int(vertex)] for vertex in polygon.vertices]
        if not vertices:
            centers.append(Vector((0.0, 0.0, 0.0)))
            continue
        centers.append(sum(vertices, Vector((0.0, 0.0, 0.0))) / float(len(vertices)))

    corridor = set(contact_faces)
    for face in list(contact_faces):
        corridor.update(int(n) for n in adjacency[face] if int(n) in selected)
    oriented_normals = _orient_normals_locally(normals, adjacency, corridor)
    curvature = _signed_face_curvature(centers, oriented_normals, adjacency)
    finite = [float(curvature[index]) for index in contact_faces
              if math.isfinite(float(curvature[index]))]
    negative = [value for value in finite if value < -1.0e-8]
    if len(negative) < 3:
        return set(), {
            'negative_curvature_refinement': False,
            'negative_curvature_contact_faces': int(len(contact_faces)),
            'negative_curvature_negative_faces': int(len(negative)),
            'negative_curvature_barrier_faces': 0,
            'negative_curvature_connected_faces': 0,
        }

    # Use a robust lower percentile rather than a fixed magnitude.  This is
    # considerably less sensitive to mesh tessellation density.
    threshold = min(-1.0e-8, float(np.percentile(np.asarray(negative, dtype=np.float64), 45.0)))
    barrier = {index for index in contact_faces if float(curvature[index]) <= threshold}
    barrier = {
        index for index in barrier
        if sum(1 for neighbour in adjacency[index] if int(neighbour) in barrier) >= 1
    }
    if len(barrier) < 3:
        barrier.clear()
        reliable = False
        connected_added = 0
    else:
        barrier, connected_added = _connect_barrier_components(
            barrier, contact_faces, adjacency, curvature)
        reliable = len(barrier) >= 3
    return barrier, {
        'negative_curvature_refinement': bool(reliable),
        'negative_curvature_contact_faces': int(len(contact_faces)),
        'negative_curvature_negative_faces': int(len(negative)),
        'negative_curvature_barrier_faces': int(len(barrier)),
        'negative_curvature_connected_faces': int(connected_added),
        'negative_curvature_threshold': float(threshold),
        'negative_curvature_locally_oriented': True,
    }


def _fill_confidence_gaps(selected, adjacency, scores, threshold, iterations=2):
    selected = set(selected)
    for _ in range(max(0, int(iterations))):
        add = set()
        for index, score in scores.items():
            if index in selected or float(score) < float(threshold) * 0.72:
                continue
            neighbours = adjacency[index]
            if not neighbours:
                continue
            selected_neighbours = sum(1 for neighbour in neighbours if neighbour in selected)
            required = 2 if len(neighbours) >= 3 else len(neighbours)
            if selected_neighbours >= required:
                add.add(index)
        if not add:
            break
        selected.update(add)
    return selected



def _mesh_boundary_faces(mesh):
    """Return face indices touching a true open edge of the IOS mesh."""
    n_faces = len(mesh.polygons)
    n_loops = len(mesh.loops)
    n_edges = len(mesh.edges)
    if not n_faces or not n_loops or not n_edges:
        return set()
    try:
        loop_total = np.empty(n_faces, dtype=np.int64)
        mesh.polygons.foreach_get('loop_total', loop_total)
        edge_index = np.empty(n_loops, dtype=np.int64)
        mesh.loops.foreach_get('edge_index', edge_index)
        face_index = np.repeat(np.arange(n_faces, dtype=np.int64), loop_total)
        counts = np.bincount(edge_index, minlength=n_edges)
        boundary_mask = counts[edge_index] == 1
        return set(face_index[boundary_mask].tolist())
    except Exception:
        edge_faces = defaultdict(list)
        for polygon in mesh.polygons:
            verts = tuple(int(v) for v in polygon.vertices)
            for pos, first in enumerate(verts):
                second = verts[(pos + 1) % len(verts)]
                key = (first, second) if first < second else (second, first)
                edge_faces[key].append(int(polygon.index))
        return {faces[0] for faces in edge_faces.values() if len(faces) == 1}


def _fill_topological_pinhole_gaps(selected, adjacency, scores, threshold, iterations=6,
                                   forbidden=None):
    """Fill black pinholes/narrow channels without performing a blind Select More.

    A repeated Ctrl+ grows *both* inward and outward.  For immediate extraction we
    only want the inward effect: a small unselected face surrounded by selected
    crown faces should join the crown, while the cervical exterior should remain
    untouched.  The score gate is deliberately weak because tiny IOS/CBCT
    triangulation differences are exactly what create these holes.
    """
    selected = set(selected)
    forbidden = set(forbidden or ())
    added_total = 0
    threshold = float(threshold)
    for _ in range(max(0, int(iterations))):
        frontier = set()
        for index in selected:
            frontier.update(adjacency[index])
        frontier.difference_update(selected)
        # A confirmed interproximal valley is a stop line.  Never let a
        # topological tidy-up cross it just because the neighbouring faces form
        # a small graph-theoretic hole.
        frontier.difference_update(forbidden)
        add = set()
        for index in frontier:
            neighbours = adjacency[index]
            if not neighbours:
                continue
            inside = sum(1 for neighbour in neighbours if neighbour in selected)
            degree = len(neighbours)
            # Fully surrounded faces are always holes.  On manifold triangular
            # scans, 2/3 selected neighbours is also a strong pinhole signal, but
            # require at least weak geometric support to avoid growing the outer
            # cervical boundary.
            fully_surrounded = inside == degree and degree >= 2
            bridge_gap = inside >= 2 and (inside / float(degree)) >= 0.66
            weak_support = float(scores.get(index, 0.0)) >= max(0.04, threshold * 0.18)
            if fully_surrounded or (bridge_gap and weak_support):
                add.add(index)
        if not add:
            break
        for index in add:
            scores[index] = max(float(scores.get(index, 0.0)), threshold * 0.90)
        selected.update(add)
        added_total += len(add)
    return selected, int(added_total)


def _fill_enclosed_selection_holes(selected, adjacency, mesh, scores, threshold,
                                   max_hole_faces=None, forbidden=None):
    """Fill every reasonably sized unselected island completely enclosed by selection.

    This is the graph equivalent of Fill Selection and is safer than repeated
    Select More: it cannot expand onto the outer IOS merely because the surface is
    connected.  Components that touch a pre-existing scan opening, or that escape
    into the large unselected exterior, are never filled.
    """
    selected = set(selected)
    forbidden = set(forbidden or ())
    if not selected:
        return selected, 0, 0
    boundary_faces = _mesh_boundary_faces(mesh)
    hard_limit = int(max_hole_faces or max(512, min(12000, round(len(selected) * 0.45))))
    seeds = set(forbidden)
    for index in selected:
        seeds.update(neighbour for neighbour in adjacency[index] if neighbour not in selected)

    visited = set()
    fill = set()
    components_filled = 0
    for seed in list(seeds):
        if seed in visited or seed in selected:
            continue
        component = {seed}
        frontier = [seed]
        visited.add(seed)
        touches_open_border = seed in boundary_faces
        escaped = False
        while frontier:
            current = frontier.pop()
            for neighbour in adjacency[current]:
                if neighbour in selected or neighbour in visited:
                    continue
                visited.add(neighbour)
                component.add(neighbour)
                if neighbour in boundary_faces:
                    touches_open_border = True
                if len(component) > hard_limit:
                    escaped = True
                    frontier.clear()
                    break
                frontier.append(neighbour)
        if escaped or touches_open_border or len(component) > hard_limit:
            continue
        # Do not treat a component containing the deliberate stop line as an
        # enclosed void.  It is the gap between two teeth, not a pinhole.
        if component & forbidden:
            continue
        # It is an enclosed unselected island.  A non-hole exterior component on
        # a closed manifold is enormous and is rejected by hard_limit above.
        if any(adjacency[index] & selected for index in component):
            fill.update(component)
            components_filled += 1

    if fill:
        for index in fill:
            scores[index] = max(float(scores.get(index, 0.0)), float(threshold) * 0.92)
        selected.update(fill)
    return selected, int(len(fill)), int(components_filled)


def _solidify_common_surface_selection(selected, adjacency, mesh, scores, threshold,
                                       forbidden=None):
    """Close selection pinholes and enclosed voids while preserving outer border."""
    selected = set(selected)
    selected, pinholes_first = _fill_topological_pinhole_gaps(
        selected, adjacency, scores, threshold, iterations=6, forbidden=forbidden)
    selected, enclosed_faces, enclosed_components = _fill_enclosed_selection_holes(
        selected, adjacency, mesh, scores, threshold, forbidden=forbidden)
    # Enclosed-hole fill can expose one-triangle cracks at the interface; one
    # short second pass seals those without behaving like a global Ctrl+.
    selected, pinholes_second = _fill_topological_pinhole_gaps(
        selected, adjacency, scores, threshold, iterations=3, forbidden=forbidden)
    return selected, {
        'selection_pinhole_faces_filled': int(pinholes_first + pinholes_second),
        'selection_enclosed_faces_filled': int(enclosed_faces),
        'selection_enclosed_components_filled': int(enclosed_components),
    }


def _trim_weak_spikes(selected, adjacency, scores, threshold, iterations=2):
    selected = set(selected)
    for _ in range(max(0, int(iterations))):
        remove = set()
        for index in selected:
            neighbours = adjacency[index]
            inside = sum(1 for neighbour in neighbours if neighbour in selected)
            if inside <= 1 and float(scores.get(index, 0.0)) < float(threshold) + 0.06:
                remove.add(index)
        if not remove or len(remove) >= max(1, len(selected) // 5):
            break
        selected.difference_update(remove)
    return selected


def _face_samples(polygon, world_vertices):
    vertices = [world_vertices[int(index)] for index in polygon.vertices]
    if not vertices:
        return []
    center = Vector((0.0, 0.0, 0.0))
    for vertex in vertices:
        center += vertex
    center /= float(len(vertices))
    # Center plus a sparse set of vertices catches partial matching faces while
    # keeping the check inexpensive on dense IOS scans.
    samples = [center]
    if len(vertices) <= 3:
        samples.extend(vertices)
    else:
        samples.extend((vertices[0], vertices[len(vertices) // 2], vertices[-1]))
    return samples


def _score_face(samples, face_normal, reference_bvh, target_bvh, face_index,
                adjacency, distance_limit, minimum_normal_dot,
                target_curvature=None, reference_curvature=None):
    """Score one IOS face using reciprocal surface correspondence + context."""
    distances, normal_scores, reference_faces = [], [], []
    center_reference_face = None
    for sample_index, point in enumerate(samples):
        hit, reference_normal, reference_face, distance = reference_bvh.find_nearest(point, distance_limit)
        if hit is None or distance is None or reference_face is None:
            continue
        back_hit, _back_normal, back_face, back_distance = target_bvh.find_nearest(hit, distance_limit)
        if back_hit is None or back_face is None or back_distance is None:
            continue
        if int(back_face) != int(face_index) and int(back_face) not in adjacency[face_index]:
            continue
        if reference_normal is None:
            normal_score = 0.5
        else:
            normal_dot = abs(float(face_normal.dot(reference_normal.normalized())))
            if normal_dot < minimum_normal_dot:
                continue
            normal_score = (normal_dot - minimum_normal_dot) / max(1.0 - minimum_normal_dot, 1.0e-9)
        distances.append(float(distance))
        normal_scores.append(max(0.0, min(1.0, normal_score)))
        reference_faces.append(int(reference_face))
        if sample_index == 0:
            center_reference_face = int(reference_face)
    coverage = len(distances) / float(max(len(samples), 1))
    if not distances:
        return 0.0, 0.0, float("inf"), 0.0, None
    mean_distance = sum(distances) / len(distances)
    distance_score = math.exp(-((mean_distance / max(distance_limit, 1.0e-9)) ** 2))
    normal_score = sum(normal_scores) / len(normal_scores)
    if center_reference_face is None and reference_faces:
        center_reference_face = max(set(reference_faces), key=reference_faces.count)
    context_score = 0.5
    if (
        center_reference_face is not None
        and target_curvature is not None
        and reference_curvature is not None
        and 0 <= int(center_reference_face) < len(reference_curvature)
    ):
        context_score = _curvature_similarity(
            target_curvature[face_index], reference_curvature[int(center_reference_face)])
    # Coverage and distance define the surface; curvature/context suppresses
    # interproximal/gingival look-alikes without relying on identical triangulation.
    score = 0.42 * coverage + 0.28 * distance_score + 0.12 * normal_score + 0.18 * context_score
    return float(max(0.0, min(1.0, score))), coverage, mean_distance, normal_score, center_reference_face


def _write_scores(mesh, scores):
    attribute = mesh.attributes.get(SCORE_ATTRIBUTE)
    if attribute is not None and (attribute.domain != "FACE" or attribute.data_type != "FLOAT"):
        mesh.attributes.remove(attribute)
        attribute = None
    if attribute is None:
        attribute = mesh.attributes.new(SCORE_ATTRIBUTE, "FLOAT", "FACE")
    for polygon in mesh.polygons:
        attribute.data[polygon.index].value = float(scores.get(int(polygon.index), 0.0))


def _select_components(selected, anchors, adjacency, scores, max_components):
    components = _connected_components(selected, adjacency)
    ranked = []
    for component in components:
        if not component:
            continue
        confidence = sum(scores.get(index, 0.0) for index in component) / len(component)
        anchored = bool(component & anchors)
        # An anchored region wins over an unanchored look-alike; confidence and
        # area only resolve ties. Multiple selected teeth can legitimately yield
        # several disconnected regions, hence a limited plural result.
        ranked.append((anchored, confidence, len(component), component))
    ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    # The number of retained islands follows the number of clinician-selected
    # teeth.  For a single immediate implant this deliberately retains *one*
    # connected IOS island, preventing a small interproximal look-alike on an
    # adjacent tooth from being carried into the extraction selection.
    limit = max(1, int(max_components))
    kept = [item[3] for item in ranked if item[0]][:limit]
    if not kept and ranked:
        kept = [ranked[0][3]]
    return set().union(*kept) if kept else set()


def _grow_coherent_surface(selected, adjacency, normals, scores, grow_threshold, max_angle_deg):
    if not selected:
        return set()
    cosine_limit = math.cos(math.radians(float(max_angle_deg)))
    grown = set(selected)
    frontier = list(selected)
    while frontier:
        current = frontier.pop()
        current_normal = normals[current]
        for neighbour in adjacency[current]:
            if neighbour in grown or scores.get(neighbour, 0.0) < grow_threshold:
                continue
            # Two-sided continuity makes the grow robust to local flipped
            # triangles in a partial IOS scan.
            if abs(float(current_normal.dot(normals[neighbour]))) < cosine_limit:
                continue
            grown.add(neighbour)
            frontier.append(neighbour)
    return grown





def _build_object_bvh(obj):
    if not _valid_mesh(obj):
        return None
    verts = _world_vertices(obj)
    faces = [tuple(int(index) for index in polygon.vertices) for polygon in obj.data.polygons]
    if not verts or not faces:
        return None
    try:
        return BVHTree.FromPolygons(verts, faces, all_triangles=False)
    except Exception:
        return None


def _bone_guard_face_set(ios_obj, selected_faces, target_bvh, bone_bvh, *,
                         target_limit_mm, bone_limit_mm=2.50,
                         margin_mm=0.12):
    """Reject IOS faces whose geometry is better explained by alveolar bone.

    This is negative evidence only.  It prevents buccal/lingual gingival
    overgrowth while keeping a strongly tooth-supported face even when the
    alveolar crest is close.
    """
    if bone_bvh is None or not selected_faces:
        return set()
    forbidden = set()
    normal_matrix = _world_normal_matrix(ios_obj)
    strong_target_limit = max(0.22, min(0.48, float(target_limit_mm) * 0.38))
    for index in selected_faces:
        polygon = ios_obj.data.polygons[int(index)]
        point = ios_obj.matrix_world @ polygon.center
        thit, tnormal, _tface, td = target_bvh.find_nearest(point, float(target_limit_mm) * 1.6)
        if thit is None or td is None:
            forbidden.add(int(index))
            continue
        td = float(td)
        if td <= strong_target_limit:
            continue
        bhit, bnormal, _bface, bd = bone_bvh.find_nearest(point, float(bone_limit_mm))
        if bhit is None or bd is None:
            continue
        bd = float(bd)
        bone_wins = bd + float(margin_mm) < td
        if not bone_wins and abs(bd - td) <= float(margin_mm):
            try:
                fn = _world_face_normal(ios_obj, polygon, normal_matrix)
                tdot = abs(float(fn.dot(tnormal.normalized()))) if tnormal is not None and tnormal.length > 1e-10 else 0.0
                bdot = abs(float(fn.dot(bnormal.normalized()))) if bnormal is not None and bnormal.length > 1e-10 else 0.0
                bone_wins = bdot > tdot + 0.14
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
        if bone_wins:
            forbidden.add(int(index))
    return forbidden


def select_anatomy_locked_ios_seed(ios_obj, cbct_teeth, *,
                                   distance_mm=1.25, max_components=None,
                                   competitor_teeth=None,
                                   bone_guard=None,
                                   bone_guard_margin_mm=0.12,
                                   bone_guard_distance_mm=2.50,
                                   contact_margin_mm=0.18,
                                   minimum_normal_angle_deg=73.0,
                                   sample_coverage=0.67,
                                   curvature_tie_limit=0.10,
                                   negative_curvature_refinement=True):
    """Recover a difficult match without turning proximity into tooth identity.

    This is intentionally stricter than the old 9.2.32-style fallback.  It
    accepts an IOS face only when its *surface* lies inside the selected CBCT
    tooth territory, has enough vertex support, and has a compatible normal.
    It then retains just one connected anatomical island per extracted tooth.
    Thus a nearby gingival patch or an adjacent crown cannot be accepted merely
    because one of its vertices happens to be close to the CBCT mesh.
    """
    if not _valid_mesh(ios_obj):
        raise RuntimeError("El IOS alineado no contiene una malla válida")
    teeth = [obj for obj in cbct_teeth if _valid_mesh(obj)]
    if not teeth:
        raise RuntimeError("No hay dientes CBCT válidos para comparar")
    distance_mm = max(0.10, float(distance_mm))
    max_components = len(teeth) if max_components is None else max(1, int(max_components))
    minimum_normal_angle_deg = max(1.0, min(89.0, float(minimum_normal_angle_deg)))
    sample_coverage = max(0.34, min(1.0, float(sample_coverage)))
    curvature_tie_limit = max(0.01, min(0.35, float(curvature_tie_limit)))
    started = time.perf_counter()
    world_vertices = _world_vertices(ios_obj)
    ios_faces = [tuple(int(index) for index in polygon.vertices) for polygon in ios_obj.data.polygons]
    ios_bvh = BVHTree.FromPolygons(world_vertices, ios_faces, all_triangles=False)
    if ios_bvh is None:
        raise RuntimeError("No se pudo construir la superficie IOS")

    # Build the target and neighbour references only from CBCT surfaces that the
    # aligned IOS can actually support.  This removes roots from both positive
    # and negative references before ownership is evaluated.
    reference = _reference_surface_data(
        teeth, target_bvh=ios_bvh, distance_mm=distance_mm,
        normal_angle_deg=minimum_normal_angle_deg)
    if reference is None:
        raise RuntimeError("No se pudo construir la búsqueda anatómica CBCT")
    reference_bvh = reference['bvh']
    target_curvature = reference['curvature']
    competitors = [obj for obj in (competitor_teeth or []) if _valid_mesh(obj) and obj not in teeth]
    competitor_reference = _reference_surface_data(
        competitors, target_bvh=ios_bvh, distance_mm=distance_mm * 1.10,
        normal_angle_deg=minimum_normal_angle_deg) if competitors else None
    competitor_bvh = competitor_reference['bvh'] if competitor_reference else None
    competitor_curvature = competitor_reference['curvature'] if competitor_reference else []
    bone_bvh = _build_object_bvh(bone_guard)

    # Strong positive anchors come only from the occlusal/incisal surfaces of
    # the tooth(s) of interest.  The rest of the crown may be selected later by
    # connected GeoMatch growth, but gingiva and roots can no longer become the
    # seed that decides which island wins.
    occlusal_reference = dental_surface_geometry.build_occlusal_reference_bvh(
        teeth, context_objects=(list(teeth) + list(competitors)), relaxed=False)
    if occlusal_reference is None:
        occlusal_reference = dental_surface_geometry.build_occlusal_reference_bvh(
            teeth, context_objects=(list(teeth) + list(competitors)), relaxed=True)
    occlusal_bvh = occlusal_reference.get('bvh') if occlusal_reference else None

    adjacency = _build_face_adjacency(ios_obj.data)
    normal_matrix = _world_normal_matrix(ios_obj)
    ios_normals = [_world_face_normal(ios_obj, polygon, normal_matrix)
                   for polygon in ios_obj.data.polygons]
    ios_curvature = _curvature_signatures(ios_normals, adjacency)
    bounds = _expanded_bounds(teeth, distance_mm * 0.80)
    # Allow substantial CBCT/IOS normal disagreement, but reject perpendicular
    # gingiva / interdental walls.  abs() keeps the test robust to local flips.
    minimum_normal_dot = math.cos(math.radians(minimum_normal_angle_deg))
    scores, distances, anchors, selected = {}, {}, set(), set()
    geometric_anchor_candidates = set()
    occlusal_anchor_candidates = set()
    candidate_faces = 0
    competitor_rejected_faces = 0
    competitor_forbidden = set()
    contact_boundary_faces = 0
    curvature_boundary_faces = 0
    # These are the contested, approximate regions supplied by the target vs.
    # FDI-neighbour competition.  We refine their line only after all faces
    # have been provisionally classified, never while scoring an isolated face.
    contact_candidates = set()
    for polygon in ios_obj.data.polygons:
        index = int(polygon.index)
        points = _face_samples(polygon, world_vertices)
        if not points:
            continue
        center = points[0]
        if not _inside_bounds(center, bounds):
            continue
        face_normal = ios_normals[index]
        hits, values, dots, target_curve_scores = 0, [], [], []
        competitor_wins = 0
        contact_votes = 0
        curvature_votes = 0
        for point in points:
            hit, ref_normal, ref_face, distance = reference_bvh.find_nearest(point, distance_mm)
            if hit is None or distance is None:
                continue
            normal_dot = 0.5
            if ref_normal is not None and ref_normal.length > 1.0e-10:
                normal_dot = abs(float(face_normal.dot(ref_normal.normalized())))
            if normal_dot < minimum_normal_dot:
                continue
            target_curve = 0.5
            if ref_face is not None and 0 <= int(ref_face) < len(target_curvature):
                target_curve = _curvature_similarity(ios_curvature[index], target_curvature[int(ref_face)])
            # The mesial/distal teeth are negative anatomical references.  In
            # a crowding contact their distance can tie the target, so local
            # curvature decides ownership; unresolved ties become a boundary.
            if competitor_bvh is not None:
                _chit, _cnormal, comp_face, comp_distance = competitor_bvh.find_nearest(point, distance_mm * 1.35)
                if comp_distance is not None:
                    comp_curve = 0.5
                    if comp_face is not None and 0 <= int(comp_face) < len(competitor_curvature):
                        comp_curve = _curvature_similarity(ios_curvature[index], competitor_curvature[int(comp_face)])
                    separation = float(comp_distance) - float(distance)
                    curve_delta = float(target_curve) - float(comp_curve)
                    if separation < -float(contact_margin_mm):
                        competitor_wins += 1
                        continue
                    if abs(separation) <= float(contact_margin_mm):
                        contact_votes += 1
                        # A curvature tie at an interproximal contact is a
                        # deliberate stop line, not an arbitrary ownership.
                        if abs(curve_delta) <= curvature_tie_limit:
                            curvature_votes += 1
                            continue
                        if curve_delta < 0.0:
                            competitor_wins += 1
                            continue
            hits += 1
            values.append(float(distance))
            dots.append(float(normal_dot))
            target_curve_scores.append(float(target_curve))
        # A face must be supported by a majority of its samples.  This rejects
        # boundary triangles that straddle the selected tooth and a neighbour.
        required = max(1, int(math.ceil(len(points) * sample_coverage)))
        if contact_votes:
            contact_boundary_faces += 1
            contact_candidates.add(index)
        if curvature_votes:
            curvature_boundary_faces += 1
        if competitor_wins >= required:
            competitor_rejected_faces += 1
            competitor_forbidden.add(index)
            continue
        if hits < required:
            continue
        candidate_faces += 1
        mean_distance = sum(values) / len(values)
        mean_dot = sum(dots) / len(dots)
        coverage = hits / float(len(points))
        distance_score = math.exp(-((mean_distance / max(distance_mm, 1.0e-9)) ** 2))
        normal_score = (mean_dot - minimum_normal_dot) / max(1.0 - minimum_normal_dot, 1.0e-9)
        curvature_score = sum(target_curve_scores) / max(1, len(target_curve_scores))
        score = (0.40 * distance_score + 0.24 * coverage
                 + 0.18 * max(0.0, min(1.0, normal_score)) + 0.18 * curvature_score)
        scores[index] = float(score)
        distances[index] = float(mean_distance)
        selected.add(index)
        if coverage >= 0.99 and mean_distance <= distance_mm * 0.62:
            geometric_anchor_candidates.add(index)
            if occlusal_bvh is not None:
                _ohit, _onormal, _oface, odistance = occlusal_bvh.find_nearest(
                    center, max(0.35, distance_mm * 0.95))
                if odistance is not None and float(odistance) <= max(0.30, distance_mm * 0.78):
                    occlusal_anchor_candidates.add(index)

    anchors = (
        set(occlusal_anchor_candidates)
        if len(occlusal_anchor_candidates) >= max(2, len(teeth))
        else set(geometric_anchor_candidates)
    )
    if len(selected) < MIN_SELECTED_FACES:
        raise RuntimeError("La anatomía CBCT no sostiene una isla IOS suficiente; revisa el alineamiento")
    selected = _select_components(selected, anchors, adjacency, scores, max_components)
    valley_barrier, valley_stats = (set(), {
        'negative_curvature_refinement': False,
        'negative_curvature_contact_faces': 0,
        'negative_curvature_barrier_faces': 0,
    })
    if bool(negative_curvature_refinement) and competitors:
        valley_barrier, valley_stats = _negative_curvature_contact_barrier(
            ios_obj.data, world_vertices, ios_normals, adjacency,
            contact_candidates, selected)
        # Preserve the explicit valley even if a later hole-filling pass sees
        # it as a tiny gap.  It is an interproximal boundary, not a defect.
        selected.difference_update(valley_barrier)
        anchors.difference_update(valley_barrier)
    bone_forbidden = _bone_guard_face_set(
        ios_obj, selected, reference_bvh, bone_bvh,
        target_limit_mm=distance_mm,
        bone_limit_mm=bone_guard_distance_mm,
        margin_mm=bone_guard_margin_mm,
    )
    selected.difference_update(bone_forbidden)
    anchors.difference_update(bone_forbidden)
    protected_boundary = set(valley_barrier) | set(competitor_forbidden) | set(bone_forbidden)
    selected, solid_stats = _solidify_common_surface_selection(
        selected, adjacency, ios_obj.data, scores, threshold=0.45,
        forbidden=protected_boundary)
    selected = _trim_weak_spikes(selected, adjacency, scores, threshold=0.45, iterations=2)
    selected.difference_update(protected_boundary)
    selected = _select_components(selected, anchors, adjacency, scores, max_components)
    if len(selected) < MIN_SELECTED_FACES:
        raise RuntimeError("La isla anatómica IOS resultó ambigua o insuficiente")
    _write_scores(ios_obj.data, scores)
    valid_distances = sorted(float(distances[index]) for index in selected if index in distances)
    if valid_distances:
        p95_index = min(len(valid_distances) - 1, int(math.ceil(len(valid_distances) * 0.95)) - 1)
        p95_distance = valid_distances[p95_index]
        mean_distance = sum(valid_distances) / len(valid_distances)
    else:
        p95_distance = mean_distance = 0.0
    return {
        "selected_faces": set(selected), "scores": scores,
        "candidate_faces": int(candidate_faces), "anchor_faces": int(len(anchors)),
        "selected_count": int(len(selected)), "mean_distance_mm": float(mean_distance),
        "p95_distance_mm": float(p95_distance), "distance_limit_mm": float(distance_mm),
        "requested_tooth_regions": int(max_components), "anatomy_locked": True,
        "competitor_teeth": int(len(competitors)),
        "competitor_faces_rejected": int(competitor_rejected_faces),
        "competitor_forbidden_faces": int(len(competitor_forbidden)),
        "bone_guard_enabled": bool(bone_bvh is not None),
        "bone_guard_forbidden_faces": int(len(bone_forbidden)),
        "bone_guard_distance_mm": float(bone_guard_distance_mm),
        "bone_guard_margin_mm": float(bone_guard_margin_mm),
        "contact_boundary_faces": int(contact_boundary_faces),
        "curvature_boundary_faces": int(curvature_boundary_faces),
        "minimum_normal_angle_deg": float(minimum_normal_angle_deg),
        "sample_coverage": float(sample_coverage),
        "curvature_tie_limit": float(curvature_tie_limit),
        "reference_faces_kept": int(reference.get('kept_reference_faces', 0)),
        "reference_faces_total": int(reference.get('total_reference_faces', 0)),
        "occlusal_anchor_faces": int(len(occlusal_anchor_candidates)),
        "anchor_mode": "OCCLUSAL_INCISAL" if anchors == set(occlusal_anchor_candidates) and anchors else "GEOMETRIC_FALLBACK",
        "competitor_reference_faces_kept": int(competitor_reference.get('kept_reference_faces', 0)) if competitor_reference else 0,
        **valley_stats,
        **solid_stats, "runtime_seconds": float(time.perf_counter() - started),
        "method": ANATOMY_LOCKED_METHOD_ID,
    }


def select_common_ios_surface(ios_obj, cbct_teeth, *, distance_mm=DEFAULT_DISTANCE_MM,
                              normal_angle_deg=DEFAULT_NORMAL_ANGLE_DEG,
                              score_threshold=DEFAULT_SCORE_THRESHOLD,
                              max_components=None, competitor_teeth=None,
                              competitor_margin_mm=0.10,
                              bone_guard=None, bone_guard_margin_mm=0.12,
                              bone_guard_distance_mm=2.50):
    """Precision-first common-surface matcher for immediate extraction review."""
    if not _valid_mesh(ios_obj):
        raise RuntimeError("El IOS alineado no contiene una malla válida")
    teeth = [obj for obj in cbct_teeth if _valid_mesh(obj)]
    if not teeth:
        raise RuntimeError("No hay dientes CBCT válidos para comparar")
    distance_mm = max(0.05, float(distance_mm))
    score_threshold = max(0.05, min(0.98, float(score_threshold)))
    normal_angle_deg = max(1.0, min(89.0, float(normal_angle_deg)))
    max_components = len(teeth) if max_components is None else int(max_components)
    started = time.perf_counter()

    ios_vertices = _world_vertices(ios_obj)
    ios_faces = [tuple(int(index) for index in polygon.vertices) for polygon in ios_obj.data.polygons]
    target_bvh = BVHTree.FromPolygons(ios_vertices, ios_faces, all_triangles=False)
    if target_bvh is None:
        raise RuntimeError("No se pudo construir la superficie IOS")
    reference = _reference_surface_data(
        teeth, target_bvh=target_bvh, distance_mm=distance_mm,
        normal_angle_deg=normal_angle_deg,
    )
    if reference is None:
        raise RuntimeError("No se pudo construir la superficie CBCT común")
    reference_bvh = reference['bvh']
    bone_bvh = _build_object_bvh(bone_guard)
    competitors = [obj for obj in (competitor_teeth or []) if _valid_mesh(obj) and obj not in teeth]
    occlusal_reference = dental_surface_geometry.build_occlusal_reference_bvh(
        teeth, context_objects=(list(teeth) + list(competitors)), relaxed=False)
    if occlusal_reference is None:
        occlusal_reference = dental_surface_geometry.build_occlusal_reference_bvh(
            teeth, context_objects=(list(teeth) + list(competitors)), relaxed=True)
    occlusal_bvh = occlusal_reference.get('bvh') if occlusal_reference else None

    adjacency = _build_face_adjacency(ios_obj.data)
    normal_matrix = _world_normal_matrix(ios_obj)
    normals = [_world_face_normal(ios_obj, polygon, normal_matrix)
               for polygon in ios_obj.data.polygons]
    target_curvature = _curvature_signatures(normals, adjacency)
    bounds = _expanded_bounds(teeth, distance_mm * 1.35)
    minimum_normal_dot = math.cos(math.radians(normal_angle_deg))
    scores, coverages, distances = {}, {}, {}
    candidate_faces = []

    # Strong reference->IOS anchors make the chosen connected component follow
    # the actual segmented tooth rather than a nearby gingival/interproximal patch.
    anchors = set()
    anchor_limit = max(0.30, distance_mm * 0.58)
    # The full IOS-supported crown still supplies the score field, but the island
    # is seeded from an occlusal/incisal patch whenever possible.
    if occlusal_reference is not None:
        for landmark in occlusal_reference.get('landmarks_by_fdi', {}).values():
            center = Vector(tuple(float(v) for v in np.asarray(landmark, dtype=np.float64)))
            hit, _normal, target_face, distance = target_bvh.find_nearest(center, distance_mm)
            if hit is not None and target_face is not None and distance is not None and float(distance) <= max(anchor_limit, distance_mm * 0.80):
                anchors.add(int(target_face))
    if not anchors:
        centers = reference.get('centers', [])
        if centers:
            step = max(1, len(centers) // 1200)
            for center in centers[::step]:
                hit, _normal, target_face, distance = target_bvh.find_nearest(center, distance_mm)
                if hit is not None and target_face is not None and distance is not None and float(distance) <= anchor_limit:
                    anchors.add(int(target_face))

    for polygon in ios_obj.data.polygons:
        center = ios_obj.matrix_world @ polygon.center
        if not _inside_bounds(center, bounds):
            continue
        index = int(polygon.index)
        score, coverage, mean_distance, _normal_score, _reference_face = _score_face(
            _face_samples(polygon, ios_vertices), normals[index], reference_bvh,
            target_bvh, index, adjacency, distance_mm, minimum_normal_dot,
            target_curvature=target_curvature,
            reference_curvature=reference['curvature'],
        )
        scores[index] = score
        coverages[index] = coverage
        distances[index] = mean_distance
        candidate_faces.append(index)

    anchor_threshold = min(0.94, score_threshold + 0.16)
    strong_scores = {
        index for index in candidate_faces
        if scores.get(index, 0.0) >= score_threshold and coverages.get(index, 0.0) >= 0.60
    }
    anchors.update(
        index for index in strong_scores
        if scores.get(index, 0.0) >= anchor_threshold and coverages.get(index, 0.0) >= 0.80
    )
    selected = _select_components(strong_scores, anchors, adjacency, scores, max_components)
    selected = _grow_coherent_surface(
        selected, adjacency, normals, scores,
        grow_threshold=max(0.30, min(score_threshold * 0.78, DEFAULT_GROW_SCORE_THRESHOLD)),
        max_angle_deg=DEFAULT_GROW_ANGLE_DEG,
    )
    selected = _fill_confidence_gaps(selected, adjacency, scores, score_threshold, iterations=3)

    # Even the emergency/fallback matcher must remember neighbouring teeth.
    # Otherwise a relaxed recovery pass can undo the competitive ownership
    # established by the precise matcher.
    fallback_forbidden = set()
    if competitors and selected:
        competitor_reference = _reference_surface_data(
            competitors, target_bvh=target_bvh, distance_mm=distance_mm * 1.10,
            normal_angle_deg=normal_angle_deg)
        competitor_bvh = competitor_reference['bvh'] if competitor_reference else None
        if competitor_bvh is not None:
            for index in list(selected):
                polygon = ios_obj.data.polygons[int(index)]
                center = ios_obj.matrix_world @ polygon.center
                _thit, _tnormal, _tface, target_distance = reference_bvh.find_nearest(center, distance_mm * 1.50)
                _chit, _cnormal, _cface, competitor_distance = competitor_bvh.find_nearest(center, distance_mm * 1.50)
                if competitor_distance is None:
                    continue
                if target_distance is None or float(competitor_distance) + float(competitor_margin_mm) < float(target_distance):
                    fallback_forbidden.add(int(index))
            selected.difference_update(fallback_forbidden)
            anchors.difference_update(fallback_forbidden)

    bone_forbidden = _bone_guard_face_set(
        ios_obj, selected, reference_bvh, bone_bvh,
        target_limit_mm=distance_mm,
        bone_limit_mm=bone_guard_distance_mm,
        margin_mm=bone_guard_margin_mm,
    )
    selected.difference_update(bone_forbidden)
    anchors.difference_update(bone_forbidden)
    fallback_forbidden.update(bone_forbidden)
    selected, solid_stats = _solidify_common_surface_selection(
        selected, adjacency, ios_obj.data, scores, score_threshold,
        forbidden=fallback_forbidden)
    selected = _trim_weak_spikes(selected, adjacency, scores, score_threshold, iterations=2)
    selected = _select_components(selected, anchors, adjacency, scores, max_components)
    # Final hole-only pass after component filtering.  This deliberately does not
    # grow the cervical border; it only seals holes inside the retained tooth island.
    selected, final_solid_stats = _solidify_common_surface_selection(
        selected, adjacency, ios_obj.data, scores, score_threshold,
        forbidden=fallback_forbidden)
    for key, value in final_solid_stats.items():
        solid_stats[key] = int(solid_stats.get(key, 0)) + int(value)
    _write_scores(ios_obj.data, scores)

    valid_distances = sorted(
        float(distances[index]) for index in selected
        if math.isfinite(float(distances.get(index, float("inf"))))
    )
    if valid_distances:
        p95_index = min(len(valid_distances) - 1, int(math.ceil(len(valid_distances) * 0.95)) - 1)
        p95_distance = valid_distances[p95_index]
        mean_distance = sum(valid_distances) / len(valid_distances)
    else:
        p95_distance = mean_distance = 0.0
    return {
        "selected_faces": set(selected), "scores": scores,
        "candidate_faces": int(len(candidate_faces)), "anchor_faces": int(len(anchors)),
        "selected_count": int(len(selected)), "mean_distance_mm": float(mean_distance),
        "p95_distance_mm": float(p95_distance), "distance_limit_mm": float(distance_mm),
        "score_threshold": float(score_threshold), "requested_tooth_regions": int(max_components),
        "reference_faces_kept": int(reference.get('kept_reference_faces', 0)),
        "reference_faces_total": int(reference.get('total_reference_faces', 0)),
        "occlusal_anchor_reference_faces": int(occlusal_reference.get('face_count', 0)) if occlusal_reference else 0,
        "occlusal_anchor_mode": bool(occlusal_reference is not None),
        "fallback_competitor_forbidden_faces": int(len(fallback_forbidden)),
        "bone_guard_enabled": bool(bone_bvh is not None),
        "bone_guard_forbidden_faces": int(len(bone_forbidden)),
        **solid_stats,
        "runtime_seconds": float(time.perf_counter() - started), "method": METHOD_ID,
    }


def apply_common_surface_selection(obj, result, group_name="DSG_CBCT_COMMON_SURFACE"):
    """Persist a generated selection as both edit-state and vertex group."""
    if not _valid_mesh(obj):
        raise RuntimeError("El destino de superficie común no es válido")
    selected_faces = set(result.get("selected_faces", set()))
    if len(selected_faces) < MIN_SELECTED_FACES:
        raise RuntimeError("La coincidencia no encontró una región común suficiente; revisa el alineamiento")
    existing = obj.vertex_groups.get(group_name)
    if existing is not None:
        obj.vertex_groups.remove(existing)
    group = obj.vertex_groups.new(name=group_name)
    selected_vertices = set()
    for polygon in obj.data.polygons:
        is_selected = int(polygon.index) in selected_faces
        polygon.select = is_selected
        if is_selected:
            selected_vertices.update(int(index) for index in polygon.vertices)
    group.add(sorted(selected_vertices), 1.0, "REPLACE")
    obj["DSG_common_surface_method"] = str(result.get("method", METHOD_ID))
    obj["DSG_common_surface_stats"] = json.dumps({
        key: value for key, value in result.items() if key not in {"selected_faces", "scores"}
    }, ensure_ascii=False, sort_keys=True)
    obj["DSG_common_surface_selected_faces"] = int(len(selected_faces))
    obj["DSG_common_surface_selected_vertices"] = int(len(selected_vertices))
    return int(len(selected_faces)), int(len(selected_vertices))
