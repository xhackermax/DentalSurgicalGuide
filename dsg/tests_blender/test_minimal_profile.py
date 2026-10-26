"""Saved permissive settings cannot silently bypass the minimal profile."""
import sys,tempfile
from pathlib import Path
import bpy
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import guide_module as g,cbct_dental_module as dental
from dsg.blender import implant_optimizer as opt,safety_volume as safety,upper_cavity_safety as upper

class Layout:
 def __init__(self):self.props=[];self.ops=[];self.labels=[]
 def box(self):return self
 def row(self,**kwargs):return self
 def prop(self,owner,key,**kwargs):self.props.append(key)
 def label(self,**kwargs):self.labels.append(kwargs.get('text',''))
 def operator(self,key,**kwargs):self.ops.append(key);return self
 def separator(self):pass

try:
 assert g.deferred_post_register();safety.unregister()
 scene=bpy.context.scene
 for obj in list(scene.objects):bpy.data.objects.remove(obj,do_unlink=True)
 def cube(name,location):
  bpy.ops.mesh.primitive_cube_add(size=2,location=location)
  obj=bpy.context.object;obj.name=name;return obj
 cube('Dental_DICOM_Maxilla',(0,0,0));cube('Dental_DICOM_Mandible',(0,0,0))
 tooth=cube('FixtureRoot',(30,0,0));tooth['DSG_fdi_number']=14
 canal=cube('Dental_DICOM_MandibularCanal',(30,0,0))
 zone=cube('FixtureSinus',(40,0,0));zone[upper.KIND]='left_maxillary_sinus'
 mesh=g.make_embedded_implant_mesh('ImplantReference',4.,10.)
 implant=bpy.data.objects.new(g.IMPLANT_PREFIX+'Minimal',mesh);scene.collection.objects.link(implant)
 implant['DSG_target_fdi']=15;scene.dsg_props.implant_obj=implant
 other=cube(g.IMPLANT_PREFIX+'Other',(50,0,0))
 dental.dentition_objects=lambda:[tooth]
 nasal=cube('FixtureNasal',(40,0,0));nasal[upper.KIND]='nasal_cavity_left'
 upper.objects=lambda unused:[zone,nasal]
 g.get_all_implant_objects=lambda unused:[implant,other]
 scene.dsg_opt_library='BTI_COREX';scene.dsg_opt_open=True
 scene.dsg_props.implant_tooth_clearance=.1
 for key,value in dict(dsg_opt_reserve_mm=0.,dsg_opt_coverage=0.,dsg_opt_apical_mm=1.,
  dsg_opt_graft_gap_mm=5.,dsg_opt_sinus_manual=True,dsg_opt_combine=False,
  dsg_opt_max_diameter_mm=3.,dsg_opt_max_length_mm=7.).items():setattr(scene,key,value)
 bpy.context.view_layer.objects.active=implant;implant.select_set(True)
 initial=implant.matrix_world.copy();original=implant.data
 bpy.context.view_layer.update()
 folder=Path(tempfile.mkdtemp(prefix='DSG_FIXED_PROFILE_TEST_'))
 for fdi in (15,36):
  implant['DSG_target_fdi']=fdi
  request=opt.snapshot(bpy.context,folder,'POSITION')
  assert request['settings']['sinus_invasion_mm']==2.
  assert request['settings']['graft_gap_mm']==0.
  assert request['settings']['boundary_reserve_mm']==1.6
  assert request['settings']['max_length_mm']==0.
  for obstacle in request['obstacles']:
   if obstacle['kind'].startswith('Seno maxilar'):assert obstacle['max_invasion_mm']==2.
   else:assert 'max_invasion_mm' not in obstacle
   minimum={'Raíz vecina':1.5,'Implante vecino':3.,'Nervio dentario inferior':2.}.get(obstacle['kind'],0.)
   assert obstacle['margin_mm']>=minimum,(obstacle['kind'],obstacle['margin_mm'])
 old_raw=g._raw;g._raw=lambda layout:layout
 try:
  panel=Layout();opt.draw(panel,bpy.context)
  assert set(panel.props)=={'dsg_opt_open','dsg_opt_library','dsg_opt_reviewed','dsg_opt_details'},panel.props
  assert panel.ops==['dsg.optimize_implant_size'],panel.ops
  scene.dsg_opt_details=True;panel=Layout();opt.draw(panel,bpy.context)
  assert set(panel.props)=={'dsg_opt_open','dsg_opt_library','dsg_opt_reviewed','dsg_opt_details'}
  assert any('Cavidad nasal: 0 mm · sin penetración' in label for label in panel.labels)
  assert any('hasta 2 mm de penetración' in label for label in panel.labels)
 finally:g._raw=old_raw
 assert implant.matrix_world==initial and implant.data==original
 print('MINIMAL_PROFILE_PASS:compact_panel,saved_values_ignored,nerve_roots_implants_cavities_protected,original_intact',flush=True)
finally:opt.unregister();dsg.unregister()

