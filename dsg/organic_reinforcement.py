"""Open organic branches: frame-style fairing and continuous tube sections.

The reference is a geodesic on the real IOS. Fairing is bounded by the tube
radius; continuous support is checked separately against that reference.
No Blender imports, and no invented clinical/mechanical acceptance.
"""
import numpy as np


def resample_open(points,spacing=.25,locked_indices=()):
    raw=np.asarray(points,float)
    if raw.ndim!=2 or raw.shape[1]!=3 or len(raw)<2 or not np.isfinite(raw).all():raise ValueError('INVALID_ORGANIC_PATH')
    lengths=np.linalg.norm(np.diff(raw,axis=0),axis=1);arc=np.r_[0.,np.cumsum(lengths)]
    if arc[-1]<.05:raise ValueError('ORGANIC_PATH_TOO_SHORT')
    # Small endpoint projection residuals must not become extra sweep sections.
    mandatory=sorted(set([0,len(raw)-1]+list(locked_indices)))
    targets=np.linspace(0.,arc[-1],max(3,int(np.ceil(arc[-1]/spacing))+1))
    for index in mandatory:
        targets=targets[np.abs(targets-arc[index])>spacing*.25]
        targets=np.r_[targets,arc[index]]
    targets=np.unique(np.sort(targets));keep=np.r_[True,np.diff(arc)>1e-9]
    pts=np.column_stack([np.interp(targets,arc[keep],raw[keep,k]) for k in range(3)])
    locked=[int(np.argmin(np.abs(targets-arc[i]))) for i in mandatory]
    pts[locked]=raw[mandatory]
    return pts,np.asarray(locked,int)


def curvature_profile(points):
    p=np.asarray(points,float);a=np.diff(p,axis=0);n=np.linalg.norm(a,axis=1)
    if len(a)<2:return np.zeros(len(p))
    u=a/np.maximum(n[:,None],1e-15);sine=np.linalg.norm(np.cross(u[:-1],u[1:]),axis=1)
    core=2.*sine/np.maximum(np.linalg.norm(p[2:]-p[:-2],axis=1),1e-15)
    return np.r_[core[0],core,core[-1]]


def fair_open_path(points,radius_mm,locked_indices=(),deviation_ratio=.8):
    from scipy.ndimage import gaussian_filter1d
    from .blender.organic_curve import handles,evaluate
    radius=float(radius_mm);limit=radius*float(deviation_ratio)
    raw,locked=resample_open(points,min(.25,max(.12,radius*.25)),locked_indices)
    # Sparse centripetal Catmull controls replace individual mesh-edge turns.
    arc=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(raw,axis=0),axis=1))]
    ids=set(locked);last=0.
    for i,d in enumerate(arc):
        if d-last>=max(1.,radius):ids.add(i);last=d
    ids=sorted(ids);control=raw[ids]
    padded=np.vstack((2*control[0]-control[1],control,2*control[-1]-control[-2]))
    left,right=handles(padded);samples=[]
    for j in range(len(control)-1):
        samples.extend(evaluate(control[j],right[j+1],left[j+2],control[j+1],max(5,int((arc[ids[j+1]]-arc[ids[j]])/.1)+2))[:-1])
    samples.append(control[-1]);samples=np.asarray(samples)
    sample_arc=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(samples,axis=0),axis=1))]
    curve=np.column_stack([np.interp(arc/arc[-1]*sample_arc[-1],sample_arc,samples[:,k]) for k in range(3)])
    step=float(np.median(np.diff(arc)));curve=gaussian_filter1d(curve,max(.5,radius*1.1/step),axis=0,mode='nearest')
    fixed=np.zeros(len(raw),bool);fixed[locked]=True
    for _ in range(2200):
        second=curve[2:]-2*curve[1:-1]+curve[:-2]
        gradient=np.zeros_like(curve);gradient[:-2]+=second;gradient[1:-1]-=2*second;gradient[2:]+=second
        curve-=gradient/18.
        delta=curve-raw;distance=np.linalg.norm(delta,axis=1)
        curve=raw+delta*np.minimum(1.,limit/np.maximum(distance,1e-12))[:,None]
        curve[fixed]=raw[fixed]
    maximum=float(np.linalg.norm(curve-raw,axis=1).max())
    return curve,{'locked_sample_indices':locked.tolist(),'reference_points_mm':raw.tolist(),'maximum_reference_distance_mm':maximum,
                  'reference_limit_mm':limit,'algorithm':'OPEN_CENTRIPETAL_CATMULL_BEZIER_AND_CONSTRAINED_BENDING','control_count':len(control)}


