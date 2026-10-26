"""DSG surface-corridor routing helpers.

Pure NumPy/SciPy geometry code. No bpy imports.

The frame contour is not treated as a globally shortest edge path. Instead we:
1) build an intrinsic semantic corridor around projected contour samples,
2) optimize a weighted route inside that corridor (intent + clearance + curvature),
3) optionally straighten the selected homotopy class with potpourri3d/geometry-central,
4) otherwise return a stable graph route for continuous projection/curve-shortening
   in the Blender adapter.

This module deliberately has no clinical thresholds. Those live in guide_module.py.
"""
from __future__ import annotations

import logging as _dsg_logging
_DSG_LOG = _dsg_logging.getLogger(__name__)

from dataclasses import dataclass
import heapq
from typing import Sequence

import numpy as np

try:
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import dijkstra as scipy_dijkstra
    _HAVE_SCIPY = True
except Exception:  # pragma: no cover
    csr_matrix = None
    scipy_dijkstra = None
    _HAVE_SCIPY = False


@dataclass(frozen=True)
class CorridorRoute:
    vertex_indices: list[int]
    cost: float
    backend: str
    allowed_vertices: int
    corridor_radius_mm: float
    semantic_distance_mm: np.ndarray | None = None


def _graph_from_csr(offsets, dst, weights, n_vertices: int):
    if not _HAVE_SCIPY:
        return None
    return csr_matrix(
        (np.asarray(weights, dtype=np.float64),
         np.asarray(dst, dtype=np.int32),
         np.asarray(offsets, dtype=np.int64)),
        shape=(int(n_vertices), int(n_vertices)),
        copy=False,
    )


def multisource_intrinsic_distance(offsets, dst, weights, seeds: Sequence[int], n_vertices: int,
                                   *, limit_mm: float | None = None) -> np.ndarray:
    """Distance to the nearest seed on the mesh-edge graph.

    SciPy's compiled CSR implementation is preferred. A bounded heap fallback is
    retained so the add-on never depends on SciPy merely for corridor creation.
    """
    seeds = sorted({int(s) for s in seeds if 0 <= int(s) < int(n_vertices)})
    out = np.full(int(n_vertices), np.inf, dtype=np.float64)
    if not seeds:
        return out

    if _HAVE_SCIPY:
        graph = _graph_from_csr(offsets, dst, weights, n_vertices)
        try:
            # min_only avoids an n_sources x n_vertices matrix.
            kwargs = dict(directed=True, indices=np.asarray(seeds, dtype=np.int32),
                          return_predecessors=False, min_only=True)
            if limit_mm is not None and np.isfinite(float(limit_mm)):
                kwargs["limit"] = float(limit_mm)
            dist = scipy_dijkstra(graph, **kwargs)
            return np.asarray(dist, dtype=np.float64)
        except TypeError:
            # Older SciPy without min_only. Seed count is intentionally small.
            dist = scipy_dijkstra(graph, directed=True,
                                  indices=np.asarray(seeds, dtype=np.int32),
                                  return_predecessors=False)
            if np.ndim(dist) == 2:
                dist = np.min(dist, axis=0)
            dist = np.asarray(dist, dtype=np.float64)
            if limit_mm is not None:
                dist[dist > float(limit_mm)] = np.inf
            return dist
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

    offsets = np.asarray(offsets)
    dst = np.asarray(dst)
    weights = np.asarray(weights)
    heap: list[tuple[float, int]] = []
    for s in seeds:
        out[s] = 0.0
        heapq.heappush(heap, (0.0, s))
    bound = float(limit_mm) if limit_mm is not None else float("inf")
    while heap:
        d, u = heapq.heappop(heap)
        if d != out[u]:
            continue
        if d > bound:
            break
        for pos in range(int(offsets[u]), int(offsets[u + 1])):
            v = int(dst[pos])
            nd = d + float(weights[pos])
            if nd <= bound and nd + 1e-12 < out[v]:
                out[v] = nd
                heapq.heappush(heap, (nd, v))
    return out


