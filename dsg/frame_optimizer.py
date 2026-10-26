"""Geometric candidate evaluation; mechanical validation stays explicit."""
from dataclasses import dataclass
import math
import numpy as np
from .frame_generator import validate_connectivity
from .frame_swept_clearance_core import check_swept_tube_clearance
from .ios_surface import check_mesh_obstacles


@dataclass(frozen=True)
class GenerationResult:
    status:str
    graph:object
    report:dict
    rejections:tuple=()


def _kernel():
    # Reuse the same pure kernel loader as mesh-obstacle verification.
    check_mesh_obstacles([[0.,0.,0.],[1.,0.,0.]],.01,())
    import sys
    return sys.modules[__package__+'._generative_mesh_distance']


def _intersection_outside_declared_joint(member,other,kernel):
    from scipy.spatial import cKDTree
    def dense(points,radius):
        output=[points[0]]
        for a,b in zip(points,points[1:]):
            count=max(1,int(np.ceil(np.linalg.norm(b-a)/max(.05,.5*radius))))
            output.extend(a+(b-a)*t for t in np.linspace(0,1,count+1)[1:])
        return np.asarray(output)
    a=dense(member.path.points_mm,member.radius_mm);b=dense(other.path.points_mm,other.radius_mm)
    mid_a=(a[:-1]+a[1:])*.5;mid_b=(b[:-1]+b[1:])*.5
    reach=member.radius_mm+other.radius_mm
    broad=reach+.5*np.max(np.linalg.norm(np.diff(a,axis=0),axis=1))+.5*np.max(np.linalg.norm(np.diff(b,axis=0),axis=1))
    nearby=cKDTree(mid_b).query_ball_point(mid_a,broad);contacts=set();witnesses={}
    for i,indices in enumerate(nearby):
        for j in indices:
            _p,_q,d2=kernel.closest_points_segments(a[i],a[i+1],b[j],b[j+1])
            if d2<=reach**2:contacts.add((i,j));witnesses[(i,j)]=(_p,_q)
    if not contacts:return False
    shared={member.start_id,member.end_id}&{other.start_id,other.end_id}
    seeds=set()
    for node in shared:
        i=0 if member.start_id==node else len(a)-2;j=0 if other.start_id==node else len(b)-2
        if (i,j) in contacts:seeds.add((i,j))
    # Only a connected contact region rooted at an explicit graph joint may
    # become a Boolean weld. A later crossing is a separate component.
    reached=set(seeds);pending=list(seeds)
    while pending:
        i,j=pending.pop()
        for di in (-1,0,1):
            for dj in (-1,0,1):
                key=(i+di,j+dj)
                if key in contacts and key not in reached:reached.add(key);pending.append(key)
    if contacts-reached:return True
    # Touching an undeclared terminal node requires a real additional graph
    # junction; a shared departure cannot authorize a wholly encased member.
    for label,point,other_points in ((member.start_id,a[0],b),(member.end_id,a[-1],b),(other.start_id,b[0],a),(other.end_id,b[-1],a)):
        if label in shared:continue
        delta=np.diff(other_points,axis=0);weights=np.clip(np.einsum('ij,ij->i',point-other_points[:-1],delta)/np.einsum('ij,ij->i',delta,delta),0.,1.)
        nearest=other_points[:-1]+weights[:,None]*delta
        if float(np.min(np.linalg.norm(nearest-point,axis=1)))<reach-1e-8:return True
    limits=[]
    for node in shared:
        pa=a if member.start_id==node else a[::-1];pb=b if other.start_id==node else b[::-1]
        def tangent(pts):
            distances=np.linalg.norm(pts-pts[0],axis=1);ids=np.flatnonzero(distances>=2.*max(member.radius_mm,other.radius_mm))
            vec=pts[int(ids[0])] - pts[0] if len(ids) else pts[-1]-pts[0]
            return vec/max(np.linalg.norm(vec),1e-10)
        ua,ub=tangent(pa),tangent(pb);sine=float(np.linalg.norm(np.cross(ua,ub)))
        # Acute, diverging tangents need a longer finite weld than 3r. A
        # coincident departure has no measurable divergence and remains 3r.
        limit=3.*max(member.radius_mm,other.radius_mm)
        if sine>.01:limit=min(8.*max(member.radius_mm,other.radius_mm),max(limit,reach/sine))
        limits.append((pa[0],limit))
    for key in reached:
        p,q=witnesses[key]
        if not any(max(np.linalg.norm(p-center),np.linalg.norm(q-center))<=limit+1e-7 for center,limit in limits):return True
    return False


