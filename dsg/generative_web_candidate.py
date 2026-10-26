"""Densify a certified radial backbone without changing its physical curves."""
from dataclasses import replace
import numpy as np

def densify_candidate(outcome,surface,perimeter,supports,originals,constraints,config,request,progress):
    from .geodesic_router import CandidatePath
    from .ios_surface import _readonly
    from .generative_web_growth import grow_web,growth_perimeter
    from .organic_reinforcement import smooth_network_paths
    from .frame_generator import build_frame_graph
    from .frame_optimizer import evaluate_frame
    from .reinforcement_coverage import continuous_groups,verify_coverage
    from .reinforcement_envelope import validate_path_envelope
    from .generative_frame_worker import central_ios_body
    from .geodesic_router import surface_path_certificate
    paths=[];metadata={}
    for piece in outcome['pieces']:
        points=np.asarray(piece['points_mm'],float);length=float(np.linalg.norm(np.diff(points,axis=0),axis=1).sum())
        paths.append(CandidatePath(piece['route_id'],piece['origin'],piece['port'],_readonly(points,float),(),length,length,piece.get('route_kind','IOS'),0,piece['radius_mm']))
        parent=next(row for row in outcome['render_pieces']if piece['route_id']in row['source_routes'])
        metadata[piece['route_id']]=dict(role=piece['member_role'],sleeve_id=piece['sleeve_id'],pre_faired=True,**{k:parent[k]for k in ['web_level','web_sector','reference_points_mm','joint_neck_start_mm','joint_neck_end_mm']if k in parent})
    session=None
    try:
        if request.get('native_case_file'):
            import bpy
            from .blender.generative_growth_session import NativeGrowthSession
            _,base,_=smooth_network_paths(paths,metadata,config.radius_mm)
            session=NativeGrowthSession(bpy.context,base,request)
        paths,metadata,growth,rejections=grow_web(surface,perimeter,tuple(paths),metadata,supports,originals,constraints,config,request,progress,target_edges=12,native_accept=session.accept if session else None)
    finally:
        if session:session.close()
    perimeter=growth_perimeter(perimeter,surface,request)
    paths,render,organic=smooth_network_paths(paths,metadata,config.radius_mm)
    checked=evaluate_frame(build_frame_graph(perimeter,paths,config),constraints,config,continuous_primary_groups=continuous_groups(paths,metadata))
    if checked.status!='CANDIDATE':raise ValueError('DENSE_WEB_FINAL_GRAPH:'+','.join(checked.rejections))
    distances={r['id']:float(np.linalg.norm(np.asarray(r['original_mm'])-r['point_mm']))for r in request['supports']+request['ports']}
    for piece in render:
        start=distances.get(piece['origin'])if piece['member_role']=='PRIMARY'else piece.get('frame_neck_start_mm')
        validate_path_envelope(piece['points_mm'],piece['radius_mm'],request,frame_projection_distance_mm=start,frame_end_projection_distance_mm=piece.get('frame_neck_end_mm'))
        neck_a=distances[piece['origin']]if piece['member_role']=='PRIMARY'else piece['joint_neck_start_mm']
        neck_b=distances[piece['port']]if piece['member_role']=='PRIMARY'else piece['joint_neck_end_mm']
        body,_=central_ios_body(piece['points_mm'],neck_a,neck_b,piece['radius_mm'])
        if not surface_path_certificate(surface,body,piece['radius_mm']*.8+config.surface_tolerance_mm)['valid']:raise ValueError('DENSE_WEB_FINAL_IOS_SUPPORT')
    report=dict(outcome['report'],**growth)
    report.update({key:checked.report[key]for key in ['routing_valid','connectivity_valid','swept_geometry_valid','length_mm','nominal_volume_mm3']})
    report.update(organic);report.update(organic_surface_support_verified=True,organic_final_mesh_validated=False,lattice_secondary_count=sum(p['member_role']=='SECONDARY'for p in render),lattice_links_completed=sum(p['member_role']=='SECONDARY'for p in render))
    report['frame_coverage']=verify_coverage(request,render,report)
    return dict(outcome,render_pieces=render,report=report,web_growth_supports=request.get('web_growth_supports',[]),pieces=[dict(route_id=p.route_id,origin=p.start_id,port=p.end_id,sleeve_id=metadata[p.route_id]['sleeve_id'],member_role=metadata[p.route_id]['role'],route_kind=p.backend,points_mm=p.points_mm.tolist(),radius_mm=p.radius_mm)for p in paths],rejections=outcome.get('rejections',[])+rejections)

def validated_growth_request(request,outcome):
    """Untrusted worker rows must point to unchanged, exact frame vertices."""
    rows=outcome.get('web_growth_supports',[])
    if not rows:return request
    if len(rows)>128:raise ValueError('DENSE_WEB_INVALID_FRAME_SAMPLES')
    data=np.load(request['frame_support_file'],allow_pickle=False);vertices=data['vertices']
    seen={r['id']for r in request['supports']}
    for row in rows:
        index=row['frame_vertex_index']
        if not isinstance(index,int)or index<0 or index>=len(vertices)or row['id']!='GF'+str(index)or row['id']in seen:raise ValueError('DENSE_WEB_INVALID_FRAME_SAMPLE')
        if not np.array_equal(vertices[index],row['original_mm']):raise ValueError('DENSE_WEB_FRAME_SAMPLE_CHANGED')
        seen.add(row['id'])
    return dict(request,web_growth_supports=rows)
