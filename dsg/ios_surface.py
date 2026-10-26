"""Immutable, world-mm surface contracts. No Blender dependencies."""
from dataclasses import dataclass
import hashlib
import numpy as np


def _readonly(value,dtype):
    result=np.array(value,dtype=dtype,copy=True);result.setflags(write=False);return result


@dataclass(frozen=True)
class SurfaceSnapshot:
    source_id:str
    source_role:str
    vertices_mm:np.ndarray
    triangles:np.ndarray
    csr_offsets:np.ndarray
    csr_destinations:np.ndarray
    csr_lengths_mm:np.ndarray
    components:np.ndarray
    vertex_normals:np.ndarray
    fingerprint:str


@dataclass(frozen=True)
class SurfaceAnchor:
    id:str
    surface_id:str
    face_index:int
    barycentric:tuple[float,float,float]
    component:int
    role:str='FRAME'


@dataclass(frozen=True)
class ConstraintSet:
    allowed_vertices:np.ndarray|None=None
    protected_zones:tuple=()
    required_zones_complete:bool=True
    # Portable mesh obstacles are supplied by the Blender adapter, never RNA.
    mesh_obstacles:tuple=()
    vertex_penalty:np.ndarray|None=None


@dataclass(frozen=True)
class GenerationConfig:
    variants_per_pair:int=3
    max_routes_per_sleeve:int=64
    node_merge_tolerance_mm:float=.02
    surface_tolerance_mm:float=.02
    radius_mm:float=1.
    max_reroutes_per_pair:int=12
    def __post_init__(self):
        for value in (self.node_merge_tolerance_mm,self.surface_tolerance_mm,self.radius_mm):
            if not np.isfinite(value) or value<=0:raise ValueError('INVALID_CONFIG')
        if not 1<=self.variants_per_pair<=3 or not 1<=self.max_routes_per_sleeve<=64 or self.max_reroutes_per_pair<1:
            raise ValueError('INVALID_BUDGET')


def transform_points_mm(vertices,world_matrix,unit_scale_mm):
    points=np.asarray(vertices,float);matrix=np.asarray(world_matrix,float);scale=float(unit_scale_mm)
    if points.ndim!=2 or points.shape[1]!=3 or matrix.shape!=(4,4) or not np.isfinite(points).all() or not np.isfinite(matrix).all() or not np.isfinite(scale) or scale<=0:
        raise ValueError('INVALID_WORLD_TRANSFORM')
    return (points@matrix[:3,:3].T+matrix[:3,3])*scale


def sanitize_surface_arrays(vertices_mm,triangles,offsets,destinations,lengths):
    """Drop zero-area faces only in the analysis copy; retain explicit face map.

    Original vertex IDs stay stable. Edges belonging only to deleted faces
    cannot bridge components or become artificial routes.
    """
    xyz=np.asarray(vertices_mm,float);faces=np.asarray(triangles,np.int64);n=len(xyz)
    if faces.ndim!=2 or faces.shape[1]!=3 or np.any(faces<0) or np.any(faces>=n):raise ValueError('INVALID_TRIANGLES')
    area=np.linalg.norm(np.cross(xyz[faces[:,1]]-xyz[faces[:,0]],xyz[faces[:,2]]-xyz[faces[:,0]]),axis=1)
    valid=np.isfinite(area)&(area>1e-10);clean=faces[valid].copy();remap=np.full(len(faces),-1,np.int64);remap[valid]=np.arange(len(clean))
    edges=np.concatenate((clean[:,[0,1]],clean[:,[1,2]],clean[:,[2,0]]))
    keys=np.unique(np.minimum(edges[:,0],edges[:,1])*n+np.maximum(edges[:,0],edges[:,1]))
    dst=np.asarray(destinations,np.int64);weight=np.asarray(lengths,float);src=np.repeat(np.arange(n),np.diff(offsets))
    keep=np.isin(np.minimum(src,dst)*n+np.maximum(src,dst),keys)&np.isfinite(weight)&(weight>1e-8)
    new_offsets=np.concatenate(([0],np.cumsum(np.bincount(src[keep],minlength=n))))
    return clean,new_offsets,dst[keep],weight[keep],remap


