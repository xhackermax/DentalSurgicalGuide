"""Independent, cancellable position/size proposals; originals stay untouched."""
import hashlib,json,shutil,subprocess,tempfile,uuid
from pathlib import Path
import bpy,numpy as np
from mathutils import Matrix,Vector

PREVIEW='DSG_OptimizationPreview'
MIN_GAIN=.03  # ~4 of 384 surface samples: below this a "better" pose is sampling noise.
STATE={'process':None,'log':None,'scene':None,'target':'','run_id':'','folder':None,'fingerprint':'',
       'result':None,'purpose':'SEARCH','mode':'POSITION','message':'','request':None}
REGISTERED={'active':False}
JOBS=set()
PREVIEW_VISIBILITY={}

def target(context):
    from .implant_plane import selected_implant
    return selected_implant(context)

def settings(scene):
    # Legacy saved sliders do not override the active fixed profile.
    from ..optimizer_profile import settings as fixed_settings
    return fixed_settings()


def bone_object(scene,lower):
    """Native bone for the search.  The full route segments it apart from the
    teeth; the simple route only has the CBCT arch (bone and teeth together),
    which is still the bone envelope the implant must stay inside."""
    obj=bpy.data.objects.get('Dental_DICOM_Mandible' if lower else 'Dental_DICOM_Maxilla')
    if obj is not None and obj.type=='MESH' and len(obj.data.polygons):return obj
    from .. import core
    if core.clinical_route(scene)!=core.ROUTE_SIMPLE:return None
    side='lower' if lower else 'upper'
    obj=bpy.data.objects.get(str(scene.get(f'DSG_simple_{side}_object','') or ''))
    return obj if obj is not None and obj.type=='MESH' and len(obj.data.polygons) else None

def simple_bone(scene,lower):
    obj=bone_object(scene,lower)
    return obj is not None and obj.name not in ('Dental_DICOM_Maxilla','Dental_DICOM_Mandible')

def geometry_objects(context):
    from .. import guide_module as g,cbct_dental_module as dental,core
    from .protected_neighbors import canals
    from .upper_cavity_safety import objects as cavities
    from .microscrew_safety import screws
    scene=context.scene
    objects=list(g.get_all_implant_objects(scene.dsg_props))+dental.dentition_objects()+canals()+cavities(scene)+screws()
    objects += [bpy.data.objects.get(name) for name in ('Dental_DICOM_Maxilla','Dental_DICOM_Mandible')]
    objects += [bone_object(scene,False),bone_object(scene,True)]
    return sorted({o.name:o for o in objects if o is not None and scene.objects.get(o.name)==o
        and not o.get('DSG_checkpoint_source_name') and not o.get('DSG_workflow_checkpoint_source_name') and not o.get('DSG_obsolete_hidden')}.values(),key=lambda o:o.name)

def fingerprint(context):
    """Everything a proposal depends on.  The .blend path is not part of it, so
    saving the file under another name does not discard a valid proposal."""
    from .upper_cavity_safety import signature
    from .optimizer_snapshot_geometry import display_signature
    from .nerve_safety import margin
    from .. import core
    rows=[(o.name,signature(o),[(m.type,m.show_viewport) for m in o.modifiers],display_signature(o),o.get('DSG_fdi_number'),o.get('DSG_target_fdi'),o.get('DSG_upper_cavity_kind')) for o in geometry_objects(context)]
    data={'scene':context.scene.as_pointer(),'target':target(context).name if target(context) else None,
          'objects':rows,'matrices':[(o.name,[list(r) for r in o.matrix_world]) for o in geometry_objects(context)],
          'margins':[context.scene.dsg_props.implant_tooth_clearance,margin(context.scene)],
          'route':core.clinical_route(context.scene),'settings':settings(context.scene),'family':context.scene.dsg_opt_family,
          'library':context.scene.dsg_opt_library,'catalogue':catalogue_signature(context.scene),'review':context.scene.dsg_opt_reviewed,
          'extractions':sorted(core._immediate_extraction_fdis(context.scene))}
    return hashlib.sha256(json.dumps(data,sort_keys=True,default=str).encode()).hexdigest()

def catalogue_signature(scene):
    if scene.dsg_opt_library!='CUSTOM':
        from ..implant_catalogues import signature_paths
        return [hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in signature_paths()]
    path=Path(bpy.path.abspath(scene.dsg_opt_catalogue))
    if not str(scene.dsg_opt_catalogue).strip():return None
    if not path.is_file():return 'missing'
    try:
        rows=_catalogue(scene)
        return [(str(path.resolve()),hashlib.sha256(path.read_bytes()).hexdigest())]+[
            (r[key],hashlib.sha256(Path(r[key]).read_bytes()).hexdigest()) for r in rows for key in ('vertices_path','faces_path')]
    except (ValueError,KeyError,OSError,TypeError):return 'invalid'

def readiness(context,mode):
    from . import nerve_safety as nerve,upper_cavity_safety as upper
    from .protected_neighbors import canals
    implant=target(context);missing=[]
    if implant is None:return ['Selecciona un implante o su control de emergencia.']
    if context.scene.objects.get(implant.name)!=implant:return ['El implante seleccionado no pertenece al caso actual.']
    lower=nerve.required(context.scene,implant)
    allowed={o.name:o for o in geometry_objects(context)}
    bone=bone_object(context.scene,lower)
    if bone is None or bone.name not in allowed:missing.append('Falta el hueso del CBCT; segmenta la arcada (ruta simple) o el hueso nativo (ruta completa).')
    if lower and not any(o.name in allowed for o in canals()):missing.append('Falta segmentación del nervio dentario inferior.')
    if not lower and {o.get(upper.KIND) for o in upper.objects(context.scene)}!=set(upper.KINDS):missing.append('Faltan senos maxilares o cavidades nasales.')
    if not context.scene.dsg_opt_reviewed:missing.append('Revisa las estructuras y los límites del CBCT antes de buscar.')
    if mode=='SIZE':
        if 'DSG_catalogue_platform_local_mm' in implant and implant.get('DSG_optimizer_family')!=context.scene.dsg_opt_family:
            missing.append('El implante usa la malla de otro catálogo real; compara dentro de la misma familia.')
        if not str(context.scene.dsg_opt_family).strip():missing.append('Indica el sistema/familia de implantes.')
        if context.scene.dsg_opt_library=='CUSTOM' and not Path(bpy.path.abspath(context.scene.dsg_opt_catalogue)).is_file():missing.append('Falta un catálogo real de tamaños con sus mallas y referencias cervicales.')
    return missing

