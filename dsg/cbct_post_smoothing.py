"""User-selected finishing after segmentation; background calculation, reversible meshes."""
from __future__ import annotations
import hashlib,json,os,subprocess,tempfile,time,shutil
from pathlib import Path
import bpy
from bpy.app.handlers import persistent

ORIGINAL_MESH='DSG_post_smooth_original_mesh'
CACHED_MESH='DSG_post_smooth_cached_mesh'
SOURCE_HASH='DSG_post_smooth_source_hash'
REPORT='DSG_post_smooth_report_json'
STATUS='DSG_post_smooth_status'
_JOB=None

def tooth_objects(scene):
    return [o for o in scene.objects if o.type=='MESH' and bool(o.get('DSG_tooth_instance'))]

def mesh_arrays(mesh):
    import numpy as np
    mesh.calc_loop_triangles();v=np.empty(len(mesh.vertices)*3,np.float32);f=np.empty(len(mesh.loop_triangles)*3,np.int32)
    mesh.vertices.foreach_get('co',v);mesh.loop_triangles.foreach_get('vertices',f)
    return v.reshape(-1,3),f.reshape(-1,3)

def source_mesh(obj):
    original=obj.get(ORIGINAL_MESH)
    return original if isinstance(original,bpy.types.Mesh) else obj.data

def mesh_hash(mesh):
    v,f=mesh_arrays(mesh);return hashlib.sha256(v.tobytes()+f.tobytes()).hexdigest()

def snapshot_object(obj):
    return {'object':obj,'mesh':source_mesh(obj),'data':obj.data,'hash':mesh_hash(source_mesh(obj)),
            'label':int(obj.get('DSG_universal_label',0)),'fdi':int(obj.get('DSG_fdi_number',0)),
            'matrix':tuple(tuple(row) for row in obj.matrix_world)}

def active(scene):
    return any(isinstance(o.get(CACHED_MESH),bpy.types.Mesh) and o.data==o.get(CACHED_MESH) for o in tooth_objects(scene))

def busy(scene=None):
    return _JOB is not None and (scene is None or _JOB['scene']==scene)

def _disable_legacy(obj):
    from . import cbct_dental_module as dental
    mod=obj.modifiers.get(dental.ALIGNMENT_VISUAL_SMOOTH_MODIFIER)
    if mod:mod.show_viewport=False;mod.show_render=False

def restore_originals(scene):
    count=0
    for obj in tooth_objects(scene):
        original=obj.get(ORIGINAL_MESH)
        if isinstance(original,bpy.types.Mesh) and obj.data!=original:obj.data=original;count+=1
        _disable_legacy(obj)
    scene[STATUS]='Dientes originales'
    return count

def apply_cached(scene,mode=None):
    cached_mode=scene.get('DSG_post_smooth_cache_mode')
    if mode and mode!=cached_mode:return 0
    report=json.loads(str(scene.get(REPORT,'{}')))
    expected={int(row['label']) for row in report.get('teeth',[]) if row.get('status')=='READY'}
    if not expected:return 0
    recorded=json.loads(str(scene.get('DSG_post_smooth_cache_sources','{}')))
    current={str(int(o.get('DSG_universal_label',0))):mesh_hash(source_mesh(o)) for o in tooth_objects(scene)}
    if recorded and recorded!=current:return 0
    targets=[]
    for obj in tooth_objects(scene):
        if int(obj.get('DSG_universal_label',0)) not in expected:continue
        cached=obj.get(CACHED_MESH);original=obj.get(ORIGINAL_MESH)
        if not isinstance(cached,bpy.types.Mesh) or not isinstance(original,bpy.types.Mesh):continue
        if mode and obj.get('DSG_post_smooth_mode')!=mode:continue
        if mesh_hash(original)!=obj.get(SOURCE_HASH):continue
        if obj.data not in (original,cached):continue
        targets.append((obj,cached))
    if {int(obj.get('DSG_universal_label',0)) for obj,_ in targets}!=expected:return 0
    for obj,mesh in targets:obj.data=mesh;_disable_legacy(obj)
    scene[STATUS]=f'{len(targets)} dientes suavizados · resultado en caché'
    return len(targets)

