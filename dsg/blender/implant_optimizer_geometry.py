"""Immutable full-surface exclusions and sampled native-bone support (mm)."""
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from .surface_clearance_bounds import classify
from .safety_volume import _inside
from ..guide_export.mesh_checks import manifold_report,connected_components

class Solid:
    def __init__(self,vertices,faces,name,allow_hull=False,topology=None):
        """``topology`` = (witness vertex indices) from a verified identical mesh.

        A rigidly moved copy of an already verified mesh keeps its topology, so
        repeated candidate poses skip the manifold and component analysis.
        """
        self.vertices=np.asarray(vertices,float);self.faces=np.asarray(faces,int);self.name=name;self.proxy=False
        if not np.isfinite(self.vertices).all():raise ValueError(name+': coordenadas inválidas.')
        self._tree=None
        if topology is not None:
            self.witness_indices=np.asarray(topology,int)
        else:
            if manifold_report(self.vertices,self.faces).blocking:
                if not allow_hull:raise ValueError(name+': superficie abierta o no verificable.')
                from .nerve_safety import _convex_proxy
                self.vertices,self.faces=_convex_proxy(self.vertices);self.proxy=True
                if manifold_report(self.vertices,self.faces).blocking:raise ValueError(name+': envolvente no verificable.')
            groups=connected_components(len(self.vertices),self.faces)
            used=np.unique(self.faces)
            self.witness_indices=np.asarray([used[np.flatnonzero(groups[used]==group)[0]] for group in np.unique(groups[used])],int)
        self.bounds=(self.vertices.min(axis=0),self.vertices.max(axis=0))
        self.ray_epsilon=max(1e-5,float(max(np.abs(self.bounds[0]).max(),np.abs(self.bounds[1]).max()))*np.finfo(np.float32).eps*32)
        self.witnesses=self.vertices[self.witness_indices]
    @property
    def tree(self):
        if self._tree is None:self._tree=BVHTree.FromPolygons(self.vertices.tolist(),self.faces.tolist(),all_triangles=True)
        return self._tree
    def _ray_contains(self,point,direction):
        # Advance beyond a hit by several float32 ULPs at this coordinate
        # scale; 1e-5 alone may leave the next ray on the same triangle.
        epsilon=self.ray_epsilon
        origin=Vector(point);direction=Vector(direction).normalized();count=0
        for _ in range(256):
            hit,normal,index,distance=self.tree.ray_cast(origin,direction)
            if hit is None:return bool(count%2)
            origin=hit+direction*epsilon;count+=1
        raise ValueError(self.name+': paridad de rayos no verificable.')

    def contains(self,point):
        # A single ray can count the same exit twice at floating-point edges
        # (reproduced in 80 mm cubes). Independent rays resolve that ambiguity.
        votes=[]
        for direction in ((1.,.371,.219),(.217,1.,.493),(.391,.237,1.)):
            try:votes.append(self._ray_contains(point,direction))
            except ValueError:continue
            if votes.count(True)>=2:return True
            if votes.count(False)>=2:return False
        raise ValueError(self.name+': contención 3D no verificable.')

    def signed_distances(self,points):
        rows=[]
        for point in points:
            hit=self.tree.find_nearest(Vector(point))
            if hit[0] is None:raise ValueError(self.name+': no se pudo medir el soporte.')
            rows.append(float(hit[3])*(1. if self.contains(point) else -1.))
        return np.asarray(rows)

class PlanarSlab(Solid):
    """Closed box obstacle whose clearance is measured to its inner face plane.

    Used for estimated neighbour roots (simple route).  The distance to the
    half-space behind the plane is a lower bound of the distance to the box,
    and over a triangle mesh it is exact at the vertices (linear function), so
    long implant faces need no subdivision.
    """
    def __init__(self,vertices,faces,name,point,normal):
        super().__init__(vertices,faces,name)
        n=np.asarray(normal,float)
        if not np.isfinite(n).all() or np.linalg.norm(n)<1e-9:raise ValueError(name+': plano inválido.')
        self.plane_normal=n/np.linalg.norm(n);self.plane_point=np.asarray(point,float)
    def clearance_to(self,candidate,margin):
        d=float(np.min((np.asarray(candidate.vertices,float)-self.plane_point)@self.plane_normal))
        if d<=0:return {'status':'CONTACT','lower_mm':0.,'upper_mm':0.}
        if d<margin:return {'status':'BUFFER_INVADED','lower_mm':d,'upper_mm':d}
        return {'status':'SAFE','lower_mm':d,'upper_mm':d}

