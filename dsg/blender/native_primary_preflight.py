"""Build and certify physical radial meshes before ranking a web layout.

Runs in the isolated Blender worker, against its immutable clinical snapshot.
The active scene is never loaded, cleared or edited by this process.
"""
import json
from pathlib import Path

def prepare_native_case(request):
    """Register before creating pure dataclasses: registration can reload them."""
    import bpy
    if not bpy.app.background:raise ValueError('PRIMARY_PREFLIGHT_REQUIRES_ISOLATED_WORKER')
    import dsg
    if not hasattr(bpy.types.Scene,'dsg_props'):dsg.register()
    if Path(bpy.data.filepath).resolve()!=Path(request['native_case_file']).resolve():
        bpy.ops.wm.open_mainfile(filepath=request['native_case_file'],load_ui=False,use_scripts=False)
    from . import generative_frame as gf
    from .reinforcement_envelope import verify_context_envelope
    if gf.case_fingerprint(bpy.context)!=request['case_fingerprint']:raise ValueError('PRIMARY_PREFLIGHT_STALE_CASE')
    verify_context_envelope(bpy.context,request)


def preflight_primary_pool(request,paths,owners,progress):
    import bpy
    if not bpy.app.background:raise ValueError('PRIMARY_PREFLIGHT_REQUIRES_ISOLATED_WORKER')
    from . import generative_frame as gf
    from .organic_reinforcement import build_network
    from .. import guide_module as g
    before={name:gf.case_geometry_fingerprint(bpy.data.objects[name]) for name in [request['frame_name'],request['surface_name'],request['guide_name']]}
    accepted=set();records=[]
    for index,path in enumerate(paths):
        progress(f'Comprobando malla de rama {index+1}/{len(paths)}…')
        piece={'route_id':path.route_id,'origin':path.start_id,'port':path.end_id,'sleeve_id':owners[path.route_id],
               'member_role':'PRIMARY','points_mm':path.points_mm.tolist(),'radius_mm':request['radius_mm'],'nodes':{}}
        created=[]
        try:
            created=build_network(bpy.context,[piece],request)
            obj=created[0]
            if not all(obj.get(k) for k in ['DSG_organic_final_support_verified','DSG_organic_final_keepouts_verified','DSG_reinforcement_envelope_verified','DSG_web_frame_rim_verified']):raise ValueError('PRIMARY_FINAL_MESH_UNVERIFIED')
            accepted.add(path.route_id)
            records.append({'route_id':path.route_id,'valid':True,'sleeve_receipt':json.loads(obj['DSG_sleeve_anchor_receipt_json']),
                            'frame_receipt':json.loads(obj['DSG_frame_anchor_receipt_json'])})
        except ValueError as exc:records.append({'route_id':path.route_id,'valid':False,'reason':str(exc)})
        finally:
            for obj in created:g.safe_remove_object_with_data(obj)
    for name,digest in before.items():
        if gf.case_geometry_fingerprint(bpy.data.objects[name])!=digest:raise ValueError('PRIMARY_PREFLIGHT_CHANGED_CLINICAL_INPUT')
    report={'native_primary_meshes_checked':len(paths),'native_primary_meshes_valid':len(accepted),
            'clinical_originals_preserved':True,'records':records}
    Path(request['job_dir'],'native_primary_preflight.json').write_text(json.dumps(report),encoding='utf-8')
    return accepted,report

def preflight_web_candidate(request,outcome):
    """A failed native skin rejects this layout and leaves the search running."""
    import bpy
    from . import generative_frame as gf
    if not bpy.app.background:raise ValueError('WEB_PREFLIGHT_REQUIRES_ISOLATED_WORKER')
    before=gf.case_fingerprint(bpy.context)
    if before!=request['case_fingerprint']:raise ValueError('WEB_PREFLIGHT_STALE_CASE')
    try:
        staged=gf.stage_candidate(bpy.context,request,outcome)
        report={'valid':True,'member_count':len(staged),'physical_junctions_verified':gf.STATE['result']['report'].get('web_final_junctions_verified',False),
                'frame_rim_verified':gf.STATE['result']['report'].get('web_frame_rim_final_verified',False),
                'surface_support_verified':all(o.get('DSG_organic_final_support_verified') for o in staged),
                'keepouts_verified':all(o.get('DSG_organic_final_keepouts_verified') for o in staged)}
    except ValueError as exc:report={'valid':False,'reason':str(exc)}
    finally:
        gf.discard_candidate(bpy.context)
    if gf.case_fingerprint(bpy.context)!=before:raise ValueError('WEB_PREFLIGHT_CHANGED_CLINICAL_INPUT')
    return report
