"""Blender snapshot, background transport and reversible reinforcement review."""
import array,hashlib,json,os,subprocess,tempfile,uuid
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector

OWNER='DSG_generative_preview';SAVED='DSG_generative_candidate_json'
STATE={'process':None,'request':None,'result':None,'scene_name':None,'message':'','visibility':{}}


def case_geometry_fingerprint(obj):
    digest=hashlib.sha256();digest.update(obj.name.encode());digest.update(np.asarray(obj.matrix_world,float).tobytes())
    if obj.type=='MESH':
        coords=array.array('f',[0.])*(len(obj.data.vertices)*3);obj.data.vertices.foreach_get('co',coords)
        ids=array.array('i',[0])*len(obj.data.loops);obj.data.loops.foreach_get('vertex_index',ids)
        counts=array.array('i',[0])*len(obj.data.polygons);obj.data.polygons.foreach_get('loop_total',counts)
        digest.update(coords.tobytes());digest.update(ids.tobytes());digest.update(counts.tobytes())
        if obj.data.shape_keys:
            for key in obj.data.shape_keys.key_blocks:
                digest.update(repr((key.name,key.value,key.mute,key.vertex_group)).encode())
                values=array.array('f',[0.])*(len(key.data)*3);key.data.foreach_get('co',values);digest.update(values.tobytes())
    elif obj.type=='CURVE':
        for spline in obj.data.splines:
            digest.update(repr([(tuple(p.co),float(p.radius)) for p in spline.points]).encode())
            digest.update(repr([(tuple(p.co),tuple(p.handle_left),tuple(p.handle_right),float(p.radius)) for p in spline.bezier_points]).encode())
        digest.update(repr((obj.data.bevel_depth,obj.data.bevel_resolution)).encode())
    for modifier in obj.modifiers:
        settings={}
        for prop in modifier.bl_rna.properties:
            if prop.identifier in {'rna_type','show_expanded'}:continue
            try:
                value=getattr(modifier,prop.identifier)
                if isinstance(value,(str,int,float,bool)):settings[prop.identifier]=value
                elif prop.type=='POINTER':settings[prop.identifier]=getattr(value,'name',None)
                elif prop.is_array:settings[prop.identifier]=list(value)
            except (AttributeError,TypeError,ValueError):pass
        digest.update(json.dumps(settings,sort_keys=True).encode())
    return digest.hexdigest()


def evaluated_geometry_fingerprint(context,obj):
    vertices=faces=None
    if obj.type in {'MESH','CURVE'}:
        vertices,faces=_export_mesh(context,obj)
    # Evaluating a hidden object also resolves its cold matrix_world after load.
    # Hash the source only afterwards, so both halves describe the same state.
    digest=hashlib.sha256(case_geometry_fingerprint(obj).encode())
    if vertices is not None:
        digest.update(vertices.tobytes());digest.update(faces.tobytes())
    return digest.hexdigest()


def case_fingerprint(context):
    from .. import frame_structural as s,guide_module as g
    context.view_layer.update()
    props=context.scene.dsg_props;frame=s._frame_obj(context);surface=s._passive_obj(context);guide=g.get_active_guide_obj(props)
    rows={o.name:evaluated_geometry_fingerprint(context,o) for o in (frame,surface,guide) if o is not None}
    if frame is not None:
        rows['frame_anchors']=str(frame.get('DSG_frame_source_points_json',''))
        rows['semantic_anchors']=str(frame.get(s.SUPPORT_KEY,''))
    rows['sleeves']=s._sleeve_context(context)
    for sleeve in rows['sleeves']:
        obj=bpy.data.objects.get(g.SLEEVE_SOURCE_PREFIX+f"{int(sleeve['id'][1:]):02d}")
        rows['sleeve_source:'+sleeve['id']]=evaluated_geometry_fingerprint(context,obj) if obj is not None else None
    rows['functional_paths']=str(props.irr_paths_json)
    rows['radius']=float(props.connector_diameter)*.5
    rows['step']=int(props.current_step)
    rows['functional_metadata']={str(k):str(guide[k]) for k in sorted(guide.keys()) if any(t in k.lower() for t in ('irrigation','lateral','frangible'))} if guide is not None else {}
    for o in _protected_objects(context):rows['keepout:'+o.name]=evaluated_geometry_fingerprint(context,o)
    for o in g.get_confirmed_reinforcement_curves():rows['reinforcement:'+o.name]=evaluated_geometry_fingerprint(context,o)
    model=bpy.data.objects.get(g.CLOSED_MODEL_NAME)
    rows['ios_geometry']=evaluated_geometry_fingerprint(context,model) if model else None
    rows['coverage_policy']='FAR_FRAME_GEODESIC_LATTICE_V2'
    rows['reinforcement_envelope']='FRAME_ABOVE_SIDEWALL_ONLY_V1'
    rows['reinforcement_topology']='ADAPTIVE_SPIDERWEB_V1'
    rows['generator_schema']='ORGANIC_IOS_SLEEVE_PRIORITY_3'
    rows['unit_scale']=float(context.scene.unit_settings.scale_length)
    return hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()


