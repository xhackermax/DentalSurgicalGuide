"""Visible contact alerts without interrupting native implant transforms."""
import bpy

STATE={'current':{},'shown':{},'queue':{},'blocked':{},'shown_blocked':{}}
REGISTRATION={'active':False}


def contact_label(name,implant_name=None):
    from . import upper_cavity_safety
    if name in {upper_cavity_safety.MISSING,upper_cavity_safety.UNREVIEWED}:
        return upper_cavity_safety.description(None,name)
    from . import nerve_safety
    if name==nerve_safety.MISSING:return 'Falta segmentación del nervio dentario'
    obj=bpy.data.objects.get(name)
    fdi=int(obj.get('DSG_fdi_number',0)) if obj else 0
    implant=bpy.data.objects.get(implant_name) if implant_name else None
    if implant is not None:
        upper_detail=upper_cavity_safety.description(implant,name)
        if upper_detail!=name:return upper_detail
        detail=nerve_safety.description(implant,name)
        if detail!=name:return detail
    return f'Diente FDI {fdi}' if fdi else name


def active(scene):
    return {name:contacts for (scene_name,name),contacts in STATE['current'].items() if scene_name==scene.name}


def observe(context,implant,collisions):
    from .upper_cavity_safety import alerts
    key=(context.scene.name,implant.name)
    blocked=tuple(sorted(set(collisions)))
    warning_names={row['name'] for row in alerts(implant)}
    signature=tuple(sorted(set(blocked)|warning_names))
    if not signature:
        for field in STATE.values():field.pop(key,None)
    else:
        STATE['current'][key]=signature
        STATE['blocked'][key]=blocked
        if STATE['shown'].get(key)!=signature or STATE['shown_blocked'].get(key)!=blocked:
            STATE['queue'][key]=signature
        if not bpy.app.timers.is_registered(_timer):
            bpy.app.timers.register(_timer,first_interval=.1)
    from .. import guide_module as g
    halo=bpy.data.objects.get(g._implant_safety_halo_name(implant))
    if halo:
        # red = blocked, yellow = allowed with alert (e.g. sinus ≤ 2 mm), blue = free
        halo.color=(1.,.08,.03,1.) if blocked else ((1.,.72,.05,1.) if warning_names else (.10,.55,1.,1.))
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type=='VIEW_3D':area.tag_redraw()


def _display_ready(context):
    return not bpy.app.background and context.window is not None


def _show_popup(context,name,contacts):
    lines=tuple(contact_label(item,name) for item in contacts)
    blocked=bool(STATE['blocked'].get((context.scene.name,name)))
    def draw(self,_context):
        self.layout.label(text=name+(' · contacto bloqueante' if blocked else ' · aviso anatómico'),icon='ERROR')
        for label in lines:self.layout.label(text=label,icon='ERROR')
        self.layout.separator()
        self.layout.label(text='Ajusta la posición o la rotación del implante.')
        self.layout.label(text='La confirmación permanece bloqueada.' if blocked else 'Revisa esta posición y la anatomía en el CBCT.')
    context.window_manager.popup_menu(draw,title='ALERTA DE SEGURIDAD',icon='ERROR')


def _dispatch(context):
    if not STATE['queue']:
        return None
    if not _display_ready(context):
        return None
    # A popup must not steal R/G, Circle Select, or another running modal tool.
    if context.window.modal_operators:
        return .1
    for key,signature in tuple(STATE['queue'].items()):
        if key[0]!=context.scene.name:
            continue
        STATE['queue'].pop(key,None)
        if STATE['current'].get(key)!=signature:
            continue
        _show_popup(context,key[1],signature)
        STATE['shown'][key]=signature
        STATE['shown_blocked'][key]=STATE['blocked'].get(key,())
        # Open only one popup at a time when several implants have contact.
        return .1 if STATE['queue'] else None
    return None


def _timer():
    return _dispatch(bpy.context)


class DSG_OT_ShowSafetyContacts(bpy.types.Operator):
    bl_idname='dsg.show_safety_contacts'
    bl_label='ALERTA DE SEGURIDAD'
    implant_name:bpy.props.StringProperty()

    def execute(self,context):
        contacts=active(context.scene).get(self.implant_name,())
        if not contacts:
            self.report({'INFO'},'No hay contactos de seguridad detectados.')
            return {'CANCELLED'}
        _show_popup(context,self.implant_name,contacts)
        return {'FINISHED'}


def draw_warning(layout,context):
    for name,contacts in active(context.scene).items():
        box=layout.box();box.alert=True
        labels=', '.join(contact_label(item,name) for item in contacts)
        blocked=bool(STATE['blocked'].get((context.scene.name,name)))
        action=box.operator('dsg.show_safety_contacts',text=('BLOQUEO DE SEGURIDAD · ' if blocked else 'ALERTA ANATÓMICA · ')+labels,icon='ERROR')
        action.implant_name=name


def clear():
    if bpy.app.timers.is_registered(_timer):bpy.app.timers.unregister(_timer)
    for field in STATE.values():field.clear()


def register():
    if not REGISTRATION['active']:
        bpy.utils.register_class(DSG_OT_ShowSafetyContacts)
        REGISTRATION['active']=True


def unregister():
    clear()
    if REGISTRATION['active']:
        bpy.utils.unregister_class(DSG_OT_ShowSafetyContacts)
        REGISTRATION['active']=False
