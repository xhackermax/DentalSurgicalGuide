"""Native undo plus immutable on-disk checkpoints for completed DSG operations.

Blender owns the mesh undo stack. External CBCT arrays are content-addressed,
memory-mapped, and selected by an undoable Scene token instead of Python IDs.
"""
from __future__ import annotations
import functools,hashlib,json,os,time,uuid,weakref
from pathlib import Path
import bpy
from bpy.app.handlers import persistent

STATE_KEY='DSG_history_state'
PROJECT_KEY='DSG_history_project'
_ARRAY_CACHE={}
_KEYMAPS=[]
_DEPTH=0
_RESTORING=False
_ARCHIVE_MODE=False
_ACTIVE_MODALS={}
_UNDO_EPOCH=0
_AUTOMATION_SUSPENDED=False
_RUNTIME_FIELDS=('source_path','source_kind','source_files','volume','dims_zyx','spacing_zyx_mm',
 'orientation_xyz','image_origin_patient','slopes','intercepts','density_min','density_max',
 'auto_low','auto_high','estimated_memory_mb','pipeline_volume_path','pipeline_slopes_path',
 'pipeline_intercepts_path','vdb_path','vdb_stride','vdb_dims_xyz','segmentations',
 'semantic_labels','semantic_status_path','semantic_source_signature','semantic_model_kind',
 'semantic_model_metadata','semantic_crop_info')

def _json(path,value):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True),encoding='utf-8')
    os.replace(temp,path)

def _root(scene):
    if not scene.get(PROJECT_KEY):scene[PROJECT_KEY]=uuid.uuid4().hex
    base=Path(os.environ.get('DSG_HISTORY_ROOT') or Path(bpy.utils.user_resource('SCRIPTS'))/'dsg_history')
    root=base/str(scene[PROJECT_KEY]);(root/'blobs').mkdir(parents=True,exist_ok=True)
    (root/'states').mkdir(exist_ok=True)
    return root

def _array(value,root):
    import numpy as np
    a=np.ascontiguousarray(value)
    key=(id(value),str(value.dtype),tuple(value.shape))
    # Mutable masks are always hashed: editing a mask in place creates a version.
    cached=_ARRAY_CACHE.get(key) if not value.flags.writeable else None
    if cached and cached[0]() is value and Path(cached[1]).is_file():return {'$array':cached[1]}
    hasher=hashlib.sha256();hasher.update(str(a.dtype).encode());hasher.update(str(a.shape).encode())
    hasher.update(memoryview(a).cast('B'));digest=hasher.hexdigest()
    path=root/'blobs'/f'{digest}.npy'
    if not path.exists():
        temp=path.with_suffix('.tmp')
        with temp.open('wb') as stream:np.save(stream,a,allow_pickle=False)
        os.replace(temp,path)
    if not value.flags.writeable:_ARRAY_CACHE[key]=(weakref.ref(value),str(path))
    return {'$array':str(path)}

def _encode(value,root):
    import numpy as np
    if isinstance(value,np.ndarray):return _array(value,root)
    if isinstance(value,np.generic):return value.item()
    if isinstance(value,set):return {'$set':sorted(_encode(v,root) for v in value)}
    if isinstance(value,tuple):return {'$tuple':[_encode(v,root) for v in value]}
    if isinstance(value,list):return [_encode(v,root) for v in value]
    if isinstance(value,dict):return {str(k):_encode(v,root) for k,v in value.items()}
    if value is None or isinstance(value,(str,int,float,bool)):return value
    raise TypeError(f'Estado de runtime no serializable: {type(value).__name__}')

def _decode(value):
    import numpy as np
    if isinstance(value,list):return [_decode(v) for v in value]
    if not isinstance(value,dict):return value
    if '$array' in value:return np.load(value['$array'],mmap_mode='c',allow_pickle=False)
    if '$set' in value:return set(_decode(v) for v in value['$set'])
    if '$tuple' in value:return tuple(_decode(v) for v in value['$tuple'])
    return {k:_decode(v) for k,v in value.items()}