def apply_result(scene,snapshots,result):
    import numpy as np
    # Validate the complete batch before changing any object.
    for s in snapshots:
        obj=s['object']
        if obj.name not in scene.objects or obj.data!=s['data'] or source_mesh(obj)!=s['mesh'] or mesh_hash(s['mesh'])!=s['hash']:
            raise RuntimeError('La dentición cambió durante el cálculo; resultado descartado')
        if int(obj.get('DSG_universal_label',0))!=s['label'] or int(obj.get('DSG_fdi_number',0))!=s['fdi'] or tuple(tuple(row) for row in obj.matrix_world)!=s['matrix']:
            raise RuntimeError('Cambió la identidad o transformación de un diente; resultado descartado')
    by_label={int(r['label']):r for r in result['teeth']};pending=[];created=[]
    previous=[(s['object'],s['object'].data) for s in snapshots]
    properties={s['object'].as_pointer():{k:s['object'].get(k) for k in (ORIGINAL_MESH,CACHED_MESH,SOURCE_HASH,'DSG_post_smooth_mode','DSG_post_smooth_json')} for s in snapshots}
    try:
        for s in snapshots:
            row=by_label.get(s.get('result_label',s['label']),{'status':'SKIPPED','fallback_reason':'Resultado no disponible'})
            if row['status']!='READY':continue
            v=np.load(row['vertices_path'],allow_pickle=False);f=np.load(row['faces_path'],allow_pickle=False)
            if v.ndim!=2 or v.shape[1]!=3 or f.ndim!=2 or f.shape[1]!=3 or not np.isfinite(v).all() or f.min()<0 or f.max()>=len(v):
                raise RuntimeError('Malla del worker inválida')
            obj=s['object'];mesh=bpy.data.meshes.new(f'{obj.name}_Suave_9_10_8');created.append(mesh)
            mesh.vertices.add(len(v));mesh.vertices.foreach_set('co',np.ascontiguousarray(v,dtype=np.float32).ravel())
            mesh.loops.add(3*len(f));mesh.loops.foreach_set('vertex_index',np.ascontiguousarray(f,dtype=np.int32).ravel())
            mesh.polygons.add(len(f));mesh.polygons.foreach_set('loop_start',np.arange(0,3*len(f),3,dtype=np.int32));mesh.polygons.foreach_set('loop_total',np.full(len(f),3,np.int32));mesh.polygons.foreach_set('use_smooth',np.ones(len(f),np.bool_));mesh.update(calc_edges=True)
            for material in s['mesh'].materials:mesh.materials.append(material)
            mesh.use_fake_user=True;pending.append((s,mesh,row))
        # Original ID pointers survive .blend save/load, renaming, and view toggles.
        for s,mesh,row in pending:
            obj=s['object'];s['mesh'].use_fake_user=True
            obj[ORIGINAL_MESH]=s['mesh'];obj[CACHED_MESH]=mesh;obj[SOURCE_HASH]=s['hash']
            obj['DSG_post_smooth_mode']=str(result.get('mode','CLEAN'))
            obj['DSG_post_smooth_json']=json.dumps({k:v for k,v in row.items() if not k.endswith('_path')},ensure_ascii=False)
            obj.data=mesh
        for s in snapshots:_disable_legacy(s['object'])
    except Exception:
        for obj,mesh in previous:
            obj.data=mesh
            for k,value in properties[obj.as_pointer()].items():
                if value is None:obj.pop(k,None)
                else:obj[k]=value
        for mesh in created:
            if mesh.users<=1:bpy.data.meshes.remove(mesh)
        raise
    safe={**result,'teeth':[{k:v for k,v in r.items() if not k.endswith('_path')} for r in result['teeth']]}
    scene[REPORT]=json.dumps(safe,ensure_ascii=False)
    scene['DSG_post_smooth_cache_sources']=json.dumps({str(s['label']):s['hash'] for s in snapshots})
    scene['DSG_post_smooth_cache_mode']=str(result.get('mode','CLEAN'))
    applied=len(pending);skipped=len(snapshots)-applied
    reasons=[f"FDI {r.get('fdi','?')}: {r.get('fallback_reason','')}" for r in result['teeth'] if r['status']!='READY']
    scene[STATUS]=f'{applied} suavizados · {skipped} originales'+(f' · {reasons[0]}' if reasons else '')
    return {'applied':applied,'skipped':skipped}

