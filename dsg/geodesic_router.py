"""Deterministic surface alternatives, delegating to DSG's existing CSR router."""
from dataclasses import dataclass
import hashlib
import numpy as np
from .ios_surface import validate_anchor,_readonly
from . import frame_geodesic_paths as paths
from .frame_swept_clearance_core import SphereKeepOut,CylinderKeepOut,check_swept_tube_clearance


@dataclass(frozen=True)
class CandidatePath:
    route_id:str
    start_id:str
    end_id:str
    points_mm:np.ndarray
    surface_vertex_ids:tuple
    length_mm:float
    weighted_cost:float
    backend:str
    variant_index:int
    radius_mm:float|None=None


@dataclass(frozen=True)
class RouteSearchResult:
    paths:tuple
    rejections:tuple
    search_complete:bool
    status:str


def zone_distances(points,zone):
    p=np.asarray(points,float)-np.asarray(zone.center_mm,float)
    if isinstance(zone,SphereKeepOut):return np.linalg.norm(p,axis=1)-zone.radius_mm
    if not isinstance(zone,CylinderKeepOut):raise ValueError('UNSUPPORTED_KEEP_OUT')
    axis=np.asarray(zone.axis,float);axis/=np.linalg.norm(axis)
    z=p@axis;dr=np.linalg.norm(p-z[:,None]*axis,axis=1)-zone.radius_mm;dz=np.abs(z)-zone.half_height_mm
    return np.hypot(np.maximum(dr,0),np.maximum(dz,0))+np.minimum(np.maximum(dr,dz),0)


def smooth_surface_path(surface,points,vertex_ids,constraints,config):
    """Project a short smoothing pass to the original mesh-edge corridor.

    Never search an unrelated nearby sheet. Reject the complete modification
    if a sampled span leaves this corridor or a physical keep-out is hit.
    """
    from scipy.spatial import cKDTree
    from .ios_surface import check_mesh_obstacles
    original=np.asarray(points,float)
    if len(original)<3 or not vertex_ids:return original
    mask=np.isin(surface.triangles,np.asarray(vertex_ids,int)).any(axis=1)
    if constraints.allowed_vertices is not None:mask&=np.asarray(constraints.allowed_vertices,bool)[surface.triangles].all(axis=1)
    triangles=surface.vertices_mm[surface.triangles[mask]]
    if not len(triangles):return original
    # Reuse the existing exact point-triangle kernel without importing bpy.
    check_mesh_obstacles(original,config.radius_mm,())
    import sys
    kernel=sys.modules[__package__+'._generative_mesh_distance']
    tree=cKDTree(triangles.mean(axis=1));k=min(12,len(triangles))
    def project(point):
        indices=np.atleast_1d(tree.query(point,k=k)[1])
        return min((kernel.closest_point_on_triangle(point,*triangles[int(i)])[0] for i in indices),key=lambda p:float(np.sum((p-point)**2)))
    current=original.copy()
    for _ in range(3):
        trial=current.copy()
        for i in range(1,len(current)-1):
            target=.25*current[i-1]+.5*current[i]+.25*current[i+1]
            delta=target-current[i];size=np.linalg.norm(delta);limit=max(.25,.5*config.radius_mm)
            if size>limit:target=current[i]+delta*(limit/size)
            projected=project(target)
            if np.linalg.norm(projected-current[i])<=max(.25,.5*config.radius_mm):trial[i]=projected
        current=trial
    clean=[current[0]]
    for point in current[1:]:
        if np.linalg.norm(point-clean[-1])>1e-6:clean.append(point)
    candidate=np.asarray(clean)
    # Dense samples verify the segment as well as projected control points.
    for a,b in zip(candidate,candidate[1:]):
        for t in np.linspace(0.,1.,max(3,int(np.linalg.norm(b-a)/.1)+2)):
            point=a+(b-a)*t
            if np.linalg.norm(project(point)-point)>config.surface_tolerance_mm:return original
    sweep=check_swept_tube_clearance(candidate,[config.radius_mm]*len(candidate),constraints.protected_zones)
    clear,_reason=check_mesh_obstacles(candidate,config.radius_mm,constraints.mesh_obstacles)
    return candidate if sweep.clear and clear else original