def _external_file(filename,root):
    import shutil
    path=Path(str(filename or ''))
    if not filename or not path.is_file():return str(filename or '')
    if root.resolve() in path.resolve().parents:return str(path)
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):digest.update(block)
    target=root/'blobs'/(digest.hexdigest()+path.suffix)
    if not target.exists():
        # A hard link retains an immutable file even when its temporary name is removed.
        try:os.link(path,target)
        except OSError:shutil.copyfile(path,target)
    return str(target)

def _runtime(root):
    from . import dicom_module as dicom
    values={k:_encode(getattr(dicom.RUNTIME,k),root) for k in _RUNTIME_FIELDS}
    values['_semantic_current']=bool(dicom.RUNTIME.semantic_labels is not None and str(dicom.RUNTIME.semantic_source_signature)==dicom._semantic_source_signature())
    # Use the archived calibrated inputs, never the worker's temporary directory.
    for key,array_key in (('pipeline_volume_path','volume'),('pipeline_slopes_path','slopes'),('pipeline_intercepts_path','intercepts')):
        desc=values.get(array_key)
        if isinstance(desc,dict) and '$array' in desc:values[key]=desc['$array']
    values['vdb_path']=_external_file(dicom.RUNTIME.vdb_path,root)
    return values

def _plain(value):
    if isinstance(value,bpy.types.ID):return {'id':value.name,'type':value.bl_rna.identifier}
    if isinstance(value,dict):return {str(k):_plain(v) for k,v in value.items()}
    if hasattr(value,'to_dict'):return {k:_plain(v) for k,v in value.to_dict().items()}
    if isinstance(value,(str,int,float,bool)) or value is None:return value
    try:return [_plain(v) for v in value]
    except TypeError:return str(value)

def _props(owner):
    try:return {k:_plain(owner[k]) for k in owner.keys() if k not in (STATE_KEY,PROJECT_KEY)}
    except TypeError:
        # Several built-in modifiers expose RNA settings, but no IDProperties.
        return {p.identifier:_plain(getattr(owner,p.identifier)) for p in owner.bl_rna.properties
                if p.identifier!='rna_type' and not p.is_readonly}

def _fingerprint(scene,runtime):
    import numpy as np
    digest=hashlib.sha256(json.dumps({'scene':_props(scene),'runtime':runtime},sort_keys=True,default=str).encode())
    seen=set()
    for obj in sorted(scene.objects,key=lambda o:o.name):
        mods=[(m.name,m.type,m.show_viewport,m.show_render,_props(m)) for m in obj.modifiers]
        digest.update(json.dumps((obj.name,obj.type,_props(obj),_plain(obj.matrix_world),obj.hide_viewport,obj.hide_render,obj.hide_get(),obj.select_get(),mods),sort_keys=True,default=str).encode())
        mesh=obj.data
        if obj.type=='MESH' and mesh.as_pointer() not in seen:
            seen.add(mesh.as_pointer())
            for collection,attribute,width,dtype in ((mesh.vertices,'co',3,np.float32),(mesh.edges,'vertices',2,np.int32),(mesh.loops,'vertex_index',1,np.int32),(mesh.polygons,'loop_total',1,np.int32),(mesh.polygons,'material_index',1,np.int32),(mesh.polygons,'use_smooth',1,np.bool_)):
                arr=np.empty(len(collection)*width,dtype);collection.foreach_get(attribute,arr);digest.update(arr.tobytes())
            digest.update(json.dumps(_props(mesh),sort_keys=True,default=str).encode())
    return digest.hexdigest()

def _read(path):return json.loads(Path(path).read_text(encoding='utf-8'))

