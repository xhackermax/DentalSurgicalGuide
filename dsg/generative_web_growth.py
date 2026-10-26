"""Adaptive branching and cell closure on the real IOS surface.

Existing branches are immutable physical curves. New edges bind explicit
stations on them and are rejected atomically if any geometric gate fails.
"""
from dataclasses import dataclass,replace
import hashlib
import numpy as np
from .geodesic_router import CandidatePath
from .ios_surface import _readonly

@dataclass
class Branch:
    key:str
    template:object
    points:np.ndarray
    radius:float
    metadata:dict
    nodes:dict

class BranchNetwork:
    def __init__(self,paths,metadata,primary_radius):
        groups={}
        for path in paths:
            key=path.route_id.rsplit(':SEG',1)[0] if ':SEG' in path.route_id else path.route_id
            groups.setdefault(key,[]).append(path)
        self.branches={}
        for key,parts in groups.items():
            parts.sort(key=lambda p:int(p.route_id.rsplit(':SEG',1)[1]) if ':SEG' in p.route_id else 0)
            points=[];nodes={0:parts[0].start_id}
            for part in parts:
                points.extend(part.points_mm if not points else part.points_mm[1:]);nodes[len(points)-1]=part.end_id
            row=dict(metadata[parts[0].route_id]);radius=primary_radius if parts[0].radius_mm is None else parts[0].radius_mm
            self.branches[key]=Branch(key,parts[0],_readonly(points,float),float(radius),row,nodes)
    def bind(self,key,index):
        branch=self.branches[key];index=int(index)
        if index not in branch.nodes:branch.nodes[index]='W:'+key+':'+str(index)
        return branch.nodes[index]
    def checkpoint(self):return {key:dict(branch.nodes)for key,branch in self.branches.items()}
    def rollback(self,checkpoint):
        for key in list(self.branches):
            if key not in checkpoint:self.branches.pop(key)
            else:self.branches[key].nodes=dict(checkpoint[key])
    def add(self,path,row):
        if path.route_id in self.branches:raise ValueError('DUPLICATE_GROWTH_BRANCH')
        radius=float(path.radius_mm);self.branches[path.route_id]=Branch(path.route_id,path,_readonly(path.points_mm,float),radius,dict(row),{0:path.start_id,len(path.points_mm)-1:path.end_id})
    def pack(self):
        paths=[];metadata={}
        for branch in self.branches.values():
            indices=sorted(branch.nodes)
            for n,(a,b)in enumerate(zip(indices,indices[1:])):
                points=branch.points[a:b+1];length=float(np.linalg.norm(np.diff(points,axis=0),axis=1).sum())
                path=replace(branch.template,route_id=branch.key+':SEG'+str(n),start_id=branch.nodes[a],end_id=branch.nodes[b],points_mm=_readonly(points,float),length_mm=length,radius_mm=branch.radius)
                paths.append(path);metadata[path.route_id]=dict(branch.metadata,continuous_branch=True,pre_faired=True)
        return tuple(paths),metadata
    def render(self,primary_radius):
        from .organic_reinforcement import smooth_network_paths
        paths,metadata=self.pack();return smooth_network_paths(paths,metadata,primary_radius)[1]

