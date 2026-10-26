"""Two independent bounded geometry searches. No clinical stability predictor.

Position parameters are expressed in the implant's own frame:
``(lateral_x, lateral_y, axial, tilt_x_deg, tilt_y_deg)``.  ``axial`` is
positive toward coronal and has its own limit (``max_depth_mm``) so the search
cannot gain bone coverage simply by sinking the implant unless the user allows
a depth change.
"""
import itertools,math
import numpy as np

def _matrix(value):
    m=np.asarray(value,dtype=float)
    if m.shape!=(4,4) or not np.isfinite(m).all() or not np.allclose(m[3],[0,0,0,1]) or abs(np.linalg.det(m[:3,:3]))<1e-9:
        raise ValueError('Transformación inválida.')
    return m.copy()

def _frame(base):
    u,_,vt=np.linalg.svd(base[:3,:3]);return u@vt

def pose_matrix(base,pivot,parameters):
    """Rotate about ``pivot`` in the implant frame, then translate in that frame."""
    base=_matrix(base);pivot=np.asarray(pivot,dtype=float);p=np.asarray(parameters,dtype=float)
    if pivot.shape!=(3,) or p.shape!=(5,) or not np.isfinite(pivot).all() or not np.isfinite(p).all():raise ValueError('Límites o referencia inválidos.')
    a,b=np.radians(p[3:]);ca,sa,cb,sb=math.cos(a),math.sin(a),math.cos(b),math.sin(b)
    rx=np.array([[1,0,0],[0,ca,-sa],[0,sa,ca]]);ry=np.array([[cb,0,sb],[0,1,0],[-sb,0,cb]])
    frame=_frame(base)
    rotation=frame@ry@rx@frame.T
    out=base.copy();out[:3,:3]=rotation@base[:3,:3]
    out[:3,3]=pivot+rotation@(base[:3,3]-pivot)+frame@p[:3]
    return out

def movement(parameters):
    """Size of a proposal: lateral + axial in mm, tilt weighted 1 mm per 10°."""
    p=np.asarray(parameters,dtype=float)
    return float(np.linalg.norm(p[:2])+abs(p[2])+np.linalg.norm(p[3:])/10.)

def _evaluate(evaluate,matrix,asset=None):
    try:
        row=dict(evaluate(matrix,asset=asset))
        if not np.isfinite(float(row.get('score',float('nan')))):raise ValueError('Puntuación no verificable.')
        row['admissible']=bool(row.get('admissible',False))
        return row
    except (ValueError,RuntimeError) as exc:return {'admissible':False,'score':0.,'reason':str(exc)}

def rejection_rank(row):
    """Display ordering only; never changes admissibility or clinical limits."""
    evaluation=row['evaluation'];violations=evaluation.get('violations') or [{'code':'UNVERIFIABLE','excess_mm':0.}]
    unknown=sum(v['code']=='UNVERIFIABLE' for v in violations)
    critical=[v for v in violations if v['code'] in {'STRUCTURE','NO_NATIVE'}]
    amount=lambda code:sum(max(0.,float(v.get('excess_mm',0.))) for v in violations if v['code']==code)
    return (unknown,len(critical),sum(float(v.get('excess_mm',0.)) for v in critical),amount('APICAL'),amount('WALL'),amount('COVERAGE'),
            -float(evaluation.get('support_fraction',0.)),float(row.get('movement_mm',0.)))

def rejected_options(rows):
    rejected=[r for r in rows if not r['evaluation']['admissible']]
    conditional=[r for r in rejected if r['evaluation'].get('scenario_eligible')]
    return {'closest':min(rejected,key=rejection_rank) if rejected else None,
            'conditional':min(conditional,key=rejection_rank) if conditional else None}

