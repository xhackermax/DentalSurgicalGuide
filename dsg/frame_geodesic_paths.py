"""Shared, fail-closed geodesic routing contract for DSG frames and reinforcements.

Pure NumPy geometry. Reuses the existing frame_surface_corridor.weighted_route
engine rather than creating a parallel pathfinder. Routes traverse only supplied
surface-mesh edges and never fall back to straight Euclidean chords.

Blender is responsible for face/barycentric anchors, smoothing that stays on
the surface, and explicitly validated sleeve transitions.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import frame_surface_corridor


class NoValidSurfaceRoute(ValueError):
    """No permitted intrinsic route connects the requested endpoints."""


@dataclass(frozen=True)
class GeodesicSurfacePath:
    vertex_indices: tuple[int, ...]
    points_mm: np.ndarray
    surface_length_mm: float
    weighted_cost: float
    backend: str


def route_surface_vertices(
    vertices_mm,
    csr_offsets,
    csr_destinations,
    csr_edge_lengths_mm,
    start_vertex: int,
    end_vertex: int,
    *,
    allowed_mask=None,
    vertex_penalty=None,
) -> GeodesicSurfacePath:
    """Find an intrinsic mesh-edge route under hard restrictions.

    Units: mm. The graph must represent real mesh-surface edges, not arbitrary
    3D near-neighbour chords. The wrapper rejects excluded endpoints because
    the existing weighted router normally auto-enables candidate endpoints.
    """
    xyz = np.asarray(vertices_mm, dtype=np.float64)
    offsets = np.asarray(csr_offsets, dtype=np.int64)
    dst = np.asarray(csr_destinations, dtype=np.int64)
    weights = np.asarray(csr_edge_lengths_mm, dtype=np.float64)
    if xyz.ndim != 2 or xyz.shape[1] != 3 or not np.isfinite(xyz).all():
        raise ValueError("vertices_mm must contain finite Nx3 coordinates")
    n = len(xyz)
    if n == 0 or offsets.shape != (n + 1,) or dst.ndim != 1 or weights.shape != dst.shape:
        raise ValueError("invalid surface graph shape")
    if offsets[0] != 0 or offsets[-1] != len(dst) or np.any(np.diff(offsets) < 0):
        raise ValueError("invalid CSR offsets")
    if (dst < 0).any() or (dst >= n).any() or not np.isfinite(weights).all() or (weights <= 0).any():
        raise ValueError("invalid surface graph edges")
    a, b = int(start_vertex), int(end_vertex)
    if not (0 <= a < n and 0 <= b < n):
        raise ValueError("surface endpoint outside mesh")
    permitted = np.ones(n, dtype=bool) if allowed_mask is None else np.asarray(allowed_mask, dtype=bool)
    if permitted.shape != (n,):
        raise ValueError("allowed_mask must have one entry per vertex")
    if not permitted[a] or not permitted[b]:
        raise NoValidSurfaceRoute("NO_VALID_SURFACE_ROUTE: excluded endpoint")
    penalty = None if vertex_penalty is None else np.asarray(vertex_penalty, dtype=np.float64)
    if penalty is not None and (
        penalty.shape != (n,) or not np.isfinite(penalty).all() or (penalty < 0).any()
    ):
        raise ValueError("invalid surface penalty")
    if a == b:
        return GeodesicSurfacePath((a,), xyz[[a]].copy(), 0.0, 0.0, "SAME_SURFACE_VERTEX")
    result = frame_surface_corridor.weighted_route(
        offsets, dst, weights, [a], [b], allowed_mask=permitted, vertex_penalty=penalty
    )
    if result is None:
        raise NoValidSurfaceRoute("NO_VALID_SURFACE_ROUTE: disconnected or forbidden surface corridor")
    route = tuple(int(i) for i in result.vertex_indices)
    if len(route) < 2 or route[0] != a or route[-1] != b or not permitted[list(route)].all():
        raise NoValidSurfaceRoute("NO_VALID_SURFACE_ROUTE: invalid route returned by graph solver")
    total_length = 0.0
    for u, v in zip(route, route[1:]):
        lo, hi = int(offsets[u]), int(offsets[u + 1])
        matches = np.flatnonzero(dst[lo:hi] == v)
        if not len(matches):
            raise NoValidSurfaceRoute("NO_VALID_SURFACE_ROUTE: non-surface edge")
        length = float(weights[lo + int(matches[0])])
        actual = float(np.linalg.norm(xyz[u] - xyz[v]))
        if abs(length - actual) > max(1e-5, actual * 1e-3):
            raise ValueError("surface graph edge length is inconsistent with mesh coordinates")
        total_length += length
    return GeodesicSurfacePath(
        route, xyz[list(route)].copy(), total_length,
        float(result.cost), str(result.backend)
    )


def _validate_face_anchor(xyz, face_vertices, anchor, permitted, label):
    """Validate an exact projected face anchor; never snap across a nearby sheet."""
    ids = tuple(int(v) for v in face_vertices)
    point = np.asarray(anchor, dtype=np.float64)
    if point.shape != (3,) or not np.isfinite(point).all():
        raise ValueError(f"{label}: anchor coordinates must be finite XYZ")
    if len(ids) != 3 or len(set(ids)) != 3 or any(v < 0 or v >= len(xyz) for v in ids):
        raise ValueError(f"{label}: exactly three distinct face vertices required")
    if not permitted[list(ids)].all():
        raise NoValidSurfaceRoute(f"NO_VALID_SURFACE_ROUTE: {label} lies on a protected face")
    a, b, c = xyz[list(ids)]
    u, v = b - a, c - a
    normal = np.cross(u, v)
    area_sq = float(normal @ normal)
    if area_sq <= 1e-18:
        raise ValueError(f"{label}: degenerate anchor triangle")
    offset = point - a
    distance = abs(float(offset @ normal)) / np.sqrt(area_sq)
    if distance > 1e-4:
        raise NoValidSurfaceRoute(f"NO_VALID_SURFACE_ROUTE: {label} is not on the surface triangle")
    dot_uu, dot_uv, dot_vv = float(u @ u), float(u @ v), float(v @ v)
    dot_pu, dot_pv = float(offset @ u), float(offset @ v)
    denom = dot_uu * dot_vv - dot_uv * dot_uv
    alpha = (dot_vv * dot_pu - dot_uv * dot_pv) / denom
    beta = (dot_uu * dot_pv - dot_uv * dot_pu) / denom
    if alpha < -1e-5 or beta < -1e-5 or alpha + beta > 1 + 1e-5:
        raise NoValidSurfaceRoute(f"NO_VALID_SURFACE_ROUTE: {label} is outside its face")
    return ids, point


def route_surface_face_anchors(
    vertices_mm,
    csr_offsets,
    csr_destinations,
    csr_edge_lengths_mm,
    start_face_vertices,
    start_point_mm,
    end_face_vertices,
    end_point_mm,
    *,
    allowed_mask=None,
    vertex_penalty=None,
) -> GeodesicSurfacePath:
    """Route exact triangle anchors without leaving the surface or using 3D shortcuts.

    Graph links are real evaluated-mesh edges. Virtual links are confined to the
    start and end triangles. Smoothing / meshing is a separate validated stage.
    """
    xyz = np.asarray(vertices_mm, dtype=np.float64)
    if xyz.ndim != 2 or xyz.shape[1] != 3 or not np.isfinite(xyz).all():
        raise ValueError("vertices_mm must contain finite Nx3 coordinates")
    n = len(xyz)
    permitted = np.ones(n, dtype=bool) if allowed_mask is None else np.asarray(allowed_mask, dtype=bool)
    if permitted.shape != (n,):
        raise ValueError("allowed_mask must have one entry per vertex")
    first, p0 = _validate_face_anchor(xyz, start_face_vertices, start_point_mm, permitted, "start")
    last, p1 = _validate_face_anchor(xyz, end_face_vertices, end_point_mm, permitted, "end")
    if set(first) == set(last):
        points = np.stack((p0, p1))
        return GeodesicSurfacePath(
            (), points, float(np.linalg.norm(p1 - p0)),
            float(np.linalg.norm(p1 - p0)), "SAME_TRIANGLE")
    # Validate graph before calling the legacy weighted router.
    offsets = np.asarray(csr_offsets, dtype=np.int64)
    destinations = np.asarray(csr_destinations, dtype=np.int64)
    lengths = np.asarray(csr_edge_lengths_mm, dtype=np.float64)
    if (offsets.shape != (n + 1,) or offsets[0] != 0
            or offsets[-1] != len(destinations) or np.any(np.diff(offsets) < 0)
            or lengths.shape != destinations.shape or (destinations < 0).any()
            or (destinations >= n).any() or not np.isfinite(lengths).all()
            or (lengths <= 0).any()):
        raise ValueError("invalid surface adjacency graph")
    penalty = None if vertex_penalty is None else np.asarray(vertex_penalty, dtype=np.float64)
    if penalty is not None and (
        penalty.shape != (n,) or not np.isfinite(penalty).all() or (penalty < 0).any()
    ):
        raise ValueError("invalid surface penalty")
    for u in range(n):
        for k in range(int(offsets[u]), int(offsets[u + 1])):
            v = int(destinations[k])
            distance = float(np.linalg.norm(xyz[u] - xyz[v]))
            if abs(float(lengths[k]) - distance) > max(1e-5, distance * 1e-3):
                raise ValueError("surface graph edge length is inconsistent with coordinates")
    start_offsets = [float(np.linalg.norm(xyz[v] - p0)) for v in first]
    end_offsets = [float(np.linalg.norm(xyz[v] - p1)) for v in last]
    route = frame_surface_corridor.weighted_route(
        offsets, destinations, lengths, first, last,
        start_offsets=start_offsets, goal_offsets=end_offsets,
        allowed_mask=permitted, vertex_penalty=penalty
    )
    if route is None:
        raise NoValidSurfaceRoute("NO_VALID_SURFACE_ROUTE: no surface corridor between face anchors")
    ids = tuple(int(i) for i in route.vertex_indices)
    if not ids or ids[0] not in first or ids[-1] not in last:
        raise NoValidSurfaceRoute("NO_VALID_SURFACE_ROUTE: invalid anchored route")
    mid = xyz[list(ids)]
    full = np.vstack((p0[None], mid, p1[None]))
    # Remove coincident control samples, retaining endpoint coordinates.
    cleaned = [full[0]]
    for point in full[1:]:
        if np.linalg.norm(point - cleaned[-1]) > 1e-8:
            cleaned.append(point)
    full = np.asarray(cleaned, dtype=np.float64)
    length = float(np.linalg.norm(np.diff(full, axis=0), axis=1).sum())
    # The cost includes anchor transitions, but those must not be treated as
    # unconstrained Euclidean chords across unrelated surface triangles.
    return GeodesicSurfacePath(ids, full, length, float(route.cost), str(route.backend))
