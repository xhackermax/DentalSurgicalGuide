"""Safety panel follows selected arch; lower canal is explicitly a danger zone."""
import sys,json
import bpy
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import guide_module as g,dicom_module as dicom
from dsg.blender import protected_neighbors as protected,nerve_safety as nerve,upper_cavity_safety as upper,safety_volume as safety
class Layout:
    def __init__(self):self.labels=[];self.props=[]
    def box(self):return self
    def row(self,**kw):return self
    def label(self,**kw):self.labels.append(kw.get('text',''))
    def prop(self,obj,name,**kw):self.props.append(name)
    def operator(self,*args,**kw):return type('Action',(),{})()
try:
    safety.unregister();nerve.register();upper.register()
    for obj in list(bpy.context.scene.objects):bpy.data.objects.remove(obj,do_unlink=True)
    scene=bpy.context.scene;scene['DSG_active_arch']='MAXILLA'
    implants=[]
    for fdi in (15,36):
        bpy.ops.mesh.primitive_cube_add(size=2)
        obj=bpy.context.object;obj.name=g.IMPLANT_PREFIX+str(fdi);obj['DSG_target_fdi']=fdi;implants.append(obj)
    lower=implants[1];scene.dsg_props.implant_obj=lower;bpy.context.view_layer.objects.active=lower
    assert protected.lower(scene)
    layout=Layout();nerve.draw(layout,bpy.context);upper.draw(layout,bpy.context)
    assert any('Nervio dentario inferior' in text for text in layout.labels),'Lower danger-zone identity is absent'
    assert 'dsg_nerve_margin_mm' in layout.props
    assert 'dsg_sinus_max_invasion_mm' not in layout.props
    assert any('Falta segmentación' in text for text in layout.labels)
    bpy.ops.mesh.primitive_cube_add(size=2,location=(3.8,0,0))
    canal=bpy.context.object;canal.name=dicom.NAME_DICOM_MANDIBULAR_CANAL;canal.hide_set(True)
    bpy.context.view_layer.objects.active=lower;bpy.context.view_layer.update()
    assert canal.name in nerve.failures(bpy.context,lower)
    layout=Layout();nerve.draw(layout,bpy.context)
    assert any('margen requerido' in text for text in layout.labels),'Live canal risk was not shown'
    # Upper implant remains upper even when the scene also contains a lower implant.
    selected=implants[0];bpy.context.view_layer.objects.active=selected;scene.dsg_props.implant_obj=selected
    assert not protected.lower(scene),'A different lower implant hijacked the selected upper panel'
    layout=Layout();nerve.draw(layout,bpy.context);upper.draw(layout,bpy.context)
    assert 'dsg_nerve_margin_mm' not in layout.props
    assert any('ZONAS DE PELIGRO' in text for text in layout.labels)
    # Selecting the emergence controller must resolve the same lower arch.
    controller=bpy.data.objects.new('DSG_EmergenceTube_ArchPanel',None);scene.collection.objects.link(controller)
    lower.parent=controller;bpy.context.view_layer.objects.active=controller
    assert protected.lower(scene),'Lower emergence control did not select lower safety'
    print('ARCH_SAFETY_PANEL_PASS: selected upper/lower/controller, explicit inferior nerve zone, missing-canal warning and live margin report',flush=True)
finally:dsg.unregister()