def search_position(evaluate,base,pivot,*,max_shift_mm=1.,max_tilt_deg=5.,max_depth_mm=0.,budget=100,min_gain=.03):
    """Bounded local search.

    Among admissible poses whose score is within ``min_gain`` of the best one,
    the smallest movement is chosen; when that is the original pose the result
    is ``NO_IMPROVEMENT``.  ``min_gain`` must exceed sampling noise (one sample
    out of 384 changes the position score by up to ~0.008).
    """
    base=_matrix(base)
    limits=[max_shift_mm,max_tilt_deg,max_depth_mm,min_gain]
    if not np.isfinite(limits).all() or min(limits)<0 or max_tilt_deg>30 or not isinstance(budget,(int,np.integer)) or budget<1:
        raise ValueError('Límites de búsqueda inválidos.')
    seen=set();rows=[]
    def run(parameters):
        p=np.asarray(parameters,dtype=float)
        key=tuple(np.round(p,7))
        if key in seen or len(rows)>=budget:return
        if np.linalg.norm(p[:2])>max_shift_mm+1e-8 or abs(p[2])>max_depth_mm+1e-8 or np.linalg.norm(p[3:])>max_tilt_deg+1e-8:return
        seen.add(key);matrix=pose_matrix(base,pivot,p)
        rows.append({'matrix':matrix.tolist(),'parameters':p.tolist(),'movement_mm':movement(p),'evaluation':_evaluate(evaluate,matrix)})
    def best_score():
        ok=[r for r in rows if r['evaluation']['admissible']]
        return max(ok,key=lambda r:(r['evaluation']['score'],-r['movement_mm'])) if ok else None
    run(np.zeros(5));baseline=rows[0]
    steps=(max_shift_mm,max_shift_mm,max_depth_mm,max_tilt_deg,max_tilt_deg)
    shifts=[np.zeros(3)]+[np.eye(3)[i]*sign*steps[i] for i in range(3) for sign in (-1,1) if steps[i]>0]
    tilts=[np.zeros(2)]+[np.eye(2)[i]*sign*max_tilt_deg for i in range(2) for sign in (-1,1) if max_tilt_deg>0]
    for shift,tilt in itertools.product(shifts,tilts):run(np.r_[shift,tilt])
    for divisor in (2,4,8,16):
        top=best_score();center=np.asarray(top['parameters'] if top else np.zeros(5))
        for index in range(5):
            if steps[index]<=0:continue
            for sign in (-1,1):
                p=center.copy();p[index]+=sign*steps[index]/divisor;run(p)
    top=best_score()
    reasons=sorted({r['evaluation'].get('reason','restricciones') for r in rows if not r['evaluation']['admissible']})
    common={'mode':'POSITION','baseline':baseline,'evaluated':len(rows),'min_gain':float(min_gain),
            **rejected_options(rows),
            'rejected':sum(not r['evaluation']['admissible'] for r in rows),'reasons':reasons}
    if top is None:return dict(common,status='GRAFT_SCENARIO' if common['conditional'] else 'NO_FEASIBLE',best=None)
    floor=top['evaluation']['score']-min_gain
    close=[r for r in rows if r['evaluation']['admissible'] and r['evaluation']['score']>=floor]
    chosen=min(close,key=lambda r:(r['movement_mm'],-r['evaluation']['score']))
    if chosen is baseline:return dict(common,status='NO_IMPROVEMENT',best=baseline)
    return dict(common,status='PROPOSAL',best=chosen)

SIZE_POLICIES=('LARGEST','SUPPORT')

def _asset_matches(asset,current):
    if not current:return False
    if current.get('id') is not None and asset['id']==current['id']:return True
    d,l=current.get('diameter_mm'),current.get('length_mm')
    return d is not None and l is not None and abs(float(asset['diameter_mm'])-float(d))<.01 and abs(float(asset['length_mm'])-float(l))<.01

