"""Pure NumPy mesh analysis for the guide export gate.

No ``bpy`` import: every function takes plain arrays so it can be unit-tested
in CPython and reused by workers. Geometry is expected in millimetres.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from .policy import ExportPolicy


# ── Result objects ──────────────────────────────────────────────────────────
@dataclass(frozen=True)
class CheckResult:
    """Outcome of one quality check.

    ``status`` is ``PASS``, ``WARN``, ``FAIL`` or ``SKIPPED``. ``blocking`` is
    True only for a FAIL that must cancel the export under the active policy.
    """

    name: str
    status: str
    message: str
    blocking: bool = False
    metrics: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "message": self.message,
                "blocking": self.blocking, "metrics": dict(self.metrics)}


class RayCaster(Protocol):
    """Abstraction over a ray/mesh intersection engine (BVH in Blender)."""

    def cast(self, origins: np.ndarray, directions: np.ndarray, max_distance: float
             ) -> tuple[np.ndarray, np.ndarray]:
        """Return ``(distances, hit_normals)``; ``distances`` is ``inf`` on miss."""
        ...


# ── Helpers ─────────────────────────────────────────────────────────────────
def _as_mesh(vertices, triangles) -> tuple[np.ndarray, np.ndarray]:
    v = np.asarray(vertices, dtype=np.float64).reshape(-1, 3)
    t = np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
    if t.size and (t.min() < 0 or t.max() >= len(v)):
        raise ValueError("triangle index out of range")
    return v, t


def triangle_normals_and_areas(vertices, triangles) -> tuple[np.ndarray, np.ndarray]:
    v, t = _as_mesh(vertices, triangles)
    cross = np.cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]])
    norm = np.linalg.norm(cross, axis=1)
    safe = np.where(norm > 0.0, norm, 1.0)
    return cross / safe[:, None], 0.5 * norm


# ── 1. Closed solid (2-manifold) ────────────────────────────────────────────
def manifold_report(vertices, triangles, policy: ExportPolicy = ExportPolicy()) -> CheckResult:
    """Every undirected edge must be shared by exactly two triangles, and the
    two uses must have opposite orientation (consistent normals)."""
    v, t = _as_mesh(vertices, triangles)
    if len(t) == 0:
        return CheckResult("closed_solid", "FAIL", "Empty mesh", blocking=True)
    directed = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
    undirected = np.sort(directed, axis=1)
    keys, inverse, counts = np.unique(undirected, axis=0, return_inverse=True, return_counts=True)
    inverse = inverse.reshape(-1)
    boundary_edges = int(np.count_nonzero(counts == 1))
    nonmanifold_edges = int(np.count_nonzero(counts > 2))
    # Orientation: for 2-use edges, the directed copies must be opposite.
    forward = (directed[:, 0] < directed[:, 1]).astype(np.int64)
    forward_per_edge = np.bincount(inverse, weights=forward, minlength=len(keys))
    two_use = counts == 2
    flipped_edges = int(np.count_nonzero(two_use & (forward_per_edge != 1)))
    _normals, areas = triangle_normals_and_areas(v, t)
    degenerate = int(np.count_nonzero(areas <= policy.degenerate_area_mm2))
    metrics = {"triangles": int(len(t)), "edges": int(len(keys)), "boundary_edges": boundary_edges,
               "nonmanifold_edges": nonmanifold_edges, "inconsistent_orientation_edges": flipped_edges,
               "degenerate_triangles": degenerate}
    problems = boundary_edges + nonmanifold_edges + flipped_edges
    if problems == 0 and degenerate == 0:
        return CheckResult("closed_solid", "PASS", "Closed, consistently oriented solid", metrics=metrics)
    if problems == 0:
        return CheckResult("closed_solid", "WARN", f"{degenerate} degenerate triangle(s)", metrics=metrics)
    msg = (f"Not a closed solid: {boundary_edges} open edge(s), {nonmanifold_edges} non-manifold, "
           f"{flipped_edges} flipped")
    return CheckResult("closed_solid", "FAIL", msg, blocking=policy.block_non_manifold, metrics=metrics)


def signed_volume_mm3(vertices, triangles) -> float:
    v, t = _as_mesh(vertices, triangles)
    if len(t) == 0:
        return 0.0
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


# ── 2. Connected components / islands ───────────────────────────────────────
def connected_components(n_vertices: int, triangles) -> np.ndarray:
    """Vertex component labels via vectorised label propagation + pointer jumping."""
    t = np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
    labels = np.arange(int(n_vertices), dtype=np.int64)
    if len(t) == 0:
        return labels
    a = np.concatenate([t[:, 0], t[:, 1], t[:, 2]])
    b = np.concatenate([t[:, 1], t[:, 2], t[:, 0]])
    while True:
        m = np.minimum(labels[a], labels[b])
        new = labels.copy()
        np.minimum.at(new, a, m)
        np.minimum.at(new, b, m)
        new = new[new]
        while True:  # pointer jumping to the root
            jumped = new[new]
            if np.array_equal(jumped, new):
                break
            new = jumped
        if np.array_equal(new, labels):
            return labels
        labels = new


@dataclass(frozen=True)
class Island:
    faces: int
    volume_mm3: float
    area_mm2: float


def islands(vertices, triangles) -> list[Island]:
    """Connected shells sorted largest first (by face count, then area)."""
    v, t = _as_mesh(vertices, triangles)
    if len(t) == 0:
        return []
    labels = connected_components(len(v), t)[t[:, 0]]
    _n, areas = triangle_normals_and_areas(v, t)
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    vol = np.einsum("ij,ij->i", a, np.cross(b, c)) / 6.0
    _uniq, idx = np.unique(labels, return_inverse=True)
    idx = idx.reshape(-1)
    faces = np.bincount(idx)
    volumes = np.bincount(idx, weights=vol)
    area_sum = np.bincount(idx, weights=areas)
    result = [Island(int(f), float(v_), float(a)) for f, v_, a in zip(faces, volumes, area_sum)]
    return sorted(result, key=lambda i: (i.faces, i.area_mm2), reverse=True)


def island_removal_decision(found: list[Island], policy: ExportPolicy = ExportPolicy()) -> CheckResult:
    """Decide whether dropping every island except the largest is safe to do
    automatically. A large detached piece (e.g. a sleeve that lost its
    connector) must never be deleted silently."""
    if len(found) <= 1:
        return CheckResult("islands", "PASS", "Single connected piece", metrics={"islands": len(found)})
    removed = found[1:]
    big = [i for i in removed
           if abs(i.volume_mm3) > policy.max_auto_remove_island_mm3 or i.faces > policy.max_auto_remove_island_faces]
    metrics = {"islands": len(found), "removed_islands": len(removed),
               "removed_faces": int(sum(i.faces for i in removed)),
               "largest_removed_volume_mm3": float(max(abs(i.volume_mm3) for i in removed)),
               "significant_islands": len(big)}
    if big:
        return CheckResult(
            "islands", "FAIL",
            f"{len(big)} significant detached piece(s) (up to {metrics['largest_removed_volume_mm3']:.2f} mm³) "
            "would be deleted; review the guide or confirm removal explicitly",
            blocking=True, metrics=metrics)
    return CheckResult("islands", "WARN", f"{len(removed)} small debris island(s) removed", metrics=metrics)


# ── 3. Wall thickness ───────────────────────────────────────────────────────
def _sample_faces(areas: np.ndarray, max_samples: int, seed: int = 0) -> np.ndarray:
    n = len(areas)
    if n <= max_samples:
        return np.arange(n)
    total = areas.sum()
    p = areas / total if total > 0 else None
    return np.sort(np.random.default_rng(seed).choice(n, size=max_samples, replace=False, p=p))


def wall_thickness_report(vertices, triangles, caster: RayCaster,
                          policy: ExportPolicy = ExportPolicy()) -> CheckResult:
    """Shoot a ray from each sampled face centroid along its inward normal;
    the distance to the opposite wall is the local thickness."""
    v, t = _as_mesh(vertices, triangles)
    normals, areas = triangle_normals_and_areas(v, t)
    valid = np.flatnonzero(areas > policy.degenerate_area_mm2)
    if len(valid) == 0:
        return CheckResult("wall_thickness", "SKIPPED", "No valid faces")
    idx = valid[_sample_faces(areas[valid], policy.thickness_max_samples)]
    centroids = v[t[idx]].mean(axis=1)
    inward = -normals[idx]
    origins = centroids + inward * policy.thickness_ray_epsilon_mm
    dist, hit_normals = caster.cast(origins, inward, policy.thickness_max_distance_mm)
    dist = np.asarray(dist, dtype=np.float64)
    hit_normals = np.asarray(hit_normals, dtype=np.float64).reshape(-1, 3)
    # A valid opposite wall faces away from the ray origin (back face).
    ok = np.isfinite(dist) & (np.einsum("ij,ij->i", hit_normals, inward) > 0.0)
    thickness = dist[ok] + policy.thickness_ray_epsilon_mm
    if thickness.size == 0:
        return CheckResult("wall_thickness", "SKIPPED", "No opposite wall found (open mesh?)",
                           metrics={"samples": int(len(idx))})
    thin = thickness < policy.min_wall_thickness_mm
    thin_fraction = float(thin.mean())
    order = np.argsort(dist[ok])[:5]
    metrics = {
        "samples": int(len(idx)), "measured": int(thickness.size),
        "min_mm": float(thickness.min()), "p01_mm": float(np.percentile(thickness, 1)),
        "p05_mm": float(np.percentile(thickness, 5)), "median_mm": float(np.median(thickness)),
        "threshold_mm": float(policy.min_wall_thickness_mm), "below_threshold_fraction": thin_fraction,
        "thinnest_points_mm": [list(map(float, p)) for p in centroids[ok][order]],
    }
    if thin_fraction > policy.thin_wall_warn_fraction:
        msg = (f"{thin_fraction * 100:.2f}% of sampled walls are thinner than "
               f"{policy.min_wall_thickness_mm:.2f} mm (min {metrics['min_mm']:.2f} mm)")
        status = "FAIL" if policy.block_thin_walls else "WARN"
        return CheckResult("wall_thickness", status, msg, blocking=policy.block_thin_walls, metrics=metrics)
    return CheckResult("wall_thickness", "PASS",
                       f"Walls ≥ {policy.min_wall_thickness_mm:.2f} mm (p1 {metrics['p01_mm']:.2f} mm)",
                       metrics=metrics)


# ── 4. Reference ray caster (pure NumPy; tests and small meshes) ────────────
class NumpyRayCaster:
    """Brute-force Möller–Trumbore ray caster. O(rays × triangles): use only
    for tests or small meshes; Blender uses a BVH (see blender_adapter)."""

    def __init__(self, vertices, triangles, chunk: int = 256):
        self.v, self.t = _as_mesh(vertices, triangles)
        self.normals, _ = triangle_normals_and_areas(self.v, self.t)
        self.chunk = int(chunk)

    def cast(self, origins, directions, max_distance):
        o = np.asarray(origins, dtype=np.float64).reshape(-1, 3)
        d = np.asarray(directions, dtype=np.float64).reshape(-1, 3)
        v0, v1, v2 = self.v[self.t[:, 0]], self.v[self.t[:, 1]], self.v[self.t[:, 2]]
        e1, e2 = v1 - v0, v2 - v0
        out_d = np.full(len(o), np.inf)
        out_n = np.zeros((len(o), 3))
        for s in range(0, len(o), self.chunk):
            oo, dd = o[s:s + self.chunk, None, :], d[s:s + self.chunk, None, :]
            p = np.cross(dd, e2[None])
            det = np.einsum("rtk,tk->rt", p, e1)
            with np.errstate(divide="ignore", invalid="ignore"):
                inv = 1.0 / det
                tv = oo - v0[None]
                u = np.einsum("rtk,rtk->rt", tv, p) * inv
                q = np.cross(tv, e1[None])
                w = np.einsum("rtk,rtk->rt", dd, q) * inv
                dist = np.einsum("tk,rtk->rt", e2, q) * inv
                hit = (np.abs(det) > 1e-12) & (u >= 0) & (w >= 0) & (u + w <= 1) & (dist > 0) & (dist <= max_distance)
            dist = np.where(hit, dist, np.inf)
            best = dist.argmin(axis=1)
            rows = np.arange(len(best))
            out_d[s:s + self.chunk] = dist[rows, best]
            out_n[s:s + self.chunk] = self.normals[best]
        return out_d, out_n


# ── 5. Point-set clearance (implant ↔ anatomy) ──────────────────────────────
def clearance_status(name: str, distance_mm: float | None, minimum_mm: float, *,
                     intersects: bool = False, method: str = "") -> CheckResult:
    metrics = {"distance_mm": distance_mm, "required_mm": float(minimum_mm),
               "intersects": bool(intersects), "method": method}
    if distance_mm is None:
        return CheckResult(name, "SKIPPED", "Not measured", metrics=metrics)
    if intersects or distance_mm < minimum_mm:
        return CheckResult(name, "WARN",
                           f"{'INTERSECTS' if intersects else f'{distance_mm:.2f} mm'} < {minimum_mm:.2f} mm required",
                           metrics=metrics)
    return CheckResult(name, "PASS", f"{distance_mm:.2f} mm ≥ {minimum_mm:.2f} mm", metrics=metrics)