def curvature_proxy(normals: np.ndarray, offsets, dst, src_indices: np.ndarray | None = None) -> np.ndarray:
    """Dimensionless local normal variation, vectorized over directed edges."""
    normals = np.asarray(normals, dtype=np.float64)
    n_vertices = normals.shape[0]
    offsets = np.asarray(offsets, dtype=np.int64)
    dst = np.asarray(dst, dtype=np.int32)
    if src_indices is None:
        src = np.repeat(np.arange(n_vertices, dtype=np.int32), np.diff(offsets))
    else:
        src = np.asarray(src_indices, dtype=np.int32)
        if src.shape != dst.shape:
            raise ValueError("src_indices shape mismatch")
    if src.size == 0:
        return np.zeros(n_vertices, dtype=np.float64)
    dots = np.abs(np.einsum("ij,ij->i", normals[src], normals[dst]))
    variation = 1.0 - np.clip(dots, 0.0, 1.0)
    sums = np.bincount(src, weights=variation, minlength=n_vertices).astype(np.float64, copy=False)
    counts = np.bincount(src, minlength=n_vertices).astype(np.float64, copy=False)
    out = np.zeros(n_vertices, dtype=np.float64)
    valid = counts > 0
    out[valid] = sums[valid] / counts[valid]
    return out


