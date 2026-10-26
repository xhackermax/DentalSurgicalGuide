"""Run with Blender --background --factory-startup --python this.py -- ROOT."""
import sys,json
from pathlib import Path
import bpy
from mathutils import Vector
root=Path(sys.argv[sys.argv.index('--')+1]);sys.path.insert(0,str(root))
import dsg
dsg.register()
from dsg import guide_module as g
from dsg.blender import generative_frame as engine

def cube(name,loc=(0,0,0)):
    bpy.ops.mesh.primitive_cube_add(size=2,location=loc);obj=bpy.context.object;obj.name=name;return obj

frame=cube('DSG_SourceFrame_Hidden');guide=cube('DSG_Guide');passive=cube('DSG_PassiveCombined',(0,0,-3));closed=cube(g.CLOSED_MODEL_NAME,(0,0,-10))
props=bpy.context.scene.dsg_props;props.current_step=g.STEP_REINFORCEMENT;props.model_obj=passive
props.frame_obj=frame;props.guide_obj=guide
g.register_dsg_object(frame,g.ROLE_FRAME,frame.name,{})
g.register_dsg_object(passive,g.ROLE_PASSIVE,passive.name,{})
frame['DSG_frame_source_points_json']=json.dumps([[-1,-1,0],[1,-1,0],[1,1,0],[-1,1,0],[-1,0,0]])
old=g.create_poly_curve_object(bpy.context,'DSG_Reinforcement_00',[Vector((0,0,0)),Vector((0,2,0))],bevel_radius=.2)
g.register_dsg_object(old,g.ROLE_REINFORCEMENT,old.name,{'DSG_reinforcement_confirmed':True,'DSG_reinforcement_fem_generated':True})
before=engine.case_fingerprint(bpy.context)
request={'case_fingerprint':before,'frame_name':frame.name,'guide_name':guide.name}
result={'status':'CANDIDATE','pieces':[{'route_id':'one','points_mm':[[0,0,0],[2,2,0]],'radius_mm':.3}],
        'report':{'routing_valid':True,'connectivity_valid':True,'swept_geometry_valid':True,'junction_valid':True,'mechanics_evaluated':False,'post_boolean_validated':False}}
unchecked_bridge=dict(result,report=dict(result['report'],lattice_layout='FREE_BRIDGES_BETWEEN_PRIMARY_REINFORCEMENTS',lattice_complete=True,bridge_model_verified=True))
try:engine.stage_candidate(bpy.context,request,unchecked_bridge)
except ValueError as exc:assert 'SURFACE_ROUTES_REQUIRED' in str(exc)
else:raise AssertionError('Unverified IOS bridge accepted')
incomplete=dict(result,report=dict(result['report'],lattice_layout='TRIANGLES',lattice_complete=False))
try:engine.stage_candidate(bpy.context,request,incomplete)
except ValueError as exc:assert 'INCOMPLETE_LATTICE' in str(exc)
else:raise AssertionError('Incomplete lattice accepted')
bad=dict(result,report=dict(result['report'],swept_geometry_valid=False))
try:engine.stage_candidate(bpy.context,request,bad)
except ValueError:pass
else:raise AssertionError('Unchecked geometry accepted')
# Review regressions: evaluated shape keys, exact preview membership and typed volumes.
passive.shape_key_add(name='Basis');key=passive.shape_key_add(name='Moved')
key.data[0].co.x+=5;passive.data.update()
key.value=0;bpy.context.view_layer.update()
first=engine.case_fingerprint(bpy.context);key.value=1;passive.update_tag(refresh={'OBJECT','DATA'});bpy.context.view_layer.update()
assert engine.case_fingerprint(bpy.context)!=first,'Evaluated surface changes must invalidate proposal'
key.value=0;bpy.context.view_layer.update();request['case_fingerprint']=engine.case_fingerprint(bpy.context);before=request['case_fingerprint']
assert not engine.functional_coverage({'DSG_irrigation_resolution':'APPLIED','DSG_irrigation_saved_path_count':2},
    [{'kind':'LATERAL_OPENING','owner':guide.name,'closed':True,'channel_indices':[0,1]}],guide.name)
assert not engine.functional_coverage({'DSG_irrigation_resolution':'APPLIED','DSG_irrigation_saved_path_count':2},
    [{'kind':'IRRIGATION_LUMEN','owner':guide.name,'closed':True,'channel_indices':[0]}],guide.name)
assert engine.functional_coverage({'DSG_irrigation_resolution':'APPLIED','DSG_irrigation_saved_path_count':2},
    [{'kind':'IRRIGATION_LUMEN','owner':guide.name,'closed':True,'channel_indices':[0,1]}],guide.name)
pair=dict(result,pieces=result['pieces']+[dict(result['pieces'][0],route_id='two')])
engine.stage_candidate(bpy.context,request,pair)
bpy.data.objects.remove(engine.preview_objects()[0],do_unlink=True)
try:engine.accept_candidate(bpy.context)
except ValueError as exc:assert 'STALE_PREVIEW' in str(exc)
else:raise AssertionError('Partial preview accepted')
assert old.get('DSG_reinforcement_confirmed')
engine.discard_candidate(bpy.context)
engine.stage_candidate(bpy.context,request,result)
assert bpy.data.objects.get(old.name)==old and engine.case_fingerprint(bpy.context)==before
assert len(engine.preview_objects())==1 and old.hide_get()
engine.discard_candidate(bpy.context)
assert not engine.preview_objects() and bpy.data.objects.get(old.name)==old and not old.hide_get()
engine.stage_candidate(bpy.context,request,result)
frame.location.x+=.1
try:engine.accept_candidate(bpy.context)
except ValueError as exc:assert 'STALE' in str(exc)
else:raise AssertionError('Stale candidate accepted')
frame.location.x-=.1;bpy.context.view_layer.update()
engine.discard_candidate(bpy.context);request['case_fingerprint']=engine.case_fingerprint(bpy.context)
engine.stage_candidate(bpy.context,request,result)
closed.location.z+=.1
try:engine.accept_candidate(bpy.context)
except ValueError as exc:assert 'STALE_INPUT' in str(exc)
else:raise AssertionError('Changed closed IOS accepted')
closed.location.z-=.1;bpy.context.view_layer.update()
register=g.register_dsg_object
def fail_register(*args,**kwargs):raise RuntimeError('injected commit failure')
g.register_dsg_object=fail_register
try:engine.accept_candidate(bpy.context)
except RuntimeError:pass
else:raise AssertionError('Failure injection did not run')
finally:g.register_dsg_object=register
assert bpy.data.objects.get('DSG_Reinforcement_00')==old and old.get('DSG_reinforcement_confirmed')
assert len(engine.preview_objects())==1
engine.accept_candidate(bpy.context)
assert len(g.get_confirmed_reinforcement_curves())==1
assert not engine.preview_objects()
assert engine.case_geometry_fingerprint(frame)==engine.STATE['accepted_frame_digest']
assert not guide.get('DSG_frame_fem_hard_safe',True)
assert not engine.STATE.get('process')
print('GENERATIVE_FRAME_REVIEW_PASS:preview,original,discard,stale,accept,frame_preserved')
