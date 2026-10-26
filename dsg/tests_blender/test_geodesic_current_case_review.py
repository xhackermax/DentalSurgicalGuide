import sys,json,time
from pathlib import Path
import bpy
args=sys.argv[sys.argv.index('--')+1:];sys.path.insert(0,args[0])
import dsg;dsg.register()
from dsg.blender import generative_frame as gf
from dsg import guide_module as g,frame_structural as fs
folder=Path(args[2]);request=json.loads((folder/'request.json').read_text(encoding='utf-8'));raw=json.loads((folder/'result.json').read_text(encoding='utf-8'));candidate=raw.get('result',raw)
results={}
for action in ('discard','accept'):
 bpy.ops.wm.open_mainfile(filepath=args[1],load_ui=False);gf.freeze_for_undo()
 assert gf.case_fingerprint(bpy.context)==request['case_fingerprint']
 original={o.name:gf.case_geometry_fingerprint(o) for o in (fs._frame_obj(bpy.context),bpy.data.objects[g.CLOSED_MODEL_NAME],g.get_active_guide_obj(bpy.context.scene.dsg_props))}
 started=time.perf_counter();objects=gf.stage_candidate(bpy.context,request,candidate)
 assert len(objects)==len(candidate['render_pieces'])
 if request.get('reinforcement_envelope'):assert all(o.get('DSG_reinforcement_envelope_verified') for o in objects)
 assert all(o.get('DSG_organic_final_support_verified') and o.get('DSG_organic_final_keepouts_verified') and json.loads(o['DSG_organic_body_radius_json'])['valid'] for o in objects)
 if action=='discard':
  outcome=bpy.ops.dsg.discard_generative_frame('EXEC_DEFAULT');assert not gf.preview_objects()
 else:
  outcome=bpy.ops.dsg.accept_generative_frame('EXEC_DEFAULT');assert len(g.get_confirmed_reinforcement_curves())==len(candidate['render_pieces'])
 assert outcome=={'FINISHED'}
 assert all(gf.case_geometry_fingerprint(bpy.data.objects[name])==digest for name,digest in original.items())
 results[action]={'operator_finished':True,'originals_unchanged':True,'physical_piece_count':len(objects),'elapsed_s':time.perf_counter()-started}
 print('CURRENT_CASE_REVIEW_PASS',action,flush=True)
Path(args[3]).write_text(json.dumps(results,indent=2),encoding='utf-8')