def transport_frames(points,initial_u=None):
    p=np.asarray(points,float);delta=np.diff(p,axis=0);length=np.linalg.norm(delta,axis=1)
    if np.any(length<=1e-9):raise ValueError('DUPLICATE_ORGANIC_SECTION')
    unit=delta/length[:,None];t=np.vstack((unit[0],unit[:-1]+unit[1:],unit[-1]));t/=np.maximum(np.linalg.norm(t,axis=1)[:,None],1e-15)
    normal=np.cross(t[0],np.eye(3)[int(np.argmin(abs(t[0])))]) if initial_u is None else np.asarray(initial_u,float)
    normal-=t[0]*(normal@t[0]);normal/=np.linalg.norm(normal);u=[]
    for i,tangent in enumerate(t):
        if i:
            axis=np.cross(t[i-1],tangent);s=np.linalg.norm(axis);c=float(t[i-1]@tangent)
            if s>1e-12:
                axis/=s;normal=normal*c+np.cross(axis,normal)*s+axis*(axis@normal)*(1.-c)
        normal-=tangent*(normal@tangent);normal/=np.linalg.norm(normal);u.append(normal.copy())
    u=np.asarray(u);return u,np.cross(t,u),t


def mesh_fold_report(points,radius_mm):
    p=np.asarray(points,float);u,v,t=transport_frames(p);theta=np.arange(24)*2*np.pi/24
    rings=p[:,None,:]+float(radius_mm)*(np.cos(theta)[None,:,None]*u[:,None,:]+np.sin(theta)[None,:,None]*v[:,None,:])
    advance=np.diff(rings,axis=0);axis=t[:-1]+t[1:];axis/=np.linalg.norm(axis,axis=1)[:,None]
    forward=np.einsum('nki,ni->nk',advance,axis)
    flipped=int(np.count_nonzero(forward<=1e-8));curvature=curvature_profile(p)*float(radius_mm)
    return {'valid':not flipped,'folded_longitudinal_edges':flipped,'maximum_radius_times_curvature':float(curvature.max(initial=0.))}


