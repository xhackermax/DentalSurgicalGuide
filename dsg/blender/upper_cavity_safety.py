"""Danger zones from the CBCT segmentation: maxillary sinuses and nasal cavity.

The zones are created automatically by the segmentation (labels 56-59) and
are active from the start; no separate identification or confirmation is
needed to plan.  Rules (see ``danger_zones``): the nasal cavity can never
be invaded; sinus entry up to 2 mm is limited to implants shorter than 10 mm.
"""
import hashlib,json
import bpy
import numpy as np
from . import nerve_safety
from ..cbct_upper_cavities import CLASSES

KINDS=tuple(CLASSES)
KIND='DSG_upper_cavity_kind'
REVIEW='DSG_upper_cavity_review_signature'
REPORT='DSG_upper_cavity_safety_report'
MISSING='DSG_UPPER_CAVITIES_MISSING'
UNREVIEWED='DSG_UPPER_CAVITIES_UNREVIEWED'
LABELS={'left_maxillary_sinus':'Seno maxilar izquierdo','right_maxillary_sinus':'Seno maxilar derecho',
        'nasal_cavity_left':'Cavidad nasal izquierda','nasal_cavity_right':'Cavidad nasal derecha'}
REGISTRATION={'active':False}


def objects(scene):
    return [obj for obj in scene.objects if obj.type=='MESH' and obj.get(KIND) in KINDS
            and not obj.get('DSG_checkpoint_source_name')
            and not obj.get('DSG_workflow_checkpoint_source_name')
            and not obj.get('DSG_obsolete_hidden')]


def signature(obj):
    mesh=obj.data
    points=np.empty(len(mesh.vertices)*3,dtype=np.float32);mesh.vertices.foreach_get('co',points)
    mesh.calc_loop_triangles()
    triangles=np.empty(len(mesh.loop_triangles)*3,dtype=np.int32);mesh.loop_triangles.foreach_get('vertices',triangles)
    value=hashlib.sha256(points.tobytes()+triangles.tobytes()+np.round(np.asarray(obj.matrix_world),5).tobytes())
    return value.hexdigest()


def reviewed(scene,verify_geometry=False):
    cavities=objects(scene)
    if set(obj.get(KIND) for obj in cavities)!=set(KINDS):return False
    for obj in cavities:
        if obj.modifiers or not obj.get(REVIEW):return False
        if verify_geometry and obj.get(REVIEW)!=signature(obj):
            obj[REVIEW]=''
            return False
    return True


def confirm(context,accept_partial=False):
    cavities=objects(context.scene)
    if set(obj.get(KIND) for obj in cavities)!=set(KINDS):raise RuntimeError('Faltan senos maxilares o cavidades nasales: no se pueden confirmar.')
    if not accept_partial and any(obj.get('DSG_upper_cavity_truncated') for obj in cavities):
        raise RuntimeError('El campo de visión recorta cavidades; revisa el suelo en el CBCT y confirma expresamente el campo parcial.')
    context.view_layer.update()
    from . import safety_volume
    safety_volume._GEOMETRY.clear();nerve_safety.clear()
    checks=[]
    for obj in cavities:
        if obj.modifiers:raise RuntimeError('Aplica los modificadores de la cavidad antes de confirmar.')
        nerve_safety._geometry(context,obj)
        checks.append((obj,signature(obj)))
    for obj,value in checks:
        obj[REVIEW]=value
        obj['DSG_upper_cavity_partial_review']=bool(accept_partial)
        obj.hide_set(True)
    context.scene['DSG_upper_cavities_confirmed']=True


def _orientation(verts,tris):
    """+1 when the zone's triangles wind outward (positive volume), else -1."""
    a,b,c=verts[tris[:,0]],verts[tris[:,1]],verts[tris[:,2]]
    return 1. if float(np.einsum('ij,ij->i',a,np.cross(b,c)).sum())>=0 else -1.


_SIGN={}


def _points(obj):
    mesh=obj.data
    points=np.empty(len(mesh.vertices)*3);mesh.vertices.foreach_get('co',points)
    matrix=np.asarray(obj.matrix_world)
    return points.reshape(-1,3)@matrix[:3,:3].T+matrix[:3,3]