def _protected_objects(context):
    # Functional cutters and explicit anatomical keep-outs, never the passive
    # contact surface itself. Registered object roles/names are DSG contracts.
    from .. import guide_module as g
    result=[]
    for obj in context.scene.objects:
        if obj.get('DSG_frame_keep_out') or (g.core.get_role(obj)==g.ROLE_CUTTER if hasattr(g,'core') and hasattr(g.core,'get_role') else False):
            if obj.get('DSG_frame_keep_out') or any(s in obj.name for s in ('Irr','Lateral','Frangible')):result.append(obj)
        elif obj.type=='MESH' and any(obj.name.startswith(s) for s in ('DSG_IrrCut','DSG_IrrLumen','DSG_LateralOpening','DSG_Frangible')):result.append(obj)
    return sorted({o.name:o for o in result}.values(),key=lambda o:o.name)


def _export_mesh(context,obj):
    old=(obj.hide_viewport,obj.hide_get());evaluated=None
    try:
        obj.hide_viewport=False;obj.hide_set(False);context.view_layer.update()
        deps=context.evaluated_depsgraph_get();evaluated=obj.evaluated_get(deps);mesh=evaluated.to_mesh()
        mesh.calc_loop_triangles();vertices=np.empty(len(mesh.vertices)*3);mesh.vertices.foreach_get('co',vertices)
        faces=np.empty(len(mesh.loop_triangles)*3,np.int32);mesh.loop_triangles.foreach_get('vertices',faces)
        vertices=vertices.reshape(-1,3);mx=np.asarray(evaluated.matrix_world,float)
        return vertices@mx[:3,:3].T+mx[:3,3],faces.reshape(-1,3)
    finally:
        if evaluated is not None:evaluated.to_mesh_clear()
        obj.hide_viewport=old[0];obj.hide_set(old[1]);context.view_layer.update()


def functional_coverage(guide,obstacles,guide_name):
    owned=[o for o in obstacles if o.get('owner')==guide_name and o.get('closed')]
    if str(guide.get('DSG_irrigation_resolution','')).upper()=='APPLIED':
        count=int(guide.get('DSG_irrigation_saved_path_count',guide.get('DSG_irrigation_cut_count',0)))
        covered={i for o in owned if o.get('kind')=='IRRIGATION_LUMEN' for i in o.get('channel_indices',[])}
        if count<=0 or not set(range(count)).issubset(covered):return False
    if guide.get('DSG_sleeve_lateral_opening',False) and not any(o.get('kind')=='LATERAL_OPENING' for o in owned):return False
    return True