def generate_geodesic_candidates(surface,start,end,constraints,config):
    rejected=[];found=[];complete=True
    if not constraints.required_zones_complete:return RouteSearchResult((),('MISSING_REQUIRED_GEOMETRY',),False,'UNVERIFIABLE')
    try:a=validate_anchor(surface,start);b=validate_anchor(surface,end)
    except ValueError as exc:return RouteSearchResult((),(str(exc),),True,'INVALID_INPUT')
    if start.component!=end.component:return RouteSearchResult((),('DISCONNECTED_SURFACE',),True,'NO_VALID_SURFACE_ROUTE')
    n=len(surface.vertices_mm);allowed=np.ones(n,bool) if constraints.allowed_vertices is None else np.array(constraints.allowed_vertices,bool,copy=True)
    if allowed.shape!=(n,):raise ValueError('INVALID_ALLOWED_MASK')
    src=np.repeat(np.arange(n),np.diff(surface.csr_offsets));dst=surface.csr_destinations;lengths=surface.csr_lengths_mm
    keep=allowed[src]&allowed[dst]
    for zone in constraints.protected_zones:
        distance=zone_distances(surface.vertices_mm,zone)-config.radius_mm
        allowed&=distance>config.surface_tolerance_mm
        # Lipschitz bound protects the full edge, including small obstacles
        # between free endpoint vertices. Conservative uncertainty is excluded.
        keep&=np.minimum(distance[src],distance[dst])-.5*lengths>config.surface_tolerance_mm
    keep&=allowed[src]&allowed[dst]
    counts=np.bincount(src[keep],minlength=n);offsets=np.concatenate(([0],np.cumsum(counts)))
    filtered_dst=dst[keep];filtered_lengths=lengths[keep]
    penalty=np.zeros(n) if constraints.vertex_penalty is None else np.array(constraints.vertex_penalty,float,copy=True)
    if penalty.shape!=(n,) or not np.isfinite(penalty).all() or np.any(penalty<0):raise ValueError('INVALID_VERTEX_PENALTY')
    seen=set();face_a=surface.triangles[start.face_index];face_b=surface.triangles[end.face_index]
    for attempt in range(config.max_reroutes_per_pair):
        try:
            route=paths.route_surface_face_anchors(surface.vertices_mm,offsets,filtered_dst,filtered_lengths,face_a,a,face_b,b,allowed_mask=allowed,vertex_penalty=penalty)
        except (ValueError,paths.NoValidSurfaceRoute) as exc:rejected.append(str(exc));break
        identity=tuple(route.vertex_indices);key=hashlib.sha256(np.asarray(route.points_mm,float).tobytes()).hexdigest()
        sweep=check_swept_tube_clearance(route.points_mm,[config.radius_mm]*len(route.points_mm),constraints.protected_zones)
        if not sweep.clear:
            rejected.append('SWEEP_'+sweep.status+':'+str(sweep.nearest_zone))
            inner=identity[1:-1]
            if not inner:break
            penalty[list(inner)]+=100.
            continue
        if constraints.mesh_obstacles:
            from .ios_surface import check_mesh_obstacles
            clear,reason=check_mesh_obstacles(route.points_mm,config.radius_mm,constraints.mesh_obstacles)
            if not clear:
                rejected.append(reason)
                inner=identity[1:-1]
                if not inner:break
                penalty[list(inner)]+=100.
                continue
        if key not in seen:
            seen.add(key);rid=hashlib.sha256((surface.fingerprint+start.id+'\0'+end.id+key).encode()).hexdigest()[:20]
            found.append(CandidatePath(rid,start.id,end.id,_readonly(route.points_mm,float),identity,float(route.surface_length_mm),float(route.weighted_cost),route.backend,len(found)))
        inner=identity[1:-1]
        if len(found)>=config.variants_per_pair:break
        if not inner:break
        penalty[list(inner)]+=5.
        if attempt==config.max_reroutes_per_pair-1:complete=False
    else:complete=False
    return RouteSearchResult(tuple(found),tuple(rejected),complete,'CANDIDATE' if found else 'NO_VALID_SURFACE_ROUTE')