def penetration(context,implant,zone,reach_mm):
    """(depth inside the zone, clearance outside it) in mm, implant surface vs zone surface.

    A point is inside when it lies behind the nearest zone triangle (sign of
    the offset along its outward normal); depth is its distance to the
    zone surface.  Only implant points within ``reach_mm`` of the zone's
    bounding box are measured, so far zones cost nothing.
    """
    from mathutils import Vector
    # A crossing between faces can exist even when no implant vertex is inside.
    # Use the closed full surfaces first; missing depth must never become SAFE.
    contact=nerve_safety.measure(context,implant,zone,0.)
    intersects=contact['status'] in {'CONTACT','ENVELOPE_CONTACT'}
    if not intersects and contact['status']!='SAFE':
        raise ValueError('No se pudo excluir el contacto con la superficie completa.')
    from .safety_volume import _local_geometry
    verts,tris,tree=_local_geometry(zone,context.evaluated_depsgraph_get())
    if not len(tris):raise ValueError(zone.name+': malla vacía.')
    key=(zone.name,zone.data.session_uid)
    sign=_SIGN.get(key)
    if sign is None:sign=_SIGN[key]=_orientation(verts,tris)
    inverse=np.asarray(zone.matrix_world.inverted_safe())
    scale=float(np.cbrt(abs(np.linalg.det(np.asarray(zone.matrix_world)[:3,:3])))) or 1.
    local=_points(implant)@inverse[:3,:3].T+inverse[:3,3]
    pad=reach_mm/scale
    near=np.all((local>=verts.min(axis=0)-pad)&(local<=verts.max(axis=0)+pad),axis=1)
    if not near.any():
        if intersects:raise ValueError('Contacto de superficies detectado; profundidad no cuantificable.')
        return 0.,None
    depth=0.;clearance=None
    for point in local[near]:
        hit,normal,_index,distance=tree.find_nearest(Vector(point))
        if hit is None:continue
        distance*=scale
        if sign*float((Vector(point)-hit).dot(normal))<0:depth=max(depth,distance)
        else:clearance=distance if clearance is None else min(clearance,distance)
    if intersects and depth<=.05:
        raise ValueError('Contacto de superficies detectado; profundidad no cuantificable.')
    return (depth,None) if intersects else (0.,clearance)


def _limits(scene):
    from ..danger_zones import SINUS_MAX_MM,NASAL_ALERT_MM
    sinus=SINUS_MAX_MM  # fixed user rule; retired scene slider no longer changes it
    nasal=float(getattr(scene,'dsg_nasal_alert_mm',NASAL_ALERT_MM))
    return sinus,nasal


def failures(context,implant):
    """Blocking zones only (nasal invasion, sinus > limit, unmeasurable).

    Alerts (sinus invasion within the limit, nasal proximity, missing
    zones) are stored in the report and shown without blocking.
    """
    from ..danger_zones import classify,BLOCK,ALERT
    if nerve_safety.required(context.scene,implant):
        implant[REPORT]='[]'
        return []
    zones=objects(context.scene)
    if not zones:
        implant[REPORT]=json.dumps([{'name':MISSING,'status':ALERT,'label':'Senos y cavidad nasal',
                                     'message':'sin delimitar en la segmentación: revisa el CBCT'}])
        return []
    sinus_max,nasal_alert=_limits(context.scene)
    from ..sinus_policy import permitted_invasion
    # Measure actual body height too: stale nominal metadata must never permit
    # sinus entry for a physically longer implant.
    try:
        physical_length=float(np.ptp(np.asarray([v.co.z for v in implant.data.vertices],float)))*float(implant.matrix_world.to_3x3().col[2].length)
        nominal_length=float(implant.get('DSG_implant_length',physical_length))
        sinus_max=min(permitted_invasion(physical_length,sinus_max),permitted_invasion(nominal_length,sinus_max))
    except (ValueError,TypeError) as exc:
        implant[REPORT]=json.dumps([{'name':UNREVIEWED,'status':BLOCK,'label':'Senos y cavidad nasal',
                                    'message':'Longitud no verificable: '+str(exc)}])
        return [UNREVIEWED]
    rows=[]
    for zone in zones:
        kind=zone[KIND]
        try:
            depth,clearance=penetration(context,implant,zone,max(sinus_max,nasal_alert)+3.)
            status,message=classify(kind,depth,clearance,sinus_max,nasal_alert)
            row={'penetration_mm':round(depth,2),'clearance_mm':None if clearance is None else round(clearance,2)}
        except (ValueError,RuntimeError) as exc:
            status,message,row=BLOCK,'no verificable · '+str(exc),{}
        if zone.get('DSG_upper_cavity_truncated') and status!='SAFE':message+=' · campo de visión parcial'
        rows.append({'name':zone.name,'kind':kind,'label':LABELS[kind],'status':status,'message':message,**row})
    implant[REPORT]=json.dumps(rows)
    return [row['name'] for row in rows if row['status']==BLOCK]