def snapshot_frame_case(context,folder=None):
    from .. import frame_structural as s,guide_module as g,segmentation_engines
    frame=s._frame_obj(context);surface=bpy.data.objects.get(g.CLOSED_MODEL_NAME);props=context.scene.dsg_props;guide=g.get_active_guide_obj(props)
    if frame is None or surface is None or guide is None:raise ValueError('Faltan frame, IOS cerrado o guía.')
    if context.mode!='OBJECT':raise ValueError('Termina la edición antes de generar refuerzos.')
    if int(props.current_step)!=g.STEP_REINFORCEMENT:raise ValueError('Abre el paso de refuerzos.')
    folder=Path(folder or tempfile.mkdtemp(prefix='DSG_Generative_'));folder.mkdir(parents=True,exist_ok=True)
    before=case_fingerprint(context);ctx=s.get_frame_context(context)
    old=(surface.hide_viewport,surface.hide_get())
    try:
        surface.hide_viewport=False;surface.hide_set(False);context.view_layer.update()
        g._clear_frame_surface_graph_cache() if hasattr(g,'_clear_frame_surface_graph_cache') else g._FRAME_SURFACE_GRAPH_CACHE.clear()
        cache,_reused,error=g._build_frame_surface_graph_cache(context,surface)
        if cache is None:raise ValueError(error)
        tree,_mx,_inv,error=g._frame_width_surface_bvh(context,surface,cache)
        if tree is None:raise ValueError(error)
        np.savez(folder/'surface.npz',vertices=cache['coords'],triangles=cache['triangles'],offsets=cache['csr_offsets'],destinations=cache['csr_dst'],lengths=cache['csr_weights'])
        def project(label,point,limit=None):
            row=g._frame_surface_projection(cache,Vector(point),max_distance_mm=limit)
            if row is None or row['triangle_index']<0:raise ValueError('NO_SURFACE_ANCHOR:'+label)
            bary=np.asarray(row['barycentric'],float)
            if bary.min() < -1e-4 or bary.max() > 1.0001:
                raise ValueError('INVALID_SURFACE_PROJECTION:'+label)
            bary=np.clip(bary,0.,1.);bary/=bary.sum()
            triangle=cache['coords'][cache['triangles'][row['triangle_index']]]
            projected=bary@triangle
            return {'id':label,'face_index':row['triangle_index'],'barycentric':bary.tolist(),'point_mm':projected.tolist(),'original_mm':list(point),'normal':list(row['normal'])}
        from .reinforcement_envelope import upper_frame_origins
        supports,spacing,rejected_origins,sampled_origins,origin_attempts,frame_entry_axis=upper_frame_origins(
            context,frame,ctx,project,folder,max(.3,float(props.connector_diameter)*.5))
        ports=[]
        for sleeve in ctx['sleeves']:
            _center,points,_matrix=s._fem_sleeve_cardinal_points(sleeve,g._build_world_surface_bvh(context,surface))
            for i,point in enumerate(points):
                try:row=project(sleeve['id']+'_PORT'+str(i),point)
                except ValueError:continue
                offset=np.asarray(row['original_mm'])-row['point_mm']
                if np.linalg.norm(offset)>12. or float(offset@np.asarray(row['normal']))<-.20:continue
                row.update(sleeve_id=sleeve['id'],axis=sleeve['axis']);ports.append(row)
    finally:
        surface.hide_viewport=old[0];surface.hide_set(old[1]);context.view_layer.update()
    if not ports:raise ValueError('No hay uniones al sleeve verificables sobre la superficie.')
    obstacles=[]
    from ..guide_export.mesh_checks import manifold_report
    for i,obj in enumerate(_protected_objects(context)):
        v,f=_export_mesh(context,obj);np.savez(folder/('obstacle_'+str(i)+'.npz'),vertices=v,triangles=f)
        kind=str(obj.get('DSG_functional_volume_kind',''))
        if not kind:
            kind='IRRIGATION_LUMEN' if obj.name.startswith(('DSG_IrrCut','DSG_IrrLumen')) else ('LATERAL_OPENING' if 'Lateral' in obj.name else 'OTHER')
        indices=obj.get('DSG_irrigation_channel_indices',[])
        if isinstance(indices,str):
            try:indices=json.loads(indices)
            except ValueError:indices=[]
        if 'DSG_irrigation_index' in obj:indices=[int(obj['DSG_irrigation_index'])]
        obstacles.append({'label':obj.name,'file':str(folder/('obstacle_'+str(i)+'.npz')),'closed':not manifold_report(v,f).blocking,
                          'kind':kind,'owner':str(obj.get('DSG_guide',obj.get('DSG_owner_guide',''))),'channel_indices':list(indices)})
    if not functional_coverage(guide,obstacles,guide.name):
        from .functional_keepouts import export_missing
        obstacles.extend(export_missing(context,guide,folder,_export_mesh))
    required=functional_coverage(guide,obstacles,guide.name)
    if not required:
        raise ValueError('Faltan volúmenes verificables de irrigación o apertura lateral.')
    request={'schema_version':3,'run_id':uuid.uuid4().hex,'addon_dir':str(Path(__file__).resolve().parents[1]),'job_dir':str(folder),
             'scene_name':context.scene.name,'case_fingerprint':before,'frame_name':frame.name,'guide_name':guide.name,
             'frame_digest':case_geometry_fingerprint(frame),'surface_name':surface.name,'surface_file':str(folder/'surface.npz'),
             'surface_role':'IOS','surface_matrix':[list(r) for r in surface.matrix_world],'supports':supports,'ports':ports,'sleeves':ctx['sleeves'],
             'frame_support_file':str(folder/'frame_support.npz'),'support_identity_source':ctx['support_identity_source'],'radius_mm':max(.3,float(props.connector_diameter)*.5),
             'obstacles':obstacles,'required_zones_complete':required,'section_site_paths':segmentation_engines.active_site_paths()}
    for sleeve in request['sleeves']:
        implant=bpy.data.objects.get(sleeve['implant_name'])
        sleeve['entry_axis']=(np.asarray(sleeve['axis'])*g.get_sleeve_occlusal_sign(props,implant)).tolist()
    request['frame_lower_surface_file']=str(folder/'frame_lower_surface.npz')
    request['reinforcement_topology']='ADAPTIVE_SPIDERWEB_V1'
    request['reinforcement_envelope']={'version':1,'policy':'FRAME_ABOVE_SIDEWALL_ONLY_V1',
        'frame_entry_axis':frame_entry_axis,'frame_origins':'UPPER_SURFACE_ONLY','sleeve_contact':'CURVED_WALL_ONLY'}
    from ..reinforcement_coverage import augment_request
    request['lateral_openings']=json.loads(str(guide.get('DSG_sleeve_lateral_opening_records','[]'))) if guide.get('DSG_sleeve_lateral_opening') else []
    augment_request(request,project,float(s.SLEEVE_ATTACHMENT_END_CLEARANCE_MM))
    from .axial_web_pipeline import augment_snapshot
    augment_snapshot(context,request,folder)
    if case_fingerprint(context)!=before:raise ValueError('STALE_INPUT: el caso cambió al exportar.')
    (folder/'request.json').write_text(json.dumps(request),'utf-8');return request