def _images(scene,root):
    """Memfile undo does not restore generated MPR pixel buffers."""
    import numpy as np
    images={};seen=set()
    def visit(tree):
        if tree is None or tree.as_pointer() in seen:return
        seen.add(tree.as_pointer())
        for node in tree.nodes:
            image=getattr(node,'image',None)
            if image is not None and image.source=='GENERATED' and image.size[0] and image.size[1]:
                pixels=np.empty(len(image.pixels),np.float32);image.pixels.foreach_get(pixels)
                images[image.name]={'pixels':_array(pixels,root),'size':list(image.size)}
            visit(getattr(node,'node_tree',None))
    for obj in scene.objects:
        for material in getattr(getattr(obj,'data',None),'materials',()):
            if material is not None:visit(material.node_tree)
    return images

def _restore_images(images):
    for name,desc in images.items():
        image=bpy.data.images.get(name)
        if image is None:continue
        if list(image.size)!=desc['size']:image.scale(*desc['size'])
        image.pixels.foreach_set(desc['pixels']);image.update()

def _capture(context,label,force=False):
    scene=context.scene;root=_root(scene);runtime=_runtime(root)
    from . import guide_module
    guide_return=_plain(guide_module._IMPLANT_STEP_RETURN_STATE.get(scene.name,{}))
    images=_images(scene,root)
    fingerprint=_fingerprint(scene,{**runtime,'guide_return_state':guide_return,'images':images});previous=str(scene.get(STATE_KEY) or '')
    if not force and previous and Path(previous).is_file() and _read(previous).get('fingerprint')==fingerprint:return previous
    name=uuid.uuid4().hex;path=root/'states'/f'{name}.json';blend=path.with_suffix('.blend')
    started=time.perf_counter();old_token=scene.get(STATE_KEY)
    scene[STATE_KEY]=str(path)
    saved_paths=[]
    try:
        for obj in scene.objects:
            if obj.type=='VOLUME' and obj.data.filepath:
                saved_paths.append((obj.data,obj.data.filepath));obj.data.filepath=_external_file(obj.data.filepath,root)
        bpy.data.libraries.write(str(blend),{scene},fake_user=True,compress=True)
        record={'schema':2,'label':str(label),'parent':previous,'blend':str(blend),
                'scene_name':scene.name,'runtime':runtime,'fingerprint':fingerprint,
                'guide_return_state':guide_return,
                'images':images,
                'timestamp':time.time(),'capture_s':time.perf_counter()-started}
        _json(path,record)
    except Exception:
        if old_token is None:scene.pop(STATE_KEY,None)
        else:scene[STATE_KEY]=old_token
        blend.unlink(missing_ok=True);raise
    finally:
        for data,filename in saved_paths:data.filepath=filename
    return str(path)

def begin(context,label):
    global _ARCHIVE_MODE,_AUTOMATION_SUSPENDED
    if _RESTORING:return
    previous=context.scene.get(STATE_KEY)
    token=_capture(context,'Antes de '+str(label))
    if token!=previous or _ARCHIVE_MODE:
        bpy.ops.ed.undo_push(message='DSG · '+str(label)+' · estado anterior')
    _ARCHIVE_MODE=False
    _AUTOMATION_SUSPENDED=False

def commit(context,label):
    if _RESTORING:return
    # Complete delayed stage presentation inside the same transaction. Undo
    # must restore the completed stage, not a menu followed by a stale timer.
    from . import guide_module as guide,lifecycle
    scene=context.scene
    pending=any(key[0]==scene.name for key in guide.WORKFLOW_RESTORE_PENDING)
    pending=pending or scene.name in guide._IMPLANT_STEP_RESTORE_PENDING
    if pending:
        lifecycle.cancel_named_timers(guide.__name__,{'_restore_timer'})
        guide.WORKFLOW_RESTORE_PENDING.clear();guide._IMPLANT_STEP_RESTORE_PENDING.clear()
        guide._restore_workflow_stage(context,scene,scene.dsg_props.current_step)
    return _capture(context,label,force=True)