def _cleanup(job):
    if job.get('log') is not None:job['log'].close()
    root=Path(job['root']).resolve();base=Path(tempfile.gettempdir()).resolve()
    if root.parent==base and root.name.startswith('DSG_POST_SMOOTH_'):shutil.rmtree(root,ignore_errors=True)

def cancel(update_status=True):
    global _JOB
    job=_JOB
    if job is None:return
    _JOB=None
    proc=job['process']
    if proc.poll() is None:proc.terminate()
    try:proc.wait(timeout=2)
    except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=2)
    try:
        if update_status:job['scene'][STATUS]='Suavizado cancelado · geometría sin cambios'
    except ReferenceError:pass
    if job.get('on_cancel'):job['on_cancel'](job)
    _cleanup(job)

@persistent
def cancel_on_load(_):cancel()

def _poll():
    global _JOB
    job=_JOB
    if job is None:return None
    try:
        if bpy.context.scene!=job['scene']:cancel();return None
        if job.get('scope_valid') and not job['scope_valid']():cancel();return None
        if time.monotonic()-job['started']>300:cancel();job['scene'][STATUS]='Suavizado cancelado: tiempo máximo superado';return None
        status=Path(job['root'])/'status.json'
        if status.exists():
            try:job['scene'][STATUS]=json.loads(status.read_text(encoding='utf-8')).get('message','Calculando…')
            except (OSError,json.JSONDecodeError):pass  # Transient progress-file contention.
        if job['process'].poll() is None:return .3
        result_path=Path(job['root'])/'result.json'
        if not result_path.is_file():raise RuntimeError('El worker no devolvió una superficie; revisa VTK del runtime')
        result=json.loads(result_path.read_text(encoding='utf-8'))
        if job['process'].returncode!=0 or result['status']!='OK':raise RuntimeError(result.get('error','Falló el cálculo'))
        if job.get('signature'):
            from . import dicom_module
            if str(dicom_module.RUNTIME.semantic_source_signature)!=job['signature']:raise RuntimeError('Cambió el CBCT; resultado descartado')
        apply_result(job['scene'],job['snapshots'],result)
        if job.get('on_complete'):job['on_complete'](job,result)
        from . import workflow_history
        workflow_history.commit(bpy.context,job.get('history_label','Suavizar dientes'))
        bpy.ops.ed.undo_push(message='DSG · '+job.get('history_label','Suavizar dientes'))
    except Exception as exc:
        if job.get('on_failure'):job['on_failure'](job)
        try:job['scene'][STATUS]=f'Suavizado no aplicado: {exc}'[:300]
        except ReferenceError:pass
    finally:
        if job['process'].poll() is not None:
            _JOB=None;_cleanup(job)
        for screen in bpy.data.screens:
            for area in screen.areas:area.tag_redraw()
    return .3 if _JOB is not None else None