def preview_objects():
    return [o for o in bpy.data.objects if o.get(OWNER,False)]


def _stop():
    from .. import lifecycle
    lifecycle.unregister_timer(poll)
    process=STATE.get('process')
    if process is not None and process.poll() is None:process.terminate()
    STATE['process']=None


def discard_candidate(context):
    from .. import guide_module as g
    _stop()
    for obj in preview_objects():g.safe_remove_object_with_data(obj)
    for name,hidden in STATE.get('visibility',{}).items():
        obj=bpy.data.objects.get(name)
        if obj is not None:obj.hide_set(hidden)
    if SAVED in context.scene:del context.scene[SAVED]
    STATE.update(request=None,result=None,visibility={},message='Propuesta descartada.')


def stage_candidate(context,request,result):
    if request.get('reinforcement_topology')=='AXIAL_RADIAL_WEB_V2':
        from .axial_web_pipeline import stage
        return stage(context,request,result)
    from ..generative_web_candidate import validated_growth_request
    request=validated_growth_request(request,result)
    from .. import guide_module as g
    if request['case_fingerprint']!=case_fingerprint(context):raise ValueError('STALE_INPUT: repite la generación.')
    from .reinforcement_envelope import verify_context_envelope
    verify_context_envelope(context,request)
    if result.get('status')!='CANDIDATE':raise ValueError('No hay un candidato geométrico válido.')
    if not all(result.get('report',{}).get(key,False) for key in ('routing_valid','connectivity_valid','swept_geometry_valid','junction_valid')):
        raise ValueError('UNVERIFIED_GEOMETRY: faltan comprobaciones de la propuesta.')
    if result.get('report',{}).get('lattice_layout','').startswith('FREE_BRIDGES') or any(p.get('route_kind')=='CERTIFIED_FREE_BRIDGE' for p in result.get('pieces',[])):
        raise ValueError('SURFACE_ROUTES_REQUIRED: la celosía debe recorrer el IOS.')
    direct_layout=result.get('report',{}).get('lattice_layout')=='DIRECT_SLEEVE_NETWORK' and result['report'].get('direct_sleeve_layout_valid',False)
    if result.get('report',{}).get('lattice_layout') and not result['report'].get('lattice_complete') and not direct_layout:
        raise ValueError('INCOMPLETE_LATTICE: faltan conexiones de la celosía.')
    if result.get('report',{}).get('lattice_layout') and (request.get('surface_role')!='IOS' or not result['report'].get('surface_adherence_verified')):
        raise ValueError('IOS_SURFACE_UNVERIFIED: faltan comprobar los tramos sobre el IOS.')
    if request.get('schema_version',0)>=2 and (not result['report'].get('organic_geometry_valid') or not result['report'].get('organic_surface_support_verified') or not result.get('render_pieces')):
        raise ValueError('ORGANIC_GEOMETRY_UNVERIFIED: faltan suavidad y apoyo del refuerzo.')
    if request.get('coverage_policy'):
        from ..reinforcement_coverage import verify_coverage
        verify_coverage(request,result.get('render_pieces',result['pieces']),result['report'])
    old=list(preview_objects());staged=[];prepared=[]
    pieces=result.get('render_pieces',result['pieces'])
    try:
        if result.get('render_pieces'):
            from .organic_reinforcement import build_network
            STATE['building_candidate']=True
            try:prepared=build_network(context,pieces,request)
            finally:STATE['building_candidate']=False
            verify_context_envelope(context,request)
            result=dict(result,report=dict(result['report'],organic_final_mesh_validated=True,organic_collar_count=2*len(prepared)))
            if request.get('coverage_policy'):
                receipts={piece['route_id']:json.loads(obj['DSG_sleeve_anchor_receipt_json']) for piece,obj in zip(pieces,prepared) if piece['member_role']=='PRIMARY'}
                result['report']['frame_coverage']=verify_coverage(request,pieces,result['report'],receipts)
                if not all(obj.get('DSG_organic_final_support_verified') and obj.get('DSG_organic_final_keepouts_verified') for obj in prepared):raise ValueError('STRUCTURAL_NECK_UNVERIFIED')
                result['report'].update(structural_neck_support_pending=False,structural_neck_support_verified=True)
                if request.get('reinforcement_topology'):
                    web_joints=[obj for piece,obj in zip(pieces,prepared) if piece['member_role']=='SECONDARY']
                    if not web_joints or not all(obj.get('DSG_web_joints_verified') for obj in web_joints):raise ValueError('WEB_PHYSICAL_JUNCTIONS_UNVERIFIED')
                    result['report']['web_final_junctions_verified']=True
                    if not all(obj.get('DSG_web_frame_rim_verified') for obj in prepared):raise ValueError('WEB_FRAME_RIM_UNVERIFIED')
                    result['report']['web_frame_rim_final_verified']=True
        for index,piece in enumerate(pieces):
            if prepared:obj=prepared[index];mesh=obj.data
            else:
                from ..frame_generator import sweep_path_mesh
                vertices,faces=sweep_path_mesh(piece['points_mm'],piece['radius_mm'])
                name='DSG_GenerativePreview_'+request.get('run_id','test')+'_'+str(index)
                mesh=bpy.data.meshes.new(name);mesh.from_pydata(vertices.tolist(),[],faces.tolist());mesh.update()
                obj=bpy.data.objects.new(name,mesh);context.scene.collection.objects.link(obj)
            staged.append(obj);obj[OWNER]=True;obj['DSG_generative_run_id']=request.get('run_id','test')
            obj['DSG_generative_radius_mm']=float(piece['radius_mm'])
            obj['DSG_generative_route_id']=piece['route_id'];obj['DSG_reinforcement_confirmed']=False
            role=piece.get('member_role','PRIMARY');obj['DSG_lattice_member_role']=role;obj['DSG_lattice_route_kind']=piece.get('route_kind','SURFACE')
            color=(1.,.28,.05,1.) if role=='PRIMARY' else (.04,.8,.9,1.)
            obj.color=color;obj.show_in_front=False
            material_name='DSG_Lattice_'+role
            material=bpy.data.materials.get(material_name) or bpy.data.materials.new(material_name)
            material.diffuse_color=color;material.use_nodes=True
            shader=material.node_tree.nodes.get('Principled BSDF')
            if shader:shader.inputs['Base Color'].default_value=color;shader.inputs['Roughness'].default_value=.45
            obj.data.materials.clear();obj.data.materials.append(material)
            for polygon in mesh.polygons:polygon.use_smooth=True
    except Exception:
        for obj in set(staged+prepared):g.safe_remove_object_with_data(obj)
        raise
    for obj in old:g.safe_remove_object_with_data(obj)
    visibility=dict(STATE.get('visibility',{}))
    for obj in g.get_confirmed_reinforcement_curves():
        visibility.setdefault(obj.name,bool(obj.hide_get()));obj.hide_set(True)
    STATE.update(request=request,result=result,scene_name=context.scene.name,visibility=visibility,message=('Telaraña propuesta · mallas y uniones verificadas.' if request.get('reinforcement_topology') else 'Refuerzos propuestos · geometría; mecánica pendiente.'))
    STATE['preview_hashes']={obj.name:case_geometry_fingerprint(obj) for obj in staged}
    STATE['sleeve_anchor_receipts']={obj.name:obj['DSG_sleeve_anchor_receipt_json'] for obj in staged if obj.get('DSG_lattice_member_role')=='PRIMARY' and obj.get('DSG_sleeve_anchor_receipt_json')}
    if request.get('schema_version',0)>=3:
        result['report']['physical_sleeve_anchor_count']=len(STATE['sleeve_anchor_receipts'])
        result['report']['physical_sleeve_anchors_verified']=len(STATE['sleeve_anchor_receipts'])==sum(p.get('member_role')=='PRIMARY' for p in pieces)
    context.scene[SAVED]=json.dumps({'request':request,'result':result,'preview_hashes':STATE['preview_hashes'],'visibility':visibility,'sleeve_anchor_receipts':STATE['sleeve_anchor_receipts']})
    return staged


