"""Rejected alternatives and hypothetical graft diagnostics. Never admissibility."""
import numpy as np
from .implant_optimizer_geometry import Solid,transformed,clearance,invasion_depth,bone_reserve

def diagnose(evaluator,matrix,asset,strict):
    violations=[]
    def add(code,label,excess=0.,actual=None,limit=None):
        row={'code':code,'label':label,'excess_mm':float(max(0.,excess))}
        if actual is not None:row['actual']=float(actual)
        if limit is not None:row['limit']=float(limit)
        violations.append(row)
    vertices,faces,witnesses,samples,area,proxy,platform,length=evaluator._prepare(asset)
    candidate=evaluator._diagnostic.get('candidate')
    if candidate is None:candidate=Solid(transformed(vertices,matrix),faces,'Rejected reference',topology=witnesses)
    points=transformed(samples,matrix);settings=evaluator.settings
    for index,entry in enumerate(evaluator.obstacles):
        obstacle,margin,kind=entry[:3];tolerance=float(entry[3]) if len(entry)>3 else 0.
        try:
            if tolerance>0:
                cached=evaluator._diagnostic['guards'].get(index,{})
                depth=cached['depth'] if 'depth' in cached else invasion_depth(candidate,obstacle,points)
                if depth=='UNMEASURABLE':add('UNVERIFIABLE',kind+' · profundidad no cuantificable')
                elif depth is not None and depth>tolerance:add('STRUCTURE',kind+' · invasión sobre el límite',depth-tolerance,depth,tolerance)
            else:
                cached=evaluator._diagnostic['guards'].get(index,{})
                value=cached['clearance'] if 'clearance' in cached else clearance(candidate,obstacle,float(margin))
                if value['status'] not in {'SAFE','CONTACT','BUFFER_INVADED'}:add('UNVERIFIABLE',kind+' · margen no verificable')
                elif value['status']!='SAFE':
                    measured=value.get('upper_mm')
                    if measured is None:add('UNVERIFIABLE',kind+' · distancia no cuantificable')
                    else:add('STRUCTURE',kind+' · '+obstacle.name,max(0.,margin-float(measured)),measured,margin)
        except (ValueError,RuntimeError) as exc:add('UNVERIFIABLE',kind+' · '+str(exc))
    native=np.ones(len(points),bool);socket_info={};exclude=None
    if evaluator.sockets:
        native,engagement=evaluator.socket_split(points,matrix,platform,length)
        minimum=float(settings.get('min_apical_mm',3.))
        socket_info={'socket_fraction':float(1-native.mean()),'apical_engagement_mm':engagement,'apical_minimum_mm':minimum}
        if engagement<minimum:add('APICAL','Anclaje apical insuficiente',minimum-engagement,engagement,minimum)
        if not native.any():add('NO_NATIVE','Referencia completamente dentro del alvéolo')
        dense=np.vstack((candidate.vertices,points));keep=evaluator.socket_split(dense,matrix,platform,length)[0]
        exclude=(dense,keep)
    reserve=float(settings.get('boundary_reserve_mm',.5))
    distances=evaluator.bone.signed_distances(points)
    selected=distances[native]
    support=float(np.mean(selected>0)) if len(selected) else 0.
    robust=float(np.mean(selected>reserve)) if len(selected) else 0.
    minimum_coverage=float(settings.get('min_coverage',.8))
    if support<minimum_coverage:add('COVERAGE','Cobertura nativa por debajo del mínimo',minimum_coverage-support,support,minimum_coverage)
    axis=np.asarray(matrix,float)[:3,2];axis=axis/np.linalg.norm(axis)
    top=transformed(np.asarray([platform]),matrix)[0];depth=(top-points)@axis
    free=min(max(float(settings.get('cervical_free_mm',1.)),.05),length*.5)
    relevant=native & (depth>=free);missing=relevant & (distances<-.02)
    maximum_gap=float(np.max(-distances[missing])) if missing.any() else 0.
    wall_ok=False
    try:
        if not missing.any():wall_ok=bone_reserve(candidate,evaluator.bone,reserve,matrix,platform,length,settings.get('cervical_free_mm',1.),exclude=exclude)
    except (ValueError,RuntimeError) as exc:add('UNVERIFIABLE','Reserva ósea · '+str(exc))
    if not wall_ok:
        if missing.any():add('WALL','Hueco fuera del hueso nativo',maximum_gap,maximum_gap,0.)
        else:add('WALL',f'Reserva de pared insuficiente o no verificable · exige {reserve:g} mm',reserve)
    graft_limit=float(settings.get('graft_gap_mm',0.))
    if not np.isfinite(graft_limit) or graft_limit<0:raise ValueError('Límite de espacio de injerto inválido.')
    adjacent=np.zeros(len(points),bool)
    if graft_limit>0 and missing.any() and evaluator.sockets:
        for socket in evaluator.sockets:
            adjacent[missing]|=socket.signed_distances(points[missing])>=-(graft_limit+evaluator.SOCKET_CLEARANCE_MM)
    planned=missing & adjacent & (-distances<=graft_limit)
    remainder=native & ~planned
    remainder_coverage=float(np.mean(distances[remainder]>0)) if remainder.any() else 0.
    blockers=[v for v in violations if v['code'] not in {'WALL','COVERAGE'}]
    eligible=bool(graft_limit>0 and missing.any() and np.all(planned[missing]) and not blockers
                  and remainder.any() and remainder_coverage>=minimum_coverage)
    if not violations:add('UNVERIFIABLE',strict.get('reason','Restricción no cuantificable'))
    return {**strict,'admissible':False,'score':0.,'violations':violations,'scenario_eligible':eligible,
            'support_fraction':support,'reserve_fraction':robust,'sampled_area_mm2':area,'conservative_envelope':proxy,
            'boundary_reserve_mm':reserve,'wall_gap_max_mm':maximum_gap,'graft_gap_limit_mm':graft_limit,
            'planned_graft_samples':int(planned.sum()),'sample_count':len(points),
            'native_coverage_without_planned_gap':remainder_coverage,
            'graft_is_hypothetical':True,'graft_points_world':points[planned].tolist(),
            'metric':'NATIVE_BONE_AND_HYPOTHETICAL_GRAFT_ARE_SEPARATE',**socket_info}