def _catalogue(scene):
    if scene.dsg_opt_library!='CUSTOM':
        from ..implant_catalogues import hierarchy_rows
        catalogue=hierarchy_rows(scene.dsg_opt_library)
        if not catalogue or catalogue[0]['family']!=scene.dsg_opt_family:raise ValueError('La familia no coincide con la biblioteca elegida.')
        return catalogue
    file=Path(bpy.path.abspath(scene.dsg_opt_catalogue)).resolve();data=json.loads(file.read_text('utf-8'))
    if data.get('schema_version')!=1 or data.get('units')!='mm' or data.get('family')!=scene.dsg_opt_family:
        raise ValueError('Catálogo incompatible: versión, unidades o familia incorrectas.')
    rows=[]
    for item in data['implants']:
        row=dict(item);row['family']=data['family']
        if row.get('axis_local',[0,0,1])!=[0,0,1]:raise ValueError('El catálogo debe usar eje +Z hacia coronal.')
        for key in ('vertices_path','faces_path'):
            path=Path(row[key]);path=path if path.is_absolute() else file.parent/path
            if path.suffix.lower()!='.npy' or not path.is_file():raise ValueError('Falta una malla NPY del catálogo.')
            row[key]=str(path.resolve())
        rows.append(row)
    return rows

def current_size(implant):
    """Identity of the implant being compared: catalogue id and nominal size."""
    out={'id':implant.get('DSG_catalogue_asset_id')}
    for key,name in (('diameter_mm','DSG_implant_diameter'),('length_mm','DSG_implant_length')):
        if implant.get(name) is not None:out[key]=float(implant[name])
    return out

def snapshot(context,folder,mode):
    from .. import core,guide_module as g,cbct_dental_module as dental,segmentation_engines
    from . import nerve_safety as nerve,upper_cavity_safety as upper
    from .protected_neighbors import canals
    from .microscrew_safety import screws
    from .safety_volume import _mesh_arrays
    implant=target(context);lower=nerve.required(context.scene,implant)
    def export(obj,kind=''):
        from .optimizer_snapshot_geometry import mesh_arrays
        v,f=mesh_arrays(obj,allow_measured=obj!=implant)
        ident=hashlib.sha256(obj.name.encode()).hexdigest()[:16]
        vp=folder/(ident+'_v.npy');fp=folder/(ident+'_f.npy')
        np.save(vp,v,allow_pickle=False);np.save(fp,f,allow_pickle=False)
        return {'name':obj.name,'vertices_path':str(vp),'faces_path':str(fp),'matrix':[list(r) for r in obj.matrix_world],'kind':kind,'fdi':int(obj.get('DSG_fdi_number',0))}
    bone=bone_object(context.scene,lower)
    from ..optimizer_profile import margins
    limits=margins(context.scene.dsg_props.implant_tooth_clearance,nerve.margin(context.scene),g.INTERIMPLANT_MIN_CLEARANCE_MM)
    obstacles=[]
    cut=set(core._immediate_extraction_fdis(context.scene)) if core.clinical_route(context.scene)==core.ROUTE_IMMEDIATE else set()
    all_objects={o.name:o for o in geometry_objects(context)}
    def add(obj,margin,kind,allow_hull=False):
        if obj.name not in all_objects:return
        row=export(obj,kind);row.update(margin_mm=float(margin),allow_hull=allow_hull);obstacles.append(row)
    for tooth in dental.dentition_objects():
        if int(tooth.get('DSG_fdi_number',0)) not in cut:add(tooth,limits['tooth'],'Raíz vecina')
    if simple_bone(context.scene,lower) and not dental.dentition_objects():
        # 9.24.6: no segmented teeth – neighbour roots estimated from the
        # crown removed from the IOS (mesial/distal contacts of the gap).
        from .simple_site_limits import obstacles as neighbour_limits
        obstacles+=neighbour_limits(context,implant,folder,limits['tooth'])
    for canal in canals():add(canal,limits['nerve'],'Nervio dentario inferior')
    if not lower:
        for zone in upper.objects(context.scene):
            kind=zone[upper.KIND];add(zone,limits['cavity'],upper.LABELS[kind])
            if 'sinus' in kind and obstacles and obstacles[-1]['name']==zone.name:
                obstacles[-1]['max_invasion_mm']=settings(context.scene)['sinus_invasion_mm']
    for other in g.get_all_implant_objects(context.scene.dsg_props):
        if other!=implant:add(other,limits['implant'],'Implante vecino',True)
    for screw in screws():add(screw,max(1.5,float(context.scene.dsg_props.implant_tooth_clearance)),'Microtornillo',True)
    catalogue=_catalogue(context.scene) if mode=='SIZE' else []
    for index,row in enumerate(catalogue):
        if row.get('dimension_only'):
            from ..implant_catalogues import nominal_body_mesh
            v,f=nominal_body_mesh(row['diameter_mm'],row['length_mm'])
            for key,array in (('vertices_path',v),('faces_path',f)):
                dest=folder/(str(index)+'_'+key+'.npy');np.save(dest,array,allow_pickle=False);row[key]=str(dest)
            continue
        for key in ('vertices_path','faces_path'):
            data=Path(row[key]).read_bytes();dest=folder/(str(index)+'_'+key+'.npy');dest.write_bytes(data);row[key]=str(dest)
    return {'schema_version':1,'run_id':uuid.uuid4().hex,'addon_dir':str(Path(__file__).resolve().parents[1]),'job_dir':str(folder),
            'mode':mode,'implant':export(implant),'source_nominal_length_mm':float(implant['DSG_implant_length']) if 'DSG_implant_length' in implant else None,'bone':export(bone),'obstacles':obstacles,'settings':settings(context.scene),
            'section_site_paths':segmentation_engines.active_site_paths(),
            # Immediate route: extracted roots are sockets, not missing bone.
            'sockets':[export(t,'Alvéolo') for t in dental.dentition_objects() if int(t.get('DSG_fdi_number',0)) in cut],
            'platform':list(g.get_implant_platform_center_world(context.scene.dsg_props,implant)),
            'family':context.scene.dsg_opt_family,'current_id':implant.get('DSG_catalogue_asset_id'),'target_fdi':int(implant.get('DSG_target_fdi') or core.target_fdi(context.scene) or 0),
            # Nominal libraries describe the same envelope as DSG's own implant, so the
            # current implant is recognised by size; a real-mesh catalogue only by id.
            'current':current_size(implant) if context.scene.dsg_opt_library!='CUSTOM' else None,
            'catalogue':catalogue}

def remove_preview():
    restore_visibility(PREVIEW_VISIBILITY);PREVIEW_VISIBILITY.clear()
    obj=bpy.data.objects.get(PREVIEW)
    if obj is not None:
        restore_followers(obj)
        mesh=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
        if mesh.users==0:bpy.data.meshes.remove(mesh)


def stop():
    process=STATE['process']
    if process is not None and process.poll() is None:
        process.terminate()
        try:process.wait(timeout=1.)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=1.)
    if STATE['log'] is not None:STATE['log'].close()
    STATE.update(process=None,log=None)

def clean_jobs():
    root=Path(tempfile.gettempdir()).resolve()
    for folder in list(JOBS):
        resolved=folder.resolve()
        if resolved.parent!=root or not resolved.name.startswith('DSG_OPTIMIZER_'):
            raise ValueError('Directorio temporal fuera del ámbito permitido.')
        try:
            shutil.rmtree(resolved)
            JOBS.remove(folder)
        except FileNotFoundError:JOBS.remove(folder)
        except OSError as exc:print('[DSG] No se pudo borrar el cálculo temporal:',exc)

def discard():
    stop();remove_preview();STATE.update(result=None,message='Propuesta descartada; original conservado.');clean_jobs()