def weighted_route(offsets, dst, base_lengths, start_candidates: Sequence[int], goal_candidates: Sequence[int],
                   *, start_offsets: Sequence[float] | None = None,
                   goal_offsets: Sequence[float] | None = None,
                   allowed_mask: np.ndarray | None = None,
                   vertex_penalty: np.ndarray | None = None,
                   src_indices: np.ndarray | None = None) -> CorridorRoute | None:
    """Minimum weighted graph route with face-anchor endpoint candidates.

    Multiple endpoint candidates let a continuous surface anchor depart via any
    vertex of its containing triangle instead of being snapped irrevocably to one
    triangulation vertex.
    """
    offsets = np.asarray(offsets, dtype=np.int64)
    dst = np.asarray(dst, dtype=np.int32)
    lengths = np.asarray(base_lengths, dtype=np.float64)
    n_vertices = len(offsets) - 1

    starts = [int(v) for v in start_candidates if 0 <= int(v) < n_vertices]
    goals = [int(v) for v in goal_candidates if 0 <= int(v) < n_vertices]
    if not starts or not goals:
        return None

    allowed = np.ones(n_vertices, dtype=bool) if allowed_mask is None else np.asarray(allowed_mask, dtype=bool).copy()
    for v in starts + goals:
        allowed[v] = True

    penalty = np.zeros(n_vertices, dtype=np.float64) if vertex_penalty is None else np.asarray(vertex_penalty, dtype=np.float64)
    penalty = np.maximum(penalty, 0.0)

    # Edge penalty is trapezoidal in the endpoint scalar field.
    if src_indices is None:
        src = np.repeat(np.arange(n_vertices, dtype=np.int32), np.diff(offsets))
    else:
        src = np.asarray(src_indices, dtype=np.int32)
        if src.shape != dst.shape:
            raise ValueError("src_indices shape mismatch")
    weighted = lengths * (1.0 + 0.5 * (penalty[src] + penalty[dst]))

    global_indices = np.flatnonzero(allowed).astype(np.int32, copy=False)
    if global_indices.size < 2:
        return None
    remap = np.full(n_vertices, -1, dtype=np.int32)
    remap[global_indices] = np.arange(global_indices.size, dtype=np.int32)
    local_starts = np.array([remap[v] for v in starts if remap[v] >= 0], dtype=np.int32)
    local_goals = np.array([remap[v] for v in goals if remap[v] >= 0], dtype=np.int32)
    if local_starts.size == 0 or local_goals.size == 0:
        return None

    so = np.zeros(len(starts), dtype=np.float64) if start_offsets is None else np.asarray(start_offsets, dtype=np.float64)
    go = np.zeros(len(goals), dtype=np.float64) if goal_offsets is None else np.asarray(goal_offsets, dtype=np.float64)
    if len(so) != len(starts) or len(go) != len(goals):
        raise ValueError("endpoint offset length mismatch")

    # Construct global CSR once from weighted data then slice in C/SciPy.
    if _HAVE_SCIPY:
        graph = csr_matrix((weighted, dst, offsets), shape=(n_vertices, n_vertices), copy=False)
        local_graph = graph[global_indices][:, global_indices].tocsr()
        try:
            dist, pred = scipy_dijkstra(local_graph, directed=True,
                                        indices=local_starts,
                                        return_predecessors=True)
            dist = np.atleast_2d(np.asarray(dist, dtype=np.float64))
            pred = np.atleast_2d(np.asarray(pred, dtype=np.int64))
            best = None
            for srow, sv in enumerate(starts):
                for gj, gv in enumerate(goals):
                    gl = int(remap[gv])
                    val = float(so[srow] + dist[srow, gl] + go[gj])
                    if np.isfinite(val) and (best is None or val < best[0]):
                        best = (val, srow, gj, gl)
            if best is None:
                return None
            value, srow, gj, current = best
            start_local = int(local_starts[srow])
            route_local = [int(current)]
            guard = 0
            while current != start_local:
                previous = int(pred[srow, current])
                if previous < 0 or previous == current:
                    return None
                route_local.append(previous)
                current = previous
                guard += 1
                if guard > int(local_graph.shape[0]) + 2:
                    return None
            route_local.reverse()
            route = [int(global_indices[i]) for i in route_local]
            return CorridorRoute(route, float(value), "SCIPY_WEIGHTED_CORRIDOR",
                                 int(global_indices.size), 0.0)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)

    # Python multi-source fallback. Initial distances contain exact anchor->vertex offsets.
    best_dist = np.full(n_vertices, np.inf, dtype=np.float64)
    parent = np.full(n_vertices, -1, dtype=np.int32)
    heap: list[tuple[float, int]] = []
    for i, s in enumerate(starts):
        d = float(so[i])
        if d < best_dist[s]:
            best_dist[s] = d
            heapq.heappush(heap, (d, s))
    goal_set = set(goals)
    best_goal = None
    best_total = float("inf")
    while heap:
        d, u = heapq.heappop(heap)
        if d != best_dist[u]:
            continue
        if d >= best_total:
            break
        if u in goal_set:
            gj = goals.index(u)
            total = d + float(go[gj])
            if total < best_total:
                best_total = total
                best_goal = u
        for pos in range(int(offsets[u]), int(offsets[u + 1])):
            v = int(dst[pos])
            if not allowed[v]:
                continue
            nd = d + float(weighted[pos])
            if nd + 1e-12 < best_dist[v]:
                best_dist[v] = nd
                parent[v] = u
                heapq.heappush(heap, (nd, v))
    if best_goal is None:
        return None
    route = [int(best_goal)]
    current = int(best_goal)
    while parent[current] >= 0:
        current = int(parent[current])
        route.append(current)
    route.reverse()
    return CorridorRoute(route, float(best_total), "PYTHON_WEIGHTED_CORRIDOR",
                         int(np.count_nonzero(allowed)), 0.0)


def resample_polyline(points: np.ndarray, spacing_mm: float) -> np.ndarray:
    pts = np.asarray(points, dtype=np.float64)
    if len(pts) <= 1:
        return pts.copy()
    spacing = max(1e-4, float(spacing_mm))
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    cumulative = np.concatenate(([0.0], np.cumsum(seg)))
    total = float(cumulative[-1])
    if total <= 1e-9:
        return pts[[0]].copy()
    count = max(2, int(np.ceil(total / spacing)) + 1)
    samples = np.linspace(0.0, total, count)
    out = np.empty((count, 3), dtype=np.float64)
    j = 0
    for i, s in enumerate(samples):
        while j + 1 < len(cumulative) and cumulative[j + 1] < s:
            j += 1
        if j + 1 >= len(cumulative):
            out[i] = pts[-1]
            continue
        den = cumulative[j + 1] - cumulative[j]
        t = 0.0 if den <= 1e-12 else (s - cumulative[j]) / den
        out[i] = (1.0 - t) * pts[j] + t * pts[j + 1]
    return out



