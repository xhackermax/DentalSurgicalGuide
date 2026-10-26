"""Semantic frame topology. Existing perimeter geometry is never regenerated."""
from dataclasses import dataclass
import numpy as np
from .ios_surface import _readonly


@dataclass(frozen=True)
class FramePerimeter:
    id:str
    points_mm:np.ndarray
    anchors:tuple
    geometry_hash:str
    analytical_path_verified:bool=False
    def __post_init__(self):
        points=np.asarray(self.points_mm,float)
        if points.ndim!=2 or points.shape[1]!=3 or len(points)!=len(self.anchors) or len(points)<3 or not np.isfinite(points).all():raise ValueError('INVALID_PERIMETER')
        if len({a.id for a in self.anchors})!=len(self.anchors):raise ValueError('DUPLICATE_ANCHOR_ID')
        object.__setattr__(self,'points_mm',_readonly(points,float))


@dataclass(frozen=True)
class SleevePort:
    id:str
    sleeve_id:str
    anchor:object
    attachment_mm:tuple
    axis:tuple=(0.,0.,1.)


@dataclass(frozen=True)
class AnchorPair:
    start:object
    end:object
    port:SleevePort
    side:int
    priority:float


@dataclass(frozen=True)
class FrameNode:
    id:str
    point_mm:tuple
    role:str


@dataclass(frozen=True)
class FrameMember:
    id:str
    start_id:str
    end_id:str
    path:object
    radius_mm:float


@dataclass(frozen=True)
class FrameGraph:
    perimeter:FramePerimeter
    nodes:tuple
    members:tuple


@dataclass(frozen=True)
class ConnectivityReport:
    valid:bool
    orphan_nodes:tuple


def select_frame_anchor_pairs(perimeter,sleeve_ports,support_anchors,config):
    # Support identity is never an exclusion zone. Corners that happen to
    # be P1..Pn remain available as reinforcement origins.
    pairs=[]
    for sleeve in sorted({port.sleeve_id for port in sleeve_ports}):
        ports=sorted((p for p in sleeve_ports if p.sleeve_id==sleeve),key=lambda p:p.id)
        center=np.mean([p.attachment_mm for p in ports],axis=0)
        axis=np.asarray(ports[0].axis,float);axis/=max(np.linalg.norm(axis),1e-15)
        toward=np.mean(perimeter.points_mm,axis=0)-center;toward-=axis*(toward@axis)
        lateral=np.cross(axis,toward)
        if np.linalg.norm(lateral)<1e-8:lateral=np.cross(axis,np.array([1.,0.,0.]) if abs(axis[0])<.9 else np.array([0.,1.,0.]))
        lateral/=np.linalg.norm(lateral)
        ranked=[]
        for anchor,point in zip(perimeter.anchors,perimeter.points_mm):
            distance=float(np.linalg.norm(point-center))
            side=1 if (point-center)@lateral>=0 else -1
            ranked.append((distance,anchor.id,side,anchor,point))
        ranked.sort(key=lambda r:(-r[0],r[1]))
        # Alternate the farthest origins on opposing sides before other
        # corners/spans. This gives the square example both far corners.
        first=[]
        for side in (-1,1):
            match=next((r for r in ranked if r[2]==side),None)
            if match is not None:first.append(match)
        ordered=first+[r for r in ranked if r[1] not in {f[1] for f in first}]
        for distance,_label,side,anchor,point in ordered:
            for port in sorted(ports,key=lambda p:(float(np.linalg.norm(np.asarray(p.attachment_mm)-point)),p.id)):
                pairs.append(AnchorPair(anchor,port.anchor,port,side,distance))
    return tuple(pairs)


def perimeter_sleeve_topology(support_ids,sleeve_id='S1'):
    ids=tuple(support_ids)
    if not 3<=len(ids)<=8 or len(set(ids))!=len(ids):raise ValueError('INVALID_SUPPORT_IDENTITIES')
    return {'sleeve_id':sleeve_id,'branches':[{'from':label,'to':sleeve_id,'direction':'SUPPORT_TO_SLEEVE'} for label in ids],
            'route_groups':[],'forbidden_direct_diagonals':[],'dynamic_support_count':len(ids),
            'invariants':['PRESERVE_EXISTING_PERIMETER','NO_UNDECLARED_SUPPORTS','TERMINATE_ON_SLEEVE_STRUCTURAL_ENVELOPE']}


def build_frame_graph(perimeter,paths,config):
    nodes={a.id:FrameNode(a.id,tuple(p),'PERIMETER') for a,p in zip(perimeter.anchors,perimeter.points_mm)}
    members=[];seen=set()
    for path in paths:
        if path.route_id in seen:continue
        seen.add(path.route_id)
        for label,point,role in ((path.start_id,path.points_mm[0],'FREE'),(path.end_id,path.points_mm[-1],'PORT')):
            if label not in nodes:nodes[label]=FrameNode(label,tuple(float(x) for x in point),role)
        members.append(FrameMember(path.route_id,path.start_id,path.end_id,path,config.radius_mm if path.radius_mm is None else path.radius_mm))
    return FrameGraph(perimeter,tuple(nodes.values()),tuple(members))