def accept_candidate(context):
    if (STATE.get('request') or {}).get('reinforcement_topology')=='AXIAL_RADIAL_WEB_V2':
        from .axial_web_pipeline import accept
        return accept(context)
    from .. import guide_module as g,frame_structural as s
    request=STATE.get('request');result=STATE.get('result')
    if not request or not result or request['case_fingerprint']!=case_fingerprint(context):raise ValueError('STALE_INPUT: el caso cambió; repite la propuesta.')
    from .reinforcement_envelope import verify_context_envelope
    verify_context_envelope(context,request)
    staged=preview_objects()
    if not staged or {obj.name for obj in staged}!=set(STATE.get('preview_hashes',{})) or len(staged)!=len(result.get('render_pieces',result['pieces'])) or any(STATE['preview_hashes'].get(obj.name)!=case_geometry_fingerprint(obj) for obj in staged):raise ValueError('STALE_PREVIEW: la propuesta ha sido modificada.')
    if request.get('schema_version',0)>=3:
        expected={p['route_id']:p for p in result.get('render_pieces',[])}
        actual={obj.get('DSG_generative_route_id'):obj for obj in staged}
        if len(actual)!=len(staged) or set(actual)!=set(expected) or any(actual[key].get('DSG_lattice_member_role')!=piece['member_role'] for key,piece in expected.items()):
            raise ValueError('SLEEVE_ANCHOR_UNVERIFIED: la identidad del refuerzo ha cambiado.')
        receipts=STATE.get('sleeve_anchor_receipts',{})
        primary=[actual[key] for key,piece in expected.items() if piece['member_role']=='PRIMARY']
        if not primary or any(not receipts.get(obj.name) or receipts[obj.name]!=obj.get('DSG_sleeve_anchor_receipt_json') or not json.loads(receipts[obj.name]).get('positive_volume_overlap') or json.loads(receipts[obj.name]).get('sleeve_id')!=expected[obj['DSG_generative_route_id']]['sleeve_id'] for obj in primary):
            raise ValueError('SLEEVE_ANCHOR_UNVERIFIED: falta una unión real al sleeve.')
        if any(sum(piece['member_role']=='PRIMARY' and piece['sleeve_id']==sleeve['id'] for piece in expected.values())<2 for sleeve in request['sleeves']):
            raise ValueError('SLEEVE_ANCHOR_UNVERIFIED: faltan conexiones independientes.')
    if request.get('coverage_policy'):
        from ..reinforcement_coverage import verify_coverage
        pieces=result.get('render_pieces',result['pieces'])
        physical={obj.get('DSG_generative_route_id'):json.loads(str(obj.get('DSG_sleeve_anchor_receipt_json','{}'))) for obj in staged}
        verify_coverage(request,pieces,result['report'],physical)
        if result['report'].get('structural_neck_support_pending',True) or not all(obj.get('DSG_organic_final_support_verified') and obj.get('DSG_organic_final_keepouts_verified') for obj in staged):raise ValueError('STRUCTURAL_NECK_UNVERIFIED')
    if request.get('reinforcement_envelope') and not all(obj.get('DSG_reinforcement_envelope_verified') for obj in staged):raise ValueError('REINFORCEMENT_ENVELOPE_UNVERIFIED')
    if request.get('reinforcement_topology') and not all(obj.get('DSG_web_joints_verified') for obj in staged if obj.get('DSG_lattice_member_role')=='SECONDARY'):raise ValueError('WEB_PHYSICAL_JUNCTIONS_UNVERIFIED')
    if request.get('reinforcement_topology') and not all(obj.get('DSG_web_frame_rim_verified') for obj in staged):raise ValueError('WEB_FRAME_RIM_UNVERIFIED')
    guide=bpy.data.objects.get(request['guide_name']);frame=s._frame_obj(context);props=context.scene.dsg_props
    old=g.get_confirmed_reinforcement_curves();saved=[];count=int(props.reinforcement_count)
    preview_names=[(obj,obj.name) for obj in staged]
    keys=('DSG_frame_fem_hard_safe','DSG_frame_fem_recommended','DSG_generative_report_json','DSG_frame_fem_design_aid_not_validation')
    guide_state={key:(key in guide,guide.get(key)) for key in keys}
    try:
        for obj in old:
            saved.append((obj,obj.name,bool(obj.hide_get()),bool(obj.get('DSG_reinforcement_confirmed'))))
            obj.name='DSG_GenerativeArchive_'+uuid.uuid4().hex[:8]+'_'+obj.name;obj['DSG_reinforcement_confirmed']=False;obj.hide_set(True)
        for index,obj in enumerate(staged):
            obj.name=g.REINFORCEMENT_PREFIX+f'{index:02d}';obj[OWNER]=False
            obj['DSG_reinforcement_confirmed']=True;obj['DSG_reinforcement_index']=index
            obj['DSG_reinforcement_generative_generated']=True;obj['DSG_reinforcement_diameter']=float(obj['DSG_generative_radius_mm'])*2.
            g.register_dsg_object(obj,g.ROLE_REINFORCEMENT,obj.name,{})
        if case_geometry_fingerprint(frame)!=request.get('frame_digest',case_geometry_fingerprint(frame)):raise ValueError('FRAME_CHANGED')
        props.reinforcement_count=len(staged)
        guide['DSG_frame_fem_hard_safe']=False;guide['DSG_frame_fem_recommended']=False
        guide['DSG_generative_report_json']=json.dumps(result['report'])
        guide['DSG_frame_fem_design_aid_not_validation']=True
        STATE['accepted_frame_digest']=case_geometry_fingerprint(frame)
    except Exception:
        for obj,name in preview_names:obj.name=name;obj[OWNER]=True;obj['DSG_reinforcement_confirmed']=False
        for obj,name,hidden,confirmed in saved:obj.name=name;obj.hide_set(hidden);obj['DSG_reinforcement_confirmed']=confirmed
        for key,(present,value) in guide_state.items():
            if present:guide[key]=value
            elif key in guide:del guide[key]
        props.reinforcement_count=count;raise
    if SAVED in context.scene:del context.scene[SAVED]
    STATE.update(request=None,result=None,visibility={},message='Refuerzos aplicados · validación mecánica pendiente.')