def start(context,mode='CLEAN',*,objects_override=None):
    global _JOB
    from . import dicom_module as dicom,segmentation_engines as engines
    if _JOB is not None:raise RuntimeError('Ya hay un suavizado en curso')
    objects=tooth_objects(context.scene) if objects_override is None else list(objects_override)
    if not objects:raise RuntimeError('Segmenta los dientes antes de suavizar')
    if any(o.mode!='OBJECT' for o in objects):raise RuntimeError('Sal del modo edición antes de suavizar')
    import numpy as np
    labels=None
    if mode in ('CLEAN','ORGANIC','ORGANIC_ARCHES'):
        if not dicom.RUNTIME.is_loaded():raise RuntimeError('Abre el CBCT original para comprobar la segmentación')
        labels=dicom.get_cached_semantic_cbct_labels(model_kind='universal',require_current_source=True)
        if labels is None:raise RuntimeError('La segmentación original no está disponible para este CBCT')
    py=engines._python_path()
    if not py or not Path(py).is_file():raise RuntimeError('No se encontró Python de Blender')
    from . import workflow_history
    workflow_history.begin(context,'Suavizar dientes')
    root=Path(tempfile.mkdtemp(prefix='DSG_POST_SMOOTH_'));snapshots=[snapshot_object(o) for o in objects];targets=[]
    try:
        for index,s in enumerate(snapshots):
            obj=s['object'];v,f=mesh_arrays(s['mesh']);k=s['label']
            if mode=='ORGANIC_ARCHES':
                arch=str(obj.get('DSG_simple_arch',''))
                if arch not in ('UPPER','LOWER'):raise RuntimeError('Falta la identidad de la arcada simple')
                s['result_label']=k=1 if arch=='UPPER' else 2
            elif k<=0 and objects_override is not None:s['result_label']=k=index+1
            if k<=0:raise RuntimeError('Los dientes no tienen labels de segmentación')
            vp=root/f'source_v_{k}.npy';fp=root/f'source_f_{k}.npy';np.save(vp,v);np.save(fp,f)
            spacing=obj.get('DSG_cbct_spacing_zyx_mm')
            if spacing is None and dicom.RUNTIME.is_loaded():spacing=dicom.RUNTIME.spacing_zyx_mm
            if spacing is None:raise RuntimeError('Falta el espaciado del CBCT original')
            # Native segmented teeth use root-local coordinates. Reject modified local transforms.
            if mode in ('CLEAN','ORGANIC','ORGANIC_ARCHES') and not np.allclose(np.array(obj.matrix_basis),np.eye(4),atol=1e-6):raise RuntimeError('Restablece la transformación local de los dientes para usar el modo fiel')
            targets.append({'label':k,'fdi':s['fdi'],'vertex_count':len(v),'source_vertices_path':str(vp),'source_faces_path':str(fp),'spacing_zyx_mm':list(spacing)})
        labels_path=root/'labels.npy'
        if labels is not None:np.save(labels_path,labels,allow_pickle=False)
        request={'job_dir':str(root),'mode':mode,'labels_path':str(labels_path),'targets':targets,
                 'site_paths':[str(engines.site_packages()),str(dicom.VENDOR_DIR)],
                 'spacing_zyx_mm':list(dicom.RUNTIME.spacing_zyx_mm),'dims_zyx':list(dicom.RUNTIME.dims_zyx),
                 'display_signs_xyz':list(dicom._dicom_display_signs_xyz()) if mode in ('CLEAN','ORGANIC','ORGANIC_ARCHES') else [1,1,1]}
        rp=root/'request.json';rp.write_text(json.dumps(request,ensure_ascii=False),encoding='utf-8')
        log=(root/'worker.log').open('w',encoding='utf-8');env=os.environ.copy();env['PYTHONUNBUFFERED']='1'
        flags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0
        try:proc=subprocess.Popen([py,str(Path(__file__).with_name('cbct_post_smoothing_worker.py')),str(rp)],stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,env=env,creationflags=flags)
        except Exception:log.close();raise
    except Exception:
        _cleanup({'root':str(root),'log':None});raise
    _JOB={'scene':context.scene,'snapshots':snapshots,'root':str(root),'process':proc,'log':log,
          'started':time.monotonic(),
          'signature':str(dicom.RUNTIME.semantic_source_signature) if mode in ('CLEAN','ORGANIC','ORGANIC_ARCHES') else ''}
    context.scene[STATUS]='Calculando suavizado de dientes…'
    if not bpy.app.timers.is_registered(_poll):bpy.app.timers.register(_poll,first_interval=.3)
    return True