def freeze_for_undo():
    """Release runtime references before native undo, without editing Blender IDs."""
    for callback in (poll, watch_preview, _recover_after_undo):
        if bpy.app.timers.is_registered(callback):bpy.app.timers.unregister(callback)
    stop()
    PREVIEW_VISIBILITY.clear()
    STATE.update(scene=None,preview_view_layer=None,result=None,request=None,fingerprint='',
                 message='Deshacer: propuesta pendiente descartada sin aplicar.')
    clean_jobs()


def _recover_after_undo():
    from .. import dicom_module
    if dicom_module.RUNTIME.undo_in_progress:return .2
    # Look up restored IDs afresh; never retain pre-undo RNA pointers.
    recover_saved_previews()
    return None


def resume_after_undo():
    if not bpy.app.timers.is_registered(_recover_after_undo):
        bpy.app.timers.register(_recover_after_undo,first_interval=.2)

@bpy.app.handlers.persistent
def on_load(_unused):
    if bpy.app.timers.is_registered(_recover_after_undo):bpy.app.timers.unregister(_recover_after_undo)
    discard();STATE.update(scene=None,message='')

def start(context,mode,purpose='SEARCH'):
    if context.mode!='OBJECT':raise ValueError('Termina la edición de la malla antes de buscar o aplicar.')
    errors=readiness(context,mode)
    if errors:raise ValueError(' '.join(errors))
    if STATE['process'] is not None:raise ValueError('Hay una evaluación en curso; cancélala antes de iniciar otra.')
    old=STATE['result']
    if purpose=='APPLY':
        if not context.scene.dsg_opt_profile_confirmed:raise ValueError('Revisa el perfil del modelo, los tejidos y los límites protésicos antes de aplicar.')
        if old is None or old.get('best') is None or old.get('status') not in APPLICABLE or fingerprint(context)!=STATE['fingerprint']:raise ValueError('La propuesta ha caducado; vuelve a buscar.')
    if purpose=='SEARCH':
        remove_preview();STATE['result']=None;clean_jobs();context.scene.dsg_opt_profile_confirmed=False
    initial_fingerprint=fingerprint(context)
    folder=Path(tempfile.mkdtemp(prefix='DSG_OPTIMIZER_'));JOBS.add(folder);request=snapshot(context,folder,mode)
    if purpose=='APPLY':request.update(mode='VALIDATE',candidate=old['best'])
    else:remove_preview()
    file=folder/'request.json';file.write_text(json.dumps(request,ensure_ascii=False),'utf-8')
    log=(folder/'worker.log').open('w',encoding='utf-8')
    from ..cbct_pipeline_client import _creationflags
    worker=Path(__file__).resolve().parents[1]/'implant_optimizer_worker.py'
    try:process=subprocess.Popen([bpy.app.binary_path,'--background','--factory-startup','--python-exit-code','1','--python',str(worker),'--',str(file)],stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,creationflags=_creationflags())
    except OSError:
        log.close();raise
    STATE.update(process=process,log=log,scene=context.scene,workflow_step=context.scene.dsg_props.current_step,target=target(context).name,run_id=request['run_id'],folder=folder,
                 fingerprint=initial_fingerprint,purpose=purpose,mode=mode,request=request,
                 result=old if purpose=='APPLY' else None,message='Revalidando antes de aplicar…' if purpose=='APPLY' else 'Buscando en segundo plano…')
    if not bpy.app.timers.is_registered(poll):bpy.app.timers.register(poll,first_interval=.5)

APPLICABLE={'PROPOSAL','COMPARISON','NOMINAL_PROPOSAL'}

def _preview(context,result):
    from .. import guide_module as g
    from . import implant_plane
    remove_preview();valid=bool(result.get('best') and result['status'] in APPLICABLE)
    if result['status'] not in APPLICABLE|{'NO_FEASIBLE','GRAFT_SCENARIO','BONE_REVIEW','SECTION_REVIEW'}:return
    row=result.get('best') if valid else (result.get('conditional') or result.get('closest'))
    if row is None:return
    implant=bpy.data.objects[STATE['target']]
    if row.get('asset'):
        asset=row['asset']
        if asset.get('dimension_only'):
            from ..implant_catalogues import inside_envelope
            from .safety_volume import _mesh_arrays
            mesh=g.make_embedded_implant_mesh(PREVIEW,asset['diameter_mm'],asset['length_mm'])
            vertices,_,_=_mesh_arrays(mesh)
            if not inside_envelope(vertices,asset['diameter_mm'],asset['length_mm']):
                bpy.data.meshes.remove(mesh);raise ValueError('La referencia DSG no cabe en la envolvente propuesta.')
        else:
            vertices=np.load(asset['vertices_path'],allow_pickle=False);faces=np.load(asset['faces_path'],allow_pickle=False)
            mesh=bpy.data.meshes.new(PREVIEW);mesh.from_pydata(vertices.tolist(),[],faces.tolist());mesh.update()
    else:mesh=implant.data.copy()
    obj=bpy.data.objects.new(PREVIEW,mesh);context.scene.collection.objects.link(obj);obj.matrix_world=Matrix(row['matrix'])
    material=bpy.data.materials.get(PREVIEW) or bpy.data.materials.new(PREVIEW)
    color=(.1,.8,.9,1.) if valid else ((.95,.55,.1,1.) if result.get('conditional') or result['status'] in {'BONE_REVIEW','SECTION_REVIEW'} else (1.,.2,.08,1.))
    material.diffuse_color=color
    # Material Preview renders shader inputs, not only viewport diffuse_color.
    material.use_nodes=True
    for node in material.node_tree.nodes:
        if node.type=='BSDF_PRINCIPLED':
            node.inputs['Base Color'].default_value=color
            node.inputs['Roughness'].default_value=.45
    mesh.materials.clear();mesh.materials.append(material)
    obj.display_type='SOLID';obj.show_in_front=True;obj.hide_select=True;obj.hide_render=True;obj.color=color
    obj['DSG_optimizer_advisory_only']=not valid
    for original in (implant,implant.parent if implant.parent is not None and implant.parent.get('DSG_implant_emergence_controller') else None,bpy.data.objects.get(g._implant_safety_halo_name(implant))):
        if original is not None:
            PREVIEW_VISIBILITY[original.name]={'hidden':original.hide_get(),'disabled':original.hide_viewport,'scene':context.scene.name,'view_layer':context.view_layer.name}
            original.hide_set(True)
    obj['DSG_optimizer_preview']=True
    obj['DSG_measure_context_id']=uuid.uuid4().hex
    obj['DSG_optimizer_original']=implant.name
    plane=implant_plane.plane_for(implant)
    if plane is not None:
        constraint=plane.constraints.get('DSG_FollowImplant')
        if constraint is not None:constraint.target=obj
    obj['DSG_optimizer_visibility_backup']=json.dumps(PREVIEW_VISIBILITY)
    STATE['preview_view_layer']=context.view_layer
    STATE['preview_step']=context.scene.dsg_props.current_step
    if not bpy.app.timers.is_registered(watch_preview):bpy.app.timers.register(watch_preview,first_interval=.5)
    obj['DSG_preview_only']=True