def has_checkpoint(scene):
    return bool(scene and Path(str(scene.get(STATE_KEY) or '')).is_file())

def automation_suspended():return _RESTORING or _AUTOMATION_SUSPENDED

def restore_runtime(scene,force=False):
    from . import dicom_module as dicom
    path=str(scene.get(STATE_KEY) or '')
    if not path or not Path(path).is_file():return False
    record=_read(path);values=_decode(record['runtime']);images=_decode(record.get('images',{}))
    semantic_current=values.pop('_semantic_current',False)
    # Decode all references first: a missing file cannot leave a half-restored runtime.
    if values['source_path']!=dicom.RUNTIME.source_path:dicom.RUNTIME.header=None;dicom.RUNTIME.datasets=[]
    for key,value in values.items():setattr(dicom.RUNTIME,key,value)
    dicom.RUNTIME.pipeline_cache_dir='';dicom.RUNTIME.pipeline_result_dir=''
    dicom.RUNTIME.native_density_fullres=None;dicom.RUNTIME.native_density_cache_key=''
    dicom.RUNTIME.native_threshold_index=None;dicom.RUNTIME.native_threshold_index_key=''
    dicom.RUNTIME.surface_preview_sample_cache.clear()
    # Python hashes are randomized between Blender sessions.
    if semantic_current:dicom.RUNTIME.semantic_source_signature=dicom._semantic_source_signature()
    from . import guide_module as guide
    guide._IMPLANT_STEP_RETURN_STATE[scene.name]=record.get('guide_return_state',{})
    _restore_images(images)
    return True

def restore_checkpoint(context,path):
    global _RESTORING,_ARCHIVE_MODE
    record=_read(path);blend=Path(record['blend'])
    if not blend.is_file():raise RuntimeError('No se encontró la copia de esta etapa')
    if len(bpy.data.scenes)!=1:raise RuntimeError('La recuperación archivada requiere una escena; Ctrl+Z nativo sigue disponible')
    _RESTORING=True
    try:
        _before_undo()
        old=context.scene
        names={};loaded={};old_ids={}
        categories=('objects','collections','meshes','curves','materials','volumes','images','node_groups')
        with bpy.data.libraries.load(str(blend),link=False) as (source,target):
            target.scenes=[record['scene_name']]
            for category in categories:
                names[category]=list(getattr(source,category,()))
                old_ids[category]={name:getattr(bpy.data,category).get(name) for name in names[category]}
                setattr(target,category,list(names[category]))
        new=target.scenes[0]
        for category in categories:loaded[category]=list(getattr(target,category))
        for window in context.window_manager.windows:
            if window.scene==old:window.scene=new
        for obj in list(old.objects):bpy.data.objects.remove(obj,do_unlink=True)
        bpy.data.scenes.remove(old)
        for category in categories:
            datablocks=getattr(bpy.data,category)
            for name,block in old_ids[category].items():
                if block is None:continue
                try:
                    if block.users<=int(block.use_fake_user):datablocks.remove(block)
                    elif name in names[category]:block.name='__DSG_previous_'+name
                except ReferenceError:pass
            for name,block in zip(names[category],loaded[category]):
                if block is not None:block.name=name
        new.name=record['scene_name'];new[STATE_KEY]=str(path)
        restore_runtime(new,force=True);_ARCHIVE_MODE=True
        _after_undo()
    finally:
        _RESTORING=False
        from . import dicom_module as dicom
        dicom.RUNTIME.undo_in_progress=False;dicom.RUNTIME.update_lock=False
    return True

