"""Adaptive radial web on the actual IOS; topology is independent of triangles."""
from dataclasses import replace
import hashlib
import numpy as np
from .ios_surface import SurfaceAnchor,_readonly,validate_anchor
from .geodesic_router import CandidatePath,zone_distances

TOPOLOGY='ADAPTIVE_SPIDERWEB_V1'
_ROUTER_CACHE={}

def ring_links(parents,levels=2,closed=False):
    parents=list(parents)
    if len(parents)<2 or levels<2:raise ValueError('SPIDERWEB_INCOMPLETE_RADIALS')
    if closed and len(parents)<3:raise ValueError('SPIDERWEB_CLOSED_RING_NEEDS_THREE_RADIALS')
    pairs=list(zip(parents,parents[1:]))
    if closed:pairs.append((parents[-1],parents[0]))
    return [((a,level),(b,level)) for level in range(levels) for a,b in pairs]

def split_spoke(parent,indices):
    points=np.asarray(parent.points_mm,float);indices=list(map(int,indices))
    if len(indices)<2 or indices!=sorted(set(indices)) or indices[0]<=0 or indices[-1]>=len(points)-1:raise ValueError('SPIDERWEB_INVALID_JOINTS')
    labels=[parent.start_id]+['J:'+parent.route_id+':'+str(i) for i in range(len(indices))]+[parent.end_id]
    cuts=[0]+indices+[len(points)-1];parts=[];nodes=[]
    for level,index in enumerate(indices):nodes.append({'id':labels[level+1],'parent':parent.route_id,'level':level,'index':index,'point_mm':points[index].copy()})
    for i,(a,b) in enumerate(zip(cuts,cuts[1:])):
        p=points[a:b+1];length=float(np.linalg.norm(np.diff(p,axis=0),axis=1).sum())
        parts.append(replace(parent,route_id=parent.route_id+':SEG'+str(i),start_id=labels[i],end_id=labels[i+1],points_mm=_readonly(p,float),length_mm=length,weighted_cost=length))
    return tuple(parts),tuple(nodes)

def verify_web(pieces,*,frame_rim=False,frame_nodes=()):
    prim=[p for p in pieces if p['member_role']=='PRIMARY'];arcs=[p for p in pieces if p['member_role']=='SECONDARY' and p.get('web_kind')!='GROWTH']
    if len(prim)<2 or not arcs:raise ValueError('SPIDERWEB_INCOMPLETE')
    owners={node:p['route_id'] for p in prim for node in p['nodes']};sectors={};graph={p['route_id']:set() for p in prim};seen=set()
    for arc in arcs:
        a,b=arc['origin'],arc['port'];level=arc.get('web_level')
        if a not in owners or b not in owners or owners[a]==owners[b] or level is None:raise ValueError('SPIDERWEB_INVALID_ARC')
        edge=tuple(sorted((a,b)))
        if edge in seen:raise ValueError('SPIDERWEB_DUPLICATE_ARC')
        seen.add(edge);pair=tuple(sorted((owners[a],owners[b])))
        sectors.setdefault(pair,{}).setdefault(int(level),[]).append(arc)
    complete={pair:levels for pair,levels in sectors.items() if len(levels)>=(1 if frame_rim else 2)}
    if len(complete)!=len(sectors):raise ValueError('SPIDERWEB_INCOMPLETE_RING_SECTOR')
    for a,b in complete:graph[a].add(b);graph[b].add(a)
    by_sleeve={}
    for p in prim:by_sleeve.setdefault(p.get('sleeve_id',''),set()).add(p['route_id'])
    for members in by_sleeve.values():
        if len(members)<2:raise ValueError('SPIDERWEB_INCOMPLETE_RADIALS')
        reached=set();pending=[next(iter(members))]
        while pending:
            node=pending.pop()
            if node in reached:continue
            reached.add(node);pending.extend(graph[node]-reached)
        if reached!=members or any(not graph[node] for node in members):raise ValueError('SPIDERWEB_DISCONNECTED')
    # Two different attachment stations per radial are needed to form a cell.
    for parent in graph:
        labels={a[key] for a in arcs for key in ('origin','port') if owners[a[key]]==parent}
        if len(labels)<(1 if frame_rim else 2):raise ValueError('SPIDERWEB_INCOMPLETE_RADIAL_STATIONS')
    resolved=set(frame_nodes)|{node for p in prim+arcs for node in p.get('nodes',{})}|{p[key]for p in prim+arcs for key in ('origin','port')if key in p}
    growth=[p for p in pieces if p.get('web_kind')=='GROWTH'];pending=list(growth)
    while pending:
        advanced=False
        for branch in pending[:]:
            if branch['origin']==branch['port']:raise ValueError('SPIDERWEB_GROWTH_LOOP')
            if {branch['origin'],branch['port']}<=resolved:
                edge=tuple(sorted((branch['origin'],branch['port'])))
                for older in pieces:
                    if older is branch or 'points_mm'not in branch or 'points_mm'not in older:continue
                    a=np.asarray(branch['points_mm']);b=np.asarray(older['points_mm'])
                    if a.shape==b.shape and (np.array_equal(a,b)or np.array_equal(a,b[::-1])):raise ValueError('SPIDERWEB_DUPLICATE_CURVE')
                seen.add(edge);resolved.update(branch.get('nodes',{}));pending.remove(branch);advanced=True
        if not advanced:raise ValueError('SPIDERWEB_ORPHAN_GROWTH')
    levels=sorted({int(a['web_level']) for a in arcs})
    return {'web_growth_connected_branches':len(growth),'spiderweb_topology_verified':True,'web_ring_levels':len(levels)+int(frame_rim),'web_internal_ring_levels':len(levels),'web_existing_frame_outer_ring':bool(frame_rim),'web_sector_count':len(complete),'web_closed_rings':len(levels) if len(prim)>=3 and all(len(graph[p['route_id']])==2 for p in prim) else 0}