def _matches(a,b,tolerance=1e-4):
    return max(abs(a[r][c]-b[r][c]) for r in range(4) for c in range(4))<=tolerance

def _commit_nominal(context,row):
    """Apply a nominal catalogue size with DSG's own implant mesh.

    The DSG mesh of that size is rebuilt in place (platform and axis fixed) and
    must lie inside the nominal envelope that was just revalidated; otherwise
    the previous size and pose are restored.
    """
    from . import implant_resize
    from ..implant_catalogues import inside_envelope
    from .safety_volume import _mesh_arrays
    implant=bpy.data.objects[STATE['target']];asset=row['asset'];world=Matrix(row['matrix'])
    props=context.scene.dsg_props
    if row.get('parameters') is not None:
        from ..implant_search_frames import validate_candidate_reference
        validate_candidate_reference(STATE['request'],row)
    old_matrix=implant.matrix_world.copy();old_size=(float(implant.get('DSG_implant_diameter',props.implant_diameter)),float(implant.get('DSG_implant_length',props.implant_length)))
    old_parent=implant.parent.matrix_world.copy() if implant.parent else None
    saved={key:list(implant[key]) if key=='DSG_catalogue_platform_local_mm' and key in implant else implant.get(key) for key in ('DSG_catalogue_asset_id','DSG_optimizer_family','DSG_catalogue_platform_local_mm','DSG_implant_diameter','DSG_implant_length')}
    old_mesh=implant.data;old_fake=old_mesh.use_fake_user;old_mesh.use_fake_user=True
    d,l=float(asset['diameter_mm']),float(asset['length_mm'])
    try:
        implant_resize.resize(context,implant,d,l)
        context.view_layer.update()
        if row.get('parameters') is not None:
            if implant.parent is not None and implant.parent.get('DSG_implant_emergence_controller'):
                implant.parent.matrix_world=(world@implant.matrix_world.inverted_safe())@implant.parent.matrix_world
            else:implant.matrix_world=world
            context.view_layer.update()
        if not _matches(implant.matrix_world,world):raise RuntimeError('La posición final no coincide con la validada.')
        vertices,_,_=_mesh_arrays(implant.data)
        if not inside_envelope(vertices,d,l):raise RuntimeError('El implante DSG de esa medida no cabe en la envolvente validada.')
        implant['DSG_catalogue_asset_id']=asset['id'];implant['DSG_optimizer_family']=asset['family']
    except (ValueError,RuntimeError,ReferenceError,KeyError,TypeError):
        failed_mesh=implant.data;implant.data=old_mesh
        if implant.parent is not None and old_parent is not None:implant.parent.matrix_world=old_parent
        implant.matrix_world=old_matrix
        for key,value in saved.items():
            if value is not None:implant[key]=value
            elif key in implant:del implant[key]
        if failed_mesh!=old_mesh and failed_mesh.users==0:bpy.data.meshes.remove(failed_mesh)
        from . import safety_volume
        safety_volume.visible(context,props,implant);context.view_layer.update()
        raise
    finally:
        old_mesh.use_fake_user=old_fake
        if old_mesh.users==0:bpy.data.meshes.remove(old_mesh)

def _commit(context,row):
    remove_preview()
    from .. import guide_module as g
    from . import safety_volume as safety,nerve_safety as nerve
    implant=bpy.data.objects[STATE['target']];world=Matrix(row['matrix'])
    if row.get('asset',{}).get('dimension_only'):_commit_nominal(context,row)
    else:
        old_matrix=implant.matrix_world.copy();old_parent=implant.parent.matrix_world.copy() if implant.parent else None
        old_mesh=implant.data;new_mesh=None
        keys=('DSG_catalogue_asset_id','DSG_optimizer_family','DSG_implant_diameter','DSG_implant_length','DSG_catalogue_platform_local_mm')
        saved={key:list(implant[key]) if key=='DSG_catalogue_platform_local_mm' and key in implant else implant.get(key) for key in keys}
        try:
            if row.get('asset'):
                asset=row['asset'];v=np.load(asset['vertices_path'],allow_pickle=False);f=np.load(asset['faces_path'],allow_pickle=False)
                new_mesh=bpy.data.meshes.new(implant.data.name+'_Catalog');new_mesh.from_pydata(v.tolist(),[],f.tolist());new_mesh.update()
                for material in old_mesh.materials:new_mesh.materials.append(material)
                implant.data=new_mesh
            if implant.parent is not None and implant.parent.get('DSG_implant_emergence_controller'):
                implant.parent.matrix_world=(world@old_matrix.inverted_safe())@implant.parent.matrix_world
            else:implant.matrix_world=world
            context.view_layer.update()
            if not _matches(implant.matrix_world,world):raise RuntimeError('La posición final no coincide con la validada.')
            if row.get('asset'):
                implant['DSG_catalogue_asset_id']=row['asset']['id'];implant['DSG_optimizer_family']=row['asset']['family']
                implant['DSG_implant_diameter']=row['asset']['diameter_mm'];implant['DSG_implant_length']=row['asset']['length_mm']
                implant['DSG_catalogue_platform_local_mm']=row['asset']['platform_local_mm']
        except Exception:
            implant.data=old_mesh
            for key,value in saved.items():
                if value is None:
                    if key in implant:del implant[key]
                else:implant[key]=value
            if implant.parent is not None and old_parent is not None:implant.parent.matrix_world=old_parent
            implant.matrix_world=old_matrix
            if new_mesh is not None and new_mesh.users==0:bpy.data.meshes.remove(new_mesh)
            raise
    from . import implant_resize
    implant_resize._BUSY['active']=True
    try:
        context.scene.dsg_props.implant_diameter=float(implant.get('DSG_implant_diameter',context.scene.dsg_props.implant_diameter))
        context.scene.dsg_props.implant_length=float(implant.get('DSG_implant_length',context.scene.dsg_props.implant_length))
    finally:implant_resize._BUSY['active']=False
    safety._GEOMETRY.clear();nerve.clear();safety.STATE['checked'].clear()
    safety.visible(context,context.scene.dsg_props,implant)
    remove_preview()

MESSAGES={'NO_CREST_REFERENCE':'Cresta no verificable dentro del ajuste axial de ±1,5 mm.', 'REFERENCE_UNVERIFIABLE':'No se pudo verificar la referencia anatómica.', 'SEARCH_INCOMPLETE':'Búsqueda incompleta: quedan medidas prioritarias sin verificar.', 'SECTION_REVIEW':'Alternativa no admisible; solo para revisión.', 'BONE_REVIEW':'Requiere revisión ósea en CBCT.', 'NO_FEASIBLE':'No se encontró una alternativa admisible.','NO_IMPROVEMENT':'Ninguna alternativa mejora de forma apreciable; se conserva el actual.',
          'NO_CATALOG':'Falta un catálogo de implantes.','NOMINAL_PROPOSAL':'Propuesta lista para revisar.',
          'GRAFT_SCENARIO':'Escenario de injerto: comparación hipotética, no propuesta admisible.'}

