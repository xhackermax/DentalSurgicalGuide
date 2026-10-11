"""Measure true planar cross-sections of a closed, evaluated Boolean mesh.

Pure NumPy, Blender-independent; closed triangular mesh in millimetres.
Unlike local ideal-circle contact approximations, these section properties
are computed from the *actual mesh*, including holes and multiple components.

It is a geometric diagnostic, NOT an automatic clinical safety gate or an
equivalent Euler-Bernoulli/torsion beam-material model of a merged guide.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np


class InvalidBooleanSection(ValueError):
    """Slice cannot be proven to be a closed section of the requested solid."""


@dataclass(frozen=True)
class BooleanSection:
    area_mm2: float
    centroid_uv_mm: tuple[float, float]
    inertia_uu_mm4: float
    inertia_vv_mm4: float
    inertia_uv_mm4: float
    principal_inertia_min_mm4: float
    principal_inertia_max_mm4: float
    perimeter_mm: float
    boundary_count: int
    hole_count: int
    global_component_count: int
    selected_component: int
    section_origin_mm: tuple[float, float, float]
    section_axis: tuple[float, float, float]
    backend: str = "ACTUAL_TRIANGULATED_BOOLEAN_MESH"


def _point_in_polygon(pt, polygon, tol=1e-10):
    x, y = map(float, pt)
    inside = False
    for a, b in zip(polygon, np.roll(polygon, -1, axis=0)):
        x0, y0 = map(float, a)
        x1, y1 = map(float, b)
        dx, dy = x1 - x0, y1 - y0
        area2 = (x - x0) * dy - (y - y0) * dx
        if abs(area2) < tol and min(x0, x1)-tol <= x <= max(x0,x1)+tol and min(y0,y1)-tol <= y <= max(y0,y1)+tol:
            raise InvalidBooleanSection("SECTION_PROBE_ON_BOUNDARY")
        if (y0 > y) != (y1 > y):
            crossing = x0 + (y-y0) * dx / dy
            if crossing > x:
                inside = not inside
    return inside


def _moments_uv(vertices):
    """Positive signed area, first and second area moments around UV origin."""
    p = np.asarray(vertices, dtype=float)
    q = np.roll(p, -1, axis=0)
    cross = p[:, 0]*q[:, 1]-q[:, 0]*p[:, 1]
    signed_area = float(np.sum(cross)/2)
    if abs(signed_area) <= 1e-12:
        raise InvalidBooleanSection("SECTION_DEGENERATE_LOOP")
    sign = 1.0 if signed_area > 0 else -1.0
    x0,y0,x1,y1=p[:,0],p[:,1],q[:,0],q[:,1]
    area=abs(signed_area)
    mx=sign*float(np.sum((x0+x1)*cross)/6)
    my=sign*float(np.sum((y0+y1)*cross)/6)
    iuu=sign*float(np.sum((y0*y0+y0*y1+y1*y1)*cross)/12)
    ivv=sign*float(np.sum((x0*x0+x0*x1+x1*x1)*cross)/12)
    iuv=sign*float(np.sum((2*x0*y0+x0*y1+x1*y0+2*x1*y1)*cross)/24)
    perimeter=float(np.linalg.norm(p-q, axis=1).sum())
    return area,mx,my,iuu,ivv,iuv,perimeter


def _closed_manifold(triangles, vertex_count):
    a=np.asarray(triangles,dtype=np.int64)
    if (a<0).any() or (a>=vertex_count).any() or len(a)==0:
        raise InvalidBooleanSection("SECTION_INVALID_TRIANGLES")
    if np.any((a[:,0]==a[:,1]) | (a[:,1]==a[:,2]) | (a[:,0]==a[:,2])):
        raise InvalidBooleanSection("SECTION_DEGENERATE_TRIANGLE")
    edges=np.sort(np.concatenate((a[:,[0,1]],a[:,[1,2]],a[:,[2,0]])),axis=1)
    _,counts=np.unique(edges,axis=0,return_counts=True)
    if not np.all(counts==2):
        raise InvalidBooleanSection("SECTION_NON_MANIFOLD_OR_OPEN_MESH")


def measure_boolean_section(
    vertices_mm, triangles, origin_mm, tangent,
    *, probe_point_mm, tolerance_mm=1e-5, require_closed=True,
    max_triangles=500_000,
) -> BooleanSection:
    """Compute the local actual mesh section containing an interior probe point.

    The triangulated mesh must be the *already Boolean-cut* guide. A probe
    identifies a particular connected section among multiple intersections.
    It must lie inside retained solid, never in a hole or on the boundary.
    Coplanar/vertex-tangent ambiguities fail closed rather than reporting area.
    """
    verts=np.asarray(vertices_mm,dtype=np.float64)
    faces=np.asarray(triangles,dtype=np.int64)
    orig=np.asarray(origin_mm,dtype=np.float64)
    axis=np.asarray(tangent,dtype=np.float64)
    probe=np.asarray(probe_point_mm,dtype=np.float64)
    if (verts.ndim!=2 or verts.shape[1]!=3 or faces.ndim!=2 or faces.shape[1]!=3
            or orig.shape!=(3,) or axis.shape!=(3,) or probe.shape!=(3,)
            or not np.isfinite(verts).all() or not np.isfinite(orig).all()
            or not np.isfinite(axis).all() or not np.isfinite(probe).all()):
        raise ValueError("SECTION_INPUT: require finite world-space geometry")
    if len(faces)>max_triangles:
        raise InvalidBooleanSection("SECTION_MESH_TOO_LARGE: resample or window the inspected mesh")
    tol=float(tolerance_mm)
    if not math.isfinite(tol) or tol<=0 or tol>0.05:
        raise ValueError("SECTION_TOLERANCE_INVALID")
    length=float(np.linalg.norm(axis))
    if length<=1e-12:
        raise ValueError("SECTION_AXIS_INVALID")
    axis=axis/length
    if abs(float(np.dot(probe-orig,axis)))>tol:
        raise InvalidBooleanSection("SECTION_PROBE_NOT_IN_PLANE")
    if require_closed:
        _closed_manifold(faces,len(verts))
    side=(verts-orig)@axis
    signed=side[faces]
    crosses=(np.min(signed,axis=1)<-tol)&(np.max(signed,axis=1)>tol)
    border=(np.min(signed,axis=1)<=tol)&(np.max(signed,axis=1)>=-tol)
    if np.any(border & np.any(np.abs(signed)<=tol,axis=1)):
        raise InvalidBooleanSection("SECTION_COPLANAR_OR_VERTEX_TOUCH: shift section point")
    hits=faces[crosses]
    if not len(hits):
        raise InvalidBooleanSection("SECTION_NO_INTERSECTION")
    ref=np.array([0.,0.,1.]) if abs(axis[2])<0.85 else np.array([0.,1.,0.])
    u=np.cross(ref,axis)
    u/=np.linalg.norm(u)
    v=np.cross(axis,u)
    pts3=verts[hits]
    ds=side[hits]
    pieces=[]
    for edge0,edge1 in ((0,1),(1,2),(2,0)):
        a=ds[:,edge0];b=ds[:,edge1]
        active=(a*b<0)
        if not active.any():
            continue
        t=a[active]/(a[active]-b[active])
        points=pts3[active,edge0,:] + t[:,None]*(pts3[active,edge1,:]-pts3[active,edge0,:])
        ids=np.flatnonzero(active)
        pieces.append((ids, np.stack(((points-orig)@u, (points-orig)@v),axis=1)))
    per_triangle=[[] for _ in range(len(hits))]
    for ids,points in pieces:
        for i,p in zip(ids,points):
            per_triangle[int(i)].append(p)
    # Mesh triangle sections form two endpoints per intersected triangle.
    if any(len(pair)!=2 for pair in per_triangle):
        raise InvalidBooleanSection("SECTION_AMBIGUOUS_TRIANGLE_INTERSECTION")
    keys={}
    locations=[]
    graph={}
    def identify(p):
        key=tuple(np.rint(p/tol).astype(np.int64))
        if key not in keys:
            keys[key]=len(locations)
            locations.append(np.asarray(p,dtype=float))
        else:
            if float(np.linalg.norm(locations[keys[key]]-p))>2*tol:
                raise InvalidBooleanSection("SECTION_SNAP_COLLISION")
        return keys[key]
    for pair in per_triangle:
        i,j=identify(pair[0]),identify(pair[1])
        if i==j:
            raise InvalidBooleanSection("SECTION_ZERO_EDGE")
        graph.setdefault(i,[]).append(j)
        graph.setdefault(j,[]).append(i)
    if any(len(adj)!=2 or len(set(adj))!=2 for adj in graph.values()):
        raise InvalidBooleanSection("SECTION_OPEN_OR_NONMANIFOLD_CONTOUR")
    visited=set()
    loops=[]
    for start in sorted(graph):
        if start in visited:
            continue
        route=[start]
        previous=-1
        current=start
        for _ in range(len(graph)+1):
            visited.add(current)
            next_id=graph[current][0] if graph[current][0]!=previous else graph[current][1]
            if next_id==start:
                break
            if next_id in route:
                raise InvalidBooleanSection("SECTION_SELF_INTERSECTING_CONTOUR")
            route.append(next_id)
            previous,current=current,next_id
        else:
            raise InvalidBooleanSection("SECTION_UNCLOSED_CONTOUR")
        if len(route)<3:
            raise InvalidBooleanSection("SECTION_TOO_FEW_POINTS")
        loops.append(np.array([locations[i] for i in route],dtype=float))
    if len(visited)!=len(graph):
        raise InvalidBooleanSection("SECTION_UNUSED_CONTOUR_NODES")
    moments=[_moments_uv(poly) for poly in loops]
    parents=[]
    for i,poly in enumerate(loops):
        vertex=poly[0]
        candidates=[j for j,outer in enumerate(loops)
            if i!=j and moments[j][0]>moments[i][0] and _point_in_polygon(vertex,outer)]
        parents.append(min(candidates,key=lambda j:moments[j][0]) if candidates else None)
    def root_of(i):
        seen=set()
        while parents[i] is not None:
            if i in seen: raise InvalidBooleanSection("SECTION_NESTING_CYCLE")
            seen.add(i)
            i=parents[i]
        return i
    roots=sorted(i for i,parent in enumerate(parents) if parent is None)
    selected=[]
    p_uv=np.array([float((probe-orig)@u),float((probe-orig)@v)])
    for root in roots:
        if _point_in_polygon(p_uv,loops[root]):
            selected.append(root)
    if len(selected)!=1:
        raise InvalidBooleanSection("SECTION_PROBE_AMBIGUOUS_OR_OUTSIDE")
    root=selected[0]
    # Inside the chosen component iff the point is enclosed by an odd number
    # of its nested boundaries (outer plus any holes/islands).
    containing=[i for i in range(len(loops))
        if root_of(i)==root and _point_in_polygon(p_uv,loops[i])]
    if len(containing)%2==0:
        raise InvalidBooleanSection("SECTION_PROBE_INSIDE_VOID")
    material=[i for i in range(len(loops)) if root_of(i)==root]
    def relative_depth(i):
        depth=0
        while parents[i] is not None:
            i=parents[i]; depth+=1
        return depth
    accum=np.zeros(7,dtype=float)
    holes=0
    for i in material:
        depth=relative_depth(i)
        sign=1 if depth%2==0 else -1
        if sign<0: holes+=1
        accum+=sign*np.asarray(moments[i])
    area,mx,my,iuu,ivv,iuv,perimeter=accum
    if area<=tol*tol:
        raise InvalidBooleanSection("SECTION_NONPOSITIVE_AREA")
    cx,cy=mx/area,my/area
    iuu=float(iuu-area*cy*cy)
    ivv=float(ivv-area*cx*cx)
    iuv=float(iuv-area*cx*cy)
    eigen=np.linalg.eigvalsh(np.array([[iuu,-iuv],[-iuv,ivv]]))
    if eigen[0]<=tol**4:
        raise InvalidBooleanSection("SECTION_DEGENERATE_BENDING_INERTIA")
    return BooleanSection(
        area_mm2=float(area), centroid_uv_mm=(float(cx),float(cy)),
        inertia_uu_mm4=iuu, inertia_vv_mm4=ivv, inertia_uv_mm4=iuv,
        principal_inertia_min_mm4=float(eigen[0]),
        principal_inertia_max_mm4=float(eigen[1]),
        perimeter_mm=float(sum(moments[i][6] for i in material)),
        boundary_count=len(material), hole_count=holes,
        global_component_count=len(roots), selected_component=roots.index(root),
        section_origin_mm=tuple(map(float,orig)),
        section_axis=tuple(map(float,axis)),
    )