def freeze_for_undo():
    _stop();STATE.update(request=None,result=None,visibility={},scene_name=None)


def recover(context):
    if STATE.get('result') is None and context.scene.get(SAVED):
        try:STATE.update(json.loads(context.scene[SAVED]));STATE['scene_name']=context.scene.name
        except (ValueError,TypeError):STATE['message']='Propuesta guardada no verificable: descártala.'


def start(context):
    from .. import lifecycle
    if STATE.get('process') is not None:raise ValueError('Ya hay un cálculo en curso.')
    discard_candidate(context);request=snapshot_frame_case(context);folder=Path(request['job_dir'])
    if request.get('reinforcement_topology'):
        request['native_case_file']=str(Path(request['job_dir'])/'clinical_case.blend')
        original_path=bpy.data.filepath
        bpy.ops.wm.save_as_mainfile(filepath=request['native_case_file'],copy=True,check_existing=False)
        if bpy.data.filepath!=original_path or case_fingerprint(context)!=request['case_fingerprint']:raise ValueError('NATIVE_SNAPSHOT_CHANGED_CASE')
        (Path(request['job_dir'])/'request.json').write_text(json.dumps(request),encoding='utf-8')

    worker=Path(__file__).resolve().parents[1]/'generative_frame_worker.py';log=(folder/'worker.log').open('w',encoding='utf-8')
    try:
        process=subprocess.Popen([bpy.app.binary_path,'--background','--factory-startup','--python-exit-code','1','--python',str(worker),'--',str(folder/'request.json')],stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    finally:log.close()
    STATE.update(process=process,request=request,result=None,scene_name=context.scene.name,message='Calculando rutas sobre la superficie…')
    lifecycle.register_timer(poll,first_interval=.3)


def poll():
    process=STATE.get('process');request=STATE.get('request')
    if process is None or request is None:return None
    scene=bpy.data.scenes.get(STATE.get('scene_name',''))
    if scene is None or bpy.context.scene!=scene:freeze_for_undo();return None
    if int(scene.dsg_props.current_step)!=6:freeze_for_undo();return None
    folder=Path(request['job_dir']);progress=folder/'progress.json'
    if progress.exists():
        try:STATE['message']=json.loads(progress.read_text('utf-8'))['text']
        except (ValueError,OSError):pass
    if process.poll() is None:return .4
    STATE['process']=None
    try:
        result=json.loads((folder/'result.json').read_text('utf-8'))
        if result.get('run_id')!=request['run_id']:raise ValueError('Resultado de otro cálculo.')
        if not result.get('ok'):raise ValueError(result.get('error','El cálculo no produjo resultados.'))
        if result['result']['status']=='CANDIDATE':stage_candidate(bpy.context,request,result['result'])
        else:
            from ..reinforcement_coverage import failure_message
            STATE.update(result=result['result'],message=failure_message(result['result'],request))
    except Exception as exc:STATE['message']=str(exc)
    for area in bpy.context.screen.areas if bpy.context.screen else []:area.tag_redraw()
    return None


def _draw_status(layout, message, icon='INFO'):
    import textwrap
    # Workflow's minimal-layout proxy suppresses passive labels. Calculation
    # progress and failure diagnostics must remain visible beside this action.
    target=getattr(layout,'_layout',layout)
    for index, line in enumerate(textwrap.wrap(str(message), width=45)):
        target.label(text=line, icon=icon if index == 0 else 'NONE')


def draw_review(layout,context):
    from .. import ui_style
    recover(context)
    from .. import guide_module as g
    if (STATE.get('result') or {}).get('assembly_file') or any(o.get('DSG_reinforcement_assembly') for o in g.get_confirmed_reinforcement_curves()):
        from .axial_web_pipeline import ensure_assembly_visibility
        ensure_assembly_visibility()
    if STATE.get('process') is not None or STATE.get('building_candidate'):
        _draw_status(layout,STATE['message'],icon='TIME')
        if not STATE.get('building_candidate'):layout.operator('dsg.discard_generative_frame',text='CANCELAR')
        return True
    if preview_objects():
        gaps=(STATE.get('result') or {}).get('report',{}).get('frame_coverage',{}).get('uncovered_targets',[])
        if gaps:_draw_status(layout,'Propuesta de celosía. Cobertura lateral pendiente: '+str(len(gaps))+' zona(s).',icon='WARNING')
        layout.label(text='Propuesta de refuerzos · revisión geométrica')
        layout.label(text='Mallas y uniones comprobadas; revisión mecánica pendiente.' if (STATE.get('request') or {}).get('reinforcement_topology') else 'Mecánica y sección final pendientes de validar.',icon='INFO')
        ui_style.primary_action(layout).operator('dsg.accept_generative_frame',text='USAR TELARAÑA' if (STATE.get('request') or {}).get('reinforcement_topology') else 'USAR CELOSÍA' if (STATE.get('result') or {}).get('report',{}).get('lattice_complete') else 'USAR REFUERZOS')
        ui_style.tertiary_action(layout).operator('dsg.discard_generative_frame',text='Descartar telaraña' if (STATE.get('request') or {}).get('reinforcement_topology') else 'Descartar celosía' if (STATE.get('result') or {}).get('report',{}).get('lattice_complete') else 'Descartar refuerzos')
        return True
    if STATE.get('message'):_draw_status(layout,STATE['message'])
    return False


class DSG_OT_AcceptGenerativeFrame(bpy.types.Operator):
    bl_idname='dsg.accept_generative_frame';bl_label='Usar refuerzos';bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        try:accept_candidate(context)
        except ValueError as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class DSG_OT_DiscardGenerativeFrame(bpy.types.Operator):
    bl_idname='dsg.discard_generative_frame';bl_label='Descartar refuerzos';bl_options={'REGISTER','UNDO'}
    def execute(self,context):discard_candidate(context);return {'FINISHED'}


CLASSES=(DSG_OT_AcceptGenerativeFrame,DSG_OT_DiscardGenerativeFrame)