@persistent
def _before_undo(*_):
    global _UNDO_EPOCH,_AUTOMATION_SUSPENDED
    _UNDO_EPOCH+=1
    _AUTOMATION_SUSPENDED=True
    # Modal operators retain RNA and mesh references. Release them before a
    # native undo or archived Scene replacement invalidates those references.
    for operator,context,token in list(_ACTIVE_MODALS.values()):_cancel_modal(operator,context)
    _ACTIVE_MODALS.clear()
    from . import cbct_post_smoothing as post,dicom_module as dicom,cbct_pipeline_client as pipeline,guide_module as guide,lifecycle,core
    # Archive recovery does not dispatch Blender's native handler list.
    # Freeze DICOM timers here as well, before replacing any Scene IDs.
    lifecycle.cancel_module_timers(dicom.__name__)
    dicom._clear_pending_refresh_state()
    dicom.RUNTIME.undo_in_progress=True;dicom.RUNTIME.update_lock=True
    lifecycle.cancel_module_timers(guide.__name__)
    guide.WORKFLOW_RESTORE_PENDING.clear();guide._IMPLANT_STEP_RESTORE_PENDING.clear()
    guide._AUTO_CLOSED_MODEL_ADVANCE_PENDING.clear()
    for name in ('_MODEL_TOPOLOGY_CACHE','_FRAME_SURFACE_GRAPH_CACHE','_RETENTION_BVH_CACHE','_ENGRAVE_PROJECTION_CACHE','_PREFLIGHT_UI_CACHE','_DSG_ACTION_RUNTIME'):
        getattr(guide,name,{}).clear()
    for name in ('_RETENTION_PREVIEW_REFRESH_PENDING','_ENGRAVE_PREVIEW_REFRESH_PENDING','_DICOM_MEASURE_UPDATE_PENDING','_DSG_OWNED_DATA_CLEANUP_PENDING'):
        setattr(guide,name,False)
    guide.unregister_contour_draw_handler();guide.unregister_irr_draw_handler()
    guide._draw_callback_irrigation._current_chain=[]
    if bpy.app.timers.is_registered(core._run_workflow_undo_repair):bpy.app.timers.unregister(core._run_workflow_undo_repair)
    core._WORKFLOW_UNDO_REPAIR_PENDING=False
    post.cancel(update_status=False)
    if dicom.semantic_workflow_busy():
        pipeline.cancel()
        dicom._ASYNC_SEGMENTATION.update(active=False,builder=None,prepared_surfaces=None,phase='')
        dicom._restore_ai_performance_session(bpy.context)

@persistent
def _after_undo(*_):
    try:restore_runtime(bpy.context.scene)
    except Exception as exc:
        print('[DSG] History restore error:',exc)
        bpy.context.scene['DSG_history_error']=str(exc)
    finally:
        from . import dicom_module as dicom
        dicom.RUNTIME.undo_in_progress=False;dicom.RUNTIME.update_lock=False

@persistent
def _after_load(*_):
    global _ARCHIVE_MODE
    _ARCHIVE_MODE=False;_after_undo()

def undo_previous(context):
    global _ARCHIVE_MODE
    if not _ARCHIVE_MODE and bpy.ops.ed.undo.poll():return bpy.ops.ed.undo()
    path=str(context.scene.get(STATE_KEY) or '')
    if not path:return {'CANCELLED'}
    previous=_read(path).get('parent')
    if not previous:return {'CANCELLED'}
    restore_checkpoint(context,previous);return {'FINISHED'}

class DSG_OT_WorkflowUndo(bpy.types.Operator):
    bl_idname='dsg.workflow_undo';bl_label='Deshacer último cambio DSG';bl_options={'INTERNAL'}
    @classmethod
    def poll(cls,context):return context.mode=='OBJECT' and bool(context.scene.get(STATE_KEY))
    def execute(self,context):
        try:return undo_previous(context)
        except Exception as exc:self.report({'ERROR'},str(exc)[:250]);return {'CANCELLED'}