def poll():
    process=STATE['process']
    if process is None:return None
    context=bpy.context
    if STATE.get('workflow_step',context.scene.dsg_props.current_step)!=context.scene.dsg_props.current_step:
        discard();STATE['message']='Fase cambiada; propuesta descartada sin aplicar.';return None
    if context.scene!=STATE['scene'] or target(context) is None or target(context).name!=STATE['target']:
        discard();STATE['message']='Caso o selección cambiados; cálculo descartado.';return None
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':area.tag_redraw()
    if process.poll() is None:
        progress_path=STATE['folder']/'progress.json'
        if progress_path.is_file():
            try:
                progress=json.loads(progress_path.read_text('utf-8'));STATE['message']=f"{progress['percent']:.0f} % · {progress['text']}"
            except (ValueError,OSError,KeyError):pass
        return .5
    if context.mode!='OBJECT':
        discard();STATE['message']='Edición de malla activa; resultado descartado.';return None
    if any(window.modal_operators for window in context.window_manager.windows):return .5
    try:
        data=json.loads((STATE['folder']/'result.json').read_text('utf-8'))
        if data.get('run_id')!=STATE['run_id'] or not data.get('ok'):raise ValueError(data.get('error','Resultado incompatible.'))
        if fingerprint(context)!=STATE['fingerprint']:raise ValueError('Anatomía, implante o parámetros cambiados; resultado descartado.')
        result=data['result']
        result['elapsed_s']=float(data.get('elapsed_s',0.))
        if STATE['purpose']!='APPLY':
            from ..bone_interpretation import interpret_search_result
            interpret_search_result(result,immediate=bool(STATE['request'].get('sockets')),minimum_coverage=STATE['request']['settings'].get('min_coverage',.8))
        if STATE['purpose']=='APPLY':
            if not context.scene.dsg_opt_profile_confirmed:raise ValueError('Confirma la revisión clínica antes de aplicar.')
            if result.get('status')!='VALIDATED':raise ValueError('La propuesta ya no cumple los límites actuales.')
            remove_preview()
            if not bpy.app.background:bpy.ops.ed.undo_push(message='Antes de aplicar propuesta DSG')
            _commit(context,STATE['result']['best'])
            if not bpy.app.background:bpy.ops.ed.undo_push(message='Aplicar propuesta DSG')
            STATE.update(result=None,message='Propuesta aplicada tras revalidación. Revisa el MPR y la seguridad.')
        else:
            STATE['result']=result;_preview(context,result)
            STATE['message']=MESSAGES.get(result['status'],'Propuesta geométrica lista para revisar.')
    except (ValueError,RuntimeError,OSError,KeyError) as exc:
        remove_preview();STATE.update(result=None,message=str(exc))
    finally:
        stop()
        if STATE['result'] is None:clean_jobs()
    return None

class DSG_OT_OptimizePosition(bpy.types.Operator):
    bl_idname='dsg.optimize_implant_position';bl_label='BUSCAR POSICIÓN'
    def execute(self,context):
        try:start(context,'POSITION')
        except (ValueError,RuntimeError,OSError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}
class DSG_OT_OptimizeSize(bpy.types.Operator):
    bl_idname='dsg.optimize_implant_size';bl_label='COMPARAR TAMAÑOS'
    def execute(self,context):
        try:start(context,'SIZE')
        except (ValueError,RuntimeError,OSError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}
class DSG_OT_ApplyOptimization(bpy.types.Operator):
    # No UNDO flag: execute() only starts the revalidation; the two undo steps
    # are pushed around the actual change when the worker finishes.
    bl_idname='dsg.apply_implant_optimization';bl_label='ACEPTAR CAMBIOS'
    bl_options={'REGISTER'}
    def execute(self,context):
        try:start(context,STATE['mode'],purpose='APPLY')
        except (ValueError,RuntimeError,OSError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}
class DSG_OT_DiscardOptimization(bpy.types.Operator):
    bl_idname='dsg.discard_implant_optimization';bl_label='DESCARTAR CAMBIOS / CANCELAR'
    def execute(self,context):discard();return {'FINISHED'}


def select_platform(context,group):
    """Show (and make applicable) the best proposal of one platform."""
    result=STATE['result']
    entry=(result or {}).get('by_platform',{}).get(group) if result else None
    if STATE['process'] is not None:raise ValueError('Hay un cálculo en curso.')
    if not entry or entry.get('best') is None:raise ValueError('Esta plataforma no tiene una propuesta admisible.')
    row=entry['best'];asset=row['asset']
    current=(STATE.get('request') or {}).get('current') or {}
    same=(abs(float(current.get('diameter_mm',-1))-float(asset['diameter_mm']))<.01
          and abs(float(current.get('length_mm',-1))-float(asset['length_mm']))<.01 and float(row.get('movement_mm',0.))<.01)
    result['best']=row;result['selected_platform']=group
    result['status']='NO_IMPROVEMENT' if same else ('NOMINAL_PROPOSAL' if asset.get('dimension_only') else 'COMPARISON')
    context.scene.dsg_opt_profile_confirmed=False
    _preview(context,result)
    STATE['message']=MESSAGES.get(result['status'],'Propuesta geométrica lista para revisar.')


class DSG_OT_ChoosePlatformProposal(bpy.types.Operator):
    bl_idname='dsg.choose_platform_proposal';bl_label='Elegir propuesta de plataforma'
    bl_description='Muestra la propuesta más larga y ancha admisible de esta plataforma para revisarla o aplicarla'
    platform:bpy.props.EnumProperty(items=[('NARROW','Narrow',''),('STANDARD','Standard',''),('WIDE','Wide','')])
    def execute(self,context):
        try:select_platform(context,self.platform)
        except (ValueError,RuntimeError,KeyError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}

CLASSES=(DSG_OT_OptimizePosition,DSG_OT_OptimizeSize,DSG_OT_ApplyOptimization,DSG_OT_DiscardOptimization,DSG_OT_ChoosePlatformProposal)
def library_changed(scene,context):
    from ..implant_catalogues import rows
    if scene.dsg_opt_library!='CUSTOM':scene.dsg_opt_family=rows(scene.dsg_opt_library)[0]['family']

PROPERTIES=('dsg_opt_details','dsg_opt_library','dsg_opt_open','dsg_opt_shift_mm','dsg_opt_tilt_deg','dsg_opt_depth_mm','dsg_opt_reserve_mm','dsg_opt_cervical_mm','dsg_opt_coverage','dsg_opt_sinus_manual','dsg_opt_apical_mm',
            'dsg_opt_size_policy','dsg_opt_combine','dsg_opt_graft_gap_mm','dsg_opt_max_diameter_mm','dsg_opt_max_length_mm','dsg_opt_family','dsg_opt_catalogue','dsg_opt_reviewed','dsg_opt_profile_confirmed')