def smooth_network_paths(paths,metadata,radius_mm):
    from dataclasses import replace
    from .ios_surface import _readonly
    groups={};single=[]
    for path in paths:
        if metadata[path.route_id]['role']=='PRIMARY' or metadata[path.route_id].get('continuous_branch'):groups.setdefault(path.route_id.rsplit(':SEG',1)[0],[]).append(path)
        else:single.append(path)
    revised={};render=[];diagnostics=[]
    for name,parts in groups.items():
        parts.sort(key=lambda p:int(p.route_id.rsplit(':SEG',1)[1]));raw=[];boundaries=[]
        for part in parts:
            raw.extend(part.points_mm if not raw else part.points_mm[1:]);boundaries.append(len(raw)-1)
        group_radius=radius_mm if parts[0].radius_mm is None else float(parts[0].radius_mm)
        extra=boundaries[:-1]
        if len(parts)==1 and metadata[parts[0].route_id].get('preserve_joint_fractions'):
            arc=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(raw,axis=0),axis=1))]
            extra=[int(np.argmin(abs(arc-arc[-1]*fraction))) for fraction in (.40,.72)]
        if all(metadata[p.route_id].get('pre_faired') for p in parts):
            curve=np.asarray(raw,float);locks=[0]+boundaries
            info={'maximum_reference_distance_mm':None,'reference_points_mm':metadata[parts[0].route_id].get('reference_points_mm',curve.tolist())}
        else:
            curve,info=fair_open_path(raw,group_radius,extra);locks=info['locked_sample_indices']
        if len(parts)==1:locks=[locks[0],locks[-1]]
        fold=mesh_fold_report(curve,group_radius);diagnostics.append(dict(route_id=name,**fold,maximum_reference_distance_mm=info['maximum_reference_distance_mm']))
        if not fold['valid']:raise ValueError('ORGANIC_TUBE_FOLD:'+name)
        nodes={parts[0].start_id:curve[0].tolist()}
        for i,part in enumerate(parts):
            pts=curve[locks[i]:locks[i+1]+1];length=float(np.linalg.norm(np.diff(pts,axis=0),axis=1).sum())
            revised[part.route_id]=replace(part,points_mm=_readonly(pts,float),length_mm=length)
            nodes[part.end_id]=pts[-1].tolist()
        render.append({'route_id':name,'source_routes':[p.route_id for p in parts],'origin':parts[0].start_id,'port':parts[-1].end_id,'sleeve_id':metadata[parts[0].route_id]['sleeve_id'],
                       'member_role':metadata[parts[0].route_id]['role'],'route_kind':'ORGANIC_ON_GEODESIC_REFERENCE','points_mm':curve.tolist(),'radius_mm':group_radius,'nodes':nodes,'reference_points_mm':info['reference_points_mm']})
    for part in single:
        radius=radius_mm if part.radius_mm is None else part.radius_mm
        if metadata[part.route_id].get('pre_faired'):
            curve=np.asarray(part.points_mm,float);info={'maximum_reference_distance_mm':None,'reference_points_mm':metadata[part.route_id].get('reference_points_mm',curve.tolist())}
        else:curve,info=fair_open_path(part.points_mm,radius)
        fold=mesh_fold_report(curve,radius);diagnostics.append(dict(route_id=part.route_id,**fold,maximum_reference_distance_mm=info['maximum_reference_distance_mm']))
        if not fold['valid']:raise ValueError('ORGANIC_TUBE_FOLD:'+part.route_id)
        length=float(np.linalg.norm(np.diff(curve,axis=0),axis=1).sum());revised[part.route_id]=replace(part,points_mm=_readonly(curve,float),length_mm=length)
        render.append({'route_id':part.route_id,'source_routes':[part.route_id],'origin':part.start_id,'port':part.end_id,'sleeve_id':'','member_role':'SECONDARY','route_kind':'ORGANIC_ON_GEODESIC_REFERENCE',
                       'points_mm':curve.tolist(),'radius_mm':radius,'nodes':{},'reference_points_mm':info['reference_points_mm']})
    for piece in render:
        row=metadata[piece['source_routes'][0]]
        for key in ('web_level','web_sector','web_kind','joint_neck_start_mm','joint_neck_end_mm','frame_neck_start_mm','frame_neck_end_mm'):
            if key in row:piece[key]=row[key]
    return tuple(revised[p.route_id] for p in paths),render,{'organic_geometry_valid':True,'organic_algorithm':'CENTRIPETAL_CATMULL_BEZIER_BENDING_RMF',
            'organic_branch_count':len(render),'organic_folded_edges':0,'organic_diagnostics':diagnostics,'organic_maximum_radius_times_curvature':max(d['maximum_radius_times_curvature'] for d in diagnostics)}


def intersecting_plane_candidates(triangle,others,tolerance_mm=1e-7):
    """Necessary plane tests only; retain touching/coplanar uncertainty.

    Disjoint half-spaces prove non-intersection. Remaining pairs still pass
    the original exact segment/triangle checks, including large crossing faces.
    """
    first=np.asarray(triangle,float);others=np.asarray(others,float)
    if not len(others):return np.zeros(0,bool)
    normal=np.cross(first[1]-first[0],first[2]-first[0])
    normals=np.cross(others[:,1]-others[:,0],others[:,2]-others[:,0])
    signed=np.einsum('mjk,k->mj',others-first[0],normal)
    epsilon=tolerance_mm*max(float(np.linalg.norm(normal)),1e-12)
    separate=(signed.min(axis=1)>epsilon)|(signed.max(axis=1)<-epsilon)
    signed=np.einsum('mjk,mk->mj',first[None,:,:]-others[:,0:1,:],normals)
    epsilon=tolerance_mm*np.maximum(np.linalg.norm(normals,axis=1),1e-12)
    separate|=(signed.min(axis=1)>epsilon)|(signed.max(axis=1)<-epsilon)
    return ~separate


