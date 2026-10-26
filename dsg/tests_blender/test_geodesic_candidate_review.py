import sys,json
from pathlib import Path
import bpy
args=sys.argv[sys.argv.index('--')+1:];sys.path.insert(0,args[0])
import dsg;dsg.register()
from dsg.blender import generative_frame as gf
from dsg import guide_module as g,frame_structural as fs
results={}
for action in ('discard','accept'):
 bpy.ops.wm.open_mainfile(filepath=args[1],load_ui=False);gf.freeze_for_undo();gf.recover(bpy.context)
 assert len(gf.preview_objects())==5
 original={o.name:gf.case_geometry_fingerprint(o) for o in (fs._frame_obj(bpy.context),bpy.data.objects[g.CLOSED_MODEL_NAME],g.get_active_guide_obj(bpy.context.scene.dsg_props))}
 if action=='discard':
  outcome=bpy.ops.dsg.discard_generative_frame('EXEC_DEFAULT')
  assert not gf.preview_objects()
 else:
  outcome=bpy.ops.dsg.accept_generative_frame('EXEC_DEFAULT')
  confirmed=g.get_confirmed_reinforcement_curves()
  assert len(confirmed)==5,len(confirmed)
  assert all(o.get('DSG_reinforcement_confirmed') for o in confirmed)
  assert int(bpy.context.scene.dsg_props.reinforcement_count)==5
 assert outcome=={'FINISHED'},outcome
 assert all(gf.case_geometry_fingerprint(bpy.data.objects[name])==digest for name,digest in original.items())
 results[action]={'operator_finished':True,'clinical_original_geometry_preserved':True,'preview_count':len(gf.preview_objects())}
 print('CANDIDATE_REVIEW_ACTION_PASS',action,flush=True)
Path(args[2]).write_text(json.dumps(results,indent=2),encoding='utf-8')
