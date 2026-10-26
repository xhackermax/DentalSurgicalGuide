"""Danger zones from segmentation: nasal never invaded, sinus ≤ 2 mm with alert."""
import bpy,sys,json
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import guide_module as g
from dsg.blender import upper_cavity_safety as upper,safety_volume as safety
try:
    safety.unregister();upper.register()
    for obj in list(bpy.context.scene.objects):bpy.data.objects.remove(obj,do_unlink=True)
    bpy.ops.mesh.primitive_cube_add(size=2)
    implant=bpy.context.object;implant.name=g.IMPLANT_PREFIX+'UpperTest';implant['DSG_target_fdi']=15
    # No zones: alert, never a block.
    assert not upper.failures(bpy.context,implant)
    assert json.loads(implant[upper.REPORT])[0]['name']==upper.MISSING
    zones={}
    for index,kind in enumerate(upper.KINDS):
        bpy.ops.mesh.primitive_cube_add(size=8,location=(30+index*12,0,0))
        obj=bpy.context.object;obj.name='Upper_'+kind;obj[upper.KIND]=kind;obj.hide_set(True);zones[kind]=obj
    bpy.context.view_layer.update()
    # Zones from segmentation are active immediately: no review or confirmation.
    assert not upper.failures(bpy.context,implant) and not upper.alerts(implant)
    clone=zones['left_maxillary_sinus'].copy();clone.data=zones['left_maxillary_sinus'].data.copy()
    bpy.context.scene.collection.objects.link(clone);clone['DSG_checkpoint_source_name']=clone.name;clone.location=(0,0,0)
    assert clone not in upper.objects(bpy.context.scene),'Checkpoint clone became clinical anatomy'
    bpy.data.objects.remove(clone,do_unlink=True)
    sinus=zones['left_maxillary_sinus'];nasal=zones['nasal_cavity_left']
    # Implant = 2 mm cube (x in -1..1); zone = 8 mm cube whose -x face sits at 1-d.
    # Sinus invaded 1.5 mm: allowed with alert.
    sinus.location=(1-1.5+4,0,0);bpy.context.view_layer.update()
    assert not upper.failures(bpy.context,implant),'Sinus invasion ≤ 2 mm must not block'
    rows=upper.alerts(implant);assert rows and rows[0]['name']==sinus.name and 1.3<rows[0]['penetration_mm']<1.7
    # Sinus invaded 2.5 mm: blocked, and the confirmation gate refuses.
    sinus.location=(1-2.5+4,0,0);bpy.context.view_layer.update()
    assert sinus.name in upper.failures(bpy.context,implant),'Sinus invasion > 2 mm did not block'
    from dsg.blender import safety_alerts
    assert 'Seno maxilar' in safety_alerts.contact_label(sinus.name,implant.name)
    class Reporter:
        messages=[]
        def report(self,level,message):self.messages.append(message)
    reporter=Reporter()
    assert not safety.gate(bpy.context,reporter),'Sinus > 2 mm did not block confirmation/export'
    assert any('Seno maxilar' in message for message in reporter.messages)
    # Nasal cavity: 0.4 mm invasion blocks; 0.6 mm away alerts; far is free.
    sinus.location=(30,0,0);nasal.location=(0,0,1-.4+4);bpy.context.view_layer.update()
    assert nasal.name in upper.failures(bpy.context,implant),'Nasal invasion did not block'
    nasal.location=(0,0,1+.6+4);bpy.context.view_layer.update()
    assert not upper.failures(bpy.context,implant) and upper.alerts(implant)[0]['name']==nasal.name
    nasal.location=(0,0,12);bpy.context.view_layer.update()
    assert not upper.failures(bpy.context,implant) and not upper.alerts(implant)
    implant['DSG_target_fdi']=36
    assert not upper.failures(bpy.context,implant),'Upper zones blocked a lower implant'
    print('UPPER_CAVITY_SAFETY_PASS: segmentation zones active without review, sinus ≤2 mm alert / >2 mm block, nasal block/alert',flush=True)
finally:dsg.unregister()