def _trim_ball_prefix(points,center,radius):
    pts=np.asarray(points,float);center=np.asarray(center,float)
    for i in range(1,len(pts)):
        if np.linalg.norm(pts[i]-center)<=radius:continue
        a=pts[i-1]-center;d=pts[i]-pts[i-1];aa=float(d@d);bb=2.*float(a@d);cc=float(a@a)-radius*radius
        if aa<=1e-16:continue
        root=(-bb+np.sqrt(max(0.,bb*bb-4.*aa*cc)))/(2.*aa)
        point=pts[i-1]+np.clip(root,0.,1.)*d
        return np.vstack((point,pts[i:]))
    return None


def bridge_free_core(points,joint_radius_mm):
    pts=np.asarray(points,float);first=_trim_ball_prefix(pts,pts[0],joint_radius_mm)
    if first is None:return None
    last=_trim_ball_prefix(first[::-1],pts[-1],joint_radius_mm)
    return None if last is None else last[::-1].copy()


def generate_bridge_candidates(start_id,end_id,start_mm,end_mm,start_outward,end_outward,model,constraints,config,*,joint_radius_mm):
    """Direct or lifted free-space polyline, matching the geometry checked.

    Only bounded terminal attachment pockets may contact the IOS. The full
    centerline must escape it immediately; all protected structures apply to
    the complete tube, including the attachment pockets.
    """
    from .ios_surface import check_mesh_obstacles
    if model is None or not constraints.required_zones_complete:return RouteSearchResult((),('BRIDGE_INPUT_UNVERIFIABLE',),False,'UNVERIFIABLE')
    a=np.asarray(start_mm,float);b=np.asarray(end_mm,float);na=np.asarray(start_outward,float);nb=np.asarray(end_outward,float)
    for value in (a,b,na,nb):
        if value.shape!=(3,) or not np.isfinite(value).all():raise ValueError('INVALID_BRIDGE_INPUT')
    if np.linalg.norm(b-a)<2.*config.radius_mm:return RouteSearchResult((),('INSUFFICIENT_FREE_SPAN',),True,'NO_VALID_FREE_BRIDGE')
    if np.linalg.norm(na)<1e-8 or np.linalg.norm(nb)<1e-8:raise ValueError('INVALID_BRIDGE_NORMAL')
    na=na/np.linalg.norm(na);nb=nb/np.linalg.norm(nb);found=[];rejections=[];radius=config.radius_mm
    axis=next((np.asarray(z.axis,float) for z in constraints.protected_zones if isinstance(z,CylinderKeepOut)),na+nb)
    lateral=np.cross(b-a,axis)
    if np.linalg.norm(lateral)<1e-8:lateral=np.cross(b-a,np.eye(3)[int(np.argmin(np.abs(b-a)))])
    lateral/=np.linalg.norm(lateral)
    layouts=tuple((factor,bow) for factor in (0.,2.,4.,6.,8.,12.) for bow in (0.,4.,-4.,8.,-8.,12.,-12.))
    raw_layouts=[]
    for factor,bow in layouts:
        height=factor*radius;offset=bow*radius
        count=max(3,int(np.ceil((np.linalg.norm(b-a)+2.*height+2.*abs(offset))/max(.15,.5*radius)))+1)
        t=np.linspace(0.,1.,count)[:,None];u=1.-t
        pts=u**3*a+3.*u*u*t*(a+na*height)+3.*u*t*t*(b+nb*height)+t**3*b+16.*u*u*t*t*lateral*offset
        if np.any(np.linalg.norm(np.diff(pts,axis=0),axis=1)<1e-8):continue
        length=float(np.linalg.norm(np.diff(pts,axis=0),axis=1).sum())
        raw_layouts.append((length,factor,bow,pts))
    for _length,_factor,_bow,pts in sorted(raw_layouts,key=lambda row:(row[0],row[1],abs(row[2]),row[2])):
        sweep=check_swept_tube_clearance(pts,[radius]*len(pts),constraints.protected_zones)
        if not sweep.clear:rejections.append('BRIDGE_'+sweep.status);continue
        clear,reason=check_mesh_obstacles(pts,radius,constraints.mesh_obstacles)
        if not clear:rejections.append(reason);continue
        interior=bridge_free_core(pts,.02)
        if interior is None:continue
        clear,reason=model.clear(interior,1e-6)
        if not clear:rejections.append(reason);continue
        core=bridge_free_core(pts,float(joint_radius_mm))
        length=float(np.linalg.norm(np.diff(pts,axis=0),axis=1).sum())
        free_length=0. if core is None else float(np.linalg.norm(np.diff(core,axis=0),axis=1).sum())
        if free_length<max(2.*radius,.25*length):rejections.append('INSUFFICIENT_FREE_SPAN');continue
        clear,reason=model.clear(core,radius)
        if not clear:rejections.append(reason);continue
        key=hashlib.sha256((start_id+'\0'+end_id).encode()+pts.tobytes()).hexdigest()[:20]
        found.append(CandidatePath(key,start_id,end_id,_readonly(pts,float),(),length,length,'CERTIFIED_FREE_BRIDGE',len(found),radius))
        if len(found)>=config.variants_per_pair:break
    return RouteSearchResult(tuple(found),tuple(rejections),len(found)<config.variants_per_pair,'CANDIDATE' if found else 'NO_VALID_FREE_BRIDGE')