def search_size(evaluate,catalogue,family,base,platform,*,current_id=None,current=None,policy='LARGEST',max_diameter_mm=0.,max_length_mm=0.):
    """Compare catalogue sizes with the platform and axis fixed.

    ``policy``: ``LARGEST`` = largest admissible length, then diameter;
    ``SUPPORT`` = largest sampled area beyond the wall reserve.  Optional caps
    (0 = none) let the clinician bound diameter/length for the site.  The
    current implant is recognised by catalogue id or, failing that, by its
    nominal diameter and length (``current``).
    """
    base=_matrix(base);platform=np.asarray(platform,dtype=float)
    if policy not in SIZE_POLICIES:raise ValueError('Criterio de tamaño desconocido.')
    if not np.isfinite([max_diameter_mm,max_length_mm]).all() or min(max_diameter_mm,max_length_mm)<0:raise ValueError('Límites de tamaño inválidos.')
    if platform.shape!=(3,) or not np.isfinite(platform).all():raise ValueError('Referencia cervical inválida.')
    if not np.allclose(base[:3,:3].T@base[:3,:3],np.eye(3),atol=1e-5) or np.linalg.det(base[:3,:3])<0:
        raise ValueError('El catálogo requiere escala aplicada y eje sin deformación.')
    if not catalogue:return {'mode':'SIZE','status':'NO_CATALOG','best':None,'evaluated':0}
    if not str(family).strip():raise ValueError('Falta el sistema/familia del implante.')
    current=dict(current or {})
    if current_id is not None:current['id']=current_id
    rows=[];ids=set();capped=0
    for asset in catalogue:
        if asset.get('availability','LISTED')!='LISTED':continue
        mandatory={'id','family','diameter_mm','length_mm','platform_local_mm','vertices_path','faces_path','reference'}
        if not mandatory<=asset.keys():raise ValueError('Catálogo incompleto: se requieren geometría, medidas, referencia del cuello e instrucciones.')
        if asset['id'] in ids:raise ValueError('Identificador de catálogo duplicado.')
        ids.add(asset['id'])
        if asset['family']!=family:continue
        dimensions=np.array([asset['diameter_mm'],asset['length_mm']],float)
        local=np.asarray(asset['platform_local_mm'],float)
        if not np.isfinite(dimensions).all() or min(dimensions)<=0 or local.shape!=(3,) or not np.isfinite(local).all() or not str(asset['reference']).strip():raise ValueError('Medidas o referencias de catálogo inválidas.')
        is_current=_asset_matches(asset,current)
        if not is_current and ((max_diameter_mm and dimensions[0]>max_diameter_mm+1e-9) or (max_length_mm and dimensions[1]>max_length_mm+1e-9)):
            capped+=1;continue
        matrix=base.copy();matrix[:3,3]=platform-matrix[:3,:3]@local
        rows.append({'matrix':matrix.tolist(),'asset':dict(asset),'current':is_current,'evaluation':_evaluate(evaluate,matrix,asset)})
    feasible=[row for row in rows if row['evaluation']['admissible'] and not (row['current'] and _over_cap(row,max_diameter_mm,max_length_mm))]
    if policy=='LARGEST':
        def rank(row):return (float(row['asset']['length_mm']),float(row['asset']['diameter_mm']),row['evaluation']['score'])
    else:
        def rank(row):return (row['evaluation']['score'],-float(row['asset']['diameter_mm']),-float(row['asset']['length_mm']))
    best=max(feasible,key=rank) if feasible else None
    baseline=next((row for row in rows if row['current']),None)
    status='NO_FEASIBLE' if best is None else ('PROPOSAL' if baseline is not None else 'COMPARISON')
    if baseline is not None and baseline in feasible and best is not None and rank(best)<=rank(baseline):status='NO_IMPROVEMENT';best=baseline
    options=rejected_options([r for r in rows if not _over_cap(r,max_diameter_mm,max_length_mm)])
    if best is None and options['conditional']:status='GRAFT_SCENARIO'
    return {'mode':'SIZE','selection_policy':policy,'status':status,'baseline':baseline,'best':best,'evaluated':len(rows),'capped':capped,**options,
            'baseline_match':'ID' if baseline is not None and baseline['asset']['id']==current.get('id') else ('DIMENSIONS' if baseline is not None else None),
            'rejected':len(rows)-len(feasible),'reasons':sorted({r['evaluation'].get('reason','restricciones') for r in rows if not r['evaluation']['admissible']})}