def try_potpourri_heat_distance(vertices: np.ndarray, faces: np.ndarray, seeds: Sequence[int], solver=None):
    """Optional robust intrinsic heat distance. Returns (dist, solver, backend, error)."""
    try:
        import potpourri3d as pp3d
    except Exception as exc:
        return None, solver, "", f"potpourri3d unavailable: {exc}"
    try:
        if solver is None:
            solver = pp3d.MeshHeatMethodDistanceSolver(
                np.asarray(vertices, dtype=np.float64),
                np.asarray(faces, dtype=np.int32),
                use_robust=True,
            )
        clean = sorted({int(v) for v in seeds if 0 <= int(v) < len(vertices)})
        if not clean:
            return None, solver, "", "no heat seeds"
        dist = solver.compute_distance_multisource(clean)
        dist = np.asarray(dist, dtype=np.float64)
        if dist.shape != (len(vertices),):
            return None, solver, "", "unexpected heat-distance shape"
        return dist, solver, "POTPOURRI_HEAT", ""
    except Exception as exc:
        return None, solver, "", f"potpourri3d heat failed: {type(exc).__name__}: {exc}"

def try_potpourri_edgeflip(vertices: np.ndarray, faces: np.ndarray,
                            route_vertices: Sequence[int], allowed_mask: np.ndarray | None = None,
                            *, max_controls: int = 16) -> tuple[np.ndarray | None, str]:
    """Optional continuous path straightening via geometry-central edge flips.

    The weighted route supplies the homotopy class. `find_geodesic_path_poly()`
    receives sparse control vertices from that route so it does not replace the
    clinician-selected corridor with an unrelated global shortest path.
    """
    try:
        import potpourri3d as pp3d
    except Exception as exc:  # optional dependency
        return None, f"potpourri3d unavailable: {exc}"

    V = np.asarray(vertices, dtype=np.float64)
    F = np.asarray(faces, dtype=np.int32)
    route = [int(v) for v in route_vertices]
    if len(route) < 2 or len(F) < 1:
        return None, "insufficient route/triangles"

    try:
        if allowed_mask is None:
            keep_v = np.ones(len(V), dtype=bool)
        else:
            keep_v = np.asarray(allowed_mask, dtype=bool)
        keep_f = np.all(keep_v[F], axis=1)
        subF_global = F[keep_f]
        used = np.unique(subF_global)
        if used.size < 3 or len(subF_global) < 1:
            return None, "empty corridor submesh"
        remap = np.full(len(V), -1, dtype=np.int32)
        remap[used] = np.arange(len(used), dtype=np.int32)
        subV = V[used]
        subF = remap[subF_global]

        # Controls sample the weighted path, preserving its route class.
        n_controls = min(max(2, int(max_controls)), len(route))
        pick = np.unique(np.linspace(0, len(route) - 1, n_controls).round().astype(int))
        controls_global = [route[i] for i in pick]
        controls_local = [int(remap[g]) for g in controls_global if 0 <= int(remap[g]) < len(subV)]
        if len(controls_local) < 2:
            return None, "route controls outside corridor submesh"

        solver = pp3d.EdgeFlipGeodesicSolver(subV, subF)
        pts = solver.find_geodesic_path_poly(controls_local, max_iterations=80,
                                             max_relative_length_decrease=0.55)
        pts = np.asarray(pts, dtype=np.float64)
        if pts.ndim != 2 or pts.shape[0] < 2 or pts.shape[1] != 3:
            return None, "edge-flip solver returned invalid path"
        return pts, "POTPOURRI_EDGEFLIP"
    except Exception as exc:
        return None, f"potpourri3d edgeflip failed: {type(exc).__name__}: {exc}"