def register():
    if REGISTERED['active']:return
    from ..implant_catalogues import LIBRARIES
    fields={
        'dsg_opt_library':bpy.props.EnumProperty(name='Biblioteca',items=LIBRARIES,default='BTI_COREX',update=library_changed),
        'dsg_opt_open':bpy.props.BoolProperty(default=False),
        'dsg_opt_details':bpy.props.BoolProperty(name='Detalles y márgenes',default=False),
        'dsg_opt_shift_mm':bpy.props.FloatProperty(name='Desplazamiento lateral máximo · mm',default=1.,min=0.,max=3.,
            description='Movimiento perpendicular al eje del implante'),
        'dsg_opt_tilt_deg':bpy.props.FloatProperty(name='Cambio angular máximo · °',default=5.,min=0.,max=15.),
        'dsg_opt_depth_mm':bpy.props.FloatProperty(name='Cambio de profundidad máximo · mm',default=0.,min=0.,max=2.,
            description='Movimiento a lo largo del eje. 0 = profundidad fija; hundir el implante casi siempre aumenta la cobertura y no debe decidirlo el optimizador por defecto'),
        'dsg_opt_reserve_mm':bpy.props.FloatProperty(name='Reserva de pared local · mm',default=.5,min=0.,max=2.),
        'dsg_opt_cervical_mm':bpy.props.FloatProperty(name='Zona cervical libre · mm',default=1.,min=0.,max=4.,
            description='Franja coronal del implante excluida de la reserva de pared (cresta irregular o colocación subcrestal)'),
        'dsg_opt_apical_mm':bpy.props.FloatProperty(name='Anclaje apical en hueso nativo · mm',default=3.,min=1.,max=8.,
            description='Implante inmediato: longitud mínima del implante más allá del ápice del alvéolo'),
        'dsg_opt_sinus_manual':bpy.props.BoolProperty(name='Seno: invasión permitida como en planificación manual',default=True,
            description='El seno maxilar admite la misma invasión que la planificación manual (alerta). La cavidad nasal mantiene 2 mm de margen'),
        'dsg_opt_coverage':bpy.props.FloatProperty(name='Cobertura muestreada mínima · %',default=80.,min=0.,max=100.),
        'dsg_opt_size_policy':bpy.props.EnumProperty(name='Criterio de tamaño',default='LARGEST',items=(
            ('LARGEST','Mayor medida admisible','Mayor longitud y después mayor diámetro que cumplan todas las restricciones'),
            ('SUPPORT','Mayor soporte con reserva','Mayor área muestreada que supera la reserva de pared'))),
        'dsg_opt_combine':bpy.props.BoolProperty(name='Combinar tamaño y posición',default=True),
        'dsg_opt_graft_gap_mm':bpy.props.FloatProperty(name='Simular hueco a injertar · mm',default=0.,min=0.,max=5.,
            description='0 desactivado. Solo huecos próximos al alvéolo; simulación, no hueso nativo ni propuesta aplicable'),
        'dsg_opt_max_diameter_mm':bpy.props.FloatProperty(name='Diámetro máximo · mm',default=0.,min=0.,max=8.,description='0 = sin límite. Tope clínico para la posición'),
        'dsg_opt_max_length_mm':bpy.props.FloatProperty(name='Longitud máxima · mm',default=0.,min=0.,max=20.,description='0 = sin límite'),
        'dsg_opt_family':bpy.props.StringProperty(name='Sistema / familia',default='BTI CORE-X'),
        'dsg_opt_catalogue':bpy.props.StringProperty(name='Catálogo de tamaños',subtype='FILE_PATH'),
        'dsg_opt_reviewed':bpy.props.BoolProperty(name='He revisado las estructuras y el campo del CBCT',default=False),
        'dsg_opt_profile_confirmed':bpy.props.BoolProperty(name='Perfil, tejidos y límites protésicos revisados',default=False)}
    for key,value in fields.items():setattr(bpy.types.Scene,key,value)
    for cls in CLASSES:bpy.utils.register_class(cls)
    if on_load not in bpy.app.handlers.load_pre:bpy.app.handlers.load_pre.append(on_load)
    if recover_saved_previews not in bpy.app.handlers.load_post:bpy.app.handlers.load_post.append(recover_saved_previews)
    recover_saved_previews()
    REGISTERED['active']=True
def unregister():
    discard()
    if bpy.app.timers.is_registered(_recover_after_undo):bpy.app.timers.unregister(_recover_after_undo)
    if bpy.app.timers.is_registered(poll):bpy.app.timers.unregister(poll)
    if on_load in bpy.app.handlers.load_pre:bpy.app.handlers.load_pre.remove(on_load)
    if recover_saved_previews in bpy.app.handlers.load_post:bpy.app.handlers.load_post.remove(recover_saved_previews)
    if bpy.app.timers.is_registered(watch_preview):bpy.app.timers.unregister(watch_preview)
    if REGISTERED['active']:
        for cls in reversed(CLASSES):bpy.utils.unregister_class(cls)
        for name in PROPERTIES:
            if name in bpy.types.Scene.bl_rna.properties:delattr(bpy.types.Scene,name)
    REGISTERED['active']=False