def validate_mesh_keepouts(vertices,faces,zones,obstacles=()):
    """Conservative full-triangle certificate, including containment.

    Checking mesh vertices alone would miss a protected solid piercing the
    interior of a large triangle. Lipschitz subdivision proves each whole face.
    """
    from .geodesic_router import zone_distances
    from .ios_surface import check_mesh_obstacles,_inside_triangles
    import sys
    xyz=np.asarray(vertices,float);faces=np.asarray(faces,int);triangles=xyz[faces]
    if not np.isfinite(xyz).all() or not len(faces):return {'valid':False,'reason':'INVALID_FINAL_MESH'}
    def clear_triangle(tri,zone,depth=0):
        distances=zone_distances(tri,zone)
        if distances.min()<=1e-7:return False
        diameter=max(np.linalg.norm(tri[0]-tri[1]),np.linalg.norm(tri[0]-tri[2]),np.linalg.norm(tri[1]-tri[2]))
        if distances.min()>diameter+1e-7:return True
        if depth>=12:return False
        a,b,c=tri;ab=(a+b)*.5;ac=(a+c)*.5;bc=(b+c)*.5
        return all(clear_triangle(np.array(t),zone,depth+1) for t in ((a,ab,ac),(ab,b,bc),(ac,bc,c),(ab,bc,ac)))
    for zone in zones:
        distances=zone_distances(xyz,zone);diameter=np.linalg.norm(triangles-triangles.mean(axis=1)[:,None,:],axis=2).max(axis=1)
        # A centroid ball bounds the whole triangle.
        centers=triangles.mean(axis=1);candidates=np.flatnonzero(zone_distances(centers,zone)<=diameter+1e-7)
        for i in candidates:
            if not clear_triangle(triangles[i],zone):return {'valid':False,'reason':'FINAL_MESH_KEEP_OUT:'+zone.label}
        if _inside_triangles(zone.center_mm,triangles):return {'valid':False,'reason':'FINAL_MESH_ENCLOSES:'+zone.label}
    check_mesh_obstacles([[0,0,0],[1,0,0]],.01,());kernel=sys.modules[__package__+'._generative_mesh_distance']
    for obstacle in obstacles:
        if not obstacle.get('closed',False):return {'valid':False,'reason':'UNVERIFIABLE_FINAL_OBSTACLE'}
        other=np.asarray(obstacle['vertices_mm'])[np.asarray(obstacle['triangles'],int)]
        # A disconnected channel mesh is a union, not one representative point.
        faces_other=np.asarray(obstacle['triangles'],int);parent=np.arange(len(obstacle['vertices_mm']))
        def root(i):
            while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
            return i
        for a,b,c in faces_other:
            ra,rb,rc=root(a),root(b),root(c);parent[rb]=ra;parent[rc]=ra
        representatives={root(int(face[0])) for face in faces_other}
        candidate_low=xyz.min(axis=0);candidate_high=xyz.max(axis=0)
        inside=False
        for index in representatives:
            point=np.asarray(obstacle['vertices_mm'])[index]
            if np.all(point>=candidate_low) and np.all(point<=candidate_high) and _inside_triangles(point,triangles):inside=True;break
        if _inside_triangles(xyz[0],other) or inside:return {'valid':False,'reason':'FINAL_MESH_CONTAINMENT:'+obstacle['label']}
        low=other.min(axis=1);high=other.max(axis=1)
        global_low=low.min(axis=0);global_high=high.max(axis=0)
        possible=np.all(triangles.max(axis=1)>=global_low-1e-7,axis=1)&np.all(triangles.min(axis=1)<=global_high+1e-7,axis=1)
        for tri in triangles[possible]:
            candidates=other[np.all(high>=tri.min(axis=0)-1e-7,axis=1)&np.all(low<=tri.max(axis=0)+1e-7,axis=1)]
            candidates=candidates[intersecting_plane_candidates(tri,candidates)]
            for other_tri in candidates:
                if any(kernel._segment_triangle_hit(a,b,other_tri) for a,b in zip(tri,np.roll(tri,-1,axis=0))) or any(kernel._segment_triangle_hit(a,b,tri) for a,b in zip(other_tri,np.roll(other_tri,-1,axis=0))):
                    return {'valid':False,'reason':'FINAL_MESH_INTERSECTION:'+obstacle['label']}
    return {'valid':True,'triangles_checked':len(faces)}


def bounded_collar_handle(start, tube_center, tangent, support_direction, handle):
    """Keep the Bezier control hull on the support side of the tube ring.

    Shortening a positive tangent handle preserves the support tangent and
    prevents the collar folding back through the nominal tube cross-section.
    The attachment footprint and tube ring are never moved.
    """
    start,center,axis,direction=(np.asarray(x,float) for x in (start,tube_center,tangent,support_direction))
    if any(x.shape!=(3,) or not np.isfinite(x).all() for x in (start,center,axis,direction)) or not np.isfinite(handle) or handle<0:
        raise ValueError('ORGANIC_COLLAR_INVALID_HANDLE')
    clearance=-float(np.dot(start-center,axis))
    if clearance < -1.e-4:
        raise ValueError('ORGANIC_COLLAR_SUPPORT_CROSSES_TUBE_PLANE')
    projection=float(np.dot(direction,axis))
    return min(float(handle),max(0.,clearance)/projection) if projection>1.e-8 else float(handle)
