import sys,numpy as np,bpy
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import guide_module as g
from dsg.blender import implant_optimizer as opt,safety_volume as safety
try:
 assert g.deferred_post_register();safety.unregister()
 for o in list(bpy.context.scene.objects):bpy.data.objects.remove(o,do_unlink=True)
 scene=bpy.context.scene
 bpy.ops.mesh.primitive_cube_add(size=80);bpy.context.object.name='Dental_DICOM_Mandible'
 bpy.ops.mesh.primitive_cube_add(size=2,location=(100,0,0));bpy.context.object.name='Dental_DICOM_MandibularCanal'
 obj=bpy.data.objects.new(g.IMPLANT_PREFIX+'Advisory',g.make_embedded_implant_mesh('Reference',4.,10.));scene.collection.objects.link(obj)
 obj['DSG_target_fdi']=36;scene.dsg_props.implant_obj=obj
 bpy.context.view_layer.objects.active=obj;obj.select_set(True);scene.dsg_opt_reviewed=True;scene.dsg_opt_profile_confirmed=True
 original=obj.matrix_world.copy();mesh=obj.data;pose=np.asarray(original).copy();pose[2,3]-=.5
 row={'matrix':pose.tolist(),'parameters':[0,0,-.5,0,0],'evaluation':{'admissible':False,'score':0.,'violations':[{'code':'APICAL','label':'Anclaje insuficiente','actual':2.99,'limit':3.,'excess_mm':.01}]}}
 for conditional in (False,True,'BONE_REVIEW','SECTION_REVIEW'):
  bone_review=conditional in {'BONE_REVIEW','SECTION_REVIEW'}
  result={'status':conditional if bone_review else ('GRAFT_SCENARIO' if conditional else 'NO_FEASIBLE'),'best':None,'closest':row,'conditional':row if conditional is True else None}
  opt.STATE.update(scene=scene,target=obj.name,result=result,fingerprint=opt.fingerprint(bpy.context))
  opt._preview(bpy.context,result);preview=bpy.data.objects[opt.PREVIEW]
  assert preview['DSG_optimizer_advisory_only'] and preview.color[0]>.9
  shader=next(n for n in preview.data.materials[0].node_tree.nodes if n.type=='BSDF_PRINCIPLED')
  assert np.allclose(shader.inputs['Base Color'].default_value,preview.color),'Material preview shader stayed white'
  if bone_review:assert abs(preview.color[1]-.55)<1e-5,'Bone review was not amber'
  assert obj.matrix_world==original and obj.data==mesh and obj.hide_get()
  try:opt.start(bpy.context,'POSITION',purpose='APPLY');raise AssertionError('Rejected reference accepted')
  except ValueError:pass
  assert opt.STATE['process'] is None
  opt.discard();assert not obj.hide_get() and obj.matrix_world==original and obj.data==mesh
 opt.STATE.update(scene=scene,target=obj.name,result=result,request={'settings':opt.settings(scene),'family':scene.dsg_opt_family})
 opt._preview(bpy.context,result);scene.dsg_opt_library='STRAUMANN_SP'
 assert opt.watch_preview() is None and bpy.data.objects.get(opt.PREVIEW) is None and not obj.hide_get()
 print('ADVISORY_PREVIEW_PASS:red_and_amber,no_apply,original_untouched,discard_restore',flush=True)
finally:opt.unregister();dsg.unregister()
