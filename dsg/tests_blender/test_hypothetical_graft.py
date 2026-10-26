"""Graft is an advisory scenario, never bone and never a valid proposal."""
import sys,numpy as np,bpy
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
from dsg.blender.implant_optimizer_geometry import Solid,Evaluator
from dsg.blender.safety_volume import _mesh_arrays
from dsg.implant_catalogues import nominal_body_mesh
def arrays(obj):
    v,f,_=_mesh_arrays(obj.data);return v+np.asarray(obj.location),f
def box(size,location,scale=(1,1,1)):
    bpy.ops.mesh.primitive_cube_add(size=size,location=location);o=bpy.context.object
    for v in o.data.vertices:v.co=np.asarray(v.co)*np.asarray(scale)
    return o
bone=box(20,(0,0,-5));cut=box(2,(0,6,4.5),(10,5,5.5))
bpy.context.view_layer.objects.active=bone
mod=bone.modifiers.new('BuccalDefect','BOOLEAN');mod.operation='DIFFERENCE';mod.solver='EXACT';mod.object=cut
bpy.ops.object.modifier_apply(modifier=mod.name)
native=Solid(*arrays(bone),'Native bone');socket=Solid(*arrays(box(2,(0,0,0))),'Original root')
source=nominal_body_mesh(2,6);pose=np.eye(4);pose[:3,3]=[0,.5,-2]
settings={'explain_rejections':True,'boundary_reserve_mm':.2,'min_coverage':.8,'cervical_free_mm':.2,'min_apical_mm':3.,'graft_gap_mm':0.}
ev=Evaluator(source,native,[],settings,sockets=[socket],source_platform_local=[0,0,3])
off=ev(pose);assert not off['admissible'] and not off['scenario_eligible'],off['violations']
settings['graft_gap_mm']=1.
scenario=ev(pose);assert not scenario['admissible'] and scenario['scenario_eligible'],scenario['violations']
assert scenario['planned_graft_samples']>0 and scenario['wall_gap_max_mm']<=1.
assert scenario['support_fraction']==off['support_fraction'],'Hypothetical graft became native bone'
settings['graft_gap_mm']=.1;assert not ev(pose)['scenario_eligible'],'Chosen gap limit ignored'
settings['graft_gap_mm']=1.;settings['min_apical_mm']=5.
blocked=ev(pose);assert not blocked['scenario_eligible'] and any(v['code']=='APICAL' for v in blocked['violations'])
settings['min_apical_mm']=3.
ev.obstacles=[(Solid(*arrays(box(2,(0,0,-4))),'New nerve'),2.,'Nerve',0.)]
blocked=ev(pose);assert not blocked['scenario_eligible'] and any(v['code']=='STRUCTURE' for v in blocked['violations'])
print('HYPOTHETICAL_GRAFT_PASS:gap_bound,native_unchanged,apical_and_nerve_not_relaxed,never_admissible',flush=True)