def transformed(vertices,matrix):
    m=np.asarray(matrix,float)
    return np.asarray(vertices)@m[:3,:3].T+m[:3,3]

def clearance(a,b,margin):
    if not np.isfinite(margin) or margin<0:raise ValueError('El optimizador requiere un margen no negativo.')
    if hasattr(b,'clearance_to'):return b.clearance_to(a,margin)
    gap=np.maximum(0.,np.maximum(a.bounds[0]-b.bounds[1],b.bounds[0]-a.bounds[1]))
    bound=float(np.linalg.norm(gap))
    if bound>margin+.02:return {'status':'SAFE','lower_mm':bound,'upper_mm':None}
    direction=Vector((1.,.371,.219)).normalized()
    if a.tree.overlap(b.tree) or any(b.contains(p) for p in a.witnesses) or any(a.contains(p) for p in b.witnesses):
        return {'status':'CONTACT','lower_mm':0.,'upper_mm':0.}
    # No clinical buffer: exact surface crossing and containment were checked above.
    if margin==0:return {'status':'SAFE','lower_mm':0.,'upper_mm':None}
    def distance(point):
        hit=b.tree.find_nearest(Vector(point))
        if hit[0] is None:raise ValueError('Distancia no verificable.')
        return hit[3]
    return classify(a.vertices[a.faces],distance,margin,max_refinements=3000)

def surface_samples(vertices,faces,count=384):
    triangles=np.asarray(vertices,float)[np.asarray(faces,int)]
    areas=np.linalg.norm(np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]),axis=1)*.5
    total=float(areas.sum())
    if total<=0:raise ValueError('Superficie vacía.')
    indices=np.searchsorted(np.cumsum(areas),(np.arange(count)+.5)*total/count)
    selected=triangles[indices];u=np.sqrt(((np.arange(count)+1)*.618033988749895)%1);v=((np.arange(count)+1)*.414213562373095)%1
    return (1-u[:,None])*selected[:,0]+(u*(1-v))[:,None]*selected[:,1]+(u*v)[:,None]*selected[:,2],total

def measure_surrounding_bone(bone,matrix,platform_local,diameter,length,levels=8,directions=16):
    """Sample radial gaps and first native-bone wall, in mm; never fills a socket.

    Diagnostic measurements only: distant bone across a gap is not contact and
    none of these rays overrides the full-surface exclusion/reserve guards.
    """
    from ..implant_optimization import _matrix
    matrix=_matrix(matrix);diameter=float(diameter);length=float(length)
    if min(diameter,length)<=0 or levels<1 or directions<3:raise ValueError('Medición ósea inválida.')
    frame=matrix[:3,:3]
    if not np.allclose(frame.T@frame,np.eye(3),atol=1e-5):raise ValueError('Aplica la escala antes de medir el hueso circundante.')
    platform=transformed(np.asarray([platform_local]),matrix)[0]
    parity=Vector((1.,.371,.219)).normalized();rows=[]
    for level in range(levels):
        depth=(level+.5)*length/levels;centre=platform-frame[:,2]*depth
        for index in range(directions):
            angle=2*np.pi*index/directions
            direction=Vector(frame@np.array([np.cos(angle),np.sin(angle),0.]))
            origin=Vector(centre)+direction*(diameter/2)
            reach=float(np.linalg.norm(np.maximum(np.abs(bone.bounds[0]-np.asarray(origin)),np.abs(bone.bounds[1]-np.asarray(origin)))))+.1
            inside=bone.contains(origin)
            first=bone.tree.ray_cast(origin,direction,reach)[0]
            if inside:
                if first is None:raise ValueError('No se pudo medir la salida de la pared ósea.')
                gap=0.;wall=float((first-origin).length)
            elif first is None:gap=None;wall=None
            else:
                gap=float((first-origin).length)
                second=bone.tree.ray_cast(first+direction*max(1e-4,bone.ray_epsilon*2),direction,reach)[0]
                if second is None:raise ValueError('La pared ósea no tiene una salida verificable.')
                wall=float((second-first).length)
            rows.append({'depth_mm':depth,'angle_deg':360.*index/directions,'inside_bone':inside,'gap_mm':gap,'wall_mm':wall})
    walls=[r['wall_mm'] for r in rows if r['inside_bone']]
    gaps=[r['gap_mm'] for r in rows if r['gap_mm'] is not None]
    return {'status':'MEASURED','rays':len(rows),'direct_bone_fraction':sum(r['inside_bone'] for r in rows)/len(rows),
            'missing_rays':sum(r['gap_mm'] is None for r in rows),
            'minimum_direct_wall_mm':min(walls) if walls else None,'maximum_gap_mm':max(gaps) if gaps else None,
            'rows':rows,'metric':'SAMPLED_RADIAL_NATIVE_BONE_NOT_STABILITY'}

