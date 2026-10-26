import sys,bpy,numpy as np
from pathlib import Path
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
from dsg.section_optimizer import exact_section_evaluation
from dsg.blender.implant_optimizer_geometry import Solid,Evaluator
from dsg.blender.safety_volume import _mesh_arrays
from dsg.implant_catalogues import nominal_body_mesh
def cube(size):
 bpy.ops.mesh.primitive_cube_add(size=size);o=bpy.context.object;v,f,_=_mesh_arrays(o.data);bpy.data.objects.remove(o,do_unlink=True);return v,f
v,f=cube(40);bone=Solid(v,f,'Bone')
asset=dict(id='TEST',diameter_mm=3.1,length_mm=12.,platform_local_mm=[0,0,6],dimension_only=True)
source=nominal_body_mesh(3.1,12)
evaluation={'admissible':False,'score':1.,'section_anchor_mm':3.75,'section_hard_ok':True,'section_fit_fraction':.97,
 'violations':[{'code':'WALL','excess_mm':.03},{'code':'UNVERIFIABLE','excess_mm':0.}]}
class Field:
 summary={'sampling_uncertainty_mm':.2165};request={'settings':{'cervical_free_mm':1.}}
 def assess_matrix(self,matrix,asset):return dict(evaluation,violations=list(evaluation['violations']))
 def classification_witnesses(self,matrix,asset):return np.empty((0,3))
field=Field();evaluator=Evaluator(source,bone,[],{},asset_loader=lambda a:source)
out=exact_section_evaluation(field,evaluator,np.eye(4),asset)
assert out['admissible'],'Full 3D containment was vetoed by 3% raster disagreement'
assert out['raster_disagreement_resolved_3d'] and not out['violations']
# A real interior hole must remain unknown even if all implant surface
# samples lie in bone. The 3D interior witnesses distinguish it from aliasing.
inner_v,inner_f=cube(1.)
hollow=Solid(np.vstack((v,inner_v)),np.vstack((f,inner_f+len(v))),'Unknown void')
field.classification_witnesses=lambda matrix,asset:np.array([[0.,0.,0.]])
evaluator=Evaluator(source,hollow,[],{},asset_loader=lambda a:source)
out=exact_section_evaluation(field,evaluator,np.eye(4),asset)
assert not out['admissible'] and any(v['code']=='UNVERIFIABLE' for v in out['violations']),'Real unknown interior became bone'
print('RASTER_EXACT_PROMOTION_PASS:false_2d_veto_resolved,interior_unknown_preserved')