def frame_rim_available(request):
    """The existing frame closes a web only if its real mesh has a handle."""
    if not request.get('frame_support_file') or not request.get('frame_digest'):return False
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import connected_components
    data=np.load(request['frame_support_file'],allow_pickle=False);faces=np.asarray(data['triangles'],int)
    if not len(faces):return False
    edges=np.sort(np.concatenate((faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]])),axis=1)
    edges,counts=np.unique(edges,axis=0,return_counts=True)
    if np.any(counts!=2):return False
    used=np.unique(faces);graph=csr_matrix((np.ones(len(edges)),(edges[:,0],edges[:,1])),shape=(len(data['vertices']),len(data['vertices'])))
    _,labels=connected_components(graph,directed=False)
    return bool(len(np.unique(labels[used]))==1 and len(used)-len(edges)+len(faces)<=0)

def segment_pair_witnesses(a,b,c,d):
    """Vectorized finite-segment closest witnesses, including degenerate ends."""
    a,b=np.asarray(a,float),np.asarray(b,float);c,d=np.asarray(c,float),np.asarray(d,float)
    u=b-a;v=d-c;w=a-c
    aa=np.einsum('...i,...i->...',u,u);ee=np.einsum('...i,...i->...',v,v);ff=np.einsum('...i,...i->...',v,w);cc=np.einsum('...i,...i->...',u,w);bb=np.einsum('...i,...i->...',u,v)
    den=aa*ee-bb*bb;ss=np.clip(np.divide(bb*ff-cc*ee,den,out=np.zeros_like(den),where=abs(den)>1.e-12),0.,1.)
    tt=np.divide(bb*ss+ff,ee,out=np.zeros_like(den),where=ee>1.e-12)
    ss=np.where(tt<0,np.clip(-cc/np.maximum(aa,1.e-12),0.,1.),ss)
    ss=np.where(tt>1,np.clip((bb-cc)/np.maximum(aa,1.e-12),0.,1.),ss);tt=np.clip(tt,0.,1.)
    ss=np.where(aa<=1.e-12,0.,ss);tt=np.where(aa<=1.e-12,np.clip(ff/np.maximum(ee,1.e-12),0.,1.),tt)
    tt=np.where(ee<=1.e-12,0.,tt);ss=np.where(ee<=1.e-12,np.clip(-cc/np.maximum(aa,1.e-12),0.,1.),ss)
    return a+ss[...,None]*u,c+tt[...,None]*v

