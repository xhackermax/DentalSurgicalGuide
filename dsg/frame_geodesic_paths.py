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