def surface_path_certificate(surface,points,tolerance_mm=.02):
    """Conservative whole-segment distance bound to the actual IOS triangles.

    A segment lies within tolerance of a convex triangle when both endpoints
    do. Adaptive bisection handles changing faces; disconnected sheets never
    become a permitted chord merely because its endpoints touch the mesh.
    Nearby triangle selection may reject a valid path, never certify a gap.
    """
    from scipy.spatial import cKDTree
    from .ios_surface import check_mesh_obstacles
    import sys
    points=np.asarray(points,float)
    if points.ndim!=2 or points.shape[1]!=3 or len(points)<2 or not np.isfinite(points).all():
        return {'valid':False,'maximum_distance_bound_mm':None}
    check_mesh_obstacles(points,.01,())
    kernel=sys.modules[__package__+'._generative_mesh_distance']
    triangles=surface.vertices_mm[surface.triangles]
    if not len(triangles):return {'valid':False,'maximum_distance_bound_mm':None}
    centers=triangles.mean(axis=1)
    tree=cKDTree(centers);k=min(12,len(triangles));maximum=0.;radius_buckets=None
    def possible_faces(middle):
        nonlocal radius_buckets
        if radius_buckets is None:
            radii=np.linalg.norm(triangles-centers[:,None,:],axis=2).max(axis=1)
            bins=np.floor(np.log2(np.maximum(radii,1e-6))).astype(int)
            radius_buckets=[]
            for label in np.unique(bins):
                ids=np.flatnonzero(bins==label)
                radius_buckets.append((ids,cKDTree(centers[ids]),float(radii[ids].max())))
        # If one convex triangle is within tolerance of both endpoints, it is
        # also within tolerance of the midpoint. Its centroid lies within that
        # distance plus its circum-bound. Large faces cannot be omitted merely
        # because smaller, more distant faces have closer centroids.
        for ids,index,extent in radius_buckets:
            for row in index.query_ball_point(middle,tolerance_mm+extent+1e-9):yield int(ids[row])
    def certify(a,b,depth=0):
        nonlocal maximum
        ids=np.unique(np.atleast_1d(tree.query(np.vstack((a,b,(a+b)*.5)),k=k)[1]))
        bound=min(max(float(kernel.closest_point_on_triangle(p,*triangles[int(i)])[1]) for p in (a,b)) for i in ids)**.5
        if bound>tolerance_mm:
            for face in possible_faces((a+b)*.5):
                candidate=max(float(kernel.closest_point_on_triangle(p,*triangles[face])[1]) for p in (a,b))**.5
                bound=min(bound,candidate)
                if bound<=tolerance_mm:break
        if bound<=tolerance_mm:
            maximum=max(maximum,bound);return True
        if depth>=16 or np.linalg.norm(b-a)<tolerance_mm*.25:return False
        mid=(a+b)*.5
        return certify(a,mid,depth+1) and certify(mid,b,depth+1)
    valid=all(certify(a,b) for a,b in zip(points,points[1:]))
    return {'valid':valid,'maximum_distance_bound_mm':maximum if valid else None,'tolerance_mm':tolerance_mm}