def _over_cap(row,max_diameter_mm,max_length_mm):
    d,l=float(row['asset']['diameter_mm']),float(row['asset']['length_mm'])
    return bool((max_diameter_mm and d>max_diameter_mm+1e-9) or (max_length_mm and l>max_length_mm+1e-9))

def search_joint_sizes(evaluate,catalogue,family,base,platform,*,max_shift_mm=1.,max_depth_mm=0.,policy='LARGEST',
                       max_diameter_mm=0.,max_length_mm=0.,current_id=None,current=None,progress=None):
    """Finite size/translation stencil. Axis fixed; coronal depth never increased."""
    if not np.isfinite([max_shift_mm,max_depth_mm]).all() or min(max_shift_mm,max_depth_mm)<0:raise ValueError('Límites de traslación inválidos.')
    seeds=[]
    def collect(matrix,asset=None):
        seeds.append((matrix,asset));return {'admissible':False,'score':0.}
    checked=search_size(collect,catalogue,family,base,platform,current_id=current_id,current=current,policy=policy,
                        max_diameter_mm=max_diameter_mm,max_length_mm=max_length_mm)
    if not seeds:return dict(checked,combined_position=True)
    depths=list(dict.fromkeys([0.,-max_depth_mm/2.,-max_depth_mm]))
    shifts=[(0.,0.)]+[(sign*max_shift_mm*fraction if i==0 else 0.,sign*max_shift_mm*fraction if i==1 else 0.) for fraction in (.5,1.) for i in range(2) for sign in (-1,1) if max_shift_mm>0]
    rows=[];total=len(seeds)*len(depths)*len(shifts)
    identity=dict(current or {})
    if current_id is not None:identity['id']=current_id
    for matrix,asset in seeds:
        for depth in depths:
            for x,y in shifts:
                p=[x,y,depth,0.,0.];pose=pose_matrix(matrix,platform,p)
                value=_evaluate(evaluate,pose,asset)
                rows.append({'matrix':pose.tolist(),'asset':dict(asset),'parameters':p,'movement_mm':movement(p),
                             'current':_asset_matches(asset,identity) and movement(p)<1e-9,'evaluation':value})
                if progress:progress(len(rows),total,asset)
    feasible=[r for r in rows if r['evaluation']['admissible'] and not _over_cap(r,max_diameter_mm,max_length_mm)]
    def rank(row):
        d=float(row['asset']['diameter_mm']);l=float(row['asset']['length_mm']);score=row['evaluation']['score']
        return (l,d,score,-row['movement_mm']) if policy=='LARGEST' else (score,-row['movement_mm'],-d,-l)
    best=max(feasible,key=rank) if feasible else None;baseline=next((r for r in rows if r['current']),None)
    status='NO_FEASIBLE' if best is None else ('PROPOSAL' if baseline else 'COMPARISON')
    if best is not None and baseline in feasible and rank(best)<=rank(baseline):status='NO_IMPROVEMENT';best=baseline
    options=rejected_options([r for r in rows if not _over_cap(r,max_diameter_mm,max_length_mm)])
    if best is None and options['conditional']:status='GRAFT_SCENARIO'
    return {'mode':'SIZE','status':status,'best':best,'baseline':baseline,**options,'combined_position':True,
            'evaluated':len(rows),'evaluated_sizes':len(seeds),'capped':checked.get('capped',0),
            'rejected':len(rows)-len(feasible),'selection_policy':policy,
            'reasons':sorted({r['evaluation'].get('reason','restricciones') for r in rows if not r['evaluation']['admissible']})}