def draw(layout,context):
    from .. import guide_module as g
    scene=context.scene
    if 'dsg_opt_open' not in scene.bl_rna.properties:return
    box=g._raw(layout.box());box.prop(scene,'dsg_opt_open',text='Propuesta de implante',icon='TRIA_DOWN' if scene.dsg_opt_open else 'TRIA_RIGHT',emboss=False)
    if not scene.dsg_opt_open:return
    box.prop(scene,'dsg_opt_library')
    box.label(text='Longitud → diámetro · altura: cresta estimada')
    if scene.dsg_opt_library=='CUSTOM':
        box.prop(scene,'dsg_opt_family');box.prop(scene,'dsg_opt_catalogue')
    implant=target(context)
    if implant is not None:
        from .nerve_safety import required
        if simple_bone(scene,required(scene,implant)):
            col=box.column(align=True)
            col.label(text='Ruta simple: hueso y dientes sin separar',icon='ERROR')
            from .ios_tooth_edit import model as ios_model
            ios=ios_model(context)
            if ios is not None and int(ios.get('DSG_ios_socket_count',0) or 0) and ios.get('DSG_ios_tooth_edit_backup') is not None:
                col.label(text='Raíces vecinas estimadas desde el diente eliminado')
            else:
                col.label(text='Sin diente eliminado del IOS: sin límite de raíces')
            col.label(text='Revisa las raíces vecinas en los cortes MPR')
    box.prop(scene,'dsg_opt_reviewed',text='CBCT y estructuras revisados')
    row=box.row();row.enabled=STATE['process'] is None
    row.operator('dsg.optimize_implant_size',text='BUSCAR PROPUESTA',icon='VIEWZOOM')
    g._raw(box).prop(scene,'dsg_opt_details',text='Detalles y márgenes',icon='TRIA_DOWN' if scene.dsg_opt_details else 'TRIA_RIGHT',emboss=False)
    if scene.dsg_opt_details:
        from ..optimizer_profile import margins
        from .nerve_safety import margin
        limits=margins(scene.dsg_props.implant_tooth_clearance,margin(scene),g.INTERIMPLANT_MIN_CLEARANCE_MM)
        box.label(text=f"Dientes ≥ {limits['tooth']:g} · implantes ≥ {limits['implant']:g} mm")
        box.label(text=f"Conducto dentario ≥ {limits['nerve']:g} mm")
        box.label(text='Seno: longitud <10 mm → hasta 2 mm con alerta')
        box.label(text='Seno: longitud ≥10 mm → 0 mm, sin penetración')
        box.label(text='Cavidad nasal: 0 mm · sin penetración')
        box.label(text='Cortes locales · contorno, hueso y alvéolo separados')
        box.label(text='Inmediato: anclaje geométrico mínimo 3 mm')
        box.label(text='Tamaño y posición · trayectos del implante y del diente extraído')
        box.label(text=f"Trayecto anatómico: hasta {settings(scene)['anatomical_frame_max_angle_deg']:g}° · revisión antes de aplicar")
        box.label(text='Mayor longitud admisible; después, mayor diámetro')
        box.label(text='Altura: cresta ósea estimada · ajuste axial ±1,5 mm')
        box.label(text='Medidas nominales · no predice estabilidad primaria')
    if STATE['message']:
        message=STATE['message']
        if STATE['process'] is not None:
            progress=message.split(' · ',1)[0] if '%' in message else ''
            box.label(text='Calculando propuesta'+(' · '+progress if progress else '…'),icon='TIME')
            if scene.dsg_opt_details:box.label(text=message)
        else:box.label(text='Sin propuesta admisible' if STATE['result'] and STATE['result'].get('status')=='NO_FEASIBLE' else message,icon='INFO')
    result=STATE['result']
    if result and result.get('section_fallback_reason'):
        box.label(text='Búsqueda 3D de respaldo',icon='INFO')
        if scene.dsg_opt_details:box.label(text=result['section_fallback_reason'])
    if result and result.get('section_search'):
        box.label(text=f"Mapa de cortes · {result.get('verified_3d',0)} comprobaciones 3D")
        if result.get('verification_budget_exhausted'):box.label(text='Búsqueda limitada; quedan candidatos sin verificar.',icon='INFO')
    if result and STATE.get('request') and result.get('best'):
        catalogue=STATE['request'].get('catalogue',[])
        listed=[float(a['length_mm']) for a in catalogue if a.get('availability','LISTED')=='LISTED']
        if listed and float(result['best']['asset']['length_mm'])>=max(listed)-.01:
            box.label(text=f'Longitud máxima del catálogo: {max(listed):g} mm',icon='INFO')
    if result and result.get('evaluated') is not None:
        duration=f" · {result['elapsed_s']:.0f} s" if result.get('elapsed_s') is not None else ''
        box.label(text=f"{result['evaluated']} alternativas comprobadas{duration}")
    if scene.dsg_opt_details and result and result.get('original_support') and not result.get('section_search'):
        measured=result['original_support']
        box.label(text=f"Original: hueso {100*measured['support_fraction']:.1f} % · con reserva {100*measured['reserve_fraction']:.1f} %")
        draw_surround(box,measured.get('surround',{}),'Original')
    if result and result.get('status') in {'NO_FEASIBLE','GRAFT_SCENARIO'}:
        if scene.dsg_opt_details:
            for reason in result.get('reasons',[])[:5]:box.label(text=reason,icon='DOT')
    if result and result.get('by_platform'):draw_platforms(box,result)
    shown=(result.get('best') or result.get('conditional') or result.get('closest')) if result else None
    if shown:
        best=shown;asset=best.get('asset',{})
        if not result.get('best') and result['status']=='SECTION_REVIEW':
            box.label(text='Alternativa NO admisible · ámbar',icon='INFO')
            box.label(text='Contorno o soporte pendientes de revisión.')
            box.label(text='No se puede aplicar como propuesta.')
        elif not result.get('best') and result['status']=='BONE_REVIEW':
            box.label(text='Referencia para revisión ósea · ámbar',icon='INFO')
            box.label(text='Viabilidad clínica no determinada.')
            box.label(text='El criterio de reserva no se cumple.')
            box.label(text='Revisa pared y alvéolo en el CBCT.')
        elif not result.get('best'):
            box.label(text='ESCENARIO DE INJERTO · ámbar' if result.get('conditional') else 'Referencia rechazada · rojo',icon='ERROR')
            box.label(text='Solo comparación; no se puede aplicar.')
        if asset:
            box.label(text=f"Medida: Ø {asset['diameter_mm']:g} × {asset['length_mm']:g} mm"+(f" · ref. {asset['source_cell']}" if asset.get('dimension_only') and asset.get('source_cell') else ''))
            if scene.dsg_opt_details and result.get('baseline_match')=='DIMENSIONS':box.label(text='Implante actual reconocido por su diámetro y longitud.')
            elif result.get('status')=='COMPARISON':box.label(text='Implante actual fuera del catálogo: comparación, no mejora.')
        if scene.dsg_opt_details and best.get('parameters') is not None:
            p=best['parameters'];angle=float(best.get('axis_angle_deg',0.))+np.hypot(p[3],p[4]);box.label(text=f"Lateral {np.hypot(p[0],p[1]):.2f} mm · profundidad {p[2]:+.2f} mm · ángulo {angle:.1f}°")
        metrics=best['evaluation']
        mpr=metrics.get('mpr_checks',{})
        if mpr.get('status')=='MEASURED':
            box.label(text=f"Pared MPR mínima muestreada: {mpr['minimum_wall_mm']:.2f} mm")
            if scene.dsg_opt_details:box.label(text=f"{mpr['axial_levels']} niveles · {mpr['angular_directions']} direcciones alrededor del eje")
        if best.get('axis_reference','').startswith('EXTRACTED_TOOTH:'):
            box.label(text='Trayecto del diente extraído · revisar en MPR')
        if metrics.get('crest_reference'):
            box.label(text='Plataforma referida a la cresta, no al seno')
        if result.get('reference_error') and scene.dsg_opt_details:
            box.label(text=result['reference_error'],icon='ERROR')
        if metrics.get('metric')=='SECTION_ENVELOPE_AND_NATIVE_SUPPORT_NOT_STABILITY':
            box.label(text='Encaje geométrico · revisar paredes en MPR')
            box.label(text=f"Tramo con hueso en ≥50 % de sección: {metrics.get('section_anchor_mm',0):.2f} mm")
            if scene.dsg_opt_details:
                box.label(text=f"Anillo en hueso segmentado: {100*metrics.get('section_contact_fraction',0):.1f} %")
                box.label(text=f"Hueso segmentado ocupado: {metrics.get('native_bone_volume_mm3',0):.1f} mm³")
                box.label(text=f"Espacio de alvéolo: {metrics.get('socket_space_volume_mm3',0):.1f} mm³")
                sinus_volume=metrics.get('sinus_space_volume_mm3',0)
                if sinus_volume<.05 and metrics.get('alerts'):
                    box.label(text='Volumen en seno: por debajo del muestreo de cortes')
                else:box.label(text=f"Volumen estimado en seno: {sinus_volume:.1f} mm³")
                box.label(text=f"Área útil mínima: {metrics.get('minimum_usable_section_mm2',0):.1f} mm²")
        if not result.get('best') and not metrics.get('violations'):box.label(text=metrics.get('reason','Comprobación no verificable'),icon='ERROR')
        if scene.dsg_opt_details and metrics.get('metric')!='SECTION_ENVELOPE_AND_NATIVE_SUPPORT_NOT_STABILITY':
            box.label(text=f"Cobertura muestreada: {100*metrics.get('support_fraction',0):.1f} %")
            box.label(text=f"Con reserva local: {100*metrics.get('reserve_fraction',0):.1f} %")
        if scene.dsg_opt_details and metrics.get('apical_engagement_mm') is not None:box.label(text=f"Anclaje apical estimado: {metrics['apical_engagement_mm']:.3f} mm")
        for violation in metrics.get('violations',[]):
            label='Muestras fuera del hueso segmentado' if result['status']=='BONE_REVIEW' and violation['code']=='WALL' and 'actual' in violation else violation['label']
            box.label(text=label,icon='INFO' if result['status']=='BONE_REVIEW' else 'ERROR')
            if 'actual' in violation and 'limit' in violation:
                if violation['code']=='COVERAGE':box.label(text=f"Medido {100*violation['actual']:.1f} % · mínimo {100*violation['limit']:.1f} %")
                elif result['status']=='BONE_REVIEW' and violation['code']=='WALL':box.label(text=f"Separación muestreada: {violation['actual']:.2f} mm")
                else:box.label(text=f"Medido {violation['actual']:.3f} · límite {violation['limit']:.3f} mm")
        if metrics.get('graft_gap_limit_mm',0)>0:
            box.label(text=f"Hueco máximo medido {metrics.get('wall_gap_max_mm',0):.2f} mm · elegido {metrics['graft_gap_limit_mm']:.2f} mm")
            box.label(text=f"Muestras de injerto hipotético: {metrics.get('planned_graft_samples',0)} · no son hueso")
        for alert in metrics.get('alerts',[]):
            box.label(text=f"{alert['label']}: penetración {alert['depth_mm']:.2f} mm",icon='ERROR')
            box.label(text=f"Límite de planificación: {alert['limit_mm']:g} mm")
        if scene.dsg_opt_details and metrics.get('metric')!='SECTION_ENVELOPE_AND_NATIVE_SUPPORT_NOT_STABILITY':draw_surround(box,metrics.get('surround',{}),'Propuesta')
        if result['status'] in APPLICABLE:
            box.label(text='Propuesta cian · el MPR sigue el cambio')
            box.label(text='Alertas generales: original hasta aceptar.')
            box.prop(scene,'dsg_opt_profile_confirmed')
            row=box.row();row.enabled=STATE['process'] is None and scene.dsg_opt_profile_confirmed
            row.operator('dsg.apply_implant_optimization')
    if STATE['process'] is not None or result:box.operator('dsg.discard_implant_optimization')