# Operations that edit Blender/RUNTIME but historically omitted native undo.
_EXTRA_UNDO={'dicom_wizard_pro.clear_drawings','dicom_wizard_pro.calculate_segmentation',
 'dicom_wizard_pro.remove_small_islands','dicom_wizard_pro.keep_largest_island',
 'dicom_wizard_pro.close_gaps','dicom_wizard_pro.fill_holes','dicom_wizard_pro.to_segmentation',
 'dicom_wizard_pro.back_to_viewer','dicom_wizard_pro.adjust_tissue_sensitivity',
 'dicom_wizard_pro.reset_tissue_range','dicom_wizard_pro.direct_dicom_to_surface',
 'dicom_wizard_pro.next','dicom_wizard_pro.new_file','dicom_wizard_pro.auto_threshold',
 'dicom_wizard_pro.reset_plane','dicom_wizard_pro.center_plane','dicom_wizard_pro.analyze_tissues',
 'dicom_wizard_pro.generate_surface','dicom_wizard_pro.back_to_segmentation',
 'dicom_wizard_pro.move_review_plane','dicom_wizard_pro.rotate_review_plane',
 'dsg.cbct_toggle_fdi','dsg.cbct_post_smooth_teeth'}

# Scene operations in these workflow modules always participate, including
# sleeves/drill Booleans, route navigation and resets previously lacking UNDO.
# Installation, bridge administration and file export are external side effects.
_WORKFLOW_MODULES={'core','dicom_module','cbct_dental_module','alignment_module','guide_module','frame_structural'}
_EXTERNAL_OPERATORS={'dsg_suite.install_engines_core','dsg.install_dicom_runtime',
 'dsg.copy_pipeline_diagnostic',
 'dsg.install_ai_runtime','dsg.ai_status_refresh','dicp.back_to_alignment',
 'dicom_wizard_pro.undo_last','dicom_wizard_pro.export_surface_stl','dsg.export_guide_stl'}

def _cancel_modal(operator,context):
    for name in ('cancel','_cancel','_finish','_cleanup','_finish_modal','_finish_cursor','_remove_timer'):
        method=getattr(operator,name,None)
        if callable(method):
            try:
                if self_module(operator)=='guide_module' and name=='_finish_modal' and operator.bl_idname=='dsg.start_irrigation':method(context.scene.dsg_props)
                else:method(context)
            except (ReferenceError,RuntimeError,TypeError,AttributeError):continue
            break
    timer=getattr(operator,'_timer',None)
    if timer is not None:
        try:context.window_manager.event_timer_remove(timer);operator._timer=None
        except (ReferenceError,RuntimeError):pass

def self_module(operator):return type(operator).__module__.rsplit('.',1)[-1]

def _track_modal(self,context,result,token):
    key=self.as_pointer()
    if 'RUNNING_MODAL' in result:
        _ACTIVE_MODALS[key]=(self,context,token)
        self._dsg_undo_epoch=_UNDO_EPOCH
    elif result in ({'FINISHED'},{'CANCELLED'}):_ACTIVE_MODALS.pop(key,None)

def _busy():
    from . import dicom_module,cbct_post_smoothing
    return bool(_ACTIVE_MODALS) or dicom_module.semantic_workflow_busy() or cbct_post_smoothing.busy()

def _wrap_execute(execute):
    @functools.wraps(execute)
    def wrapped(self,context):
        global _DEPTH
        outer=_DEPTH==0 and not _RESTORING
        if outer:begin(context,self.bl_label)
        token=context.scene.get(STATE_KEY)
        _DEPTH+=1
        try:result=execute(self,context)
        finally:_DEPTH-=1
        _track_modal(self,context,result,token)
        if outer and result=={'FINISHED'} and not _busy():commit(context,self.bl_label)
        return result
    return wrapped

def _wrap_invoke(invoke):
    @functools.wraps(invoke)
    def wrapped(self,context,event):
        global _DEPTH
        outer=_DEPTH==0 and not _RESTORING
        if outer:begin(context,self.bl_label)
        token=context.scene.get(STATE_KEY)
        _DEPTH+=1
        try:result=invoke(self,context,event)
        finally:_DEPTH-=1
        _track_modal(self,context,result,token)
        if outer and result=={'FINISHED'} and not _busy():commit(context,self.bl_label)
        return result
    return wrapped

