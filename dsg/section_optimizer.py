"""Local configuration space from a stack of mesh sections.

Section fit is sampled, not a clinical assessment. Native bone, socket and
authorized sinus space remain separate. Protected structures are checked in
3D on the final candidates; no raster result alone authorizes application.
"""
import math,time
import numpy as np
from .section_geometry import raster_sections
from .implant_optimization import _matrix,movement,pose_matrix,rejected_options
from .optimizer_reference import crest_reference,candidate_rank

class SectionField:
    def __init__(self,request,bone,obstacles,sockets,*,pitch=.25,progress=None):
        import sys
        for path in request.get('section_site_paths',[]):
            if path not in sys.path:sys.path.append(path)
        from scipy.ndimage import binary_fill_holes,distance_transform_edt
        self.request=request;self.pitch=float(pitch);self.progress=progress
        self.base=_matrix(request['implant']['matrix']);self.origin=np.asarray(request['platform'],float)
        self.frame=self.base[:3,:3]
        if not np.allclose(self.frame.T@self.frame,np.eye(3),atol=1e-5) or np.linalg.det(self.frame)<0:
            raise ValueError('Los cortes requieren escala aplicada y eje sin deformación.')
        catalogue=request.get('catalogue') or []
        diameter=max([float(a['diameter_mm']) for a in catalogue]+[8.])
        length=max([float(a['length_mm']) for a in catalogue]+[20.])
        shift=float(request['settings']['max_shift_mm']);depth=float(request['settings'].get('max_depth_mm',0.))
        padding=max([float(o[1]) for o in obstacles]+[3.])+1.
        radius=math.ceil((shift+diameter/2+padding)/pitch)*pitch
        self.x=self.y=np.arange(-radius,radius+pitch*.5,pitch)
        # Anchor sampling to the world axial coordinate, not the initial
        # implant length/platform: changing the initial size must not shift
        # the anatomical sampling grid.
        axial=float(self.origin@self.frame[:,2])
        first=math.floor((axial-length-depth-3.)/pitch)*pitch+pitch*.173
        self.z=np.arange(first,axial+3.,pitch)-axial
        shape=(len(self.z),len(self.y),len(self.x));self.cache={}
        self.inventory=[]
        def raster(solid):
            local=(solid.vertices-self.origin)@self.frame
            lo=local.min(axis=0);hi=local.max(axis=0)
            if np.any(hi<np.array([self.x[0],self.y[0],self.z[0]])) or np.any(lo>np.array([self.x[-1],self.y[-1],self.z[-1]])):
                self.inventory.append({'name':solid.name,'triangles':len(solid.faces),'local':False})
                return np.zeros(shape,bool)
            self.inventory.append({'name':solid.name,'triangles':len(solid.faces),'local':True})
            return raster_sections(local,solid.faces,self.x,self.y,self.z)
        self.native=raster(bone)
        if not self.native.any():raise ValueError('No hay hueso segmentado en los cortes locales.')
        # Fill only to describe the outer section envelope. Filled pixels are
        # never attributed to native bone; protected cavity masks override it.
        outer=np.asarray([binary_fill_holes(layer) for layer in self.native])
        self.socket=np.zeros(shape,bool)
        for socket in sockets:self.socket|=raster(socket)
        self.sinus=np.zeros(shape,bool);nasal=np.zeros(shape,bool);self.blocked=np.zeros(shape,bool)
        uncertainty=math.sqrt(3)*pitch/2
        self.sinus_allowed=np.zeros(shape,bool)
        for index,entry in enumerate(obstacles):
            solid,margin,kind=entry[:3];limit=float(entry[3]) if len(entry)>3 else 0.
            mask=raster(solid)
            if progress:progress(25+15*(index+1)/max(1,len(obstacles)),'Cortes locales · '+kind)
            if not mask.any():continue
            if limit>0:
                self.sinus|=mask
                inside=distance_transform_edt(np.pad(mask,1))[1:-1,1:-1,1:-1]*pitch
                self.sinus_allowed|=mask & (inside<=limit)
                self.blocked|=mask & (inside>limit)
            else:
                distance=distance_transform_edt(~mask)*pitch
                self.blocked|=distance<=float(margin)+uncertainty
                if 'nasal' in kind.lower():nasal|=mask
        self.socket&=~(self.sinus|nasal)
        self.native&=~(self.socket|self.sinus|nasal)
        # Per-section native wall distance; filled envelope/socket never becomes bone.
        self.mpr_native_wall = None
        if request['settings'].get('mpr_guided_selection'):
            self.mpr_native_wall=np.asarray([distance_transform_edt(np.pad(layer,1))[1:-1,1:-1]*pitch
                                             for layer in self.native],dtype=np.float32)
        self.available=(outer|self.socket|self.sinus_allowed)&~self.blocked
        self.summary={'pitch_mm':pitch,'sampling_uncertainty_mm':uncertainty,'layers':len(self.z),
            'grid_shape':list(shape),'structures':self.inventory,'axis_fixed':True,
            'cross_sections':[{'depth_mm':float(-z),'available_area_mm2':float(layer.sum()*pitch*pitch)}
                              for z,layer in zip(self.z,self.available)]}

    def maps(self,diameter,length=8.):
        from scipy.signal import fftconvolve
        from .sinus_policy import permitted_invasion
        limit=permitted_invasion(length,float(self.request['settings'].get('sinus_invasion_mm',2.)))
        key=(float(diameter),limit)
        if key not in self.cache:
            r=float(diameter)/2;reach=int(math.ceil((r+self.pitch*.5)/self.pitch))
            q=np.arange(-reach,reach+1)*self.pitch;xx,yy=np.meshgrid(q,q)
            disk=(xx*xx+yy*yy<=(r+self.pitch*.5)**2).astype(np.float32)
            ring=((xx*xx+yy*yy>=(max(0.,r-self.pitch*.65))**2)&(disk>0)).astype(np.float32)
            kernel=disk[None,:,:];den=float(disk.sum())
            def fraction(mask,k=kernel,total=den):
                return np.clip(fftconvolve(mask.astype(np.float32),k,mode='same',axes=(1,2))/total,0.,1.)
            self.cache[key]={'available':fraction(self.available if limit>0 else self.available&~self.sinus),'native':fraction(self.native),
                'socket':fraction(self.socket),'sinus':fraction(self.sinus_allowed if limit>0 else np.zeros_like(self.sinus_allowed)),
                'blocked':fraction(self.blocked if limit>0 else self.blocked|self.sinus),'unknown':fraction(self.available&~(self.native|self.socket|self.sinus_allowed)),'contact':fraction(self.native,ring[None,:,:],float(ring.sum()))}
        return self.cache[key]

    def reference(self,x,y):
        for radius in (3.,2.25,1.5):
            value=crest_reference(self.native,self.x,self.y,self.z,x,y,radius=radius)
            if value is not None:return value
        return None

    def assess(self,diameter,length,parameters):
        x,y,top=map(float,parameters[:3]);r=float(diameter)/2;length=float(length)
        if not np.isfinite([x,y,top,r,length]).all() or min(r,length)<=0:raise ValueError('Medidas de corte inválidas.')
        if top>self.z[-1]+self.pitch/2 or top-length<self.z[0]-self.pitch/2 or abs(x)+r>self.x[-1] or abs(y)+r>self.y[-1]:
            raise ValueError('El implante sale del mapa calculado.')
        ix=int(round((x-self.x[0])/self.pitch));iy=int(round((y-self.y[0])/self.pitch))
        if not (0<=ix<len(self.x) and 0<=iy<len(self.y)):raise ValueError('Centro fuera del mapa local.')
        active=(self.z<=top)&(self.z>=top-length)
        free=float(self.request['settings'].get('cervical_free_mm',1.))
        supported=active&(self.z<=top-min(free,length*.5))
        if not active.any() or not supported.any():raise ValueError('Longitud no cubierta por los cortes.')
        maps=self.maps(diameter,length)
        values={k:v[:,iy,ix] for k,v in maps.items()}
        hard_ok=bool(np.max(values['blocked'][active])<1e-5)
        fit=float(np.min(values['available'][supported]))
        # Explicit geometric support measure: longest consecutive run where
        # >= half the implant section intersects segmented native bone.
        longest=run=0
        for inside in (active&(values['native']>=.5)):
            run=run+1 if inside else 0;longest=max(longest,run)
        anchor=max(0,longest-1)*self.pitch
        area=math.pi*r*r;dv=area*self.pitch
        contact=float(np.mean(values['contact'][active]));minimum=float(self.request['settings'].get('min_apical_mm',3.))
        fit_ok=fit>=1.-1e-5
        unknown=bool(np.max(values['unknown'][supported])>1e-5)
        review=not fit_ok or anchor<minimum or unknown
        violations=[]
        if not hard_ok:violations.append({'code':'STRUCTURE','label':'Zona protegida en los cortes','excess_mm':0.})
        if not fit_ok:violations.append({'code':'WALL','label':'Contorno óseo/alveolar pendiente de revisión','excess_mm':1.-fit})
        if unknown:violations.append({'code':'UNVERIFIABLE','label':'Espacio no clasificado dentro del contorno','excess_mm':0.})
        if anchor<minimum:violations.append({'code':'APICAL','label':'Tramo de soporte geométrico corto','actual':anchor,'limit':minimum,'excess_mm':minimum-anchor})
        wall=0.
        if getattr(self,'mpr_native_wall',None) is not None:
            wall=max(0.,float(self.mpr_native_wall[supported,iy,ix].min())-r-self.pitch*math.sqrt(2))
        return {'mpr_wall_reserve_mm':wall,'admissible':bool(hard_ok and not review),'score':float(contact*2*math.pi*r*length),
            'support_fraction':contact,'section_contact_fraction':contact,'violations':violations,
            'reason':'' if hard_ok and not review else 'Revisar contorno o soporte en cortes',
            'section_fit_fraction':fit,'section_hard_ok':hard_ok,'section_anchor_mm':anchor,
            'native_bone_volume_mm3':float(values['native'][active].sum()*dv),
            'unclassified_space_volume_mm3':float(values['unknown'][active].sum()*dv),
            'socket_space_volume_mm3':float(values['socket'][active].sum()*dv),
            'sinus_space_volume_mm3':float(values['sinus'][active].sum()*dv),
            'minimum_usable_section_mm2':float(values['available'][supported].min()*area),
            'implant_volume_mm3':area*length,'metric':'SECTION_ENVELOPE_AND_NATIVE_SUPPORT_NOT_STABILITY',
            'section_pitch_mm':self.pitch,'section_immediate':bool(self.request.get('sockets'))}

    def export(self,path):
        np.savez_compressed(path,x=self.x,y=self.y,z=self.z,native=self.native,socket=self.socket,sinus=self.sinus,
                            sinus_allowed=self.sinus_allowed,available=self.available,blocked=self.blocked,origin=self.origin,frame=self.frame)

    def assess_matrix(self,matrix,asset):
        m=_matrix(matrix)
        if not np.allclose(m[:3,:3],self.frame,atol=1e-5):raise ValueError('Eje distinto al mapa de cortes.')
        platform=m[:3,:3]@np.asarray(asset['platform_local_mm'],float)+m[:3,3]
        xyz=(platform-self.origin)@self.frame
        return self.assess(asset['diameter_mm'],asset['length_mm'],np.r_[xyz,0.,0.])

    def classification_witnesses(self,matrix,asset):
        """Interior cells that the raster cannot classify as bone/socket/air.

        These are checked against the original 3D solids before a raster
        disagreement can be cleared. A closed interior void must not be
        missed merely because the implant's surface samples lie in bone.
        """
        from .sinus_policy import permitted_invasion
        m=_matrix(matrix)
        platform=m[:3,:3]@np.asarray(asset['platform_local_mm'],float)+m[:3,3]
        x,y,top=(platform-self.origin)@self.frame
        length=float(asset['length_mm']);radius=float(asset['diameter_mm'])/2
        free=min(float(self.request['settings'].get('cervical_free_mm',1.)),length*.5)
        zs=np.flatnonzero((self.z>=top-length)&(self.z<=top-free))
        iy,ix=np.nonzero((self.x[None,:]-x)**2+(self.y[:,None]-y)**2<=radius**2)
        if not len(zs) or not len(ix):return np.empty((0,3))
        known=self.native[zs[:,None],iy[None,:],ix[None,:]]|self.socket[zs[:,None],iy[None,:],ix[None,:]]
        if permitted_invasion(length,float(self.request['settings'].get('sinus_invasion_mm',2.)))>0:
            known|=self.sinus_allowed[zs[:,None],iy[None,:],ix[None,:]]
        iz,j=np.nonzero(~known)
        local=np.column_stack((self.x[ix[j]],self.y[iy[j]],self.z[zs[iz]]))
        return local@self.frame.T+self.origin