def draw_platforms(box,result):
    """Best admissible size per platform; the chosen one is previewed."""
    from ..implant_platforms import ORDER,SHORT,platform_class
    best=result.get('best')
    selected=result.get('selected_platform') or (platform_class(best['asset']) if best and best.get('asset') else None)
    column=box.column(align=True)
    column.label(text='Mejor propuesta por plataforma',icon='MOD_LENGTH')
    for group in ORDER:
        entry=result['by_platform'].get(group) or {}
        row=column.row(align=True)
        winner=entry.get('best')
        if winner is not None:
            asset=winner['asset'];chosen=group==selected
            text=f"{SHORT[group]} · Ø {float(asset['diameter_mm']):g} × {float(asset['length_mm']):g} mm"
            if asset.get('platform'):text+=f" ({asset['platform']})"
            if asset.get('library_family'):text+=f" · {asset['library_family']}"
            op=row.operator('dsg.choose_platform_proposal',text=text,icon='CHECKMARK' if chosen else 'BLANK1',depress=chosen)
            op.platform=group
            if entry.get('contained_in'):
                note=column.row(align=True);note.scale_y=.8;note.active=False
                note.label(text=f"   en la posición de la propuesta {entry['contained_in']} (cabe dentro)",icon='BLANK1')
        else:
            reason=entry.get('reason') or 'No cabe'
            if entry.get('exhausted'):reason='búsqueda incompleta'
            row.label(text=f"{SHORT[group]} · no posible: {reason}"[:90],icon='X')


def draw_surround(box,measurement,label):
    if measurement.get('status')=='UNVERIFIABLE':
        box.label(text=label+': medición de pared no verificable.',icon='ERROR');return
    if measurement.get('status')!='MEASURED':return
    wall=measurement.get('minimum_direct_wall_mm');gap=measurement.get('maximum_gap_mm')
    if wall is not None:box.label(text=f"{label} · pared radial mínima medida: {wall:.2f} mm")
    if gap is not None and gap>0:box.label(text=f"{label} · hueco radial máximo hasta hueso: {gap:.2f} mm")
    if measurement['missing_rays']:box.label(text=f"{label} · sin hueso en {measurement['missing_rays']}/{measurement['rays']} direcciones medidas",icon='ERROR')


def restore_visibility(backup):
    for name,row in backup.items():
        obj=bpy.data.objects.get(name);scene=bpy.data.scenes.get(row['scene'])
        if obj is None or scene is None:continue
        obj.hide_viewport=row['disabled']
        layer=scene.view_layers.get(row['view_layer'])
        if layer is not None and layer.objects.get(name) is not None:
            obj.hide_set(row['hidden'],view_layer=layer)


@bpy.app.handlers.persistent
def recover_saved_previews(_unused=None):
    for obj in list(bpy.data.objects):
        if not obj.name.startswith(PREVIEW) or not obj.get('DSG_optimizer_preview'):continue
        restore_visibility(json.loads(obj.get('DSG_optimizer_visibility_backup','{}')))
        restore_followers(obj)
        mesh=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
        if mesh.users==0:bpy.data.meshes.remove(mesh)
    PREVIEW_VISIBILITY.clear()
    STATE.update(result=None,scene=None)


def restore_followers(preview):
    source=bpy.data.objects.get(preview.get('DSG_optimizer_original',''))
    for plane in bpy.data.objects:
        constraint=plane.constraints.get('DSG_FollowImplant')
        if constraint is not None and constraint.target==preview:constraint.target=source


def watch_preview():
    if bpy.data.objects.get(PREVIEW) is None:return None
    context=bpy.context
    from .. import guide_module as g
    if context.scene.dsg_props.current_step!=STATE.get('preview_step',g.STEP_IMPLANT):
        discard();STATE['message']='Fase cambiada; propuesta descartada sin aplicar.';return None
    request=STATE.get('request')
    if request and (settings(context.scene)!=request['settings'] or context.scene.dsg_opt_family!=request.get('family',context.scene.dsg_opt_family)):
        discard();STATE['message']='Parámetros cambiados; vuelve a calcular la comparación.';return None
    if context.scene!=STATE['scene'] or context.view_layer!=STATE.get('preview_view_layer',context.view_layer) or target(context) is None or target(context).name!=STATE['target']:
        discard();STATE['message']='Caso o implante cambiados; propuesta descartada.';return None
    for name in PREVIEW_VISIBILITY:
        original=bpy.data.objects.get(name)
        if original is not None and not original.hide_get():original.hide_set(True)
    return .5