def evaluate_frame(graph,constraints,config,*,continuous_primary_groups=None):
    report={'routing_valid':False,'connectivity_valid':False,'swept_geometry_valid':False,'junction_valid':False,
            'mechanics_evaluated':False,'post_boolean_validated':False,'clinical_acceptance':False,
            'warnings':[],'length_mm':0.,'nominal_volume_mm3':0.}
    if not graph.perimeter.analytical_path_verified:report['warnings'].append('FRAME_PATH_SOURCE_UNVERIFIABLE')
    if not constraints.required_zones_complete:return GenerationResult('UNVERIFIABLE',graph,report,('MISSING_REQUIRED_GEOMETRY',))
    connectivity=validate_connectivity(graph);report['connectivity_valid']=connectivity.valid
    if not connectivity.valid:return GenerationResult('INVALID_INPUT',graph,report,('ORPHAN_BRANCH',))
    positions={n.id:np.asarray(n.point_mm,float) for n in graph.nodes};rejections=[]
    for member in graph.members:
        points=member.path.points_mm
        if len(points)<2 or not np.isfinite(points).all() or np.any(np.linalg.norm(np.diff(points,axis=0),axis=1)<=1e-8):
            rejections.append('INVALID_MEMBER_PATH');continue
        if np.linalg.norm(points[0]-positions[member.start_id])>config.node_merge_tolerance_mm or np.linalg.norm(points[-1]-positions[member.end_id])>config.node_merge_tolerance_mm:
            rejections.append('MEMBER_ENDPOINT_MISMATCH');continue
        sweep=check_swept_tube_clearance(points,[member.radius_mm]*len(points),constraints.protected_zones)
        if not sweep.clear:rejections.append('SWEEP_'+sweep.status)
        clear,reason=check_mesh_obstacles(points,member.radius_mm,constraints.mesh_obstacles)
        if not clear:rejections.append(reason)
        length=float(np.linalg.norm(np.diff(points,axis=0),axis=1).sum());report['length_mm']+=length
        report['nominal_volume_mm3']+=math.pi*member.radius_mm**2*length
    # Artificial graph cuts expose junction nodes but do not turn a continuous
    # tube into several physical bars. Validate the current joined polyline as
    # one tube instead of rejecting the proximity of its own short end pieces.
    # A caller cannot use a group to exempt unrelated or disconnected members.
    kernel=_kernel();parents={};self_members=[]
    by_id={m.id:m for m in graph.members}
    from types import SimpleNamespace
    for parent,labels in (continuous_primary_groups or {}).items():
        if not isinstance(labels,(tuple,list)):
            return GenerationResult('INVALID_INPUT',graph,report,('INVALID_CONTINUOUS_PRIMARY_GROUP',))
        labels=tuple(labels)
        if not labels or len(set(labels))!=len(labels) or any(label not in by_id or label in parents for label in labels):
            return GenerationResult('INVALID_INPUT',graph,report,('INVALID_CONTINUOUS_PRIMARY_GROUP',))
        parts=[by_id[label] for label in labels]
        if any(a.end_id!=b.start_id or np.linalg.norm(a.path.points_mm[-1]-b.path.points_mm[0])>1e-8 or a.radius_mm!=b.radius_mm for a,b in zip(parts,parts[1:])):
            return GenerationResult('INVALID_INPUT',graph,report,('INVALID_CONTINUOUS_PRIMARY_GROUP',))
        nodes=[parts[0].start_id]+[part.end_id for part in parts]
        if len(set(nodes))!=len(nodes):
            return GenerationResult('INVALID_INPUT',graph,report,('INVALID_CONTINUOUS_PRIMARY_GROUP',))
        points=np.vstack([parts[0].path.points_mm]+[part.path.points_mm[1:] for part in parts[1:]])
        # Subdivide long edges without moving them. Otherwise a folded-back
        # two-edge path would evade the nonadjacent-segment sweep below.
        dense=[points[0]];spacing=max(.05,.5*parts[0].radius_mm)
        for a,b in zip(points,points[1:]):
            count=max(1,int(np.ceil(np.linalg.norm(b-a)/spacing)))
            dense.extend(a+(b-a)*t for t in np.linspace(0,1,count+1)[1:])
        self_members.append(SimpleNamespace(path=SimpleNamespace(points_mm=np.asarray(dense)),radius_mm=parts[0].radius_mm,continuous_parent=True))
        for label in labels:parents[label]=parent
    self_members.extend(member for member in graph.members if member.id not in parents)
    for member in self_members:
        pts=np.asarray(member.path.points_mm,float);arcs=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(pts,axis=0),axis=1))]
        radius=member.radius_mm
        if getattr(member,'continuous_parent',False):
            # The closest pair can lie inside the local joint neighborhood
            # while another pair on those edges folds back nonlocally.
            for i,point in enumerate(pts):
                far=pts[arcs-arcs[i]>3.*radius]
                if len(far) and np.any(np.linalg.norm(far-point,axis=1)<2.*radius-1e-8):
                    rejections.append('MEMBER_SELF_INTERSECTION');break
        for i,(a,b) in enumerate(zip(pts,pts[1:])):
            for j in range(i+2,len(pts)-1):
                c,d=pts[j],pts[j+1]
                p,q,d2=kernel.closest_points_segments(a,b,c,d)
                # A local neighbourhood shares the same swept section. Compare
                # nonlocal material using arclength at the closest positions.
                along_a=arcs[i]+np.linalg.norm(p-a);along_b=arcs[j]+np.linalg.norm(q-c)
                if along_b-along_a>3.*radius and d2<(2.*radius-1e-8)**2:
                    rejections.append('MEMBER_SELF_INTERSECTION');break
            if 'MEMBER_SELF_INTERSECTION' in rejections:break
    for i,member in enumerate(graph.members):
        for other in graph.members[i+1:]:
            if member.id in parents and other.id in parents and parents[other.id]==parents[member.id]:continue
            if _intersection_outside_declared_joint(member,other,kernel):
                rejections.append('MEMBER_INTERSECTION')
                report.setdefault('member_intersection_pairs',[]).append((member.id,other.id))
    report['routing_valid']=not rejections;report['swept_geometry_valid']=not rejections
    report['junction_valid']=False;report['warnings'].append('SLEEVE_JUNCTION_REQUIRES_ADAPTER_PREFLIGHT')
    return GenerationResult('INVALID_INPUT' if rejections else 'CANDIDATE',graph,report,tuple(sorted(set(rejections))))


def rank_candidate_sets(candidates):
    return tuple(sorted(candidates,key=lambda result:(result.status!='CANDIDATE',result.report['length_mm'],result.report['nominal_volume_mm3'],tuple(m.id for m in result.graph.members))))