class SurfaceWebRouter:
    """Cached IOS CSR graph with physical masks and explicit surface anchors."""
    def __init__(self,surface,constraints,request,radius):
        from scipy.spatial import cKDTree
        self.surface=surface;self.constraints=constraints;self.request=request or {};self.radius=float(radius)
        self.src=np.repeat(np.arange(len(surface.vertices_mm)),np.diff(surface.csr_offsets));self.dst=surface.csr_destinations
        self.allowed=np.ones(len(surface.vertices_mm),bool) if constraints.allowed_vertices is None else np.array(constraints.allowed_vertices,bool)
        points=surface.vertices_mm
        if self.request.get('reinforcement_envelope'):
            from .reinforcement_envelope import frame_barrier
            for sleeve in self.request['sleeves']:
                axis=np.asarray(sleeve['entry_axis'],float);axis/=np.linalg.norm(axis);local=points-np.asarray(sleeve['center']);axial=local@axis
                radial=np.linalg.norm(local-np.outer(axial,axis),axis=1);half=float(sleeve['height_mm'])*.5
                self.allowed&=(axial+self.radius<=half-.05)
                self.allowed&=~((abs(abs(axial)-half)<=self.radius+.05)&(radial<=sleeve['outer_radius_mm']+self.radius))
            if self.request.get('frame_lower_surface_file'):
                barrier=frame_barrier(self.request['frame_lower_surface_file'])
                self.allowed&=np.asarray([not barrier.near(p,self.radius+.05) for p in points])
        self.edge_ok=self.allowed[self.src]&self.allowed[self.dst]
        for zone in constraints.protected_zones:
            distances=zone_distances(points,zone)
            self.edge_ok&=np.minimum(distances[self.src],distances[self.dst])-surface.csr_lengths_mm*.5>self.radius+.01
        self.penalty=np.zeros(len(points)) if constraints.vertex_penalty is None else np.asarray(constraints.vertex_penalty,float).copy()
        self.triangles=points[surface.triangles];self.centers=self.triangles.mean(axis=1);self.tree=cKDTree(self.centers);self.corridors={}
        self.vertex_tree=cKDTree(points);self.radial_field=None;self.radial_fields={};self.obstacle_cache={};self.edge_contact_cache={};self.last_failure={}
        from scipy.sparse import csr_matrix
        from scipy.sparse.csgraph import connected_components
        base=csr_matrix((np.ones(np.count_nonzero(self.edge_ok)),(self.src[self.edge_ok],self.dst[self.edge_ok])),shape=(len(points),len(points)))
        _,self.base_components=connected_components(base,directed=False)
        if self.request.get('ports'):
            from scipy.sparse.csgraph import dijkstra
            graph=csr_matrix((surface.csr_lengths_mm,(self.src,self.dst)),shape=(len(points),len(points)))
            for sid in {p['sleeve_id'] for p in self.request['ports']}:
                seeds=np.unique(self.vertex_tree.query(np.asarray([p['point_mm'] for p in self.request['ports'] if p['sleeve_id']==sid],float))[1])
                self.radial_fields[sid]=dijkstra(graph,directed=False,indices=seeds,min_only=True)
            self.radial_field=next(iter(self.radial_fields.values()))
        if self.request.get('web_diagnostics'):print('WEB_GRAPH',len(points),int(self.allowed.sum()),int(self.edge_ok.sum()),flush=True)
    def project(self,label,point,vertex_ids=None):
        from scipy.spatial import cKDTree
        from .frame_optimizer import _kernel
        kernel=_kernel();point=np.asarray(point,float)
        key=tuple(vertex_ids) if vertex_ids else ()
        if key not in self.corridors:
            ids=np.flatnonzero(np.isin(self.surface.triangles,np.asarray(key,int)).any(axis=1)) if key else np.arange(len(self.triangles))
            if not len(ids):raise ValueError('SPIDERWEB_MISSING_IOS_CORRIDOR')
            tri=self.triangles[ids];centers=self.centers[ids];radii=np.linalg.norm(tri-centers[:,None,:],axis=2).max(axis=1);bins=np.floor(np.log2(np.maximum(radii,1.e-6))).astype(int)
            buckets=[]
            for bin_id in np.unique(bins):
                members=ids[bins==bin_id];buckets.append((members,cKDTree(self.centers[members]),float(radii[bins==bin_id].max())))
            self.corridors[key]=(ids,cKDTree(centers),buckets)
        ids,tree,buckets=self.corridors[key];best=None
        def inspect(face):
            nonlocal best
            triangle=self.triangles[face];projected,distance=kernel.closest_point_on_triangle(point,*triangle)
            if best is None or distance<best[0]:best=(distance,int(face),projected)
        for i in np.atleast_1d(tree.query(point,k=min(24,len(ids)))[1]):inspect(ids[int(i)])
        for members,index,extent in buckets:
            for i in index.query_ball_point(point,best[0]**.5+extent+1.e-8):inspect(members[i])
        d2,face,projected=best;tri=self.triangles[face];uv=np.linalg.lstsq(np.column_stack((tri[1]-tri[0],tri[2]-tri[0])),projected-tri[0],rcond=None)[0]
        bary=np.clip([1.-uv.sum(),uv[0],uv[1]],0.,1.);bary/=bary.sum()
        return SurfaceAnchor(label,self.surface.fingerprint,face,tuple(bary),int(self.surface.components[self.surface.triangles[face,0]]),'WEB_JUNCTION'),projected,float(d2**.5)
    def route(self,start,end,*,obstacles=(),contacts=None,target_distance=None,ring_band=None,variant=0):
        from scipy.spatial import cKDTree
        from scipy.sparse import csr_matrix
        from scipy.sparse.csgraph import dijkstra
        contacts=contacts or {};allowed=self.allowed.copy();penalty=self.penalty.copy();xyz=self.surface.vertices_mm;obstacle_edges=np.ones(len(self.src),bool)
        if ring_band is not None and self.radial_field is not None:allowed&=(self.radial_field>=ring_band[0])&(self.radial_field<=ring_band[1])
        base_a=self.surface.triangles[start.face_index];base_b=self.surface.triangles[end.face_index]
        base_a=base_a[allowed[base_a]];base_b=base_b[allowed[base_b]]
        if not len(base_a) or not len(base_b) or not set(self.base_components[base_a])&set(self.base_components[base_b]):
            self.last_failure={'start_vertices':len(base_a),'end_vertices':len(base_b),'start_components':self.base_components[base_a].tolist(),'end_components':self.base_components[base_b].tolist()}
            return None
        for obstacle in obstacles:
            pts=np.asarray(obstacle['points'],float);r=float(obstacle['radius']);samples=[];spacing=max(.15,r*.4)
            key=(obstacle['id'],r,hashlib.sha256(pts.tobytes()).hexdigest())
            if key not in self.obstacle_cache:
                for a,b in zip(pts,pts[1:]):samples.extend(a+(b-a)*t for t in np.linspace(0,1,max(2,int(np.linalg.norm(b-a)/spacing)+2)))
                self.obstacle_cache[key]=cKDTree(np.asarray(samples)).query(xyz)[0]
            if len(self.obstacle_cache)>24:
                oldest=next(iter(self.obstacle_cache))
                if oldest!=key:self.obstacle_cache.pop(oldest);self.edge_contact_cache.pop(oldest,None)
            distance=self.obstacle_cache[key];clear=distance>r+self.radius+spacing*.5
            if key not in self.edge_contact_cache:
                possible=np.flatnonzero(np.minimum(distance[self.src],distance[self.dst])-self.surface.csr_lengths_mm*.5<=r+self.radius+spacing*.5)
                aa=xyz[self.src[possible]];bb=xyz[self.dst[possible]];hits=[];witness_a=[];witness_b=[]
                for c,d in zip(pts,pts[1:]):
                    pp,qq=segment_pair_witnesses(aa,bb,c,d);mask=np.einsum('ij,ij->i',pp-qq,pp-qq)<=(r+self.radius+.01)**2
                    if np.any(mask):hits.extend(possible[mask]);witness_a.extend(pp[mask]);witness_b.extend(qq[mask])
                self.edge_contact_cache[key]=(np.asarray(hits,int),np.asarray(witness_a,float).reshape(-1,3),np.asarray(witness_b,float).reshape(-1,3))
            ids,wp,wq=self.edge_contact_cache[key];authorized=np.zeros(len(ids),bool);edge_clear=np.ones(len(self.src),bool)
            for point in contacts.get(obstacle['id'],[]):
                authorized|=(np.linalg.norm(wp-point,axis=1)<=3.*max(r,self.radius))&(np.linalg.norm(wq-point,axis=1)<=3.*max(r,self.radius))
            edge_clear[ids[~authorized]]=False
            for point in contacts.get(obstacle['id'],[]):
                near=np.linalg.norm(xyz-point,axis=1)<=3.*max(r,self.radius)
                clear|=near
            if variant==0:obstacle_edges&=edge_clear
            if variant==0:allowed&=clear
            penalty+=20.*np.maximum(0.,1.-distance/(r+self.radius+spacing))
        keep=self.edge_ok&allowed[self.src]&allowed[self.dst]&obstacle_edges
        if target_distance is not None and self.radial_field is not None:
            field=np.nan_to_num(self.radial_field,nan=1000.,posinf=1000.);penalty+=float(16.+variant*8.)*np.abs(field-target_distance)/max(1.,target_distance*.2)
        weights=self.surface.csr_lengths_mm*(1.+(penalty[self.src]+penalty[self.dst])*.5)
        graph=csr_matrix((weights[keep],(self.src[keep],self.dst[keep])),shape=(len(xyz),len(xyz)))
        av=self.surface.triangles[start.face_index];bv=self.surface.triangles[end.face_index];av=av[allowed[av]];bv=bv[allowed[bv]]
        self.last_failure={'start_vertices':len(av),'end_vertices':len(bv),'start_components':self.base_components[av].tolist(),'end_components':self.base_components[bv].tolist()}
        if not len(av) or not len(bv) or not set(self.base_components[av])&set(self.base_components[bv]):return None
        a=validate_anchor(self.surface,start);b=validate_anchor(self.surface,end)
        distance,pred=dijkstra(graph,directed=False,indices=av,return_predecessors=True)
        score=distance[:,bv]+np.linalg.norm(xyz[av]-a,axis=1)[:,None]+np.linalg.norm(xyz[bv]-b,axis=1)[None,:]
        i,j=np.unravel_index(np.argmin(score),score.shape)
        if not np.isfinite(score[i,j]):return None
        current=int(bv[j]);chain=[current];source=int(av[i])
        while current!=source:
            current=int(pred[i,current])
            if current<0:return None
            chain.append(current)
            if len(chain)>len(xyz):raise ValueError('SPIDERWEB_INVALID_PREDECESSOR')
        chain.reverse();points=np.vstack((a,xyz[chain],b));points=points[np.r_[True,np.linalg.norm(np.diff(points,axis=0),axis=1)>1.e-7]]
        if len(points)<2:return None
        length=float(np.linalg.norm(np.diff(points,axis=0),axis=1).sum());key=hashlib.sha256((start.id+'|'+end.id+'|'+str(chain)).encode()).hexdigest()[:20]
        return CandidatePath(key,start.id,end.id,_readonly(points,float),tuple(chain),length,float(score[i,j]),'IOS_GEODESIC_WEB',int(variant),self.radius)