def _wrap_modal(modal):
    @functools.wraps(modal)
    def wrapped(self,context,event):
        global _DEPTH
        if getattr(self,'_dsg_undo_epoch',_UNDO_EPOCH)!=_UNDO_EPOCH:return {'CANCELLED'}
        entry=_ACTIVE_MODALS.get(self.as_pointer())
        # Preserve existing local point undo. ICP and modals without local
        # point history revert their complete pre-operation state on Ctrl+Z.
        local_undo='Z' in modal.__code__.co_consts and self.bl_idname!='dicp.run_alignment'
        if event.type=='Z' and getattr(event,'ctrl',False) and event.value=='PRESS' and not local_undo and entry:
            _cancel_modal(self,context);_ACTIVE_MODALS.pop(self.as_pointer(),None)
            restore_checkpoint(context,entry[2]);return {'CANCELLED'}
        _DEPTH+=1
        try:result=modal(self,context,event)
        finally:_DEPTH-=1
        if result in ({'FINISHED'},{'CANCELLED'}):_ACTIVE_MODALS.pop(self.as_pointer(),None)
        if result=={'FINISHED'} and not _RESTORING and not _busy():commit(context,self.bl_label)
        return result
    return wrapped

def prepare_operators(modules):
    for module in modules:
        for cls in getattr(module,'CLASSES',()):
            if not isinstance(cls,type) or not issubclass(cls,bpy.types.Operator):continue
            options=set(getattr(cls,'bl_options',()))
            workflow=module.__name__.rsplit('.',1)[-1] in _WORKFLOW_MODULES
            if cls.bl_idname in _EXTERNAL_OPERATORS:continue
            if workflow or cls.bl_idname in _EXTRA_UNDO:options.add('UNDO');cls.bl_options=options
            if 'UNDO' not in options or cls.__dict__.get('_dsg_history_wrapped',False):continue
            execute=cls.__dict__.get('execute');invoke=cls.__dict__.get('invoke');modal=cls.__dict__.get('modal')
            if execute is not None:cls.execute=_wrap_execute(execute)
            if invoke is not None:cls.invoke=_wrap_invoke(invoke)
            if modal is not None:cls.modal=_wrap_modal(modal)
            cls._dsg_history_wrapped=True

def register():
    if not DSG_OT_WorkflowUndo.is_registered:bpy.utils.register_class(DSG_OT_WorkflowUndo)
    for name,handler in (('undo_pre',_before_undo),('undo_post',_after_undo),('redo_pre',_before_undo),('redo_post',_after_undo),('load_pre',_before_undo),('load_post',_after_load)):
        group=getattr(bpy.app.handlers,name)
        if handler not in group:group.insert(0,handler)
    keyconfig=bpy.context.window_manager.keyconfigs.addon
    if keyconfig:
        keymap=keyconfig.keymaps.new(name='Object Mode',space_type='EMPTY')
        item=keymap.keymap_items.new(DSG_OT_WorkflowUndo.bl_idname,'Z','PRESS',ctrl=True,head=True)
        _KEYMAPS.append((keymap,item))

def unregister():
    for keymap,item in _KEYMAPS:keymap.keymap_items.remove(item)
    _KEYMAPS.clear()
    for name,handler in (('undo_pre',_before_undo),('undo_post',_after_undo),('redo_pre',_before_undo),('redo_post',_after_undo),('load_pre',_before_undo),('load_post',_after_load)):
        group=getattr(bpy.app.handlers,name)
        if handler in group:group.remove(handler)
    if DSG_OT_WorkflowUndo.is_registered:bpy.utils.unregister_class(DSG_OT_WorkflowUndo)
    _ARRAY_CACHE.clear()
    _ACTIVE_MODALS.clear()
