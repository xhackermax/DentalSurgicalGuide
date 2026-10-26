"""Pure NumPy mesh-distance helpers used by DSG safety gates.

The fast Blender BVH sampler remains useful for interactive feedback.  This
module provides a deterministic triangle-pair distance kernel plus an exact
AABB broad phase that can be used as a slower confirmation verifier.

No bpy/mathutils imports live here so the geometry kernel can be unit tested
outside Blender.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
import math

import numpy as np

_EPS = 1.0e-12


@dataclass(frozen=True)
class MeshDistanceResult:
    distance: float
    source_point: tuple[float, float, float]
    target_point: tuple[float, float, float]
    source_triangle: int
    target_triangle: int
    candidate_pairs: int
    complete: bool


def _v3(x) -> np.ndarray:
    a = np.asarray(x, dtype=np.float64)
    if a.shape != (3,):
        raise ValueError("expected XYZ vector")
    return a


def closest_point_on_triangle(point, a, b, c):
    """Ericson closest-point-on-triangle, returning point and squared distance."""
    p, a, b, c = map(_v3, (point, a, b, c))
    ab = b - a; ac = c - a; ap = p - a
    d1 = float(np.dot(ab, ap)); d2 = float(np.dot(ac, ap))
    if d1 <= 0.0 and d2 <= 0.0:
        q = a
        return q, float(np.dot(p-q, p-q))
    bp = p - b
    d3 = float(np.dot(ab, bp)); d4 = float(np.dot(ac, bp))
    if d3 >= 0.0 and d4 <= d3:
        q = b
        return q, float(np.dot(p-q, p-q))
    vc = d1*d4 - d3*d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        v = d1 / max(d1 - d3, _EPS)
        q = a + v * ab
        return q, float(np.dot(p-q, p-q))
    cp = p - c
    d5 = float(np.dot(ab, cp)); d6 = float(np.dot(ac, cp))
    if d6 >= 0.0 and d5 <= d6:
        q = c
        return q, float(np.dot(p-q, p-q))
    vb = d5*d2 - d1*d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        w = d2 / max(d2 - d6, _EPS)
        q = a + w * ac
        return q, float(np.dot(p-q, p-q))
    va = d3*d6 - d5*d4
    if va <= 0.0 and (d4-d3) >= 0.0 and (d5-d6) >= 0.0:
        w = (d4-d3) / max((d4-d3)+(d5-d6), _EPS)
        q = b + w * (c-b)
        return q, float(np.dot(p-q, p-q))
    denom = 1.0 / max(va + vb + vc, _EPS)
    v = vb * denom; w = vc * denom
    q = a + ab*v + ac*w
    return q, float(np.dot(p-q, p-q))


def closest_points_segments(p1, q1, p2, q2):
    """Return closest points and squared distance between two finite 3D segments."""
    p1, q1, p2, q2 = map(_v3, (p1, q1, p2, q2))
    d1 = q1-p1; d2 = q2-p2; r = p1-p2
    a = float(np.dot(d1,d1)); e = float(np.dot(d2,d2)); f = float(np.dot(d2,r))
    if a <= _EPS and e <= _EPS:
        return p1, p2, float(np.dot(p1-p2,p1-p2))
    if a <= _EPS:
        s = 0.0; t = min(1.0, max(0.0, f/max(e,_EPS)))
    else:
        c = float(np.dot(d1,r))
        if e <= _EPS:
            t = 0.0; s = min(1.0, max(0.0, -c/max(a,_EPS)))
        else:
            b = float(np.dot(d1,d2)); denom = a*e-b*b
            s = 0.0 if abs(denom) <= _EPS else min(1.0, max(0.0, (b*f-c*e)/denom))
            t = (b*s+f)/e
            if t < 0.0:
                t = 0.0; s = min(1.0, max(0.0, -c/max(a,_EPS)))
            elif t > 1.0:
                t = 1.0; s = min(1.0, max(0.0, (b-c)/max(a,_EPS)))
    c1 = p1+d1*s; c2 = p2+d2*t
    return c1, c2, float(np.dot(c1-c2,c1-c2))


def _segment_triangle_hit(p0, p1, tri, eps=1.0e-10) -> bool:
    """Möller-Trumbore segment/triangle intersection."""
    p0 = _v3(p0); p1 = _v3(p1); a,b,c = np.asarray(tri,dtype=np.float64)
    direction = p1-p0
    e1 = b-a; e2 = c-a
    h = np.cross(direction,e2); det = float(np.dot(e1,h))
    if abs(det) <= eps:
        return False
    inv = 1.0/det; s=p0-a
    u=inv*float(np.dot(s,h))
    if u < -eps or u > 1.0+eps: return False
    q=np.cross(s,e1); v=inv*float(np.dot(direction,q))
    if v < -eps or u+v > 1.0+eps: return False
    t=inv*float(np.dot(e2,q))
    return -eps <= t <= 1.0+eps


def triangle_triangle_distance(tri_a, tri_b):
    """Exact Euclidean distance between two 3D triangles, with witness points."""
    A=np.asarray(tri_a,dtype=np.float64); B=np.asarray(tri_b,dtype=np.float64)
    if A.shape!=(3,3) or B.shape!=(3,3): raise ValueError("triangles must be (3,3)")
    edges=((0,1),(1,2),(2,0))
    for i,j in edges:
        if _segment_triangle_hit(A[i],A[j],B) or _segment_triangle_hit(B[i],B[j],A):
            # For an intersection, the exact witness is not needed by the clinical gate.
            return 0.0, A[i].copy(), A[i].copy()
    best2=math.inf; pa=None; pb=None
    for p in A:
        q,d2=closest_point_on_triangle(p,*B)
        if d2<best2: best2=d2; pa=p.copy(); pb=q.copy()
    for p in B:
        q,d2=closest_point_on_triangle(p,*A)
        if d2<best2: best2=d2; pa=q.copy(); pb=p.copy()
    for ia,ja in edges:
        for ib,jb in edges:
            qa,qb,d2=closest_points_segments(A[ia],A[ja],B[ib],B[jb])
            if d2<best2: best2=d2; pa=qa.copy(); pb=qb.copy()
    if best2 <= 1.0e-20: best2=0.0
    return math.sqrt(best2), pa, pb


def _aabb_distance2(min_a,max_a,min_b,max_b):
    delta=np.maximum(0.0, np.maximum(min_a-min_b, min_b-max_a))
    return float(np.dot(delta,delta))


def exact_mesh_surface_distance(source_triangles, target_triangles, *, upper_bound_mm: float,
                                max_candidate_pairs: int=1_500_000) -> MeshDistanceResult:
    """Compute exact triangle-surface distance using an AABB-safe broad phase.

    ``upper_bound_mm`` must be a real already-observed surface distance (the
    full-vertex BVH pass supplies it).  Any triangle pair able to beat that
    bound must have AABBs separated by at most the bound; the sweep below visits
    every such pair.  If the candidate budget is exceeded, ``complete`` is
    False and callers must *not* use the result as a hard safety pass.
    """
    A=np.asarray(source_triangles,dtype=np.float64); B=np.asarray(target_triangles,dtype=np.float64)
    if A.ndim!=3 or A.shape[1:]!=(3,3) or B.ndim!=3 or B.shape[1:]!=(3,3):
        raise ValueError("mesh triangles must have shape (N,3,3)")
    if len(A)==0 or len(B)==0: raise ValueError("empty triangle mesh")
    best=float(upper_bound_mm)
    if not math.isfinite(best) or best < 0.0: raise ValueError("upper_bound_mm must be finite and >=0")
    amin=A.min(axis=1); amax=A.max(axis=1); bmin=B.min(axis=1); bmax=B.max(axis=1)
    order=np.argsort(bmin[:,0],kind="mergesort")
    bminx=bmin[order,0].tolist()
    best_pair=(-1,-1); best_pa=np.zeros(3); best_pb=np.zeros(3); count=0
    eps=1.0e-10
    for ia in range(len(A)):
        # Any target with min-x above this cannot be within current best.
        right=bisect_right(bminx, float(amax[ia,0]+best+eps))
        minx=float(amin[ia,0]-best-eps)
        for pos in range(right):
            ib=int(order[pos])
            if float(bmax[ib,0]) < minx: continue
            if _aabb_distance2(amin[ia],amax[ia],bmin[ib],bmax[ib]) > (best+eps)*(best+eps):
                continue
            count += 1
            if count > int(max_candidate_pairs):
                return MeshDistanceResult(best, tuple(best_pa), tuple(best_pb), best_pair[0], best_pair[1], count, False)
            d,pa,pb=triangle_triangle_distance(A[ia],B[ib])
            if d < best:
                best=float(d); best_pair=(ia,ib); best_pa=np.asarray(pa); best_pb=np.asarray(pb)
                if best <= 1.0e-10:
                    return MeshDistanceResult(0.0, tuple(best_pa), tuple(best_pb), ia, ib, count, True)
    return MeshDistanceResult(best, tuple(best_pa), tuple(best_pb), best_pair[0], best_pair[1], count, True)
