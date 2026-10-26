"""Nonblocking anatomical warnings must reach popup, panel, and yellow halo."""
import sys,json
from types import SimpleNamespace
from unittest.mock import patch
import bpy
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import guide_module as g
from dsg.blender import safety_alerts as alerts,upper_cavity_safety as upper,safety_volume as safety
try:
    safety.unregister();upper.register();alerts.register()
    for obj in list(bpy.context.scene.objects):bpy.data.objects.remove(obj,do_unlink=True)
    bpy.ops.mesh.primitive_cube_add(size=2)
    implant=bpy.context.object;implant.name=g.IMPLANT_PREFIX+'UpperAlert';implant['DSG_target_fdi']=15
    halo=bpy.data.objects.new(g._implant_safety_halo_name(implant),None);bpy.context.scene.collection.objects.link(halo)
    bpy.ops.mesh.primitive_cube_add(size=8,location=(3.5,0,0))
    zone=bpy.context.object;zone.name='RightSinus';zone[upper.KIND]='right_maxillary_sinus';zone.hide_set(True)
    bpy.context.view_layer.update()
    blocked=upper.failures(bpy.context,implant)
    assert not blocked and upper.alerts(implant),'Fixture must be sinus invasion with a nonblocking alert'
    from dsg import core
    import time
    status=[]
    bpy.context.scene.dsg_props['current_step']=g.STEP_IMPLANT
    safety.STATE['pending']={implant.name:bpy.context.scene.name};safety.STATE['pending_since']=time.monotonic()-1
    with patch.object(core,'infer_stage',return_value=core.STAGE_GUIDE),patch.object(safety,'contacts',return_value=[]),patch.object(core,'set_status_bar',side_effect=lambda ctx,text:status.append(text)):
        safety._audit_timer()
    assert any('Alerta anatómica' in text for text in status),'Audit falsely reported no contacts during sinus invasion'
    assert not any('sin contactos' in text for text in status)
    alerts.clear()
    messages=[]
    context=SimpleNamespace(scene=bpy.context.scene,window=SimpleNamespace(modal_operators=[object()]))
    with patch.object(alerts,'_display_ready',return_value=True),patch.object(alerts,'_show_popup',side_effect=lambda ctx,name,contacts:messages.append((name,contacts))):
        alerts.observe(context,implant,blocked)
        assert zone.name in alerts.active(context.scene).get(implant.name,()),'Sinus ALERT was omitted from visible alerts'
        assert alerts._dispatch(context)==.1 and not messages,'Popup interrupted native rotation'
        context.window.modal_operators=[]
        assert alerts._dispatch(context) is None and len(messages)==1
        assert halo.color[0]>.9 and halo.color[1]>.6,'Nonblocking warning must have a yellow halo'
        assert not alerts.STATE['blocked'].get((context.scene.name,implant.name))
        alerts.observe(context,implant,blocked);alerts._dispatch(context)
        assert len(messages)==1,'Repeated same warning popup'
        # The same zone becoming blocking is a new event, even if its name is unchanged.
        alerts.observe(context,implant,[zone.name]);alerts._dispatch(context)
        assert len(messages)==2,'Warning escalation to blocking did not alert'
        assert halo.color[1]<.2,'Blocking contact must have a red halo'
        implant[upper.REPORT]='[]';alerts.observe(context,implant,[]);alerts._dispatch(context)
        assert not alerts.active(context.scene)
        assert halo.color[2]>.9 and halo.color[0]<.2
        upper.failures(bpy.context,implant);alerts.observe(context,implant,[]);alerts._dispatch(context)
        assert len(messages)==3,'Re-entering sinus warning did not alert'
        # Missing anatomy and nasal proximity are also visible warnings.
        for name,label in ((upper.MISSING,'Senos y cavidad nasal'),('Nasal','Cavidad nasal derecha')):
            alerts.clear();implant[upper.REPORT]=json.dumps([{'name':name,'status':'ALERT','label':label,'message':'revisar CBCT'}])
            alerts.observe(context,implant,[]);alerts._dispatch(context)
            assert name in alerts.active(context.scene)[implant.name]
    # Actual popup content must distinguish warning from a blocking contact.
    drawn=[]
    layout=SimpleNamespace(label=lambda **kw:drawn.append(kw['text']),separator=lambda:None)
    context.window_manager=SimpleNamespace(popup_menu=lambda draw,**kw:draw(SimpleNamespace(layout=layout),context))
    alerts._show_popup(context,implant.name,alerts.active(context.scene)[implant.name])
    assert 'La confirmación permanece bloqueada.' not in drawn
    assert any('Revisa esta posición' in text for text in drawn)
    print('UPPER_ALERT_VISIBILITY_PASS: real hidden sinus warning, popup/panel route, R/G deferral, warning escalation, yellow/red/blue halo, re-entry and missing anatomy',flush=True)
finally:dsg.unregister()