def report(implant):
    try:return json.loads(str(implant.get(REPORT,'[]')))
    except ValueError:return []


def alerts(implant):
    from ..danger_zones import ALERT
    return [row for row in report(implant) if row.get('status')==ALERT]


def description(implant,name):
    if name==MISSING:return 'Senos y cavidad nasal sin delimitar en la segmentación: revisa el CBCT.'
    if name==UNREVIEWED:return 'Senos y cavidad nasal pendientes de revisión.'
    for item in report(implant) if implant is not None else ():
        if item.get('name')==name:return f"{item.get('label',name)} · {item.get('message','')}"
    return name


def import_surfaces(context,prepared,root=None):
    from .. import dicom_module as dicom
    collection=dicom.get_collection()
    root=root if root is not None else dicom.get_root(collection)
    previous=objects(context.scene)
    made=[]
    try:
        for kind,item in (prepared or {}).items():
            if kind not in KINDS or not item.get('vertices_path') or not item.get('faces_path'):continue
            vertices=np.load(item['vertices_path'],allow_pickle=False);faces=np.load(item['faces_path'],allow_pickle=False)
            if not len(vertices) or not len(faces):continue
            name='Dental_DICOM_'+kind+'_CANDIDATE'
            obj=dicom._new_surface_from_arrays(context,object_name=name,vertices_xyz=vertices,faces=faces,root=root)
            obj[KIND]=kind;obj['DSG_upper_cavity_truncated']=bool(item.get('touches_fov_boundary'))
            obj['dental_suite_dsg_role']='DICOM_UPPER_CAVITY';obj['dental_suite_component']='DICOM'
            obj.display_type='WIRE';obj.show_in_front=True;obj.hide_render=True;obj.hide_set(True)
            made.append(obj)
    except Exception:
        for obj in made:bpy.data.objects.remove(obj,do_unlink=True)
        raise
    # Commit after all provided meshes exist. Missing classes remain explicitly blocked.
    for old in previous:bpy.data.objects.remove(old,do_unlink=True)
    for obj in made:obj.name='Dental_DICOM_'+obj[KIND]
    context.scene['DSG_upper_cavities_confirmed']=False
    # Segmented danger zones are shown right away (blue sinus, red nose).
    if made and 'dsg_show_danger_zones' in bpy.types.Scene.bl_rna.properties:
        if context.scene.dsg_show_danger_zones:_show_zones(context.scene,context)
        else:context.scene.dsg_show_danger_zones=True
    return made