def prepare_surface(vertices_mm,triangles,csr_offsets,csr_destinations,csr_lengths_mm,*,source_id,source_role,world_matrix,unit_scale_mm):
    xyz=np.asarray(vertices_mm,float);faces=np.asarray(triangles,np.int64)
    offsets=np.asarray(csr_offsets,np.int64);dst=np.asarray(csr_destinations,np.int64);lengths=np.asarray(csr_lengths_mm,float)
    matrix=np.asarray(world_matrix,float);scale=float(unit_scale_mm);n=len(xyz)
    if not source_id or not source_role or xyz.ndim!=2 or xyz.shape[1]!=3 or n<3 or not np.isfinite(xyz).all():raise ValueError('INVALID_SURFACE')
    if matrix.shape!=(4,4) or not np.isfinite(matrix).all() or not np.isfinite(scale) or scale<=0:raise ValueError('INVALID_TRANSFORM_PROVENANCE')
    if faces.ndim!=2 or faces.shape[1]!=3 or not len(faces) or np.any(faces<0) or np.any(faces>=n):raise ValueError('INVALID_TRIANGLES')
    cross=np.cross(xyz[faces[:,1]]-xyz[faces[:,0]],xyz[faces[:,2]]-xyz[faces[:,0]])
    if np.any(np.linalg.norm(cross,axis=1)<=1e-10):raise ValueError('DEGENERATE_TRIANGLE')
    if offsets.shape!=(n+1,) or offsets[0]!=0 or offsets[-1]!=len(dst) or np.any(np.diff(offsets)<0) or lengths.shape!=dst.shape or np.any(dst<0) or np.any(dst>=n) or np.any(lengths<=0) or not np.isfinite(lengths).all():raise ValueError('INVALID_CSR')
    src=np.repeat(np.arange(n,dtype=np.int64),np.diff(offsets))
    actual=np.linalg.norm(xyz[src]-xyz[dst],axis=1)
    if np.any(np.abs(actual-lengths)>np.maximum(1e-5,actual*1e-3)):raise ValueError('INCONSISTENT_EDGE_LENGTH')
    edges=np.concatenate((faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]))
    keys=np.minimum(edges[:,0],edges[:,1])*n+np.maximum(edges[:,0],edges[:,1])
    directed_keys=np.minimum(src,dst)*n+np.maximum(src,dst)
    if not np.isin(directed_keys,np.unique(keys)).all():raise ValueError('NON_SURFACE_EDGE')
    try:
        from scipy.sparse import csr_matrix
        from scipy.sparse.csgraph import connected_components
        _,components=connected_components(csr_matrix((np.ones(len(dst)),dst,offsets),shape=(n,n)),directed=False)
    except ImportError:
        parent=np.arange(n)
        def find(i):
            while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
            return i
        for a,b in zip(src,dst):
            x,y=find(a),find(b)
            if x!=y:parent[max(x,y)]=min(x,y)
        roots=np.array([find(i) for i in range(n)]);_,components=np.unique(roots,return_inverse=True)
    normals=np.zeros_like(xyz)
    for i in range(3):np.add.at(normals,faces[:,i],cross)
    normal_len=np.linalg.norm(normals,axis=1);normals/=np.maximum(normal_len[:,None],1e-15)
    digest=hashlib.sha256()
    for text in ('dsg.surface.v1',str(source_id),str(source_role),repr(scale)):digest.update(text.encode());digest.update(b'\0')
    for arr in (xyz,faces,offsets,dst,lengths,matrix):digest.update(np.asarray(arr).tobytes())
    return SurfaceSnapshot(str(source_id),str(source_role),_readonly(xyz,float),_readonly(faces,np.int64),_readonly(offsets,np.int64),_readonly(dst,np.int64),_readonly(lengths,float),_readonly(components,np.int64),_readonly(normals,float),digest.hexdigest())