class DSG_OT_PostSmoothTeeth(bpy.types.Operator):
    bl_idname='dsg.cbct_post_smooth_teeth'
    bl_label='Suavizar dientes'
    bl_description='Suaviza los dientes después de segmentar; conserva los originales y permite restaurarlos'
    @classmethod
    def poll(cls,context):return bool(tooth_objects(context.scene)) and not busy()
    def execute(self,context):
        if active(context.scene):restore_originals(context.scene);return {'FINISHED'}
        mode=context.scene.dsg_cbct_dental.surface_finish_mode
        if apply_cached(context.scene,mode):return {'FINISHED'}
        try:start(context,mode)
        except Exception as exc:self.report({'ERROR'},str(exc)[:250]);return {'CANCELLED'}
        return {'FINISHED'}

class DSG_OT_CancelPostSmooth(bpy.types.Operator):
    bl_idname='dsg.cbct_cancel_post_smooth'
    bl_label='Cancelar suavizado'
    def execute(self,context):cancel();return {'FINISHED'}

class DSG_OT_PostSmoothReport(bpy.types.Operator):
    bl_idname='dsg.cbct_post_smooth_report'
    bl_label='Resultado del suavizado'
    def execute(self,context):
        report=json.loads(str(context.scene.get(REPORT,'{}')))
        def draw(menu,_context):
            for row in report.get('teeth',[]):
                accepted=row.get('status')=='READY'
                message='Suavizado' if accepted else 'Original: '+str(row.get('fallback_reason','Sin resultado'))
                menu.layout.label(text=f"FDI {row.get('fdi','?')} · {message}"[:110],icon='CHECKMARK' if accepted else 'INFO')
        context.window_manager.popup_menu(draw,title='Resultado por diente',icon='MOD_SMOOTH')
        return {'FINISHED'}

def draw(layout,context):
    from . import dicom_module
    if dicom_module.semantic_workflow_busy() or not tooth_objects(context.scene):
        return
    props=context.scene.dsg_cbct_dental
    if busy(context.scene):
        layout.label(text=str(context.scene.get(STATUS,'Calculando…'))[:90])
        layout.operator(DSG_OT_CancelPostSmooth.bl_idname,text='CANCELAR SUAVIZADO',icon='CANCEL');return
    layout.prop(props,'surface_finish_mode',text='Suavizado')
    layout.operator(DSG_OT_PostSmoothTeeth.bl_idname,text='DIENTES ORIGINALES' if active(context.scene) else 'SUAVIZAR DIENTES',icon='MOD_SMOOTH',depress=active(context.scene))
    if context.scene.get(STATUS):layout.label(text=str(context.scene[STATUS])[:100])
    if context.scene.get(REPORT):layout.operator(DSG_OT_PostSmoothReport.bl_idname,text='VER RESULTADO POR DIENTE',icon='INFO')
    if props.surface_finish_mode=='CLEAN':layout.label(text='Conserva originales si fallan los controles')
    else:layout.label(text='Acabado visual · sin validación anatómica')
    layout.label(text='Reversible · alineación con la referencia original')

def register_hooks():
    if cancel_on_load not in bpy.app.handlers.load_pre:bpy.app.handlers.load_pre.append(cancel_on_load)

def unregister_hooks():
    cancel()
    if bpy.app.timers.is_registered(_poll):bpy.app.timers.unregister(_poll)
    if cancel_on_load in bpy.app.handlers.load_pre:bpy.app.handlers.load_pre.remove(cancel_on_load)