def _increment_clear(perimeter,network,new_key,config,constraints):
    """Recheck the new material against immutable certified older curves."""
    from .frame_generator import build_frame_graph,validate_connectivity
    from .frame_optimizer import _kernel,_intersection_outside_declared_joint
    from scipy.spatial import cKDTree
    paths,metadata=network.pack();graph=build_frame_graph(perimeter,paths,config)
    if not validate_connectivity(graph).valid:raise ValueError('GROWTH_ORPHAN_BRANCH')
    new=[m for m in graph.members if m.id.startswith(new_key+':SEG')]
    old=[m for m in graph.members if not m.id.startswith(new_key+':SEG')];kernel=_kernel()
    for member in new:
        for other in old:
            if _intersection_outside_declared_joint(member,other,kernel):raise ValueError('GROWTH_MEMBER_INTERSECTION')
        pts=member.path.points_mm;arc=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(pts,axis=0),axis=1))]
        mids=(pts[:-1]+pts[1:])*.5;lengths=np.linalg.norm(np.diff(pts,axis=0),axis=1);radius=member.radius_mm
        tree=cKDTree(mids)
        for i,choices in enumerate(tree.query_ball_point(mids,2*radius+float(lengths.max()))):
            for j in choices:
                if j<=i+1:continue
                p,q,d2=kernel.closest_points_segments(pts[i],pts[i+1],pts[j],pts[j+1])
                if arc[j]+np.linalg.norm(q-pts[j])-arc[i]-np.linalg.norm(p-pts[i])>3*radius and d2<(2*radius-1e-8)**2:raise ValueError('GROWTH_SELF_INTERSECTION')
    return graph


def growth_frame_anchors(surface,request,router):
    """Sample real upper-frame triangles; retain their exact source vertex."""
    from .ios_surface import SurfaceAnchor
    data=np.load(request['frame_support_file'],allow_pickle=False);vertices=data['vertices'];faces=data['triangles']
    axis=np.asarray(request['reinforcement_envelope']['frame_entry_axis'],float);axis/=np.linalg.norm(axis)
    triangles=vertices[faces];normal=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]);normal/=np.maximum(1e-12,np.linalg.norm(normal,axis=1))[:,None]
    choices=np.unique(faces[normal@axis>.5]);selected=[np.asarray(r['original_mm'])for r in request['supports']];rows=[];anchors=[];originals={}
    while len(rows)<100 and len(choices):
        points=vertices[choices];distance=np.linalg.norm(points[:,None]-np.asarray(selected)[None,:],axis=2).min(axis=1);pick=int(np.argmax(distance))
        if distance[pick]<2.3:break
        index=int(choices[pick]);point=vertices[index];selected.append(point);choices=np.delete(choices,pick)
        key='GF'+str(index)
        try:anchor,projected,offset=router.project(key,point)
        except ValueError:continue
        if offset>5.:continue
        anchors.append(anchor);originals[key]=point
        rows.append(dict(id=key,face_index=int(anchor.face_index),barycentric=list(anchor.barycentric),original_mm=point.tolist(),point_mm=projected.tolist(),frame_vertex_index=index,upper_frame_surface=True))
    request['web_growth_supports']=rows
    return tuple(anchors),originals

def growth_perimeter(perimeter,surface,request):
    from .ios_surface import SurfaceAnchor
    rows=request.get('web_growth_supports',[])
    anchors=tuple(SurfaceAnchor(r['id'],surface.fingerprint,int(r['face_index']),tuple(r['barycentric']),0)for r in rows)
    return replace(perimeter,points_mm=np.vstack((perimeter.points_mm,[r['original_mm']for r in rows])),anchors=perimeter.anchors+anchors)if rows else perimeter