def generate_spiderweb_paths(surface,perimeter,primary,owners,supports,originals,sleeves,constraints,config,progress,model_index=None,*,request=None,organic_primary_paths=None,**unused):
    """Search independent attachment stations; preserve the fair radial bodies.

    Ring arcs follow the IOS graph. Only their bounded terminal necks leave
    that reference to join the physical radial meshes, checked by the adapter.
    """
    from .organic_reinforcement import fair_open_path,mesh_fold_report,smooth_network_paths
    from .geodesic_router import surface_path_certificate
    from .frame_generator import build_frame_graph
    from .frame_optimizer import evaluate_frame
    from .reinforcement_coverage import continuous_groups
    from .reinforcement_envelope import validate_path_envelope
    from .frame_swept_clearance_core import CylinderKeepOut,check_swept_tube_clearance
    from .ios_surface import check_mesh_obstacles
    from .generative_frame_worker import central_ios_body
    request=request or {};radius=min(config.radius_mm,max(.6,.7*config.radius_mm))
    zones=tuple(constraints.protected_zones)+tuple(CylinderKeepOut(s['id']+':WEB_LUMEN',tuple(s['center']),tuple(s['axis']),s['inner_radius_mm'],s['height_mm']*.5) for s in sleeves.values())
    local=replace(constraints,protected_zones=zones)
    constraint_stamp=tuple(None if a is None else hashlib.sha256(np.asarray(a).tobytes()).hexdigest() for a in (local.allowed_vertices,local.vertex_penalty))
    cache_key=(surface.fingerprint,request.get('case_fingerprint'),request.get('frame_lower_surface_file'),radius,repr(zones),constraint_stamp)
    router=_ROUTER_CACHE.get(cache_key)
    if router is None:
        router=SurfaceWebRouter(surface,local,request,radius)
        _ROUTER_CACHE.clear();_ROUTER_CACHE[cache_key]=router
    raw={p.route_id:p for p in primary};parents={};catalog={};errors=[];tasks=[];closed_groups=[];ring_targets={}
    for path in primary:
        if organic_primary_paths and path.route_id in organic_primary_paths:parent=organic_primary_paths[path.route_id]
        else:
            pts=np.asarray(path.points_mm,float);arc=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(pts,axis=0),axis=1))]
            curve,_=fair_open_path(pts,config.radius_mm,[int(np.argmin(abs(arc-arc[-1]*f))) for f in (.4,.72)])
            parent=replace(path,points_mm=_readonly(curve,float))
        parents[parent.route_id]=parent
        pts=parent.points_mm;arc=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(pts,axis=0),axis=1))]
        # Physical arclength, surface support and full-radius envelope determine
        # admissible stations. Percentages only rank the search, never fix nodes.
        ids=np.flatnonzero((arc>max(1.5,2*config.radius_mm))&(arc<arc[-1]-max(2.,2*config.radius_mm)))
        last=-100.;options=[]
        for i in ids:
            if arc[i]-last<max(.45,radius*.7):continue
            try:
                validate_path_envelope(np.vstack((pts[i],pts[i]+[1e-8,0,0])),radius,request)
                anchor,projected,distance=router.project('J:'+parent.route_id+':K'+str(i),pts[i],path.surface_vertex_ids)
                if distance>config.radius_mm*.8+.03:continue
            except ValueError:continue
            options.append({'index':int(i),'arc':float(arc[i]),'fraction':float(arc[i]/arc[-1]),'point':pts[i],'anchor':anchor,'projected':projected,'distance':distance})
            last=arc[i]
        catalog[parent.route_id]=options
    for sid,sleeve in sleeves.items():
        router.radial_field=router.radial_fields.get(sid)
        axis=np.asarray(sleeve['axis'],float);axis/=np.linalg.norm(axis);u=np.cross(axis,np.eye(3)[np.argmin(abs(axis))]);u/=np.linalg.norm(u);v=np.cross(axis,u)
        def angle(key):
            point=parents[key].points_mm[-1]-np.asarray(sleeve['center']);return float(np.arctan2(point@v,point@u))%(2*np.pi)
        keys=sorted((key for key in parents if owners[key]==sid),key=angle)
        if len(keys)<2:raise ValueError('SPIDERWEB_INSUFFICIENT_RADIALS')
        angles=np.array([angle(k) for k in keys]);gaps=np.diff(np.r_[angles,angles[0]+2*np.pi]);cut=int(np.argmax(gaps));closed=len(keys)>2 and gaps[cut]<np.deg2rad(150.)
        if not closed:keys=keys[cut+1:]+keys[:cut+1]
        if closed:closed_groups.append(sid)
        tasks.extend((a,b,level,sid) for (a,level),(b,_) in ring_links(keys,2,closed))
        if router.radial_field is not None:
            ranges=[]
            for key in keys:
                for row in catalog[key]:row['field']=float(router.radial_field[int(router.vertex_tree.query(row['projected'])[1])])
                values=[r['field'] for r in catalog[key] if np.isfinite(r['field'])]
                if not values:raise ValueError('WEB_NO_SHARED_GEODESIC_LEVEL')
                ranges.append((min(values),max(values)))
            lower=max(r[0] for r in ranges);upper=min(r[1] for r in ranges)
            if upper<=lower:raise ValueError('WEB_NO_SHARED_GEODESIC_LEVEL')
            ring_targets[sid]=(upper-.15*(upper-lower),lower+.15*(upper-lower))
    # Reserve the narrow sleeve-side corridor first; outer rings have more
    # surface available to route around it. Backtracking still checks both.
    tasks.sort(key=lambda task:-task[2])
    stations={};accepted=[];arc_meta={};attempts=0;max_attempts=96;inner_checkpoint=None;optional_start_attempt=None
    frame_rim=bool(request.get('reinforcement_topology')==TOPOLOGY and frame_rim_available(request))
    def node_name(key,level):return 'J:'+key+':'+str(level)
    def parts_and_meta():
        parts=[];meta={}
        for key,parent in parents.items():
            selected=sorted((level,row) for (k,level),row in stations.items() if k==key)
            cuts=[0]+[row['index'] for level,row in selected]+[len(parent.points_mm)-1]
            labels=[parent.start_id]+[node_name(key,level) for level,row in selected]+[parent.end_id]
            for n,(a,b) in enumerate(zip(cuts,cuts[1:])):
                pts=parent.points_mm[a:b+1];length=float(np.linalg.norm(np.diff(pts,axis=0),axis=1).sum());part=replace(parent,route_id=key+':SEG'+str(n),start_id=labels[n],end_id=labels[n+1],points_mm=_readonly(pts,float),length_mm=length)
                parts.append(part);meta[part.route_id]={'role':'PRIMARY','sleeve_id':owners[key],'pre_faired':True,'reference_points_mm':raw[key].points_mm.tolist()}
        return parts,meta
    def options(key,level):
        if (key,level) in stations:return [stations[key,level]]
        values=catalog[key];other=stations.get((key,1-level));gap=max(2.*config.radius_mm+.05,2.*radius+.3)
        if other:values=[r for r in values if (r['arc']-other['arc'] if level else other['arc']-r['arc'])>=gap]
        target=.32 if level==0 else .76
        return sorted(values,key=lambda r:abs(r.get('field',0.)-ring_targets[owners[key]][level]) if owners[key] in ring_targets else abs(r['fraction']-target))[:10]
    def search(index):
        nonlocal attempts,inner_checkpoint,optional_start_attempt
        if index==len(tasks):return True
        if frame_rim and tasks[index][2]==0 and all(t[2]==1 for t in tasks[:index]) and inner_checkpoint is None:
            inner_checkpoint=(dict(stations),list(accepted),dict(arc_meta));optional_start_attempt=attempts
        a,b,level,sid=tasks[index];router.radial_field=router.radial_fields.get(sid);oa=options(a,level);ob=options(b,level)
        def pair_score(xy):
            if sid in ring_targets:return sum(abs(r['field']-ring_targets[sid][level]) for r in xy)+abs(xy[0]['field']-xy[1]['field'])
            return sum(abs(r['fraction']-(.32 if level==0 else .76)) for r in xy)
        pairs=sorted(((x,y) for x in oa for y in ob),key=pair_score)
        for first,second in pairs[:48]:
            if attempts>=max_attempts or (optional_start_attempt is not None and attempts-optional_start_attempt>=16):return False
            attempts+=1
            progress(f'Telaraña · arco {index+1}/{len(tasks)} · estaciones {attempts}')
            new=[]
            for key,row in ((a,first),(b,second)):
                if (key,level) not in stations:stations[key,level]=row;new.append((key,level))
            an=node_name(a,level);bn=node_name(b,level)
            obstacles=[{'id':k,'points':p.points_mm,'radius':config.radius_mm} for k,p in parents.items()]+[{'id':p.route_id,'points':p.points_mm,'radius':radius} for p in accepted]
            contacts={a:[first['point']],b:[second['point']]}
            for p in accepted:
                for label,point in ((an,first['point']),(bn,second['point'])):
                    if label in (p.start_id,p.end_id):contacts.setdefault(p.route_id,[]).append(point)
            target=None if router.radial_field is None else float(np.mean(router.radial_field[router.vertex_tree.query([first['projected'],second['projected']])[1]]))
            band=None if target is None else (min(first['field'],second['field'])-max(.5,radius*.6),max(first['field'],second['field'])+max(.5,radius*.6))
            path=router.route(replace(first['anchor'],id=an),replace(second['anchor'],id=bn),obstacles=obstacles,contacts=contacts,target_distance=target,ring_band=None)
            if path is None:path=router.route(replace(first['anchor'],id=an),replace(second['anchor'],id=bn),obstacles=obstacles,contacts=contacts,target_distance=target,ring_band=None,variant=1)
            chosen=None;reason='WEB_CORRIDOR_BLOCKED'
            if path is not None:
                try:
                    cert=surface_path_certificate(surface,path.points_mm,config.surface_tolerance_mm)
                    if not cert['valid']:raise ValueError('WEB_REFERENCE_OFF_IOS')
                    reference=np.asarray(path.points_mm,float);refarc=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(reference,axis=0),axis=1))]
                    # Surface projection residuals must not create a cusp at a
                    # physical radial joint. Keep the exact IOS reference, but
                    # blend only the bounded terminal neck into its support.
                    trim_a=min(.2*refarc[-1],first['distance']+radius*1.5)
                    trim_b=min(.2*refarc[-1],second['distance']+radius*1.5)
                    middle=reference[(refarc>=trim_a)&(refarc<=refarc[-1]-trim_b)]
                    if not len(middle):raise ValueError('WEB_NO_SURFACE_BODY')
                    pts=np.vstack((first['point'],middle,second['point']));pts=pts[np.r_[True,np.linalg.norm(np.diff(pts,axis=0),axis=1)>1e-7]]
                    curve,info=fair_open_path(pts,radius)
                    validate_path_envelope(curve,radius,request)
                    fold=mesh_fold_report(curve,radius)
                    for _bend_pass in range(3):
                        if fold['valid']:break
                        curve,info=fair_open_path(curve,radius)
                        fold=mesh_fold_report(curve,radius)
                    if not fold['valid']:
                        if request.get('web_diagnostics'):
                            from pathlib import Path
                            Path(request['job_dir'],'web_fold_sample.json').write_text(__import__('json').dumps({'raw':pts.tolist(),'curve':curve.tolist(),'reference':path.points_mm.tolist(),'radius':radius,'fold':fold}))
                        raise ValueError('WEB_TUBE_FOLD')
                    if not check_swept_tube_clearance(curve,[radius]*len(curve),zones).clear:raise ValueError('WEB_LUMEN_OR_KEEP_OUT')
                    clear,why=check_mesh_obstacles(curve,radius,local.mesh_obstacles)
                    if not clear:raise ValueError(why)
                    body,_=central_ios_body(curve,first['distance'],second['distance'],radius)
                    if not surface_path_certificate(surface,body,radius*.8+config.surface_tolerance_mm)['valid']:raise ValueError('WEB_LOST_IOS_SUPPORT')
                    length=float(np.linalg.norm(np.diff(curve,axis=0),axis=1).sum());chosen=replace(path,points_mm=_readonly(curve,float),length_mm=length,radius_mm=radius)
                    parts,meta=parts_and_meta();meta.update(arc_meta);meta[chosen.route_id]={'role':'SECONDARY','sleeve_id':''}
                    checked=evaluate_frame(build_frame_graph(perimeter,tuple(parts+accepted+[chosen]),config),local,config,continuous_primary_groups=continuous_groups(parts,meta))
                    if checked.status!='CANDIDATE':
                        if request.get('web_diagnostics'):
                            from pathlib import Path
                            Path(request['job_dir'],'web_intersection_sample.json').write_text(__import__('json').dumps({'report':checked.report,'paths':[{'id':p.route_id,'start':p.start_id,'end':p.end_id,'points':p.points_mm.tolist(),'radius':config.radius_mm if p.radius_mm is None else p.radius_mm} for p in parts+accepted+[chosen]]}))
                        raise ValueError(','.join(checked.rejections))
                except ValueError as exc:reason=str(exc);chosen=None
            if chosen is not None:
                accepted.append(chosen);arc_meta[chosen.route_id]={'role':'SECONDARY','sleeve_id':'','pre_faired':True,'reference_points_mm':path.points_mm.tolist(),'web_level':level,'web_sector':a+'|'+b,'joint_neck_start_mm':first['distance'],'joint_neck_end_mm':second['distance']}
                if search(index+1):return True
                accepted.pop();arc_meta.pop(chosen.route_id)
            else:
                errors.append({'origin':an,'port':bn,'reason':reason,'indices':[first['index'],second['index']],'graph':router.last_failure if path is None else {}})
                if request.get('web_diagnostics'):print('WEB_REJECT',errors[-1],flush=True)
            for key in new:stations.pop(key)
        return False
    complete=search(0)
    if not complete and inner_checkpoint is not None:
        stations,accepted,arc_meta=inner_checkpoint;complete=True
    parts,metadata=parts_and_meta();metadata.update(arc_meta)
    report={'lattice_complete':complete,'lattice_required_links':sum(t[2]==1 for t in tasks) if frame_rim else len(tasks),'web_optional_outer_arcs_completed':sum(arc_meta[p.route_id]['web_level']==0 for p in accepted),'lattice_links_completed':len(accepted),'lattice_secondary_count':len(accepted),'primary_branch_count':len(primary),'surface_search_complete':False,'surface_adherence_verified':complete,'surface_maximum_distance_bound_mm':config.surface_tolerance_mm,'surface_tolerance_mm':config.surface_tolerance_mm,'surface_role':'IOS','lattice_layout':'ADAPTIVE_RADIAL_WEB_ON_IOS','spiderweb_topology':TOPOLOGY,'web_station_attempts':attempts,'web_geodesic_ring_distances_mm':ring_targets,'web_full_ring_sleeves':closed_groups,'lattice_joint_positions':{node_name(k,l):r['point'].tolist() for (k,l),r in stations.items()}}
    if complete:
        _,render,_=smooth_network_paths(tuple(parts+accepted),metadata,config.radius_mm);report.update(verify_web(render,frame_rim=frame_rim))
    return tuple(parts+accepted),metadata,report,errors,local