class DSG_OT_PrepareUpperCavities(bpy.types.Operator):
    bl_idname='dsg.prepare_upper_cavities'
    bl_label='IDENTIFICAR SENOS Y CAVIDAD NASAL'
    def execute(self,context):
        from . import upper_cavity_job
        try:upper_cavity_job.start(context)
        except (OSError,RuntimeError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class DSG_OT_ReviewUpperCavities(bpy.types.Operator):
    bl_idname='dsg.review_upper_cavities'
    bl_label='REVISAR SENOS Y CAVIDAD NASAL'
    def execute(self,context):
        for obj in objects(context.scene):obj.hide_set(False);obj.show_in_front=True
        self.report({'INFO'},'Contrasta el suelo de los senos y la cavidad nasal con el CBCT antes de confirmar.')
        return {'FINISHED'}


class DSG_OT_ConfirmUpperCavities(bpy.types.Operator):
    bl_idname='dsg.confirm_upper_cavities'
    bl_label='CONFIRMAR CAVIDADES SUPERIORES'
    reviewed_cbct:bpy.props.BoolProperty(name='He revisado en el CBCT el suelo de los senos y la cavidad nasal',default=False)
    accept_partial:bpy.props.BoolProperty(name='He verificado el suelo relevante pese al campo de visión parcial',default=False)
    def invoke(self,context,event):return context.window_manager.invoke_props_dialog(self,width=520)
    def execute(self,context):
        if not self.reviewed_cbct:
            self.report({'ERROR'},'Revisa primero las cavidades en el CBCT.');return {'CANCELLED'}
        try:confirm(context,self.accept_partial)
        except (ValueError,RuntimeError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class DSG_OT_AssignUpperCavity(bpy.types.Operator):
    bl_idname='dsg.assign_upper_cavity'
    bl_label='ASIGNAR MALLA DE CAVIDAD'
    kind:bpy.props.EnumProperty(items=[(key,label,'') for key,label in LABELS.items()])
    def invoke(self,context,event):return context.window_manager.invoke_props_dialog(self,width=420)
    def execute(self,context):
        obj=context.active_object
        if obj is None or obj.type!='MESH':self.report({'ERROR'},'Selecciona una malla de cavidad delineada en el CBCT.');return {'CANCELLED'}
        from .. import guide_module as g
        if g.is_valid_implant_obj(obj) or obj==context.scene.dsg_props.model_obj:
            self.report({'ERROR'},'Selecciona la cavidad, no el implante ni el IOS.');return {'CANCELLED'}
        obj[KIND]=self.kind;obj[REVIEW]='';obj.hide_render=True
        context.scene['DSG_upper_cavities_confirmed']=False
        return {'FINISHED'}


CLASSES_UI=(DSG_OT_PrepareUpperCavities,DSG_OT_ReviewUpperCavities,DSG_OT_ConfirmUpperCavities,DSG_OT_AssignUpperCavity)


def changed(_scene,context):
    from . import safety_volume
    safety_volume.STATE['checked'].clear()
    safety_volume.update(context.scene,context.evaluated_depsgraph_get())


_STAGE={'last':None,'busy':False}


@bpy.app.handlers.persistent
def _stage_watch(scene,_depsgraph=None):
    """Hide the zones while aligning (3 points), restore them afterwards.
    Stage changes are written in many places, so they are watched here."""
    if _STAGE['busy']:return
    try:
        from .. import core
        stage=core.infer_stage(scene)
        key=(scene.as_pointer(),stage)
        if _STAGE['last']==key:return
        _STAGE['busy']=True
        try:
            _STAGE['last']=key
            core._sync_danger_zones_for_stage(scene,stage)
        finally:
            _STAGE['busy']=False
    except Exception:
        pass


def register():
    for name,label,default,low,high,tip in (
            ('dsg_sinus_max_invasion_mm','Invasión máx. del seno',2.,0.,2.,'Penetración permitida (con alerta) en el seno maxilar; por encima se bloquea'),
            ('dsg_nasal_alert_mm','Alerta cavidad nasal',1.,0.,5.,'Distancia a la cavidad nasal por debajo de la cual se avisa; invadirla siempre se bloquea')):
        if name not in bpy.types.Scene.bl_rna.properties:
            setattr(bpy.types.Scene,name,bpy.props.FloatProperty(name=label,default=default,min=low,max=high,precision=1,
                                                                 description=tip,update=changed))
    if 'dsg_show_danger_zones' not in bpy.types.Scene.bl_rna.properties:
        bpy.types.Scene.dsg_show_danger_zones=bpy.props.BoolProperty(name='Mostrar zonas de peligro',default=False,update=_show_zones)
    if not REGISTRATION['active']:
        for cls in CLASSES_UI:bpy.utils.register_class(cls)
        REGISTRATION['active']=True
    from . import upper_cavity_job
    if upper_cavity_job.on_load not in bpy.app.handlers.load_pre:bpy.app.handlers.load_pre.append(upper_cavity_job.on_load)
    if _stage_watch not in bpy.app.handlers.depsgraph_update_post:bpy.app.handlers.depsgraph_update_post.append(_stage_watch)


def unregister():
    from . import upper_cavity_job
    upper_cavity_job.stop()
    if upper_cavity_job.on_load in bpy.app.handlers.load_pre:bpy.app.handlers.load_pre.remove(upper_cavity_job.on_load)
    if _stage_watch in bpy.app.handlers.depsgraph_update_post:bpy.app.handlers.depsgraph_update_post.remove(_stage_watch)
    if REGISTRATION['active']:
        for cls in reversed(CLASSES_UI):bpy.utils.unregister_class(cls)
        REGISTRATION['active']=False
    for name in ('dsg_sinus_max_invasion_mm','dsg_nasal_alert_mm','dsg_show_danger_zones'):
        if name in bpy.types.Scene.bl_rna.properties:delattr(bpy.types.Scene,name)


_COLORS={'sinus':(0.15,0.45,1.0,0.35),'nasal':(1.0,0.15,0.1,0.35)}


def _material(kind):
    key='sinus' if 'sinus' in kind else 'nasal'
    name='DSG_DangerZone_'+key
    material=bpy.data.materials.get(name) or bpy.data.materials.new(name)
    color=_COLORS[key]
    material.diffuse_color=color
    # Material Preview / render read the node tree, not diffuse_color:
    # without this the zones show up opaque grey, hidden inside the bone.
    material.use_nodes=True
    for node in material.node_tree.nodes:
        if node.type=='BSDF_PRINCIPLED':
            node.inputs['Base Color'].default_value=(color[0],color[1],color[2],1.0)
            node.inputs['Alpha'].default_value=color[3]
    # DITHERED: the only mode where 'in front' draws over the opaque bone.
    for attr,value in (('surface_render_method','DITHERED'),('blend_method','HASHED'),('use_backface_culling',False)):
        try:setattr(material,attr,value)
        except (AttributeError,TypeError):pass
    return material


def _show_zones(scene,context):
    show=bool(scene.dsg_show_danger_zones)
    for zone in objects(scene):
        if show:
            style(zone)
        zone.hide_viewport=False
        zone.hide_set(not show)


def style(zone):
    material=_material(zone[KIND])
    if not zone.data.materials:zone.data.materials.append(material)
    else:zone.data.materials[0]=material
    zone.color=_COLORS['sinus' if 'sinus' in zone[KIND] else 'nasal']
    # In front: sinus and nose sit inside the maxilla, which would hide them.
    zone.display_type='SOLID';zone.show_in_front=True;zone.show_transparent=True


def draw_toggle(layout,context):
    """Compact visibility row for the segmented danger zones (any step)."""
    scene=context.scene
    zones=objects(scene)
    if not zones or 'dsg_show_danger_zones' not in bpy.types.Scene.bl_rna.properties:return
    layout.prop(scene,'dsg_show_danger_zones',text='Senos y cavidad nasal ('+str(len(zones))+')',
                icon='HIDE_OFF' if scene.dsg_show_danger_zones else 'HIDE_ON',toggle=True)


def draw(layout,context):
    """Danger zones of the upper arch: one line per zone, live while placing."""
    from .protected_neighbors import lower
    from ..danger_zones import BLOCK,ALERT
    scene=context.scene
    if lower(scene):return
    box=layout.box()
    head=box.row(align=True)
    head.label(text='ZONAS DE PELIGRO · segmentación',icon='ERROR')
    head.prop(scene,'dsg_show_danger_zones',text='',icon='HIDE_OFF' if scene.dsg_show_danger_zones else 'HIDE_ON')
    zones=objects(scene)
    if not zones:
        box.label(text='Sin senos ni cavidad nasal en la segmentación.',icon='INFO')
        from . import upper_cavity_job
        if upper_cavity_job.STATE['process'] is not None:box.label(text=upper_cavity_job.STATE['message'],icon='TIME')
        else:box.operator('dsg.prepare_upper_cavities',text='DELIMITAR SENOS Y CAVIDAD NASAL',icon='MOD_FLUIDSIM')
        return
    from .. import guide_module as g
    implant=scene.dsg_props.implant_obj
    implants=[implant] if g.is_valid_implant_obj(implant) else g.get_all_implant_objects(scene.dsg_props)
    rows={}
    for item in implants:
        for row in report(item):
            current=rows.get(row.get('name'))
            rank={BLOCK:2,ALERT:1}.get(row.get('status'),0)
            if current is None or rank>current[0]:rows[row.get('name')]=(rank,row)
    for zone in sorted(zones,key=lambda z:z.name):
        rank,row=rows.get(zone.name,(0,{'message':'libre'}))
        line=box.row();line.alert=rank==2
        icon='CANCEL' if rank==2 else ('ERROR' if rank==1 else 'CHECKMARK')
        line.label(text=f"{LABELS[zone[KIND]]} · {row.get('message','libre')}",icon=icon)
    limits=box.row(align=True)
    limits.label(text='Seno: <10 mm → hasta 2 mm; ≥10 mm → sin entrada')
    limits.prop(scene,'dsg_nasal_alert_mm',text='Aviso nasal · mm')