def grow_web(surface,perimeter,paths,metadata,supports,originals,constraints,config,request,progress,*,target_edges=18,native_accept=None):
    from scipy.spatial import cKDTree,ConvexHull
    from .spiderweb import SurfaceWebRouter
    from .ios_surface import validate_anchor,check_mesh_obstacles
    from .geodesic_router import surface_path_certificate
    from .organic_reinforcement import fair_open_path,mesh_fold_report
    from .reinforcement_envelope import validate_path_envelope
    from .frame_swept_clearance_core import check_swept_tube_clearance
    from .generative_frame_worker import central_ios_body
    request=request or {};network=BranchNetwork(paths,metadata,config.radius_mm)
    radius=min(float(config.radius_mm),max(.6,float(config.radius_mm)*.5));pitch=max(1.5,2.8*radius)
    router=SurfaceWebRouter(surface,constraints,request,radius);anchors={a.id:a for a in supports};frame_points={key:np.asarray(originals[key],float)for key in anchors}
    frame_index=None
    if request.get('frame_support_file'):
        from .ios_surface import SolidClearanceIndex
        data=np.load(request['frame_support_file'],allow_pickle=False)
        frame_index=SolidClearanceIndex({'label':'FRAME','vertices_mm':data['vertices'],'triangles':data['triangles'],'closed':True})
        entry=np.asarray(request['reinforcement_envelope']['frame_entry_axis'],float);entry/=np.linalg.norm(entry)
        u=np.cross(entry,np.eye(3)[np.argmin(abs(entry))]);u/=np.linalg.norm(u);v=np.cross(entry,u);basis=np.array([u,v]).T
        hull=ConvexHull(data['vertices']@basis);xy=surface.vertices_mm@basis
        router.allowed&=np.all(xy@hull.equations[:,:2].T+hull.equations[:,2]<=2.5*radius,axis=1)
        router.edge_ok&=router.allowed[router.src]&router.allowed[router.dst]
    if frame_index is not None:
        extra,positions=growth_frame_anchors(surface,request,router);anchors.update({a.id:a for a in extra});frame_points.update(positions);perimeter=growth_perimeter(perimeter,surface,request)
    allowed_ids=np.flatnonzero(router.allowed);allowed_tree=cKDTree(surface.vertices_mm[allowed_ids])
    def ready(row):
        face=surface.triangles[row['anchor'].face_index]
        if not router.allowed[face].all():
            distance,nearest=allowed_tree.query(row['point'],k=1);index=int(allowed_ids[int(nearest)])
            if distance>max(2.,row['distance']+2*radius):return None
            anchor,projected,offset=router.project(row['id'],surface.vertices_mm[index])
            row=dict(row,anchor=anchor,projected=projected,distance=float(np.linalg.norm(row['point']-projected)))
        vertices=surface.triangles[row['anchor'].face_index];vertices=vertices[router.allowed[vertices]]
        row['components']=set(router.base_components[vertices])
        return row if row['components']else None
    def adds_visible_material(point):
        if not frame_index.contains(point):return True
        best=None
        for ids,tree,extent in frame_index.buckets:
            for row in np.atleast_1d(tree.query(point,k=min(8,len(ids)))[1]):
                tri=frame_index.triangles[int(ids[int(row)])]
                nearest,d2=frame_index.kernel.closest_point_on_triangle(point,*tri)
                if best is None or d2<best[0]:best=(d2,tri)
        for ids,tree,extent in frame_index.buckets:
            for row in tree.query_ball_point(point,np.sqrt(best[0])+extent+1e-9):
                tri=frame_index.triangles[int(ids[int(row)])]
                nearest,d2=frame_index.kernel.closest_point_on_triangle(point,*tri)
                if d2<best[0]:best=(d2,tri)
        normal=np.cross(best[1][1]-best[1][0],best[1][2]-best[1][0]);normal/=np.linalg.norm(normal)
        return best[0]<(radius-.12)**2 and np.dot(normal,entry)>.2
    used_pairs=set();errors=[];accepted=[];attempts=0;budget=max(200,30*target_edges);node_cache={}
    def degrees():
        result={}
        for branch in network.branches.values():
            for index,label in branch.nodes.items():result[label]=result.get(label,0)+(1 if index in [0,len(branch.points)-1]else 2)
        return result
    def catalog():
        degree=degrees();rows=[]
        for key,anchor in anchors.items():
            if degree.get(key,0)>=2:continue
            point=frame_points[key];projected=validate_anchor(surface,anchor)
            rows.append({'id':key,'frame':True,'parent':None,'point':point,'projected':projected,'distance':float(np.linalg.norm(point-projected)),'anchor':anchor})
        for key,branch in network.branches.items():
            pts=branch.points;arc=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(pts,axis=0),axis=1))];last=-100.
            neck_a=max(2*branch.radius+radius,float(branch.metadata.get('frame_neck_start_mm')or 0)+radius)
            neck_b=max(2*branch.radius+radius,float(branch.metadata.get('frame_neck_end_mm')or 0)+radius)
            for index in np.flatnonzero((arc>=neck_a)&(arc<=arc[-1]-neck_b)):
                if arc[index]-last<pitch:continue
                existing=branch.nodes.get(int(index))
                if existing and degree.get(existing,2)>=4:continue
                distances=[abs(arc[index]-arc[i]) for i in branch.nodes if i!=index]
                if distances and min(distances)<branch.radius+2*radius+.35:continue
                cache_key=(key,int(index))
                if cache_key not in node_cache:
                    try:node_cache[cache_key]=router.project('W:'+key+':'+str(index),pts[index],branch.template.surface_vertex_ids)
                    except ValueError:node_cache[cache_key]=None
                projected=node_cache[cache_key]
                if projected is None:continue
                anchor,point,distance=projected
                if distance>branch.radius*.8+.03:continue
                rows.append({'id':existing or anchor.id,'frame':False,'parent':key,'index':int(index),'point':pts[index],'projected':point,'distance':distance,'anchor':anchor});last=arc[index]
        return [row for row in (ready(r)for r in rows)if row is not None]
    while len(accepted)<target_edges and attempts<budget:
        nodes=catalog();skeleton=np.vstack([b.points for b in network.branches.values()]);tree=cKDTree(skeleton);pairs=[]
        for i,a in enumerate(nodes):
            for b in nodes[i+1:]:
                pair=tuple(sorted((a['id'],b['id'])))
                if pair in used_pairs or not a['components']&b['components']or (not a['frame'] and a['parent']==b['parent']):continue
                length=float(np.linalg.norm(a['point']-b['point']))
                if length<max(3.,4*radius) or length>30.:continue
                gap=float(tree.query((a['point']+b['point'])*.5)[0]);score=gap+.1*length
                # Prefer new bifurcations over repeatedly spanning the same two
                # main radials; both remain eligible when space is available.
                if a['frame']!=b['frame']:score+=6.
                elif not a['frame']:score+=3.
                family=int(a['frame'])+int(b['frame'])
                pairs.append((-score,a,b,pair))
        pools=[[]for _ in range(3)]
        for row in sorted(pairs,key=lambda row:(row[0],row[3])):pools[int(row[1]['frame'])+int(row[2]['frame'])].append(row)
        # Alternate branch/branch, frame/branch and frame/frame proposals so
        # hundreds of high-scoring but buried frame chords cannot starve cells.
        pairs=[]
        for index in range(max((len(pool)for pool in pools),default=0)):
            for pool in pools:
                if index<len(pool):pairs.append(pool[index])
        advanced=False
        for _,a,b,pair in pairs:
            if attempts>=budget:break
            attempts+=1;used_pairs.add(pair);checkpoint=network.checkpoint()
            for row in [a,b]:
                if not row['frame']:row['id']=network.bind(row['parent'],row['index'])
            if not a['frame'] and b['frame']:a,b=b,a
            start,end=a['id'],b['id'];contacts={}
            obstacles=[]
            for key,branch in network.branches.items():
                obstacles.append({'id':key,'points':branch.points,'radius':branch.radius})
                for label,point in [(start,a['point']),(end,b['point'])]:
                    if label in branch.nodes.values():contacts.setdefault(key,[]).append(point)
            progress(f'Trama orgánica · {len(accepted)}/{target_edges} enlaces · prueba {attempts}')
            route=router.route(replace(a['anchor'],id=start),replace(b['anchor'],id=end),obstacles=obstacles,contacts=contacts)
            if route is None:route=router.route(replace(a['anchor'],id=start),replace(b['anchor'],id=end),obstacles=obstacles,contacts=contacts,variant=1)
            if route is None:
                network.rollback(checkpoint);errors.append({'reason':'GROWTH_CORRIDOR_BLOCKED','pair':pair});continue
            try:
                if route.length_mm>max(8.,2.5*float(np.linalg.norm(a['point']-b['point']))):raise ValueError('GROWTH_UNPRODUCTIVE_DETOUR')
                if not surface_path_certificate(surface,route.points_mm,config.surface_tolerance_mm)['valid']:raise ValueError('GROWTH_REFERENCE_OFF_IOS')
                reference=route.points_mm;arc=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(reference,axis=0),axis=1))]
                trim_a=min(.2*arc[-1],a['distance']+1.5*radius);trim_b=min(.2*arc[-1],b['distance']+1.5*radius)
                middle=reference[(arc>=trim_a)&(arc<=arc[-1]-trim_b)]
                if not len(middle):raise ValueError('GROWTH_NO_IOS_BODY')
                raw=np.vstack((a['point'],middle,b['point']));raw=raw[np.r_[True,np.linalg.norm(np.diff(raw,axis=0),axis=1)>1e-7]]
                curve,info=fair_open_path(raw,radius,deviation_ratio=.55)
                for _ in range(3):
                    if mesh_fold_report(curve,radius)['valid']:break
                    curve,info=fair_open_path(curve,radius)
                if not mesh_fold_report(curve,radius)['valid']:raise ValueError('GROWTH_TUBE_FOLD')
                frame_a=a['distance']if a['frame']else None;frame_b=b['distance']if b['frame']else None
                validate_path_envelope(curve,radius,request,frame_projection_distance_mm=frame_a,frame_end_projection_distance_mm=frame_b)
                if not check_swept_tube_clearance(curve,[radius]*len(curve),constraints.protected_zones).clear:raise ValueError('GROWTH_PROTECTED_VOLUME')
                clear,reason=check_mesh_obstacles(curve,radius,constraints.mesh_obstacles)
                if not clear:raise ValueError(reason)
                body,_=central_ios_body(curve,a['distance'],b['distance'],radius)
                if not surface_path_certificate(surface,body,radius*.8+config.surface_tolerance_mm)['valid']:raise ValueError('GROWTH_LOST_IOS_SUPPORT')
                distance=tree.query(body)[0]
                if float(distance.max(initial=0))<2*radius+.35:raise ValueError('GROWTH_NO_NEW_CELL')
                if frame_index is not None:
                    samples=body[::max(1,len(body)//16)]
                    if sum(adds_visible_material(p)for p in samples)<3:raise ValueError('GROWTH_ENCASED_IN_FRAME')
                key='GROW:'+hashlib.sha256((start+'|'+end+'|'+route.route_id).encode()).hexdigest()[:16]
                length=float(np.linalg.norm(np.diff(curve,axis=0),axis=1).sum());candidate=replace(route,route_id=key,points_mm=_readonly(curve,float),length_mm=length,radius_mm=radius)
                row={'role':'SECONDARY','sleeve_id':'','pre_faired':True,'continuous_branch':True,'web_kind':'GROWTH','reference_points_mm':reference.tolist(),'joint_neck_start_mm':a['distance'],'joint_neck_end_mm':b['distance'],'frame_neck_start_mm':frame_a,'frame_neck_end_mm':frame_b}
                existing=network.render(config.radius_mm);network.add(candidate,row);_increment_clear(perimeter,network,key,config,constraints)
                if native_accept is not None:
                    piece=next(p for p in network.render(config.radius_mm)if p['route_id']==key)
                    verdict=native_accept(piece,existing)
                    if not verdict.get('valid'):raise ValueError(verdict.get('reason','GROWTH_NATIVE_REJECTION'))
                accepted.append(key);advanced=True;break
            except ValueError as exc:
                network.rollback(checkpoint);errors.append({'reason':str(exc),'pair':pair})
                if request.get('web_diagnostics'):print('GROWTH_REJECT',str(exc),pair,flush=True)
        if not advanced:break
    revised,meta=network.pack()
    return revised,meta,{'web_growth_branches':len(accepted),'web_growth_target':target_edges,'web_growth_attempts':attempts,'web_growth_radius_mm':radius,'web_growth_kind':'GEODESIC_BRANCHING_AND_CELL_CLOSURE','existing_curves_preserved':True},errors