def exact_section_evaluation(field,evaluator,matrix,asset):
    evaluation=field.assess_matrix(matrix,asset)
    try:guard=evaluator.check_structures(matrix,asset)
    except (ValueError,RuntimeError) as exc:
        return {**evaluation,'admissible':False,'score':0.,'reason':'Distancia a estructura protegida no verificable: '+str(exc),
            'violations':[{'code':'STRUCTURE','label':'Distancia a estructura protegida no verificable','excess_mm':0.}],
            'exact_structure_check':False,'alerts':[]}
    if not guard['admissible']:
        return {**evaluation,'admissible':False,'score':0.,'reason':guard.get('reason','Estructura protegida'),
            'violations':[{'code':'STRUCTURE','label':guard.get('reason','Estructura protegida'),'excess_mm':0.}],
            'exact_structure_check':True,'alerts':guard.get('alerts',[])}
    # Independently sample the real 3D union, not only its raster sections.
    # Socket/authorized sinus points never become native bone measurements.
    from .blender.implant_optimizer_geometry import transformed
    vertices,faces,witnesses,samples,area,proxy,local,length=evaluator._prepare(asset)
    points=np.vstack((transformed(vertices,matrix),transformed(samples,matrix)))
    axis=np.asarray(matrix)[:3,2];top=transformed(np.asarray([local]),matrix)[0]
    relevant=(top-points)@axis>=min(float(field.request['settings'].get('cervical_free_mm',1.)),length*.5)
    from .sinus_policy import permitted_invasion
    def union_distances(checked):
        distance=evaluator.bone.signed_distances(checked)
        for socket in evaluator.sockets:
            distance=np.maximum(distance,socket.signed_distances(checked)+evaluator.SOCKET_CLEARANCE_MM)
        for obstacle in evaluator.obstacles:
            if len(obstacle)>3 and permitted_invasion(length,float(obstacle[3]))>0:
                distance=np.maximum(distance,obstacle[0].signed_distances(checked))
        return distance
    checked=points[relevant]
    outside=max(0.,float(-union_distances(checked).min())) if len(checked) else float('inf')
    evaluation['sampled_3d_union_gap_mm']=outside
    evaluation['sampled_3d_union_points']=len(checked)
    interior=field.classification_witnesses(matrix,asset)
    if len(interior):
        # The cylinder raster can extend outside a custom mesh. Only genuine
        # candidate interior points can establish an unknown interior void.
        candidate=evaluator._diagnostic['candidate']
        interior=interior[candidate.signed_distances(interior)>=0.]
    unknown_gap=max(0.,float(-union_distances(interior).min())) if len(interior) else 0.
    evaluation['sampled_3d_interior_unknown_gap_mm']=unknown_gap
    evaluation['sampled_3d_interior_points']=len(interior)
    # The raster is a prioritizer. Resolve its WALL/UNVERIFIABLE/STRUCTURE
    # flags with the finer original geometry; retain the support requirement.
    original_flags={v['code'] for v in evaluation.get('violations',[])}
    violations=[v for v in evaluation.get('violations',[]) if v['code'] not in {'WALL','UNVERIFIABLE','STRUCTURE'}]
    tolerance=field.summary['sampling_uncertainty_mm']+.02
    if outside>tolerance:
        violations.append({'code':'WALL','label':'Contorno 3D fuera del espacio clasificado','actual':outside,
                           'limit':tolerance,'excess_mm':outside-tolerance})
    if unknown_gap>.02:
        violations.append({'code':'UNVERIFIABLE','label':'Espacio interior no clasificado en 3D',
                           'actual':unknown_gap,'limit':.02,'excess_mm':unknown_gap-.02})
    evaluation.update(violations=violations,admissible=not violations,
                      reason='; '.join(v.get('label',v['code']) for v in violations),
                      raster_disagreement_resolved_3d=bool(original_flags&{'WALL','UNVERIFIABLE','STRUCTURE'} and not any(v['code'] in {'WALL','UNVERIFIABLE'} for v in violations)))
    if evaluation['admissible'] and evaluator.settings.get('mpr_guided_selection'):
        try:evaluation['mpr_checks']=evaluator.mpr_checks(matrix,asset)
        except (ValueError,RuntimeError) as exc:
            evaluation.update(admissible=False,reason='Pared MPR no verificable: '+str(exc))
            evaluation['violations'].append({'code':'UNVERIFIABLE','label':evaluation['reason'],'excess_mm':0.})
    return {**evaluation,'exact_structure_check':True,'alerts':guard.get('alerts',[])}

