"""Background transport for deterministic geometry; no bpy imports."""
import json,sys,time,traceback
from pathlib import Path

PRIMARY_JOINT_FRACTIONS=(.40,.72)


def central_ios_body(points,start_projection_distance,end_projection_distance,radius_mm):
    """Keep structural endpoint necks bounded; never skip an interior gap.

    Neck support remains pending until the final material sections are checked
    against the captured FRAME/SLEEVE solids. The entire remaining middle is
    still certified against IOS, with at least 12 percent of axis arc retained.
    """
    import numpy as np
    points=np.asarray(points,float);arc=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
    total=float(arc[-1])
    if total<=1e-8:raise ValueError('EMPTY_IOS_BODY')
    start=min(.44*total,float(start_projection_distance)+radius_mm)
    end=total-min(.44*total,float(end_projection_distance)+radius_mm)
    def at(distance):
        index=min(len(points)-2,max(0,int(np.searchsorted(arc,distance,side='right'))-1))
        fraction=(distance-arc[index])/max(arc[index+1]-arc[index],1e-15)
        return points[index]+fraction*(points[index+1]-points[index])
    body=np.vstack((at(start),points[(arc>start)&(arc<end)],at(end)))
    return body,{'structural_neck_start_length_mm':start,'structural_neck_end_length_mm':total-end,
                 'central_ios_body_length_mm':end-start,'structural_neck_support_pending':True}