def invasion_depth(candidate,zone,samples):
    """Deepest implant point inside a tolerated zone (mm); None if it does not cross it.

    Uses every vertex and the area-weighted surface samples.  When the
    surfaces cross but no measured point lies deeper than 0.05 mm, the depth
    is reported as unmeasurable (same rule as manual planning): never safe.
    """
    # Only an actual surface crossing or containment is an invasion; being near
    # the sinus (buffer) is allowed, as in manual planning.
    if clearance(candidate,zone,.05)['status']!='CONTACT':return None
    lo,hi=zone.bounds
    def deepest(points):
        near=np.all((points>=lo-.05)&(points<=hi+.05),axis=1)
        return float(zone.signed_distances(points[near]).max()) if near.any() else 0.
    depth=deepest(np.vstack((candidate.vertices,np.asarray(samples,float))))
    if depth>.05:return depth
    # Shallow crossing between samples: resample the surface at ~0.1 mm spacing.
    dense,area=surface_samples(candidate.vertices,candidate.faces,20000)
    depth=max(depth,deepest(dense))
    if depth>.05:return depth
    spacing=float(np.sqrt(area/20000.))
    # Still no point inside: the crossing is shallower than the sampling resolution.
    return max(.1,2*spacing) if spacing<=.25 else 'UNMEASURABLE'

def bone_reserve(candidate,bone,reserve,matrix,platform_local,length,cervical_free_mm=1.,exclude=None):
    """Conservative lateral/apical wall reserve below a free cervical band.

    The coronal ``cervical_free_mm`` of the implant (measured from its platform,
    capped at half the length) is a free boundary: crestal irregularity or a
    subcrestal placement must not make every size infeasible.  Below that band
    the expanded envelope must lie inside the native bone.
    """
    from .nerve_safety import _convex_proxy
    distance=float(reserve);free=float(cervical_free_mm)
    if not np.isfinite([distance,free]).all() or distance<0 or free<0:raise ValueError('Reserva ósea inválida.')
    distance+=.02
    frame=np.asarray(matrix,float)[:3,:3]
    frame=frame/np.linalg.norm(frame,axis=0)
    axis=frame[:,2];platform=transformed(np.asarray([platform_local]),matrix)[0]
    band=min(max(free,.05),float(length)*.5)
    points=candidate.vertices.copy()
    if exclude is not None:
        # Immediate implant: the part of the implant inside the extraction socket
        # has no wall by definition; only the remaining part must be in bone.
        points,keep=exclude
        points=np.asarray(points,float)[keep]
        if len(points)<4:return True
    height=(points-platform)@axis
    points-=np.maximum(0.,height+band)[:,None]*axis
    offsets=np.asarray([(x,y,z) for x in (-1,1) for y in (-1,1) for z in (-1,0)])@frame.T*distance
    vertices,faces=_convex_proxy((points[:,None,:]+offsets[None,:,:]).reshape(-1,3))
    expanded=Solid(vertices,faces,'Reserva ósea conservadora')
    direction=Vector((1.,.371,.219)).normalized()
    if expanded.tree.overlap(bone.tree):return False
    if not all(_inside(bone.tree,Vector(p),direction) for p in expanded.witnesses):return False
    if any(_inside(expanded.tree,Vector(p),direction) for p in bone.witnesses):return False
    return True

