"""0..10mm oclusal extension preview; cached root, no Boolean while dragging."""
import bpy
from types import SimpleNamespace

CACHE = {'busy':False}
INITIALIZED = 'DSG_extraction_extension_initialized'
NAME = 'DSG_Extension_Oclusal_Preview'


def update(self,context):
    if CACHE['busy']:
        return
    context.scene[INITIALIZED] = True
    from . import ios_tooth_edit,ios_socket_boolean
    obj=ios_tooth_edit.model(context)
    if obj:
        obj[ios_socket_boolean.REVISION]=0
        obj[ios_socket_boolean.PENDING]=True
    try:
        preview(context)
    except (ValueError,RuntimeError) as exc:
        context.scene['DSG_extension_status']='No verificable: '+str(exc)


def property_definition():
    return bpy.props.FloatProperty(name='Extensión oclusal',description='Longitud adicional del resto radicular; actualiza la vista previa sin aplicar la booleana',
                                   default=0.,min=0.,max=10.,precision=2,step=10,update=update)


def preview(context):
    from .. import core
    from . import ios_tooth_edit,socket_reach
    if CACHE['busy']:
        return
    CACHE['busy']=True
    try:
        obj=ios_tooth_edit.model(context)
        teeth=core._immediate_cbct_teeth(context,core._immediate_extraction_fdis(context.scene))
        if obj is None or len(teeth)!=1:
            raise ValueError('Selecciona un FDI de extracción para previsualizar su extensión.')
        tooth=teeth[0]
        core.ensure_extraction_smoothing(context,tooth)
        context.view_layer.update()
        baseline = bpy.data.meshes.get(str(obj.get('DSG_ios_extension_base_mesh',''))) if obj.get('DSG_ios_extension_base_generation',-1)==int(obj.get('DSG_ios_socket_count',0)) else None
        surface = SimpleNamespace(data=baseline if baseline is not None else obj.data,
                                  matrix_world=obj.matrix_world.copy())
        key=(obj.name,surface.data.as_pointer(),tooth.name,tooth.data.as_pointer(),
             core.tooth_smoothing_state(context,tooth),
             tuple(value for row in obj.matrix_world for value in row),
             tuple(value for row in tooth.matrix_world for value in row))
        if CACHE.get('key')!=key:
            base,_=core._prepare_alveolar_cutter(context,tooth)
            plan=socket_reach.requirement(base,tooth,surface)
            root=base.data.copy()
            matrix=base.matrix_world.copy()
            core._remove_cutter(base)
            old_root=CACHE.get('root')
            if old_root is not None:
                try:
                    if old_root.users==0:bpy.data.meshes.remove(old_root)
                except ReferenceError:
                    old_root=None
            CACHE.update(key=key,root=root,matrix=matrix,plan=plan,tooth=tooth)
        required=CACHE['plan'][0]
        if not context.scene.get(INITIALIZED):
            context.scene.dsg_props.extraction_extension_mm=min(10.,required)
            context.scene[INITIALIZED]=True
        chosen=float(context.scene.dsg_props.extraction_extension_mm)
        visual=bpy.data.objects.get(NAME)
        if visual is None:
            visual=bpy.data.objects.new(NAME,CACHE['root'].copy())
            context.scene.collection.objects.link(visual)
        else:
            old=visual.data
            visual.data=CACHE['root'].copy()
            if old.users==0:bpy.data.meshes.remove(old)
        visual.matrix_world=CACHE['matrix']
        socket_reach.extend(visual,tooth,obj,extension_mm=chosen,plan=CACHE['plan'])
        sufficient=chosen+.001>=required
        visual.color=(.12,.85,.3,1.) if sufficient else (1.,.15,.1,1.)
        visual.display_type='WIRE'
        visual.show_in_front=True
        visual.hide_render=True
        visual.hide_set(False)
        visual['DSG_preview_only']=True
        visual['DSG_extension_mm']=chosen
        visual['DSG_required_extension_mm']=required
        visual['DSG_extension_sufficient']=sufficient
        context.scene['DSG_extension_status']=f'{chosen:.2f} mm · necesaria {required:.2f} mm · '+('SUFICIENTE' if sufficient else 'INSUFICIENTE')
        from .. import core
        core.set_status_bar(context,context.scene['DSG_extension_status'])
    finally:
        CACHE['busy']=False


class DSG_OT_ExtensionPreview(bpy.types.Operator):
    bl_idname='dsg.extraction_extension_preview'
    bl_label='VER EXTENSIÓN OCLUSAL'

    def execute(self,context):
        try:preview(context)
        except (ValueError,RuntimeError) as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class DSG_OT_ToggleExtractionSmoothing(bpy.types.Operator):
    bl_idname='dsg.toggle_extraction_tooth_smoothing'
    bl_label='Suavizado del diente a extraer'
    bl_description='Suaviza (≤0,25 mm, conserva el volumen) el diente CBCT que hace la booleana; la vista previa, la booleana del IOS y el alvéolo usan esa forma'
    bl_options={'REGISTER','UNDO'}

    def execute(self,context):
        from .. import core
        scene=context.scene
        previous=core.extraction_smoothing_wanted(scene)
        teeth=core._immediate_cbct_teeth(context,core._immediate_extraction_fdis(scene))
        before=[(tooth,tooth.data,{m.name:(m.show_viewport,m.show_render) for m in tooth.modifiers}) for tooth in teeth]
        scene[core.EXTRACTION_SMOOTHING_KEY]=not previous
        from . import ios_tooth_edit,ios_socket_boolean
        obj=ios_tooth_edit.model(context)
        if obj:
            obj[ios_socket_boolean.PENDING]=True
        try:preview(context)
        except (ValueError,RuntimeError) as exc:
            scene[core.EXTRACTION_SMOOTHING_KEY]=previous
            for tooth,mesh,flags in before:
                tooth.data=mesh
                for modifier in tooth.modifiers:
                    modifier.show_viewport,modifier.show_render=flags.get(modifier.name,(False,False))
            visual=bpy.data.objects.get(NAME)
            if visual:visual.hide_set(True)
            CACHE.pop('key',None)
            scene['DSG_extension_status']='Suavizado no aplicado: '+str(exc)
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


def draw(layout,context):
    from .. import core
    box=layout.box()
    on=core.extraction_smoothing_wanted(context.scene)
    box.operator('dsg.toggle_extraction_tooth_smoothing',text='SUAVIZADO DEL DIENTE: '+('SÍ' if on else 'NO'),
                 icon='MOD_SMOOTH',depress=on)
    box.prop(context.scene.dsg_props,'extraction_extension_mm',text='Extensión coronal · mm',slider=True)
    status=str(context.scene.get('DSG_extension_status','Mueve la barra para comprobar el alcance.'))
    box.label(text=status,icon='CHECKMARK' if 'SUFICIENTE' in status and 'INSUFICIENTE' not in status else 'ERROR')
    from .. import core
    if context.scene.get('DSG_extension_status'):
        core.set_status_bar(context,status)


CLASSES=(DSG_OT_ExtensionPreview,DSG_OT_ToggleExtractionSmoothing)
