import sys,bpy
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
from dsg.blender import upper_cavity_safety as upper
from dsg.implant_catalogues import nominal_body_mesh
from dsg.danger_zones import ALERT,BLOCK
bpy.ops.mesh.primitive_cube_add();zone=bpy.context.object;zone[upper.KIND]='right_maxillary_sinus'
original=upper.penetration;required=upper.nerve_safety.required
upper.penetration=lambda *args:(1.,None)
upper.nerve_safety.required=lambda *args:False
try:
 for length,status in [(8,ALERT),(10,BLOCK),(14,BLOCK)]:
  v,f=nominal_body_mesh(4,length);mesh=bpy.data.meshes.new('body');mesh.from_pydata(v.tolist(),[],f.tolist());implant=bpy.data.objects.new('implant',mesh);bpy.context.scene.collection.objects.link(implant)
  implant['DSG_implant_length']=8 # deliberately stale for lengths >=10
  blocked=upper.failures(bpy.context,implant)
  assert upper.report(implant)[0]['status']==status,upper.report(implant)
  assert bool(blocked)==(status==BLOCK)
  bpy.data.objects.remove(implant,do_unlink=True)
finally:
 upper.penetration=original;upper.nerve_safety.required=required
print('LIVE_LENGTH_RULE_PASS:short_alert,long_block,stale_metadata_cannot_bypass')