class Evaluator:
    """Same hard constraints for both searches: exclusions, wall reserve, coverage."""
    def __init__(self,source,bone,obstacles,settings,asset_loader=None,source_platform_local=None,sockets=(),source_nominal_length_mm=None):
        self.source=source;self.bone=bone;self.obstacles=obstacles;self.settings=settings;self.asset_loader=asset_loader
        self.sockets=list(sockets)
        self.source_nominal_length_mm=source_nominal_length_mm
        self.source_platform_local=None if source_platform_local is None else np.asarray(source_platform_local,float)
        self.cache={};self._diagnostic={}
    def _prepare(self,asset):
        key=asset['id'] if asset else '__source__'
        if key not in self.cache:
            vertices,faces=self.asset_loader(asset) if asset else self.source
            vertices=np.asarray(vertices,float)
            if asset:
                platform=np.asarray(asset['platform_local_mm'],float)
                lo=vertices.min(axis=0);hi=vertices.max(axis=0)
                if not np.allclose(platform,[0,0,hi[2]],atol=.05) or abs(lo[2]+hi[2])>.05:
                    raise ValueError('Catálogo: malla centrada, eje Z y plataforma en su extremo coronal requeridos.')
                if abs(hi[2]-lo[2]-float(asset['length_mm']))>.1:
                    raise ValueError('La longitud del catálogo no coincide con la malla.')
                if abs(max(hi[0]-lo[0],hi[1]-lo[1])-float(asset['diameter_mm']))>.1:
                    raise ValueError('El diámetro del catálogo no coincide con la malla.')
                length=float(asset['length_mm'])
            else:
                platform=self.source_platform_local if self.source_platform_local is not None else np.array([0.,0.,float(vertices[:,2].max())])
                length=float(np.ptp(vertices[:,2]))
            solid=Solid(vertices,faces,key,allow_hull=True)
            samples,area=surface_samples(solid.vertices,solid.faces)
            self.cache[key]=(solid.vertices,solid.faces,solid.witness_indices,samples,area,solid.proxy,platform,length)
        return self.cache[key]
    def __call__(self,matrix,asset=None):
        if not self.settings.get('explain_rejections'):return self._strict(matrix,asset)
        from .optimizer_diagnostics import diagnose
        try:value=self._strict(matrix,asset)
        except (ValueError,RuntimeError) as exc:value={'admissible':False,'score':0.,'reason':str(exc)}
        if value['admissible']:return dict(value,violations=[],scenario_eligible=False)
        return diagnose(self,matrix,asset,value)

    def check_structures(self,matrix,asset=None):
        self._diagnostic={'guards':{}}
        from ..implant_optimization import _matrix
        matrix=_matrix(matrix)
        vertices,faces,witnesses,samples,area,proxy,platform,length=self._prepare(asset)
        key=asset['id'] if asset else '__source__'
        candidate=Solid(transformed(vertices,matrix),faces,key,topology=witnesses)
        self._diagnostic['candidate']=candidate
        alerts=[]
        for index,entry in enumerate(self.obstacles):
            obstacle,margin,kind=entry[:3];limit=float(entry[3]) if len(entry)>3 else 0.
            if limit>0:
                from ..sinus_policy import permitted_invasion
                physical_length=float(np.ptp(vertices[:,2]))*float(np.linalg.norm(matrix[:3,2]))
                nominal_length=float(asset['length_mm']) if asset else float(length if self.source_nominal_length_mm is None else self.source_nominal_length_mm)
                limit=min(permitted_invasion(physical_length,limit),permitted_invasion(nominal_length,limit))
            if limit>0:
                depth=invasion_depth(candidate,obstacle,transformed(samples,matrix))
                self._diagnostic['guards'][index]={'depth':depth}
                if depth is None:continue
                if depth=='UNMEASURABLE':return {'admissible':False,'score':0.,'reason':kind+' · contacto de superficies; profundidad no cuantificable'}
                if depth>limit:return {'admissible':False,'score':0.,'reason':f'{kind} · invasión {depth:.2f} mm > {limit:g} mm'}
                alerts.append({'label':kind,'zone':obstacle.name,'depth_mm':float(depth),'limit_mm':limit})
                continue
            result=clearance(candidate,obstacle,margin)
            self._diagnostic['guards'][index]={'clearance':result}
            if result['status']!='SAFE':return {'admissible':False,'score':0.,'reason':kind+' · '+obstacle.name,'constraint':result}
        return {'admissible':True,'score':0.,'alerts':alerts,'conservative_envelope':proxy}

    def _strict(self,matrix,asset=None):
        guard=self.check_structures(matrix,asset)
        if not guard['admissible']:return guard
        from ..implant_optimization import _matrix
        matrix=_matrix(matrix)
        vertices,faces,witnesses,samples,area,proxy,platform,length=self._prepare(asset)
        candidate=self._diagnostic['candidate'];alerts=guard['alerts']
        reserve=float(self.settings.get('boundary_reserve_mm',.5))
        points=transformed(samples,matrix);native=np.ones(len(points),bool);socket_info={}
        exclude=None
        if self.sockets:
            native,engagement=self.socket_split(points,matrix,platform,length)
            minimum=float(self.settings.get('min_apical_mm',3.))
            socket_info={'socket_fraction':float(1-native.mean()),'apical_engagement_mm':engagement}
            if engagement<minimum:
                return {'admissible':False,'score':0.,'reason':f'Anclaje apical en hueso nativo {engagement:.1f} mm < {minimum:g} mm (alvéolo)',**socket_info}
            if not native.any():return {'admissible':False,'score':0.,'reason':'Implante completamente dentro del alvéolo',**socket_info}
            dense=np.vstack((candidate.vertices,points));keep=self.socket_split(dense,matrix,platform,length)[0]
            exclude=(dense,keep)
        if not bone_reserve(candidate,self.bone,reserve,matrix,platform,length,self.settings.get('cervical_free_mm',1.),exclude=exclude):
            return {'admissible':False,'score':0.,'reason':'Hueso remanente insuficiente o reserva de pared no verificable',**socket_info}
        distances=self.bone.signed_distances(points[native])
        support=float(np.mean(distances>0))
        robust=float(np.mean(distances>reserve))
        valid=support>=float(self.settings.get('min_coverage',.8))
        score=area*robust if asset else 2*robust+support
        invaded=max((a['depth_mm'] for a in alerts),default=0.)
        if not asset:score-=.25*invaded  # equal bone support: prefer the pose that invades the sinus less
        mpr={}
        if valid and self.settings.get('mpr_guided_selection'):
            from ..mpr_optimizer_checks import wall_bonus
            mpr=self.mpr_checks(matrix,asset)
            score+=wall_bonus(mpr['minimum_wall_mm'])*(area if asset else 1.)
        return {'admissible':valid,'mpr_checks':mpr,'score':float(score),'support_fraction':support,'reserve_fraction':robust,
                'sampled_area_mm2':area,'reserve_support_area_mm2':area*robust,'boundary_reserve_mm':reserve,
                'conservative_envelope':proxy,'reason':'' if valid else 'Cobertura geométrica muestreada insuficiente',
                'metric':'SAMPLED_NATIVE_BONE_SUPPORT_NOT_PRIMARY_STABILITY','alerts':alerts,'sinus_invasion_mm':invaded,**socket_info}

    def mpr_checks(self,matrix,asset=None):
        from ..mpr_optimizer_checks import wall_summary
        vertices,_,_,_,_,_,platform,length=self._prepare(asset)
        diameter=float(asset['diameter_mm']) if asset else 2*float(np.linalg.norm(vertices[:,:2],axis=1).max())
        surround=measure_surrounding_bone(self.bone,matrix,platform,diameter,length)
        free=min(float(self.settings.get('cervical_free_mm',1.)),length*.5)
        summary=wall_summary(surround,free)
        summary['protected_structures']=[dict(name=entry[0].name,kind=entry[2],required_margin_mm=float(entry[1]),
            **self._diagnostic.get('guards',{}).get(index,{})) for index,entry in enumerate(self.obstacles)]
        return summary

    SOCKET_CLEARANCE_MM=.3  # periodontal-ligament space around the extracted root counts as socket
    def socket_split(self,points,matrix,platform,length):
        """(mask of points in native bone region, apical engagement beyond the socket in mm)."""
        points=np.asarray(points,float);inside=np.zeros(len(points),bool)
        for socket in self.sockets:
            lo,hi=socket.bounds;near=np.all((points>=lo-.5)&(points<=hi+.5),axis=1)
            if near.any():inside[near]|=socket.signed_distances(points[near])>-self.SOCKET_CLEARANCE_MM
        frame=np.asarray(matrix,float)[:3,:3];axis=frame[:,2]/np.linalg.norm(frame[:,2])
        top=transformed(np.asarray([platform]),matrix)[0];depth=(top-points)@axis
        deepest=float(depth[inside].max()) if inside.any() else 0.
        return ~inside,float(max(0.,float(length)-max(0.,deepest)))

    def measure_bone(self,matrix,asset=None):
        vertices,faces,_,samples,area,proxy,platform,length=self._prepare(asset)
        reserve=float(self.settings.get('boundary_reserve_mm',.5))
        distances=self.bone.signed_distances(transformed(samples,matrix))
        metrics={'support_fraction':float(np.mean(distances>0)), 'reserve_fraction':float(np.mean(distances>reserve)),
                 'sample_count':len(samples),'boundary_reserve_mm':reserve,'conservative_envelope':proxy}
        diameter=float(asset['diameter_mm']) if asset else 2*float(np.linalg.norm(vertices[:,:2],axis=1).max())
        try:metrics['surround']=measure_surrounding_bone(self.bone,matrix,platform,diameter,length)
        except ValueError as exc:metrics['surround']={'status':'UNVERIFIABLE','reason':str(exc)}
        return metrics