def validate_anchor(surface,anchor):
    if anchor.surface_id!=surface.fingerprint:raise ValueError('ANCHOR_STALE_SURFACE')
    face=int(anchor.face_index)
    if not 0<=face<len(surface.triangles):raise ValueError('ANCHOR_FACE')
    ids=surface.triangles[face];bary=np.asarray(anchor.barycentric,float)
    if bary.shape!=(3,) or not np.isfinite(bary).all() or abs(float(bary.sum())-1)>1e-8 or np.any(bary<-1e-8):raise ValueError('ANCHOR_BARYCENTRIC')
    if np.any(surface.components[ids]!=anchor.component):raise ValueError('ANCHOR_COMPONENT')
    return bary@surface.vertices_mm[ids]


def _inside_triangles(point,triangles):
    """Two agreeing non-axis-aligned parity rays, deduplicating shared edges."""
    votes=[];a=triangles[:,0];e1=triangles[:,1]-a;e2=triangles[:,2]-a
    for raw in ((1.,.371,.219),(.217,1.,.493),(.391,.237,1.)):
        direction=np.asarray(raw);direction/=np.linalg.norm(direction)
        h=np.cross(np.broadcast_to(direction,e2.shape),e2);det=np.einsum('ij,ij->i',e1,h)
        mask=np.abs(det)>1e-12;inv=np.zeros_like(det);inv[mask]=1./det[mask]
        s=point-a;u=np.einsum('ij,ij->i',s,h)*inv;q=np.cross(s,e1)
        v=q@direction*inv;t=np.einsum('ij,ij->i',e2,q)*inv
        hits=np.sort(t[mask&(u>=-1e-9)&(v>=-1e-9)&(u+v<=1.+1e-9)&(t>1e-8)])
        unique=0 if not len(hits) else 1+int(np.count_nonzero(np.diff(hits)>1e-7))
        votes.append(bool(unique%2))
        if votes.count(True)>=2:return True
        if votes.count(False)>=2:return False
    raise ValueError('MESH_CONTAINMENT_UNVERIFIABLE')


def check_mesh_obstacles(points_mm,radius_mm,obstacles):
    """Exact segment/triangle capsule distance after an AABB broad phase.

    Closed mesh containment is checked separately: a complete path enclosed
    by a large obstacle need not cross its boundary triangles.
    """
    # dental_mapping.__init__ imports its Blender service. Load only the
    # existing pure kernel, so external workers never import that package.
    import importlib.util,sys
    from pathlib import Path
    name=__package__+'._generative_mesh_distance'
    kernel=sys.modules.get(name)
    if kernel is None:
        spec=importlib.util.spec_from_file_location(name,Path(__file__).parent/'dental_mapping/mesh_distance_core.py')
        kernel=importlib.util.module_from_spec(spec);sys.modules[name]=kernel;spec.loader.exec_module(kernel)
    closest_point_on_triangle=kernel.closest_point_on_triangle;closest_points_segments=kernel.closest_points_segments;_segment_triangle_hit=kernel._segment_triangle_hit
    points=np.asarray(points_mm,float);radius=float(radius_mm)
    if points.ndim!=2 or points.shape[1]!=3 or len(points)<2 or not np.isfinite(points).all() or radius<=0:raise ValueError('INVALID_MESH_SWEEP')
    for obstacle in obstacles:
        label=str(obstacle.get('label','UNNAMED'))
        if not obstacle.get('closed',False):return False,'MESH_UNVERIFIABLE:'+label
        xyz=np.asarray(obstacle['vertices_mm'],float);faces=np.asarray(obstacle['triangles'],int)
        if xyz.ndim!=2 or xyz.shape[1]!=3 or faces.ndim!=2 or faces.shape[1]!=3 or not len(faces) or not np.isfinite(xyz).all() or np.any(faces<0) or np.any(faces>=len(xyz)):return False,'MESH_INVALID:'+label
        triangles=xyz[faces];lo=triangles.min(axis=1);hi=triangles.max(axis=1)
        if _inside_triangles(points[0],triangles):return False,'MESH_CONTAINMENT:'+label
        for start,end in zip(points,points[1:]):
            boxlo=np.minimum(start,end)-radius;boxhi=np.maximum(start,end)+radius
            candidates=triangles[np.all(hi>=boxlo,axis=1)&np.all(lo<=boxhi,axis=1)]
            for tri in candidates:
                if _segment_triangle_hit(start,end,tri):return False,'MESH_INTERSECTION:'+label
                d2=min(closest_point_on_triangle(start,*tri)[1],closest_point_on_triangle(end,*tri)[1])
                for a,b in ((tri[0],tri[1]),(tri[1],tri[2]),(tri[2],tri[0])):d2=min(d2,closest_points_segments(start,end,a,b)[2])
                if d2<=radius*radius+1e-12:return False,'MESH_SWEEP_INTERSECTION:'+label
    return True,'CLEAR'