def search_sections(request,field,evaluator,progress=None,*,verification_budget=None,additional_fields=()):
    from .implant_optimization import search_size
    search_size(lambda matrix,asset=None:{'admissible':False,'score':0.},request.get('catalogue',[]),request.get('family',''),field.base,field.origin,
                max_diameter_mm=request['settings'].get('max_diameter_mm',0.),max_length_mm=request['settings'].get('max_length_mm',0.))
    start=time.perf_counter();settings=request['settings'];shift=float(settings['max_shift_mm']);depth=float(settings.get('max_depth_mm',0.))
    step=.5;coords=np.arange(-shift,shift+step*.1,step)
    lateral=[(float(x),float(y)) for x in coords for y in coords if x*x+y*y<=shift*shift+1e-8]
    fields=[field]+list(additional_fields)
    rows=[];reference_count=0
    for field_index,active_field in enumerate(fields):
        references={}
        seed=getattr(active_field,'request',{}).get('axis_frame',{'id':'PLACED','angle_deg':0.})
        for x,y in lateral:
            reference=active_field.reference(x,y)
            if reference is not None and abs(reference['height_mm'])<=depth+1e-8:
                references[x,y]=reference
        reference_count+=len(references)
        for asset in request.get('catalogue',[]):
            if asset.get('family')!=request.get('family') or asset.get('availability','LISTED')!='LISTED':continue
            d,l=float(asset['diameter_mm']),float(asset['length_mm'])
            if settings.get('max_diameter_mm',0.) and d>settings['max_diameter_mm']+1e-9:continue
            if settings.get('max_length_mm',0.) and l>settings['max_length_mm']+1e-9:continue
            for (x,y),reference in references.items():
                p=[x,y,reference['height_mm'],0.,0.];evaluation=active_field.assess(d,l,p)
                evaluation['crest_reference']=dict(reference)
                base=active_field.base.copy();base[:3,3]=active_field.origin-active_field.frame@np.asarray(asset['platform_local_mm'],float)
                matrix=pose_matrix(base,active_field.origin,p)
                rows.append({'asset':dict(asset),'parameters':p,'matrix':matrix.tolist(),
                             'movement_mm':movement(p)+seed['angle_deg']/10.,'crest_error_mm':0.,'evaluation':evaluation,
                             'field_index':field_index,'axis_reference':seed['id'],'axis_angle_deg':seed['angle_deg']})
    # The raster is only a prioritizer. Exact guards may reject a candidate
    # because a small structure lies between the sampled sections.
    minimum_anchor=float(settings.get('min_apical_mm',3.))
    eligible=sorted([r for r in rows if r['evaluation']['section_anchor_mm']>=minimum_anchor],key=candidate_rank)
    # One proposal per prosthetic platform (narrow / standard / wide): the
    # longest, then widest, admissible size of each group.  The overall best is
    # the best of the three, i.e. the same answer as a single global search.
    from .implant_platforms import ORDER,platform_class
    verified=[];cache={}
    def verify(row):
        key=(row['field_index'],str(row['asset']['id']),tuple(round(float(v),6) for v in row['parameters']))
        if key not in cache:
            value=exact_section_evaluation(fields[row['field_index']],evaluator,row['matrix'],row['asset'])
            value['crest_reference']=row['evaluation']['crest_reference']
            cache[key]={**row,'evaluation':value};verified.append(cache[key])
        return cache[key]
    cap=verification_budget
    by_platform={}
    for group_index,group in enumerate(ORDER):
        group_rows=[r for r in rows if platform_class(r['asset'])==group]
        group_eligible=[r for r in eligible if platform_class(r['asset'])==group]
        candidates=group_eligible if cap is None else group_eligible[:cap]
        found=None;tried=[]
        for index,row in enumerate(candidates):
            if progress:progress(65+25*(group_index+(index+1)/max(1,len(candidates)))/len(ORDER),
                                 'Comprobación 3D · '+group.lower()+' · '+row['asset']['id'])
            checked=verify(row);tried.append(checked)
            if checked['evaluation']['admissible']:found=checked;break
        if not group_rows:reason='Sin medidas de esta plataforma en el catálogo'
        elif found is not None:reason=''
        elif not group_eligible:reason=f'Ninguna medida alcanza {minimum_anchor:g} mm de soporte óseo'
        else:
            reasons=[r['evaluation'].get('reason','') for r in tried if r['evaluation'].get('reason')]
            reason=max(set(reasons),key=reasons.count) if reasons else 'No cabe con los márgenes actuales'
        by_platform[group]={'best':found,'reason':reason,
            'sizes':len({str(r['asset']['id']) for r in group_rows}),'checked':len(tried),
            'exhausted':found is None and len(candidates)<len(group_eligible),
            'next_unverified':group_eligible[len(candidates)] if found is None and len(candidates)<len(group_eligible) else None}
    # Containment rule: a size that is narrower AND not longer than a size
    # already verified at a pose lies inside that implant's volume at the same
    # pose and axis, so it must fit there too.  A platform must therefore never
    # be reported impossible while a wider platform fits: retry its largest
    # contained sizes at the wider winner's pose (also covers a platform that
    # ran out of verification budget before reaching its shorter sizes).
    row_index={(r['field_index'],str(r['asset']['id']),tuple(round(float(v),6) for v in r['parameters'])):r for r in rows}
    for group in ORDER:
        entry=by_platform[group]
        for donor_group in ORDER:
            donor=by_platform[donor_group]['best']
            if donor is None or donor_group==group:continue
            dd,dl=float(donor['asset']['diameter_mm']),float(donor['asset']['length_mm'])
            contained=[r for r in rows if platform_class(r['asset'])==group
                       and r['field_index']==donor['field_index']
                       and tuple(round(float(v),6) for v in r['parameters'])==tuple(round(float(v),6) for v in donor['parameters'])
                       and float(r['asset']['diameter_mm'])<=dd+1e-9 and float(r['asset']['length_mm'])<=dl+1e-9]
            contained.sort(key=candidate_rank)
            current=entry['best']
            for row in contained:
                if current is not None and candidate_rank(row)>=candidate_rank(current):break
                checked=verify(row_index.get((row['field_index'],str(row['asset']['id']),tuple(round(float(v),6) for v in row['parameters'])),row))
                entry['checked']+=1
                if checked['evaluation']['admissible']:
                    checked=dict(checked);checked['contained_in']=str(donor['asset']['id'])
                    entry['best']=checked;entry['reason']='';entry['exhausted']=False
                    entry['contained_in']=str(donor['asset']['id'])
                    break
    winners=[entry['best'] for entry in by_platform.values() if entry['best'] is not None]
    best=min(winners,key=candidate_rank) if winners else None
    # A shorter/narrower winner is not the overall answer while a better-ranked
    # candidate of another platform is still unverified.
    pending=[entry['next_unverified'] for entry in by_platform.values() if entry['next_unverified'] is not None]
    exhausted=bool(pending) and (best is None or min(candidate_rank(r) for r in pending)<candidate_rank(best))
    if exhausted:best=None
    for entry in by_platform.values():entry.pop('next_unverified',None)
    # Advisory alternatives are a separate category, never a substitute
    # winner chosen by another optimization objective.
    if best is None and not exhausted:
        advisory=[r for r in rows if not r['evaluation']['admissible'] and r['evaluation']['section_hard_ok']]
        advisory.sort(key=lambda r:(-r['evaluation']['section_fit_fraction'],-r['evaluation']['section_anchor_mm'],candidate_rank(r)))
        for row in advisory[:8]:
            value=exact_section_evaluation(fields[row['field_index']],evaluator,row['matrix'],row['asset'])
            value['crest_reference']=row['evaluation']['crest_reference']
            verified.append({**row,'evaluation':value})
            if not any(v['code']=='STRUCTURE' for v in value.get('violations',[])):break
    options=rejected_options(verified)
    status='NOMINAL_PROPOSAL' if best and best['asset'].get('dimension_only') else ('COMPARISON' if best else 'NO_FEASIBLE')
    current=request.get('current') or {}
    if best and abs(float(current.get('diameter_mm',-1))-best['asset']['diameter_mm'])<.01 and abs(float(current.get('length_mm',-1))-best['asset']['length_mm'])<.01 and best['movement_mm']<.01:
        status='NO_IMPROVEMENT'
    if not best and options.get('closest') and not any(v['code']=='STRUCTURE' for v in options['closest']['evaluation'].get('violations',[])):
        status='SECTION_REVIEW'
    if exhausted:status='SEARCH_INCOMPLETE'
    if not reference_count:status='NO_CREST_REFERENCE'
    return {'mode':'SIZE','status':status,'best':best,**options,'combined_position':True,'section_search':True,
        'evaluated':len(rows),'verified_3d':len(verified),'rejected':sum(not r['evaluation']['admissible'] for r in rows),
        'section_summary':field.summary,'section_search_s':time.perf_counter()-start,
        'verification_budget_exhausted':exhausted,'selection_policy':'LENGTH_THEN_DIAMETER_AT_NATIVE_CREST',
        'by_platform':by_platform,
        'crest_reference_count':reference_count,'axis_count':len(fields),
        'reasons':sorted({r['evaluation'].get('reason','') for r in verified if not r['evaluation']['admissible']}),
        'metric':'LOCAL_SECTION_CONFIGURATION_SPACE_WITH_EXACT_3D_STRUCTURE_CHECK'}