def validate_connectivity(graph):
    connected={a.id for a in graph.perimeter.anchors};pending=list(graph.members)
    changed=True
    while changed:
        changed=False
        for member in list(pending):
            if member.start_id in connected or member.end_id in connected:
                connected.update((member.start_id,member.end_id));pending.remove(member);changed=True
    orphan=sorted({node for m in pending for node in (m.start_id,m.end_id)})
    return ConnectivityReport(not orphan,tuple(orphan))


def sweep_path_mesh(points_mm,radius_mm,radial_segments=16):
    """Constant-radius rings with parallel-transport frames, no POLY miters.

    The output is a capped nominal tube. Final union and post-Boolean sections
    remain separate checks; this does not claim collision-free self-contact.
    """
    pts=np.asarray(points_mm,float);radius=float(radius_mm);count=int(radial_segments)
    if pts.ndim!=2 or pts.shape[1]!=3 or len(pts)<2 or not np.isfinite(pts).all() or radius<=0 or count<6:raise ValueError('INVALID_SWEEP')
    delta=np.diff(pts,axis=0);lengths=np.linalg.norm(delta,axis=1)
    if np.any(lengths<=1e-8):raise ValueError('DUPLICATE_SWEEP_POINT')
    unit=delta/lengths[:,None];tangent=np.vstack((unit[0],unit[:-1]+unit[1:],unit[-1]))
    norm=np.linalg.norm(tangent,axis=1)
    if np.any(norm<1e-8):raise ValueError('SWEEP_CUSP')
    tangent/=norm[:,None]
    reference=np.eye(3)[int(np.argmin(np.abs(tangent[0])))];normal=np.cross(tangent[0],reference);normal/=np.linalg.norm(normal)
    theta=np.arange(count)*2*np.pi/count;vertices=[]
    for i,t in enumerate(tangent):
        normal=normal-t*(normal@t)
        if np.linalg.norm(normal)<1e-8:normal=np.cross(t,np.eye(3)[int(np.argmin(np.abs(t)))])
        normal/=np.linalg.norm(normal);binormal=np.cross(t,normal)
        ring=pts[i]+radius*(np.cos(theta)[:,None]*normal+np.sin(theta)[:,None]*binormal);vertices.extend(ring)
    faces=[]
    for i in range(len(pts)-1):
        for j in range(count):
            a=i*count+j;b=i*count+(j+1)%count;c=(i+1)*count+(j+1)%count;d=(i+1)*count+j
            faces.extend(((a,b,c),(a,c,d)))
    cap_a=len(vertices);vertices.append(pts[0]);cap_b=len(vertices);vertices.append(pts[-1])
    for j in range(count):faces.extend(((cap_a,(j+1)%count,j),(cap_b,(len(pts)-1)*count+j,(len(pts)-1)*count+(j+1)%count)))
    return np.asarray(vertices,float),np.asarray(faces,np.int64)


def split_lattice_primaries(paths,fractions=(.40,.72)):
    """Split actual sampled paths into shared semantic joints, without rerouting.

    The two internal stations are layout heuristics, not stiffness estimates.
    Junctions always use existing path vertices; no projected crossing is a joint.
    """
    from dataclasses import replace
    segments=[];junctions=[]
    for parent in paths:
        pts=np.asarray(parent.points_mm,float)
        if len(pts)<4:raise ValueError('INSUFFICIENT_PRIMARY_SPAN')
        arc=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(pts,axis=0),axis=1))]
        indices=[int(np.argmin(np.abs(arc-arc[-1]*f))) for f in fractions]
        if len(set(indices))!=2 or min(indices)<1 or max(indices)>=len(pts)-1:raise ValueError('INSUFFICIENT_PRIMARY_SPAN')
        labels=[parent.start_id]
        for level,index in enumerate(indices):
            label='J:'+parent.route_id+':'+str(level);labels.append(label)
            junctions.append({'id':label,'parent':parent.route_id,'level':level,'index':index,'point_mm':pts[index].copy()})
        labels.append(parent.end_id);cuts=[0]+indices+[len(pts)-1]
        for number,(a,b) in enumerate(zip(cuts,cuts[1:])):
            part=pts[a:b+1];length=float(np.linalg.norm(np.diff(part,axis=0),axis=1).sum())
            segments.append(replace(parent,route_id=parent.route_id+':SEG'+str(number),start_id=labels[number],end_id=labels[number+1],points_mm=_readonly(part,float),length_mm=length,weighted_cost=length))
    return tuple(segments),tuple(junctions)


def lattice_links(junctions):
    """Two crossbars and one diagonal form triangles between the primaries."""
    parents=list(dict.fromkeys(j['parent'] for j in junctions));links=[]
    for first,second in zip(parents,parents[1:]):
        a=sorted((j for j in junctions if j['parent']==first),key=lambda j:j['level'])
        b=sorted((j for j in junctions if j['parent']==second),key=lambda j:j['level'])
        if len(a)!=2 or len(b)!=2:raise ValueError('INVALID_LATTICE_JUNCTIONS')
        links.extend(((a[0]['id'],b[0]['id']),(a[1]['id'],b[1]['id']),(a[0]['id'],b[1]['id'])))
    return tuple(links)