def generate_lattice_paths(surface,perimeter,primary,owners,supports,originals,sleeves,constraints,config,progress,model_index=None,*,joint_fractions=PRIMARY_JOINT_FRACTIONS,organic_preflight=False,envelope_request=None):
    import numpy as np
    from dataclasses import replace
    from scipy.spatial import cKDTree
    from dsg.ios_surface import SurfaceAnchor,_readonly,check_mesh_obstacles,validate_anchor
    from dsg.frame_generator import split_lattice_primaries,lattice_links,build_frame_graph
    from dsg.geodesic_router import generate_geodesic_candidates,smooth_surface_path,surface_path_certificate
    from dsg.frame_optimizer import evaluate_frame,_kernel
    from dsg.frame_swept_clearance_core import CylinderKeepOut,check_swept_tube_clearance
    from dsg.reinforcement_coverage import continuous_groups
    from dsg.organic_reinforcement import fair_open_path,mesh_fold_report
    validation_accepted=[];organic_verified=[]
    segments=[];junctions=[];metadata={};parent_map={r.route_id:r for r in primary};links=[];diagonal_alternatives={}
    for sleeve_id in sleeves:
        sleeve=sleeves[sleeve_id];axis=np.asarray(sleeve['axis'],float);axis/=np.linalg.norm(axis)
        u=np.cross(axis,np.eye(3)[int(np.argmin(abs(axis)))]);u/=np.linalg.norm(u);v=np.cross(axis,u)
        def angular_key(route):
            radial=route.points_mm[len(route.points_mm)//2]-np.asarray(sleeve['center'])
            return (float(np.arctan2(radial@v,radial@u)),route.route_id)
        branches=tuple(sorted((r for r in primary if owners[r.route_id]==sleeve_id),key=angular_key))
        cut,joints=split_lattice_primaries(branches,joint_fractions)
        segments.extend(cut);junctions.extend(joints);pattern=lattice_links(joints);links.extend((a,b,True) for a,b in pattern)
        for cell in range(0,len(pattern),3):
            low_a,low_b=pattern[cell];high_a,high_b=pattern[cell+1]
            diagonal_alternatives[pattern[cell+2]]=(high_a,low_b)
        for part in cut:metadata[part.route_id]={'role':'PRIMARY','sleeve_id':sleeve_id}
    validation_segments=list(segments);primary_verified=0
    if organic_preflight:
        from dsg.organic_reinforcement import smooth_network_paths
        validated_primaries,_render,_report=smooth_network_paths(tuple(segments),metadata,config.radius_mm)
        validation_segments=list(validated_primaries);primary_verified=len(_render)
    kernel=_kernel();anchors={a.id:a for a in supports};positions=dict(originals)
    for joint in junctions:
        parent=parent_map[joint['parent']];point=np.asarray(joint['point_mm'],float)
        mask=np.isin(surface.triangles,np.asarray(parent.surface_vertex_ids,int)).any(axis=1)
        ids=np.flatnonzero(mask)
        if not len(ids):raise ValueError('MISSING_PRIMARY_SURFACE_CORRIDOR')
        triangles=surface.vertices_mm[surface.triangles[ids]];tree=cKDTree(triangles.mean(axis=1))
        candidates=np.atleast_1d(tree.query(point,k=min(24,len(ids)))[1]);best=None
        for i in candidates:
            triangle=triangles[int(i)];projected,_distance2=kernel.closest_point_on_triangle(point,*triangle)
            uv=np.linalg.lstsq(np.column_stack((triangle[1]-triangle[0],triangle[2]-triangle[0])),projected-triangle[0],rcond=None)[0]
            bary=(1.-uv.sum(),uv[0],uv[1])
            distance=float(np.linalg.norm(projected-point))
            if best is None or distance<best[0]:best=(distance,int(ids[int(i)]),bary)
        if best[0]>config.surface_tolerance_mm:raise ValueError('JUNCTION_OFF_SURFACE')
        face=best[1];component=int(surface.components[surface.triangles[face,0]])
        anchors[joint['id']]=SurfaceAnchor(joint['id'],surface.fingerprint,face,tuple(best[2]),component,'JUNCTION')
        positions[joint['id']]=point
    # Attach unused marked frame supports to the closest internal lattice node.
    used={r.start_id for r in primary}
    for support in supports:
        if support.id in used:continue
        ranked=sorted(junctions,key=lambda j:(-j['level'],float(np.linalg.norm(positions[support.id]-positions[j['id']])),j['id']))
        if ranked:links.append((support.id,ranked[0]['id'],False))
    def permitted_face(anchor,allowed):
        if allowed[surface.triangles[anchor.face_index]].all():return anchor
        point=validate_anchor(surface,anchor);original_face=surface.triangles[anchor.face_index]
        choices=np.flatnonzero(np.isin(surface.triangles,original_face).any(axis=1)&allowed[surface.triangles].all(axis=1))
        for face in choices:
            tri=surface.vertices_mm[surface.triangles[face]];projected,distance2=kernel.closest_point_on_triangle(point,*tri)
            if distance2>1e-10:continue
            uv=np.linalg.lstsq(np.column_stack((tri[1]-tri[0],tri[2]-tri[0])),projected-tri[0],rcond=None)[0]
            return replace(anchor,face_index=int(face),barycentric=(1.-uv.sum(),uv[0],uv[1]))
        return None
    radius=max(.6,.7*config.radius_mm);radius=min(radius,config.radius_mm)
    zones=list(constraints.protected_zones)
    for sleeve in sleeves.values():zones.append(CylinderKeepOut(sleeve['id']+':LATTICE_LUMEN',tuple(sleeve['center']),tuple(sleeve['axis']),sleeve['inner_radius_mm'],sleeve['height_mm']*.5))
    local=replace(constraints,protected_zones=tuple(zones));small=replace(config,radius_mm=radius)
    certificates={};accepted=[];rejections=[];required_count=sum(required for _,_,required in links);required_done=0;surface_search_complete=True
    for index,(start,end,required) in enumerate(links):
        progress(f'Celosía · conexión {index+1}/{len(links)}')
        alternatives=[(start,end)]
        if (start,end) in diagonal_alternatives:alternatives.append(diagonal_alternatives[(start,end)])
        chosen=None
        for start,end in alternatives:
            allowed=np.ones(len(surface.vertices_mm),bool) if local.allowed_vertices is None else np.array(local.allowed_vertices,bool,copy=True)
            # Existing tubes are physical obstacles except at their explicit shared
            # joint. The final exact sweep still decides acceptance.
            penalty=np.zeros(len(surface.vertices_mm)) if local.vertex_penalty is None else np.array(local.vertex_penalty,float,copy=True)
            for member in segments+accepted:
                r=config.radius_mm if member.radius_mm is None else member.radius_mm
                pts=np.asarray(member.points_mm,float);samples=[];spacing=max(.15,r*.4)
                for a,b in zip(pts,pts[1:]):samples.extend(a+(b-a)*t for t in np.linspace(0,1,max(2,int(np.linalg.norm(b-a)/spacing)+2)))
                distance=cKDTree(np.asarray(samples)).query(surface.vertices_mm)[0]
                near=np.maximum(0.,1.-distance/(r+radius+spacing))
                penalty+=30.*near
                if {start,end}&{member.start_id,member.end_id}:continue
                clear=distance>r+radius+spacing*.5
                for label in {start,end}&{member.start_id,member.end_id}:
                    clear|=np.linalg.norm(surface.vertices_mm-positions[label],axis=1)<=3.*max(r,radius)
                allowed&=clear
            pair_constraints=replace(local,allowed_vertices=allowed,vertex_penalty=penalty)
            begin=permitted_face(anchors[start],allowed);finish=permitted_face(anchors[end],allowed)
            if begin is None or finish is None:continue
            routes=generate_geodesic_candidates(surface,begin,finish,pair_constraints,small)
            baseline=generate_geodesic_candidates(surface,begin,finish,replace(pair_constraints,vertex_penalty=None),small)
            surface_search_complete&=routes.search_complete and baseline.search_complete
            chosen=None
            for route in routes.paths+baseline.paths:
                smooth=smooth_surface_path(surface,route.points_mm,route.surface_vertex_ids,pair_constraints,small)
                values=np.vstack((positions[start],smooth,positions[end]));clean=[values[0]]
                for point in values[1:]:
                    if np.linalg.norm(point-clean[-1])>1e-6:clean.append(point)
                points=np.asarray(clean);length=float(np.linalg.norm(np.diff(points,axis=0),axis=1).sum())
                candidate=replace(route,points_mm=_readonly(points,float),length_mm=length,radius_mm=radius)
                certificate=surface_path_certificate(surface,points,config.surface_tolerance_mm)
                if not certificate['valid']:
                    rejections.append({'origin':start,'port':end,'reason':'OFF_IOS_SURFACE'});continue
                swept=check_swept_tube_clearance(points,[radius]*len(points),local.protected_zones)
                if not swept.clear:continue
                validation_candidate=candidate
                if organic_preflight:
                    try:
                        curve,_organic_info=fair_open_path(candidate.points_mm,radius)
                        if envelope_request:
                            from dsg.reinforcement_envelope import validate_path_envelope
                            validate_path_envelope(curve,radius,envelope_request)
                        fold=mesh_fold_report(curve,radius)
                        if not fold['valid']:raise ValueError('ORGANIC_TUBE_FOLD')
                        organic_certificate=surface_path_certificate(surface,curve,radius*.8+config.surface_tolerance_mm)
                        if not organic_certificate['valid']:raise ValueError('ORGANIC_LOST_IOS_CONTACT')
                        validation_candidate=replace(candidate,points_mm=_readonly(curve,float),length_mm=float(np.linalg.norm(np.diff(curve,axis=0),axis=1).sum()))
                    except ValueError as exc:
                        rejections.append({'origin':start,'port':end,'reason':str(exc)});continue
                checked=evaluate_frame(build_frame_graph(perimeter,tuple((validation_segments+validation_accepted if organic_preflight else segments+accepted)+[validation_candidate]),config),constraints,config,continuous_primary_groups=continuous_groups(segments,metadata))
                if checked.status=='CANDIDATE':chosen=candidate;certificates[candidate.route_id]=certificate;break
                rejections.extend({'origin':start,'port':end,'reason':r} for r in checked.rejections)
            if chosen is not None:break
        if chosen is None:
            rejections.append({'origin':start,'port':end,'reason':'NO_VALID_LATTICE_ROUTE','required':required})
            if required and envelope_request and envelope_request.get('coverage_policy',{}).get('require_lattice'):
                # A fixed greedy layout with a missing required edge cannot
                # become complete by adding its remaining edges.
                surface_search_complete=False
                break
        else:
            accepted.append(chosen);validation_accepted.append(validation_candidate)
            if organic_preflight:organic_verified.append(chosen.route_id)
            metadata[chosen.route_id]={'role':'SECONDARY','sleeve_id':''}
            if required:required_done+=1
    report={'organic_primary_paths_verified':primary_verified,'organic_secondary_paths_verified':len(organic_verified),'lattice_required_links':required_count,'lattice_links_completed':required_done,'lattice_secondary_count':len(accepted),'primary_branch_count':len(primary),'lattice_complete':required_done==required_count,'surface_search_complete':surface_search_complete,'surface_adherence_verified':True,'surface_maximum_distance_bound_mm':max((c['maximum_distance_bound_mm'] for c in certificates.values()),default=0.),'surface_tolerance_mm':config.surface_tolerance_mm,'surface_role':'IOS','lattice_layout':'TRIANGLES_BETWEEN_PRIMARY_REINFORCEMENTS','sleeve_priority':'PRIMARY_CONNECTIONS_AND_NEAR_SLEEVE_BRACING'}
    return tuple(segments+accepted),metadata,report,rejections,constraints



def primary_surface_candidates(surface,start,end,constraints,config):
    """A steering cost must not erase a valid original surface corridor."""
    from dataclasses import replace
    from dsg.geodesic_router import generate_geodesic_candidates,RouteSearchResult
    steered=generate_geodesic_candidates(surface,start,end,constraints,config)
    if constraints.vertex_penalty is None:return steered
    baseline=generate_geodesic_candidates(surface,start,end,replace(constraints,vertex_penalty=None),config)
    paths={p.route_id:p for p in steered.paths}
    for path in baseline.paths:paths.setdefault(path.route_id,path)
    return RouteSearchResult(tuple(paths.values()),steered.rejections+baseline.rejections,
                             steered.search_complete and baseline.search_complete,
                             'CANDIDATE' if paths else 'NO_VALID_SURFACE_ROUTE')

def run(request,progress=lambda text:None):
    if request.get('reinforcement_topology')=='AXIAL_RADIAL_WEB_V2':
        from dsg.blender.axial_web_pipeline import build_candidate
        return build_candidate(request,progress)
    if request.get('native_case_file'):
        from dsg.blender.native_primary_preflight import prepare_native_case
        prepare_native_case(request)
    import numpy as np
    from dataclasses import replace
    from dsg.ios_surface import prepare_surface,SurfaceAnchor,ConstraintSet,GenerationConfig,_readonly,sanitize_surface_arrays
    from dsg.frame_generator import FramePerimeter,SleevePort,select_frame_anchor_pairs,build_frame_graph
    from dsg.geodesic_router import generate_geodesic_candidates,smooth_surface_path,surface_path_certificate
    from dsg.frame_optimizer import evaluate_frame,_intersection_outside_declared_joint,_kernel
    from dsg.frame_swept_clearance_core import CylinderKeepOut
    from dsg.frame_sleeve_junction_core import preflight_sleeve_junction
    progress('Preparando la superficie y las restricciones…')
    data=np.load(request['surface_file'],allow_pickle=False)
    triangles,offsets,destinations,lengths,remap=sanitize_surface_arrays(data['vertices'],data['triangles'],data['offsets'],data['destinations'],data['lengths'])
    removed_faces=int(np.count_nonzero(remap<0))
    surface=prepare_surface(data['vertices'],triangles,offsets,destinations,lengths,source_id=request['surface_name'],source_role='IOS',world_matrix=request['surface_matrix'],unit_scale_mm=1.)
    def anchor(row):
        face=int(remap[int(row['face_index'])])
        if face<0:raise ValueError('ANCHOR_ON_DEGENERATE_FACE:'+row['id'])
        component=int(surface.components[surface.triangles[face,0]])
        return SurfaceAnchor(row['id'],surface.fingerprint,face,tuple(row['barycentric']),component)
    supports=tuple(anchor(r) for r in request['supports'])
    perimeter=FramePerimeter(request['frame_name'],np.asarray([r['original_mm'] for r in request['supports']]),supports,request['frame_digest'])
    ports=tuple(SleevePort(r['id'],r['sleeve_id'],anchor(r),tuple(r['original_mm']),tuple(r['axis'])) for r in request['ports'])
    originals={r['id']:np.asarray(r['original_mm'],float) for r in request['supports']+request['ports']}
    projection_distances={r['id']:float(np.linalg.norm(np.asarray(r['point_mm'])-r['original_mm'])) for r in request['supports']+request['ports']}
    sleeves={s['id']:s for s in request['sleeves']};zones=[]
    for sleeve in request['sleeves']:
        center=np.asarray(sleeve['center']);axis=np.asarray(sleeve['axis']);axis=axis/np.linalg.norm(axis)
        for sign in (-1,1):
            shifted=center+axis*sign*(sleeve['height_mm']*.5+10.)
            zones.append(CylinderKeepOut(sleeve['id']+':DRILL'+str(sign),tuple(shifted),tuple(axis),float(sleeve['inner_radius_mm']),10.))
    mesh=[]
    for row in request['obstacles']:
        raw=np.load(row['file'],allow_pickle=False)
        mesh.append({'label':row['label'],'vertices_mm':raw['vertices'],'triangles':raw['triangles'],'closed':row['closed']})
    config=GenerationConfig(radius_mm=request['radius_mm'])
    constraints=ConstraintSet(protected_zones=tuple(zones),mesh_obstacles=tuple(mesh),required_zones_complete=request['required_zones_complete'])
    coverage_policy=bool(request.get('coverage_policy'))
    from dsg.reinforcement_envelope import validate_path_envelope
    if request.get('reinforcement_envelope'):
        if not all(row.get('upper_frame_surface') for row in request['supports']):raise ValueError('FRAME_UPPER_ORIGINS_UNVERIFIED')
        penalty=np.zeros(len(surface.vertices_mm))
        for sleeve in request['sleeves']:
            axis=np.asarray(sleeve['entry_axis'],float);axis/=np.linalg.norm(axis)
            local=surface.vertices_mm-np.asarray(sleeve['center']);axial=local@axis
            radial=np.linalg.norm(local-np.outer(axial,axis),axis=1);half=float(sleeve['height_mm'])*.5
            penalty[(axial+config.radius_mm>half-.05)|((radial<float(sleeve['outer_radius_mm'])+config.radius_mm)&(abs(abs(axial)-half)<config.radius_mm+.05))]+=1000.
        if request.get('frame_lower_surface_file'):
            from dsg.reinforcement_envelope import frame_barrier
            progress('Preparando barrera de la cara inferior del frame…')
            penalty+=frame_barrier(request['frame_lower_surface_file']).steering_penalty(surface.vertices_mm,config.radius_mm)
        constraints=replace(constraints,vertex_penalty=penalty)

    from dsg.reinforcement_coverage import prioritize_pairs,route_metrics,continuous_groups,verify_coverage,layout_trial_report,lattice_trial_plan
    functional_routing={}
    if coverage_policy and mesh:
        from dsg.reinforcement_coverage import functional_surface_mask
        allowed,functional_routing=functional_surface_mask(surface,mesh,config.radius_mm,config.surface_tolerance_mm,progress)
        # The bound is deliberately conservative on coarse endpoint faces.
        # Use it to steer the search; exact capsule and final-mesh checks remain
        # the hard gates, so valid boundary contacts are not erased upfront.
        constraints=replace(constraints,vertex_penalty=(~allowed).astype(float)*1000.+(0. if constraints.vertex_penalty is None else constraints.vertex_penalty))
        functional_routing['routing_use']='STEERING_COST_WITH_EXACT_SWEEP_GATE'
    pairs=select_frame_anchor_pairs(perimeter,ports,supports,config)
    # Give every origin its first port before spending budget on extra ports.
    rank={};origin_order={};port_rank={}
    for pair in pairs:
        key=(pair.port.sleeve_id,pair.start.id)
        origin_order.setdefault(key,len(origin_order));rank[id(pair)]=port_rank.get(key,0);port_rank[key]=rank[id(pair)]+1
    pairs=tuple(sorted(pairs,key=lambda pair:(pair.port.sleeve_id,rank[id(pair)],origin_order[(pair.port.sleeve_id,pair.start.id)])))
    if coverage_policy:pairs=prioritize_pairs(pairs,request)
    groups={};rejections=[];complete=True;count=0;owners={};sleeve_counts={};organic_candidates={}
    from dsg.organic_reinforcement import fair_open_path,mesh_fold_report
    from dsg.frame_swept_clearance_core import check_swept_tube_clearance
    protected_anchor_cache={}
    for i,pair in enumerate(pairs):
        if sleeve_counts.get(pair.port.sleeve_id,0)>=config.max_routes_per_sleeve:complete=False;continue
        progress(f'Rutas de superficie · pareja {i+1}/{len(pairs)}')
        non_target=[]
        for sleeve in request['sleeves']:
            if sleeve['id']!=pair.port.sleeve_id:
                non_target.append(CylinderKeepOut(sleeve['id']+':LUMEN',tuple(sleeve['center']),tuple(sleeve['axis']),sleeve['inner_radius_mm'],sleeve['height_mm']*.5))
        local=replace(constraints,protected_zones=constraints.protected_zones+tuple(non_target))
        if coverage_policy and mesh:
            from dsg.reinforcement_coverage import protected_anchor_reason
            reasons=[]
            for endpoint in (pair.start,pair.end):
                if endpoint.id not in protected_anchor_cache:
                    protected_anchor_cache[endpoint.id]=protected_anchor_reason(surface,endpoint,config.radius_mm,mesh)
                if protected_anchor_cache[endpoint.id]:reasons.append(endpoint.id+':'+protected_anchor_cache[endpoint.id])
            if reasons:
                rejections.append({'origin':pair.start.id,'port':pair.end.id,'reason':'PROTECTED_ENDPOINT:'+','.join(reasons)})
                continue
        routes=primary_surface_candidates(surface,pair.start,pair.end,local,config) if request.get('reinforcement_envelope') else generate_geodesic_candidates(surface,pair.start,pair.end,local,config)
        rejections.extend({'origin':pair.start.id,'port':pair.end.id,'reason':reason} for reason in routes.rejections)
        complete&=routes.search_complete
        for route in routes.paths:
            smoothed=smooth_surface_path(surface,route.points_mm,route.surface_vertex_ids,local,config)
            values=np.vstack((originals[route.start_id],smoothed,originals[route.end_id]))
            clean=[values[0]]
            for p in values[1:]:
                if np.linalg.norm(p-clean[-1])>1e-6:clean.append(p)
            points=np.asarray(clean)
            try:junction=preflight_sleeve_junction(points,[config.radius_mm]*len(points),request['sleeves'],target_sleeve_id=pair.port.sleeve_id,maximum_deferred_tip_mm=2.)
            except ValueError as exc:rejections.append({'origin':pair.start.id,'port':pair.end.id,'reason':str(exc)});continue
            if not junction.candidate_admissible:
                rejections.append({'origin':pair.start.id,'port':pair.end.id,'reason':junction.status});continue
            length=float(np.linalg.norm(np.diff(points,axis=0),axis=1).sum())
            candidate=replace(route,points_mm=_readonly(points,float),length_mm=length)
            # An individual actual-radius sweep must pass before combining it.
            checked=evaluate_frame(build_frame_graph(perimeter,(candidate,),config),local,config)
            if checked.status!='CANDIDATE':
                rejections.extend({'origin':pair.start.id,'port':pair.end.id,'reason':reason} for reason in checked.rejections);continue
            arc=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
            locks=[int(np.argmin(abs(arc-arc[-1]*fraction))) for fraction in (.40,.72)]
            try:
                curve,info=fair_open_path(points,config.radius_mm,locks)
                validate_path_envelope(curve,config.radius_mm,request,frame_projection_distance_mm=projection_distances[pair.start.id])
                if not mesh_fold_report(curve,config.radius_mm)['valid']:raise ValueError('ORGANIC_TUBE_FOLD')
                if not check_swept_tube_clearance(curve,[config.radius_mm]*len(curve),local.protected_zones).clear:raise ValueError('ORGANIC_KEEP_OUT')
                organic_junction=preflight_sleeve_junction(curve,[config.radius_mm]*len(curve),request['sleeves'],target_sleeve_id=pair.port.sleeve_id,maximum_deferred_tip_mm=2.)
                if not organic_junction.candidate_admissible:raise ValueError('ORGANIC_'+organic_junction.status)
            except ValueError as exc:rejections.append({'origin':pair.start.id,'port':pair.end.id,'reason':str(exc)});continue
            organic_candidates[candidate.route_id]=replace(candidate,points_mm=_readonly(curve,float))
            groups.setdefault(pair.start.id,[]).append(candidate);owners[candidate.route_id]=pair.port.sleeve_id;count+=1
            sleeve_counts[pair.port.sleeve_id]=sleeve_counts.get(pair.port.sleeve_id,0)+1
    progress('Priorizando los anclajes directos al sleeve…')
    from dsg.sleeve_priority import select_sleeve_routes
    from dsg.frame_generator import FrameMember
    kernel=_kernel()
    def compatible(first,second):
        a=organic_candidates[first.route_id];b=organic_candidates[second.route_id]
        return not _intersection_outside_declared_joint(FrameMember(a.route_id,a.start_id,a.end_id,a,config.radius_mm),FrameMember(b.route_id,b.start_id,b.end_id,b,config.radius_mm),kernel)
    candidate_pool=[r for group in groups.values() for r in group]
    native_primary_report={}
    if request.get('native_case_file') and request.get('reinforcement_topology'):
        from dsg.blender.native_primary_preflight import preflight_primary_pool
        valid_ids,native_primary_report=preflight_primary_pool(request,tuple(organic_candidates[r.route_id] for r in candidate_pool),owners,progress)
        groups={key:[r for r in values if r.route_id in valid_ids] for key,values in groups.items()}
        groups={key:values for key,values in groups.items() if values}
        candidate_pool=[r for group in groups.values() for r in group];count=len(candidate_pool)

    metrics=route_metrics(candidate_pool,owners,request) if coverage_policy else None
    selected,priority_report=select_sleeve_routes(candidate_pool,owners,compatible,minimum_per_sleeve=2,
        alternatives_limit=12 if coverage_policy else 32,route_metrics=metrics,
        required_targets=[t['id'] for t in request['coverage_policy']['targets']] if coverage_policy and request['coverage_policy'].get('require_all_flanks',True) else (),
        preferred_targets=[t['id'] for t in request['coverage_policy']['targets']] if coverage_policy and not request['coverage_policy'].get('require_all_flanks',True) else (),maximum_per_sleeve=3 if coverage_policy else None)
    if coverage_policy and request.get('job_dir'):
        debug={'owners':owners,'primary_routes':[{'route_id':r.route_id,'start_id':r.start_id,'end_id':r.end_id,
            'points_mm':r.points_mm.tolist(),'surface_vertex_ids':list(r.surface_vertex_ids),'length_mm':r.length_mm,
            'weighted_cost':r.weighted_cost,'backend':r.backend,'variant_index':r.variant_index,'radius_mm':r.radius_mm} for r in candidate_pool],
            'metrics':metrics,'selection':priority_report,'rejections':rejections,'functional_routing':functional_routing}
        Path(request['job_dir'],'coverage_primary_pool.json').write_text(json.dumps(debug),encoding='utf-8')
    if native_primary_report:priority_report['native_primary_preflight']=native_primary_report
    complete&=priority_report['search_complete']
    if not selected or any(sum(owners[r.route_id]==sleeve_id for r in selected)<2 for sleeve_id in sleeves):
        return {'status':'NO_VALID_SURFACE_ROUTE','pieces':[],'rejections':rejections+['INSUFFICIENT_DIRECT_SLEEVE_CONNECTIONS'],'report':{'sleeve_anchor_selection':priority_report,'mechanics_evaluated':False}}
    def finish_layout(selected,layout_index,joint_fractions=PRIMARY_JOINT_FRACTIONS):
        progress('Construyendo telaraña geodésica…' if request.get('reinforcement_topology') else 'Triangulando entre los refuerzos principales…')
        try:
            local_supports=tuple(a for a in supports if a.id in {r.start_id for r in selected}) if coverage_policy else supports
            if request.get('reinforcement_topology')=='ADAPTIVE_SPIDERWEB_V1':
                from dsg.spiderweb import generate_spiderweb_paths
                lattice,metadata,lattice_report,lattice_rejections,lattice_constraints=generate_spiderweb_paths(surface,perimeter,tuple(selected),owners,local_supports,originals,sleeves,constraints,config,progress,request=request,organic_primary_paths=organic_candidates)
            else:
                lattice,metadata,lattice_report,lattice_rejections,lattice_constraints=generate_lattice_paths(surface,perimeter,tuple(selected),owners,local_supports,originals,sleeves,constraints,config,progress,joint_fractions=joint_fractions,organic_preflight=coverage_policy,envelope_request=request)
        except ValueError as exc:
            return {'status':'NO_VALID_LATTICE_ROUTE','pieces':[],'rejections':rejections+[str(exc)],'report':{'mechanics_evaluated':False,'lattice_complete':False}}
        local_complete=complete and lattice_report.get('surface_search_complete',False)
        if not lattice_report.get('lattice_complete'):
            if coverage_policy:return {'status':'NO_VALID_GEODESIC_LATTICE','pieces':[],'rejections':lattice_rejections,'report':dict(lattice_report,mechanics_evaluated=False)}
            # Preserve the sleeve-first result. Secondary braces must never
            # discard an independently validated direct attachment network.
            lattice=tuple(replace(path,route_id=path.route_id+':SEG0') for path in selected)
            metadata={part.route_id:{'role':'PRIMARY','sleeve_id':owners[path.route_id],'preserve_joint_fractions':True} for path,part in zip(selected,lattice)}
            reference_certificates=[surface_path_certificate(surface,path.points_mm[1:-1],config.surface_tolerance_mm) for path in selected]
            if not all(c['valid'] for c in reference_certificates):
                return {'status':'NO_VALID_SURFACE_REFERENCE','pieces':[],'rejections':['DIRECT_ANCHOR_OFF_IOS'],'report':{'mechanics_evaluated':False}}
            lattice_report['surface_maximum_distance_bound_mm']=max(c['maximum_distance_bound_mm'] for c in reference_certificates)
            lattice_report.update(lattice_layout='DIRECT_SLEEVE_NETWORK',direct_sleeve_layout_valid=True,
                                  lattice_secondary_count=0,lattice_links_completed=0,lattice_complete=False,
                                  secondary_lattice_unavailable=True)

        progress('Suavizando ramas y comprobando pliegues y apoyo en el IOS…')
        from dsg.organic_reinforcement import smooth_network_paths
        try:
            lattice,render_pieces,organic_report=smooth_network_paths(lattice,metadata,config.radius_mm)
            certificates=[]
            for piece in render_pieces:
                validate_path_envelope(piece['points_mm'],piece['radius_mm'],request,frame_projection_distance_mm=projection_distances[piece['origin']] if piece['member_role']=='PRIMARY' else None)
                # Keep a material overlap with the IOS. The reference geodesic is
                # still certified to .02 mm; the smooth tube axis need not copy it.
                body=piece['points_mm'];support_report={}
                if coverage_policy and piece['member_role']=='PRIMARY':body,support_report=central_ios_body(body,projection_distances[piece['origin']],projection_distances[piece['port']],piece['radius_mm'])
                if piece['member_role']=='SECONDARY' and 'joint_neck_start_mm' in piece:
                    body,support_report=central_ios_body(body,piece['joint_neck_start_mm'],piece['joint_neck_end_mm'],piece['radius_mm'])
                certificate=surface_path_certificate(surface,body,piece['radius_mm']*.8+config.surface_tolerance_mm)
                if not certificate['valid']:raise ValueError('ORGANIC_LOST_IOS_CONTACT:'+piece['route_id'])
                certificates.append(dict(route_id=piece['route_id'],**certificate,**support_report))
                if piece['member_role']=='PRIMARY':
                    junction=preflight_sleeve_junction(piece['points_mm'],[piece['radius_mm']]*len(piece['points_mm']),request['sleeves'],target_sleeve_id=piece['sleeve_id'],maximum_deferred_tip_mm=2.)
                    if not junction.candidate_admissible:raise ValueError('ORGANIC_'+junction.status)
                else:
                    from dsg.frame_swept_clearance_core import check_swept_tube_clearance
                    lumens=tuple(CylinderKeepOut(v['id']+':LUMEN',tuple(v['center']),tuple(v['axis']),v['inner_radius_mm'],v['height_mm']*.5) for v in sleeves.values())
                    if not check_swept_tube_clearance(piece['points_mm'],[piece['radius_mm']]*len(piece['points_mm']),lumens).clear:raise ValueError('ORGANIC_LUMEN_INTERSECTION')
            organic_report.update(organic_surface_support_verified=True,organic_surface_certificates=certificates,organic_final_mesh_validated=False)
        except ValueError as exc:
            return {'status':'NO_VALID_ORGANIC_ROUTE','pieces':[],'rejections':rejections+[str(exc)],'report':{'mechanics_evaluated':False,'organic_geometry_valid':False}}
        if coverage_policy:organic_report.update(structural_neck_support_pending=True,structural_neck_support_verified=False)
        final=evaluate_frame(build_frame_graph(perimeter,lattice,config),lattice_constraints,config,continuous_primary_groups=continuous_groups(lattice,metadata))
        final.report['junction_valid']=True;final.report['warnings'].remove('SLEEVE_JUNCTION_REQUIRES_ADAPTER_PREFLIGHT')
        final.report.update(lattice_report)
        final.report.update(organic_report)
        selection=dict(priority_report)
        selection.update(selected_direct_connection_count=len(selected),selected_route_ids=[r.route_id for r in selected],
                         selected_origins_by_sleeve={sid:sorted(r.start_id for r in selected if owners[r.route_id]==sid) for sid in sleeves},
                         selected_distinct_port_count=len({(owners[r.route_id],r.end_id) for r in selected}),selected_layout_rank=layout_index)
        selection['maximum_direct_connections_proven']=False
        selection['maximum_candidate_pool_connections_proven']=priority_report['maximum_direct_connections_proven']
        selection['optimality_scope']='FINITE_VALIDATED_ROUTE_POOL_ONLY'
        final.report['sleeve_anchor_selection']=selection
        final.report['sleeve_priority']='DIRECT_SLEEVE_ANCHORS_BEFORE_SECONDARY_LATTICE'
        final.report['geodesic_reference_maximum_distance_mm']=final.report.pop('surface_maximum_distance_bound_mm')
        final.report.update(search_complete=local_complete,valid_routes=count,perimeter_preserved=True,analysis_removed_zero_area_faces=removed_faces,support_identity_source=request['support_identity_source'],generation_criterion='FAR_FRAME_GEODESIC_LATTICE_V1' if coverage_policy else 'SLEEVE_PRIMARY_SUPPORTS_THEN_IOS_GEODESIC_LATTICE_NOT_STIFFNESS')

        if coverage_policy:
            try:final.report['frame_coverage']=verify_coverage(request,render_pieces,final.report)
            except ValueError as exc:return {'status':'NO_VALID_FRAME_COVERAGE','pieces':[],'rejections':[str(exc)],'report':final.report}
        return {'status':final.status,'pieces':[{'route_id':r.route_id,'origin':r.start_id,'port':r.end_id,'sleeve_id':metadata[r.route_id]['sleeve_id'],'member_role':metadata[r.route_id]['role'],'route_kind':r.backend,'points_mm':r.points_mm.tolist(),'radius_mm':config.radius_mm if r.radius_mm is None else r.radius_mm} for r in lattice],
                'render_pieces':render_pieces,'report':final.report,'rejections':rejections+lattice_rejections+list(final.rejections),'search_complete':local_complete}

    by_id={r.route_id:r for group in groups.values() for r in group}
    alternatives=priority_report.get('alternative_route_sets') or [[r.route_id for r in selected]]
    if coverage_policy:
        representatives={}
        for ids in alternatives:representatives.setdefault(len(ids),ids)
        first=list(representatives.values())
        alternatives=first+[ids for ids in alternatives if ids not in first]
    trials=[]
    distributions=lattice_trial_plan(alternatives,limit=16 if request.get('reinforcement_envelope') else 12,route_nodes={key:(r.start_id,r.end_id) for key,r in by_id.items()}) if coverage_policy else [(ids,PRIMARY_JOINT_FRACTIONS) for ids in alternatives]
    if request.get('reinforcement_topology'):
        unique=[];seen=set()
        for row in distributions:
            signature=tuple(sorted(row[0]))
            if signature not in seen:seen.add(signature);unique.append(row)
        distributions=[(ids,PRIMARY_JOINT_FRACTIONS) for ids in alternatives]
    for layout_index,(route_ids,joint_fractions) in enumerate(distributions):
        progress(f'Anclaje al sleeve · distribución {layout_index+1}/{len(distributions)}')
        candidate=tuple(by_id[key] for key in route_ids)
        response=finish_layout(candidate,layout_index,joint_fractions)
        if response['status']=='CANDIDATE' and request.get('native_case_file'):
            from dsg.blender.native_primary_preflight import preflight_web_candidate
            progress('Comprobando la malla completa de la telaraña…')
            native_web=preflight_web_candidate(request,response)
            response['report']['native_background_web_preflight']=native_web
            if not native_web['valid']:
                response.update(status='NATIVE_WEB_LAYOUT_REJECTED',pieces=[],render_pieces=[],rejections=response.get('rejections',[])+[native_web['reason']])

        if response['status']=='CANDIDATE' and request.get('reinforcement_topology') and request.get('native_case_file'):
            from dsg.generative_web_candidate import densify_candidate
            response=densify_candidate(response,surface,perimeter,supports,originals,constraints,config,request,progress)
            native_dense=preflight_web_candidate(request,response)
            response['report']['native_background_dense_web_preflight']=native_dense
            if not native_dense['valid']:
                response.update(status='NATIVE_DENSE_WEB_REJECTED',pieces=[],render_pieces=[],rejections=response.get('rejections',[])+[native_dense['reason']])

        trials.append({'direct_connections':len(candidate),'route_ids':route_ids,'joint_fractions':list(joint_fractions),'status':response['status'],'rejections':response.get('rejections',[]),'layout_report':layout_trial_report(response.get('report',{}))})
        if coverage_policy and request.get('job_dir'):Path(request['job_dir'],'coverage_layout_trials.json').write_text(json.dumps(trials),encoding='utf-8')
        if response['status']=='CANDIDATE':
            response['report']['sleeve_anchor_selection']['layout_trials']=trials
            return response
    return {'status':'NO_VALID_SLEEVE_ANCHORED_LATTICE','pieces':[],
            'rejections':['NO_COMPLETE_LAYOUT_WITH_VERIFIED_SLEEVE_ANCHORS'],
            'report':{'sleeve_anchor_selection':dict(priority_report,layout_trials=trials),'mechanics_evaluated':False}}



def write_json_atomic(path, payload, *, best_effort=False):
    """A progress reader can briefly block Windows replace; progress is advisory."""
    path = Path(path)
    temporary = path.with_suffix('.tmp')
    for attempt in range(6):
        try:
            temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
            temporary.replace(path)
            return True
        except OSError:
            if attempt == 5:
                if best_effort:
                    return False
                raise
            time.sleep(0.01 * (2 ** attempt))


def main():
    request=json.loads(Path(sys.argv[-1]).read_text('utf-8'));folder=Path(request['job_dir'])
    sys.path.insert(0,str(Path(request['addon_dir']).parent))
    for site in request.get('section_site_paths',[]):
        if site not in sys.path:sys.path.append(site)
    def progress(text):
        write_json_atomic(folder/'progress.json', {'text':text}, best_effort=True)
    started=time.perf_counter()
    try:result={'ok':True,'run_id':request['run_id'],'result':run(request,progress),'elapsed_s':time.perf_counter()-started}
    except Exception as exc:
        traceback.print_exc();result={'ok':False,'run_id':request['run_id'],'error':str(exc)}
    write_json_atomic(folder/'result.json', result)
    print('GENERATIVE_FRAME_DONE',json.dumps({k:v for k,v in result.items() if k!='result'}),flush=True)


if __name__=='__main__':main()