class SolidClearanceIndex:
    """Cached conservative triangle broad phase; exact capsule checks decide.

    Radius buckets prevent a few very large closure faces from expanding every
    nearest-centroid query. No triangle is omitted by the bucket bound.
    """
    def __init__(self,obstacle):
        from scipy.spatial import cKDTree
        if not obstacle.get('closed',False):raise ValueError('BRIDGE_SOLID_UNVERIFIABLE')
        self.label=str(obstacle.get('label','IOS'));xyz=np.asarray(obstacle['vertices_mm'],float);faces=np.asarray(obstacle['triangles'],int)
        if xyz.ndim!=2 or xyz.shape[1]!=3 or faces.ndim!=2 or faces.shape[1]!=3 or not len(faces) or not np.isfinite(xyz).all() or np.any(faces<0) or np.any(faces>=len(xyz)):raise ValueError('INVALID_BRIDGE_SOLID')
        # Containment is a union of independently closed edge-connected shells,
        # never global parity that cancels overlapping material components.
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components
        edges=np.concatenate((faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]));edges=np.sort(edges,axis=1)
        keys=edges[:,0]*len(xyz)+edges[:,1];order=np.argsort(keys,kind='stable');sorted_keys=keys[order]
        if len(sorted_keys)%2 or not np.array_equal(sorted_keys[::2],sorted_keys[1::2]) or np.any(sorted_keys[2::2]==sorted_keys[1:-1:2]):raise ValueError('BRIDGE_SOLID_UNVERIFIABLE')
        face_ids=np.tile(np.arange(len(faces)),3)[order];first,second=face_ids[::2],face_ids[1::2]
        _,components=connected_components(coo_matrix((np.ones(len(first)),(first,second)),shape=(len(faces),len(faces))).tocsr(),directed=False)
        self.shells=tuple(xyz[faces[components==label]] for label in np.unique(components));self.normal_cache={}
        self.triangles=xyz[faces];self.lo=self.triangles.min(axis=1);self.hi=self.triangles.max(axis=1)
        centers=self.triangles.mean(axis=1);radii=np.linalg.norm(self.triangles-centers[:,None,:],axis=2).max(axis=1)
        bins=np.floor(np.log2(np.maximum(radii,1e-6))).astype(int);self.buckets=[];self.containment_cache={}
        for label in sorted(set(bins)):
            ids=np.flatnonzero(bins==label);self.buckets.append((ids,cKDTree(centers[ids]),float(radii[ids].max())))
        check_mesh_obstacles([[0,0,0],[1,0,0]],.01,())
        import sys
        self.kernel=sys.modules[__package__+'._generative_mesh_distance']

    def clear(self,points_mm,radius_mm):
        pts=np.asarray(points_mm,float);radius=float(radius_mm)
        if pts.ndim!=2 or pts.shape[1]!=3 or len(pts)<2 or not np.isfinite(pts).all() or not np.isfinite(radius) or radius<=0:raise ValueError('INVALID_BRIDGE_SWEEP')
        inside=self.contains(pts[0])
        if inside:return False,'MODEL_CONTAINMENT:'+self.label
        kernel=self.kernel
        for a,b in zip(pts,pts[1:]):
            middle=(a+b)*.5;half=.5*np.linalg.norm(b-a);lo=np.minimum(a,b)-radius;hi=np.maximum(a,b)+radius
            for ids,tree,extent in self.buckets:
                rows=tree.query_ball_point(middle,half+radius+extent+1e-9)
                if not rows:continue
                selected=ids[np.asarray(rows,int)];selected=selected[np.all(self.hi[selected]>=lo,axis=1)&np.all(self.lo[selected]<=hi,axis=1)]
                for tri in self.triangles[selected]:
                    if kernel._segment_triangle_hit(a,b,tri):return False,'MODEL_INTERSECTION:'+self.label
                    distance=min(kernel.closest_point_on_triangle(a,*tri)[1],kernel.closest_point_on_triangle(b,*tri)[1])
                    for c,d in ((tri[0],tri[1]),(tri[1],tri[2]),(tri[2],tri[0])):distance=min(distance,kernel.closest_points_segments(a,b,c,d)[2])
                    if distance<=radius*radius+1e-12:return False,'MODEL_TUBE_INTERSECTION:'+self.label
        return True,'CLEAR'


    def contains(self,point):
        point=np.asarray(point,float);key=tuple(point)
        inside=self.containment_cache.get(key)
        if inside is None:
            inside=any(_inside_triangles(point,shell) for shell in self.shells)
            if len(self.containment_cache)>256:self.containment_cache.clear()
            self.containment_cache[key]=inside
        return inside

    def outward_at(self,point):
        point=np.asarray(point,float);key=tuple(point)
        if key in self.normal_cache:return self.normal_cache[key].copy()
        best=None
        for ids,tree,_extent in self.buckets:
            rows=np.atleast_1d(tree.query(point,k=min(8,len(ids)))[1])
            for row in rows:
                face=int(ids[int(row)]);tri=self.triangles[face];normal=np.cross(tri[1]-tri[0],tri[2]-tri[0]);size=np.linalg.norm(normal)
                if size<1e-12:continue
                nearest,distance=self.kernel.closest_point_on_triangle(point,*tri)
                if best is None or distance<best[0]:best=(distance,nearest,normal/size)
        if best is None:raise ValueError('BRIDGE_NORMAL_UNVERIFIABLE')
        for ids,tree,extent in self.buckets:
            rows=tree.query_ball_point(point,np.sqrt(best[0])+extent+1e-9)
            for row in rows:
                tri=self.triangles[int(ids[int(row)])];normal=np.cross(tri[1]-tri[0],tri[2]-tri[0]);size=np.linalg.norm(normal)
                if size<1e-12:continue
                nearest,distance=self.kernel.closest_point_on_triangle(point,*tri)
                if distance<best[0]:best=(distance,nearest,normal/size)
        distance,nearest,normal=best
        if distance>1e-8 and self.contains(point):raise ValueError('BRIDGE_ATTACHMENT_INSIDE_MODEL')
        direction=(point-nearest)/np.sqrt(distance) if distance>1e-8 else normal
        if self.contains(point+direction*.05):direction=-direction
        if self.contains(point+direction*.05):raise ValueError('BRIDGE_NORMAL_UNVERIFIABLE')
        self.normal_cache[key]=direction.copy();return direction
